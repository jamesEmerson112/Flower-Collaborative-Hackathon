"""pricing.combine / format_quote: the C4 quote built from store replies."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1])
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from robot_shop.pricing import combine, format_quote, money, to_cents  # noqa: E402

POLOLU_NODE = "13119347499498202955"  # > 2**53: node ids stay strings
ADAFRUIT_NODE = "6111386887060621717"
TEAM_NODE = "3342843433609131587"


def item(product_id, qty, name=None, store_id=None):
    out = {"product_id": product_id, "qty": qty}
    if name:
        out["name"] = name
    if store_id:
        out["store_id"] = store_id
    return out


def quote(product_id, unit_price, name="Part", qty=1, sku="", currency="USD"):
    return {
        "product_id": product_id,
        "name": name,
        "sku": sku,
        "qty": qty,
        "unit_price": unit_price,
        "currency": currency,
        "url": f"https://example.com/{product_id}",
    }


def ok(node_id, store_id, store_name, quotes):
    return {
        "node_id": node_id,
        "reply": {"ok": True, "store_id": store_id, "store_name": store_name, "quotes": quotes},
    }


def fail(node_id, code, message="why"):
    return {"node_id": node_id, "reply": {"ok": False, "code": code, "message": message}}


class CombineTest(unittest.TestCase):
    def test_multi_store_combine(self):
        items = [
            item("pololu-3500", 1, "Romi chassis", "pololu"),
            item("adafruit-3777", 2, "TT motor", "adafruit"),
            item("niryo-ned2", 1, "Niryo Ned2"),
        ]
        replies = [
            ok(ADAFRUIT_NODE, "adafruit", "Adafruit Industries",
               [quote("adafruit-3777", 2.95, "DC Gearbox Motor", 2, "3777")]),
            ok(POLOLU_NODE, "pololu", "Pololu Robotics & Electronics",
               [quote("pololu-3500", 39.95, "Romi Chassis Kit - Black", 1, "3500")]),
            fail(TEAM_NODE, "NO_CATALOG"),
        ]
        q = combine("Build this robot for me", items, replies, asked=3, timed_out=0, targeted=True)

        self.assertEqual(q["request"], "Build this robot for me")
        self.assertEqual([line["product_id"] for line in q["lines"]], ["pololu-3500", "adafruit-3777"])
        pololu, adafruit = q["lines"]
        self.assertEqual(pololu["subtotal"], 39.95)
        self.assertEqual(pololu["node_id"], POLOLU_NODE)
        self.assertEqual(pololu["store_name"], "Pololu Robotics & Electronics")
        self.assertEqual(adafruit["qty"], 2)
        self.assertEqual(adafruit["unit_price"], 2.95)
        self.assertEqual(adafruit["subtotal"], 5.90)
        self.assertEqual(set(pololu), {"product_id", "name", "sku", "qty", "unit_price", "currency",
                                       "subtotal", "url", "store_id", "store_name", "node_id"})

        self.assertEqual(q["totals"], {"USD": 45.85})
        stores = {s["store_id"]: s for s in q["stores"]}
        self.assertEqual(stores["pololu"]["subtotal"], 39.95)
        self.assertEqual(stores["adafruit"]["subtotal"], 5.90)
        self.assertEqual(stores["adafruit"]["items"], 1)
        self.assertEqual(stores["adafruit"]["node_id"], ADAFRUIT_NODE)
        self.assertEqual(stores["adafruit"]["currency"], "USD")

        self.assertEqual(q["unquoted"], [{
            "product_id": "niryo-ned2", "name": "Niryo Ned2", "qty": 1, "store_id": "niryo",
            "code": "no_store", "reason": "no store sells it",
        }])
        self.assertEqual(q["nodes"], {"asked": 3, "targeted": True, "stores_replied": 2,
                                      "no_catalog": 1, "errors": [], "timed_out": 0})
        json.dumps(q, allow_nan=False)  # strict JSON, like Flower's event encoder

    def test_cents_are_exact(self):
        q = combine("r", [item("a-1", 3), item("b-1", 3)],
                    [ok("7", "a", "A", [quote("a-1", 10.95)]),
                     ok("8", "b", "B", [quote("b-1", 0.1)])],
                    asked=2, timed_out=0)
        lines = {line["product_id"]: line for line in q["lines"]}
        self.assertEqual(lines["a-1"]["subtotal"], 32.85)
        self.assertEqual(lines["b-1"]["subtotal"], 0.3)
        self.assertEqual(q["totals"], {"USD": 33.15})
        self.assertEqual(to_cents(10.95), 1095)
        self.assertEqual(to_cents("39.95"), 3995)
        self.assertEqual(money(3285), 32.85)

    def test_unquoted_not_stocked_when_its_store_replied(self):
        q = combine("r", [item("pololu-9999", 1, "Mystery part")],
                    [ok(POLOLU_NODE, "pololu", "Pololu Robotics & Electronics", [])],
                    asked=1, timed_out=0)
        self.assertEqual(q["lines"], [])
        self.assertEqual(q["totals"], {})
        [entry] = q["unquoted"]
        self.assertEqual(entry["code"], "not_stocked")
        self.assertEqual(entry["reason"], "Pololu Robotics & Electronics doesn't stock it")
        self.assertEqual(entry["store_id"], "pololu")

    def test_unquoted_name_falls_back_to_product_id(self):
        q = combine("r", [item("pollen-reachy", 2)], [], asked=0, timed_out=0)
        self.assertEqual(q["unquoted"][0]["name"], "pollen-reachy")
        self.assertEqual(q["unquoted"][0]["code"], "no_store")

    def test_no_catalog_is_not_an_error(self):
        q = combine("r", [item("a-1", 1)],
                    [fail("1001", "NO_CATALOG"), fail("1002", "NO_CATALOG")],
                    asked=2, timed_out=0)
        self.assertEqual(q["nodes"]["no_catalog"], 2)
        self.assertEqual(q["nodes"]["errors"], [])
        self.assertEqual(q["nodes"]["stores_replied"], 0)

    def test_errors_rejected_and_timed_out(self):
        replies = [
            {"node_id": "2001", "error": "message not accepted"},
            {"node_id": "2002", "error": "node crashed"},
            fail("2003", "CATALOG_ERROR", "cannot read the catalogue"),
            fail("2004", "BAD_TASK", ""),
            ok("2005", "a", "A", [quote("a-1", 1.00)]),
        ]
        q = combine("r", [item("a-1", 1)], replies, asked=6, timed_out=1)
        self.assertEqual(q["nodes"]["errors"], [
            {"node_id": "2001", "message": "message not accepted"},
            {"node_id": "2002", "message": "node crashed"},
            {"node_id": "2003", "message": "CATALOG_ERROR: cannot read the catalogue"},
            {"node_id": "2004", "message": "BAD_TASK"},
        ])
        self.assertEqual(q["nodes"]["timed_out"], 1)
        self.assertEqual(q["nodes"]["asked"], 6)
        self.assertEqual(q["nodes"]["stores_replied"], 1)
        self.assertFalse(q["nodes"]["targeted"])

    def test_duplicate_product_first_reply_wins(self):
        replies = [
            ok("3001", "first", "First Store", [quote("x-1", 5.00, "From first")]),
            ok("3002", "second", "Second Store", [quote("x-1", 1.00, "From second"),
                                                  quote("y-1", 2.50)]),
        ]
        q = combine("r", [item("x-1", 2), item("y-1", 1)], replies, asked=2, timed_out=0)
        lines = {line["product_id"]: line for line in q["lines"]}
        self.assertEqual(lines["x-1"]["store_id"], "first")
        self.assertEqual(lines["x-1"]["subtotal"], 10.00)
        self.assertEqual(lines["y-1"]["store_id"], "second")
        self.assertEqual(q["totals"], {"USD": 12.50})
        self.assertEqual({s["store_id"]: s["subtotal"] for s in q["stores"]},
                         {"first": 10.00, "second": 2.50})

    def test_same_node_counted_once(self):
        replies = [ok("4001", "a", "A", [quote("a-1", 1.00)]),
                   ok("4001", "a", "A", [quote("a-1", 1.00)])]
        q = combine("r", [item("a-1", 1)], replies, asked=1, timed_out=0)
        self.assertEqual(q["nodes"]["stores_replied"], 1)

    def test_bad_prices_and_unrequested_quotes_are_skipped(self):
        replies = [ok("5001", "a", "A", [
            quote("a-1", float("nan")), quote("a-2", -1), quote("a-3", "abc"),
            quote("a-4", None), quote("zz-9", 1.00), "not a dict", quote("a-5", "2.50"),
        ])]
        items = [item("a-1", 1), item("a-2", 1), item("a-3", 1), item("a-4", 1), item("a-5", 2)]
        q = combine("r", items, replies, asked=1, timed_out=0)
        self.assertEqual([line["product_id"] for line in q["lines"]], ["a-5"])
        self.assertEqual(q["totals"], {"USD": 5.00})
        self.assertEqual(len(q["unquoted"]), 4)
        self.assertTrue(all(u["code"] == "not_stocked" for u in q["unquoted"]))
        json.dumps(q, allow_nan=False)

    def test_request_qty_is_authoritative(self):
        q = combine("r", [item("a-1", 3)], [ok("6001", "a", "A", [quote("a-1", 1.00, qty=99)])],
                    asked=1, timed_out=0)
        self.assertEqual(q["lines"][0]["qty"], 3)
        self.assertEqual(q["totals"], {"USD": 3.00})


class FormatQuoteTest(unittest.TestCase):
    def test_plain_text(self):
        replies = [
            ok(POLOLU_NODE, "pololu", "Pololu Robotics & Electronics",
               [quote("pololu-3500", 39.95, "Romi Chassis Kit - Black", sku="3500")]),
            {"node_id": "9", "error": "message not accepted"},
            fail(TEAM_NODE, "NO_CATALOG"),
        ]
        q = combine("Build this robot for me",
                    [item("pololu-3500", 1), item("niryo-ned2", 1, "Niryo Ned2")],
                    replies, asked=4, timed_out=1)
        text = format_quote(q)
        self.assertIn("Quote for: Build this robot for me", text)
        self.assertIn("Pololu Robotics & Electronics: subtotal 39.95 USD", text)
        self.assertIn("1 x Romi Chassis Kit - Black (3500): 39.95 USD each, 39.95 USD", text)
        self.assertIn("1 x Niryo Ned2: no store sells it", text)
        self.assertIn("Total: 39.95 USD", text)
        self.assertIn("1 of 4 asked node(s) replied with a catalogue", text)
        self.assertIn("1 had no catalogue, 1 error(s), 1 timed out", text)
        self.assertIn("node 9: message not accepted", text)

    def test_nothing_quoted(self):
        q = combine("r", [item("niryo-ned2", 1)], [], asked=0, timed_out=0)
        self.assertIn("no store quoted any of these parts", format_quote(q))


if __name__ == "__main__":
    unittest.main()
