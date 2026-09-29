"""Local bridge between index.html and Flower's SuperLink.

A browser can't call SuperGrid directly: the Control API speaks protobuf over HTTPS and
needs the tokens that `flwr login` saved in ~/.flwr. This small server does what
`flwr chat` does for one message, using flwr's own CLI helpers, and streams the run's
events back to the page as NDJSON (one JSON object per line).

Run it with the Python that has flwr installed (hello-app/.venv), after `flwr login supergrid`:
    python bridge.py                      # then open http://127.0.0.1:8765

Routes:
    GET  /            index.html (re-read on every request, so edit and reload)
    GET  /api/info    {"app_dir", "app_id", "superlink", "federations": [...]}
    POST /api/run     {"prompt", "federation", "series_id"?}  ->  NDJSON stream:
                        {"kind": "run", "run_id", "series_id", "app_id"}
                        {"kind": "event", "type", "payload"}     (every event, incl. Grid tool calls)
                        {"kind": "done", "terminal_seen": bool}  or  {"kind": "error", "message"}
    POST /api/stop    {"run_id"}  ->  {"stopped": bool}

Uses flwr 1.39.0 internals (flwr.cli.chat.*), so it may need small changes after an upgrade.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import click
from flwr.cli.chat.chat_app import format_failure_event, parse_task_event, start_chat_run
from flwr.cli.chat.chat_local_agent import build_local_agent
from flwr.cli.constant import CHAT_FAILURE_EVENTS, CHAT_TERMINAL_EVENTS
from flwr.cli.flower_config import read_superlink_connection
from flwr.cli.utils import init_http_client_from_connection
from flwr.proto.control_pb2 import (  # pylint: disable=E0611
    ListFederationsRequest,
    StopRunRequest,
    StreamRunEventsRequest,
)

HERE = Path(__file__).resolve().parent
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class Bridge(BaseHTTPRequestHandler):
    """One instance per HTTP request; settings live on the server object."""

    server: "BridgeServer"

    # ------------------------------------------------------------------ routing
    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/info":
            if self._authorized():
                self._json(200, self._info())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        body = self._read_json()
        if self.path == "/api/run":
            self._run(body)
        elif self.path == "/api/stop":
            self._json(200, {"stopped": self._stop(int(body.get("run_id", 0)))})
        else:
            self._json(404, {"error": "not found"})

    # ------------------------------------------------------------------ Flower calls
    def _client(self):
        """A fresh Control API client per request (two requests can be in flight at once)."""
        return init_http_client_from_connection(read_superlink_connection(self.server.superlink))

    def _info(self) -> dict[str, Any]:
        client = self._client()
        try:
            federations = [f.name for f in client.ListFederations(ListFederationsRequest()).federations]
        except click.ClickException as exc:
            federations, error = [], exc.format_message()
        else:
            error = None
        finally:
            client.close()
        return {
            "app_dir": str(self.server.app_dir),
            "app_id": self._app_id(),
            "superlink": self.server.superlink,
            "federations": federations,
            "error": error,
        }

    def _app_id(self) -> str | None:
        try:
            return build_local_agent(self.server.app_dir).app_spec
        except click.ClickException:
            return None

    def _run(self, body: dict[str, Any]) -> None:
        """Start one run (= one chat message) and stream its events to the page."""
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        client = self._client()
        try:
            prompt = str(body.get("prompt", "")).strip()
            if not prompt:
                raise click.ClickException("Empty prompt.")
            # Same as /load <dir>: package the app folder into a FAB, rebuilt on every message.
            agent = build_local_agent(self.server.app_dir)
            run_id, series_id = start_chat_run(
                client,
                prompt,
                body.get("federation") or None,
                body.get("series_id"),
                fab_hash=agent.fab_hash,
                fab_content=agent.fab_content,
            )
            self._line({"kind": "run", "run_id": run_id, "series_id": series_id, "app_id": agent.app_spec})

            terminal_seen = False
            for res in client.StreamRunEvents(StreamRunEventsRequest(run_id=run_id)):
                event_type, payload = parse_task_event(res.task_event)
                self._line({"kind": "event", "type": event_type, "payload": payload})
                if event_type in CHAT_FAILURE_EVENTS:
                    raise click.ClickException(format_failure_event(payload))
                terminal_seen = terminal_seen or event_type in CHAT_TERMINAL_EVENTS
            self._line({"kind": "done", "terminal_seen": terminal_seen})
        except (BrokenPipeError, ConnectionResetError):
            pass  # the page went away; nothing left to write to
        except click.ClickException as exc:
            self._safe_line({"kind": "error", "message": exc.format_message()})
        except Exception as exc:  # pylint: disable=broad-except
            self._safe_line({"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            client.close()

    def _stop(self, run_id: int) -> bool:
        client = self._client()
        try:
            return bool(client.StopRun(request=StopRunRequest(run_id=run_id)).success)
        except click.ClickException:
            return False
        finally:
            client.close()

    # ------------------------------------------------------------------ HTTP helpers
    def _authorized(self) -> bool:
        token = self.server.token
        if token and self.headers.get("X-Bridge-Token") != token:
            self._json(401, {"error": "missing or wrong X-Bridge-Token"})
            return False
        return True

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _line(self, obj: Any) -> None:
        self.wfile.write(json.dumps(obj).encode() + b"\n")
        self.wfile.flush()

    def _safe_line(self, obj: Any) -> None:
        try:
            self._line(obj)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[bridge] {self.address_string()} {fmt % args}\n")


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr: tuple[str, int], app_dir: Path, superlink: str, token: str | None):
        super().__init__(addr, Bridge)
        self.app_dir, self.superlink, self.token = app_dir, superlink, token


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--app-dir", type=Path, default=HERE.parent / "hello-app",
                        help="AgentApp folder sent with every run (like /load <dir>)")
    parser.add_argument("--superlink", default=os.environ.get("FLWR_CHAT_SUPERLINK", "supergrid"),
                        help="connection name from ~/.flwr/config.toml")
    args = parser.parse_args()

    token = os.environ.get("BRIDGE_TOKEN") or None
    if args.host not in LOOPBACK and not token:
        # Anyone who can reach this port could start runs in your federations as you.
        sys.exit("Refusing to listen on a non-loopback host without BRIDGE_TOKEN set.")

    server = BridgeServer((args.host, args.port), args.app_dir.resolve(), args.superlink, token)
    print(f"Master UI bridge on http://{args.host}:{args.port}  app={args.app_dir.resolve()}  "
          f"superlink={args.superlink}  token={'on' if token else 'off'}")
    server.serve_forever()


if __name__ == "__main__":
    main()
