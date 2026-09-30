"""llm: Responses-API text extraction, SSE parsing, and write_answer against a fake streaming server."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

APP_DIR = str(Path(__file__).resolve().parents[1])
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from robot_shop.llm import _iter_sse, extract_text, write_answer  # noqa: E402

HAVE_HTTPX = importlib.util.find_spec("httpx") is not None


class ExtractTextTest(unittest.TestCase):
    def test_output_text_field(self):
        self.assertEqual(extract_text({"output_text": "  Hi there \n"}), "Hi there")

    def test_output_items(self):
        data = {
            "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": [
                    {"type": "output_text", "text": "Pololu supplies "},
                    {"type": "output_text", "text": "the chassis."},
                    {"type": "refusal", "refusal": "no"},
                ]},
            ]
        }
        self.assertEqual(extract_text(data), "Pololu supplies the chassis.")

    def test_nothing_usable(self):
        for data in (None, [], {}, {"output_text": "  "}, {"output": [{"content": [{"type": "x"}]}]}):
            with self.subTest(data=data):
                self.assertIsNone(extract_text(data))


class IterSseTest(unittest.TestCase):
    def test_frames_comments_done_and_event_name_fallback(self):
        lines = [
            ": keep-alive", "",
            "event: response.output_text.delta",
            'data: {"type":"response.output_text.delta","delta":"Hi"}', "",
            "event: response.completed",
            'data: {"response":', 'data: {"status":"completed"}}', "",  # multi-line data, no "type"
            "data: [DONE]", "",
        ]
        events = list(_iter_sse(lines))
        self.assertEqual([e["type"] for e in events], ["response.output_text.delta", "response.completed"])
        self.assertEqual(events[1]["response"], {"status": "completed"})


def _frame(event: dict) -> bytes:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()


class _FakeRuntime(BaseHTTPRequestHandler):
    """POST /responses: records the request and replays the server's scripted reply."""

    status = 200
    events: list = []
    requests: list = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        type(self).requests.append(
            {"path": self.path, "auth": self.headers.get("Authorization"), "body": json.loads(body)}
        )
        if self.status != 200:
            payload = json.dumps({"error": {"message": "Internal server error.", "code": "internal_error"}})
            self.send_response(self.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload.encode())
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in self.events:
            self.wfile.write(_frame(event))
            self.wfile.flush()

    def log_message(self, *args):  # keep test output quiet
        pass


class WriteAnswerTest(unittest.TestCase):
    def test_missing_runtime_env_returns_none(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(write_answer("r", {"lines": []}))


@unittest.skipUnless(HAVE_HTTPX, "httpx not installed (use SuperNode_James/hello-app/.venv/bin/python)")
class WriteAnswerStreamTest(unittest.TestCase):
    def setUp(self):
        _FakeRuntime.status, _FakeRuntime.events, _FakeRuntime.requests = 200, [], []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeRuntime)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        env = {
            "FLWR_RUNTIME_BASE_URL": f"http://127.0.0.1:{self.server.server_address[1]}/v1/runtime/",
            "FLWR_RUNTIME_API_KEY": "test-token",
        }
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _answer(self):
        with mock.patch("builtins.print"):  # silence the diagnostic prints
            return write_answer("a small rover", {"lines": [], "unquoted": []})

    def test_deltas_joined_until_completed(self):
        _FakeRuntime.events = [
            {"type": "response.created", "response": {"status": "in_progress"}},
            {"type": "response.output_text.delta", "delta": "Pololu supplies "},
            {"type": "response.output_text.delta", "delta": "the chassis "},
            {"type": "response.output_text.delta", "delta": "(USD 20.00)."},
            {"type": "response.completed", "response": {"status": "completed", "output": []}},
        ]
        self.assertEqual(self._answer(), "Pololu supplies the chassis (USD 20.00).")
        (req,) = _FakeRuntime.requests
        self.assertEqual(req["path"], "/v1/runtime/responses")
        self.assertEqual(req["auth"], "Bearer test-token")
        self.assertIs(req["body"]["stream"], True)
        self.assertEqual(req["body"]["model"], "openai/gpt-5.6-sol")

    def test_completed_without_deltas_uses_response_output(self):
        _FakeRuntime.events = [
            {"type": "response.completed", "response": {"output": [
                {"type": "message", "content": [{"type": "output_text", "text": "All from Adafruit."}]},
            ]}},
        ]
        self.assertEqual(self._answer(), "All from Adafruit.")

    def test_failure_events_return_none(self):
        for failure in (
            {"type": "response.failed", "response": {"status": "failed", "error": {"code": "x", "message": "boom"}}},
            {"type": "error", "code": "model_task_failed", "message": "Model task ended without a response."},
        ):
            with self.subTest(kind=failure["type"]):
                _FakeRuntime.events = [{"type": "response.output_text.delta", "delta": "partial"}, failure]
                self.assertIsNone(self._answer())

    def test_incomplete_keeps_partial_text(self):
        _FakeRuntime.events = [
            {"type": "response.output_text.delta", "delta": "Pololu supplies"},
            {"type": "response.incomplete", "response": {"incomplete_details": {"reason": "max_output_tokens"}}},
        ]
        self.assertEqual(self._answer(), "Pololu supplies")

    def test_stream_without_terminal_event_returns_none(self):
        _FakeRuntime.events = [{"type": "response.output_text.delta", "delta": "cut off"}]
        self.assertIsNone(self._answer())

    def test_http_500_returns_none(self):
        _FakeRuntime.status = 500
        self.assertIsNone(self._answer())


if __name__ == "__main__":
    unittest.main()
