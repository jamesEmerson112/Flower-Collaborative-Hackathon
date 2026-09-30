"""catalog (the worker's pure logic): CSV lookup and the C3 reply it builds."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

APP_DIR = str(Path(__file__).resolve().parents[1])
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from robot_shop.catalog import (  # noqa: E402
    build_reply,
    load_catalog,
    quote_items,
    store_identity,
    summarize_reply,
)
from robot_shop.protocol import make_task  # noqa: E402

HEADER = "product_id,store_id,store_name,product_name,sku,product_url,price,currency,part_type,primary_role\n"
ROWS = (
    'pololu-3500,pololu,Pololu Robotics & Electronics,Romi Chassis Kit - Black,3500,'
    'https://www.pololu.com/product/3500,39.95,USD,chassis,structure\n'
    'pololu-3036,pololu,Pololu Robotics & Electronics,"5:1 Micro Metal Gearmotor, HPCB 12V",3036,'
    'https://www.pololu.com/product/3036,10.95,USD,dc_gearmotor,actuators\n'
    'pololu-0000,pololu,Pololu Robotics & Electronics,Broken price,0000,,nan,USD,misc,misc\n'
)


def task_prompt(items):
    return json.dumps({"message_id": "m-1", "src_node_id": "1", "payload": make_task(items)})


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "pololu.csv")
        with open(self.path, "w", encoding="utf-8", newline="") as handle:
            handle.write(HEADER + ROWS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_load_catalog(self):
        catalog = load_catalog(self.path)
        self.assertEqual(set(catalog), {"pololu-3500", "pololu-3036", "pololu-0000"})
        self.assertEqual(catalog["pololu-3036"]["product_name"], "5:1 Micro Metal Gearmotor, HPCB 12V")

    def test_quote_items(self):
        items = [{"product_id": "pololu-3036", "qty": 3},
                 {"product_id": "adafruit-3777", "qty": 2},
                 {"product_id": "pololu-0000", "qty": 1},
                 {"product_id": "pololu-3500", "qty": 1}]
        quotes = quote_items(items, load_catalog(self.path))
        self.assertEqual(quotes, [
            {"product_id": "pololu-3036", "name": "5:1 Micro Metal Gearmotor, HPCB 12V", "sku": "3036",
             "qty": 3, "unit_price": 10.95, "currency": "USD", "url": "https://www.pololu.com/product/3036"},
            {"product_id": "pololu-3500", "name": "Romi Chassis Kit - Black", "sku": "3500",
             "qty": 1, "unit_price": 39.95, "currency": "USD", "url": "https://www.pololu.com/product/3500"},
        ])

    def test_store_identity(self):
        catalog = load_catalog(self.path)
        self.assertEqual(store_identity(catalog), ("pololu", "Pololu Robotics & Electronics"))
        self.assertEqual(store_identity(catalog, "pololu-eu"), ("pololu-eu", "Pololu Robotics & Electronics"))
        self.assertEqual(store_identity({}, "empty"), ("empty", "empty"))
        with self.assertRaises(ValueError):
            store_identity({})

    def test_build_reply_ok(self):
        prompt = task_prompt([{"product_id": "pololu-3500", "qty": 1},
                              {"product_id": "niryo-ned2", "qty": 1}])
        reply = json.loads(build_reply(prompt, {"robotshop-catalog": self.path,
                                                "robotshop-store": "pololu"}))
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["store_id"], "pololu")
        self.assertEqual(reply["store_name"], "Pololu Robotics & Electronics")
        self.assertEqual([q["product_id"] for q in reply["quotes"]], ["pololu-3500"])
        self.assertEqual(summarize_reply(json.dumps(reply)), "pololu: quoted 1 part(s)")

    def test_build_reply_no_catalog(self):
        prompt = task_prompt([{"product_id": "pololu-3500", "qty": 1}])
        for config in ({}, {"catalog": self.path}, {"robotshop-catalog": ""}, {"robotshop-catalog": True}):
            with self.subTest(config=config):
                reply = json.loads(build_reply(prompt, config))
                self.assertEqual((reply["ok"], reply["code"]), (False, "NO_CATALOG"))

    def test_build_reply_catalog_error(self):
        prompt = task_prompt([{"product_id": "pololu-3500", "qty": 1}])
        missing = os.path.join(self.tmp.name, "missing.csv")
        reply = json.loads(build_reply(prompt, {"robotshop-catalog": missing}))
        self.assertEqual(reply["code"], "CATALOG_ERROR")
        self.assertNotIn(self.tmp.name, reply["message"])  # no local paths leak to the master

        no_price = os.path.join(self.tmp.name, "no_price.csv")
        with open(no_price, "w", encoding="utf-8") as handle:
            handle.write("product_id,name\npololu-3500,Romi\n")
        reply = json.loads(build_reply(prompt, {"robotshop-catalog": no_price}))
        self.assertEqual(reply["code"], "CATALOG_ERROR")
        self.assertIn("price", reply["message"])

    def test_build_reply_bad_task(self):
        for prompt in ("Build me a robot", json.dumps({"message_id": "m", "payload": "{}"})):
            with self.subTest(prompt=prompt):
                reply = json.loads(build_reply(prompt, {"robotshop-catalog": self.path}))
                self.assertEqual(reply["code"], "BAD_TASK")


if __name__ == "__main__":
    unittest.main()
