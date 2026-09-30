"""protocol: C1 parsing, C2 task envelope, C3 replies, node targeting."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1])
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from robot_shop.protocol import (  # noqa: E402
    make_error_reply,
    make_reply,
    make_task,
    parse_request,
    read_reply,
    read_task,
    reply_entry,
    select_targets,
    usage,
)


def envelope(payload: str) -> str:
    return json.dumps({"message_id": "m-1", "src_node_id": "1", "payload": payload})


class ParseRequestTest(unittest.TestCase):
    def test_good_request(self):
        prompt = json.dumps({
            "request": "Build this robot for me",
            "items": [
                {"product_id": "pololu-3500", "qty": 1, "name": "Romi chassis", "store_id": "pololu"},
                {"product_id": "adafruit-3777", "qty": 2},
                {"product_id": "pololu-3500", "qty": 2},
            ],
        })
        text, items = parse_request(prompt)
        self.assertEqual(text, "Build this robot for me")
        self.assertEqual(items, [
            {"product_id": "pololu-3500", "qty": 3, "name": "Romi chassis", "store_id": "pololu"},
            {"product_id": "adafruit-3777", "qty": 2, "name": "adafruit-3777", "store_id": "adafruit"},
        ])

    def test_missing_request_text_gets_default(self):
        text, _ = parse_request('{"items": [{"product_id": "a-1", "qty": 1}]}')
        self.assertEqual(text, "Build this robot for me")

    def test_bad_requests(self):
        bad = [
            "Build me a robot",  # plain chat text
            "",
            "[1, 2]",
            '{"request": "x"}',
            '{"items": []}',
            '{"items": ["pololu-3500"]}',
            '{"items": [{"product_id": "", "qty": 1}]}',
            '{"items": [{"product_id": 5, "qty": 1}]}',
            '{"items": [{"product_id": "a-1"}]}',
            '{"items": [{"product_id": "a-1", "qty": 0}]}',
            '{"items": [{"product_id": "a-1", "qty": -2}]}',
            '{"items": [{"product_id": "a-1", "qty": "2"}]}',
            '{"items": [{"product_id": "a-1", "qty": 1.5}]}',
            '{"items": [{"product_id": "a-1", "qty": true}]}',
            '{"items": [{"product_id": "a-1", "qty": NaN}]}',
            '{"items": [{"product_id": "a-1", "qty": 1000000}]}',
        ]
        for prompt in bad:
            with self.subTest(prompt=prompt):
                with self.assertRaises(ValueError):
                    parse_request(prompt)

    def test_usage_shows_the_format(self):
        text = usage("not JSON")
        self.assertIn('"product_id": "pololu-3500"', text)
        self.assertIn("not JSON", text)


class TaskTest(unittest.TestCase):
    def test_make_task_keeps_only_id_and_qty(self):
        items = [{"product_id": "pololu-3500", "qty": 1, "name": "Romi", "store_id": "pololu"}]
        self.assertEqual(json.loads(make_task(items)),
                         {"task": "quote", "items": [{"product_id": "pololu-3500", "qty": 1}]})

    def test_read_task_unwraps_envelope(self):
        task = make_task([{"product_id": "pololu-3500", "qty": 2}])
        self.assertEqual(read_task(envelope(task)),
                         {"task": "quote", "items": [{"product_id": "pololu-3500", "qty": 2}]})

    def test_read_task_rejects_bad_input(self):
        bad = [
            "not json",
            json.dumps({"payload": {"task": "quote"}}),  # payload must be a string
            json.dumps(["x"]),
            envelope("not json"),
            envelope(json.dumps({"task": "greet", "prompt": "hi"})),
            envelope(json.dumps({"task": "quote", "items": []})),
            envelope(json.dumps({"task": "quote", "items": [{"product_id": "a-1", "qty": 0}]})),
        ]
        for prompt in bad:
            with self.subTest(prompt=prompt):
                with self.assertRaises(ValueError):
                    read_task(prompt)


class ReplyTest(unittest.TestCase):
    def test_round_trip(self):
        quotes = [{"product_id": "pololu-3500", "name": "Romi", "sku": "3500", "qty": 1,
                   "unit_price": 39.95, "currency": "USD", "url": "u"}]
        reply = read_reply(make_reply("pololu", "Pololu Robotics & Electronics", quotes))
        self.assertEqual(reply, {"ok": True, "store_id": "pololu",
                                 "store_name": "Pololu Robotics & Electronics", "quotes": quotes})
        self.assertEqual(read_reply(make_error_reply("NO_CATALOG", "none")),
                         {"ok": False, "code": "NO_CATALOG", "message": "none"})

    def test_make_reply_refuses_nan(self):
        with self.assertRaises(ValueError):
            make_reply("a", "A", [{"product_id": "a-1", "unit_price": float("nan")}])

    def test_read_reply_rejects_bad_payloads(self):
        bad = ["Hello James", "PROFILE_ERROR: x", "{}", '{"ok": true, "quotes": []}',
               '{"ok": true, "store_id": "a", "quotes": {}}', '{"ok": true, "store_id": "a", "quotes": [NaN]}']
        for payload in bad:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    read_reply(payload)

    def test_reply_entry(self):
        good = {"message_id": "r1", "reply_to_message_id": "m1", "src_node_id": "123",
                "payload": make_error_reply("NO_CATALOG", "x"), "error": None}
        self.assertEqual(reply_entry(good)["reply"]["code"], "NO_CATALOG")
        self.assertEqual(reply_entry(good)["node_id"], "123")
        errored = dict(good, payload=None, error="boom")
        self.assertEqual(reply_entry(errored), {"node_id": "123", "error": "boom"})
        garbage = dict(good, payload="Hello James")
        self.assertTrue(reply_entry(garbage)["error"].startswith("bad reply:"))


class SelectTargetsTest(unittest.TestCase):
    def test_store_nodes_only(self):
        nodes = [{"id": "1", "name": "store-pololu", "location": None},
                 {"id": "2", "name": "motor-a", "location": None},
                 {"id": "3", "name": None, "location": None}]
        targets, targeted = select_targets(nodes)
        self.assertTrue(targeted)
        self.assertEqual([n["id"] for n in targets], ["1"])

    def test_broadcast_without_store_names(self):
        nodes = [{"id": "2", "name": "motor-a"}, {"id": "3", "name": None}]
        targets, targeted = select_targets(nodes)
        self.assertFalse(targeted)
        self.assertEqual([n["id"] for n in targets], ["2", "3"])


if __name__ == "__main__":
    unittest.main()
