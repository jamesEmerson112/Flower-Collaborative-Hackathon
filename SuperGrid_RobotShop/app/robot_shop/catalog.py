"""The worker's pure logic: read this node's private catalogue and quote a task from it.

No flwr import, so the unit tests run it with a plain python3; worker.py wraps it with
the Grid calls. The catalogue path comes from the node operator's --node-config, never
from the FAB or the run config, so the data stays on the node.

Catalogue CSV columns (node/catalogs/<store>.csv): product_id, store_id, store_name,
product_name, sku, product_url, price, currency, part_type, primary_role.
Only product_id and price are required.
"""

from __future__ import annotations

import csv
import json
from collections.abc import Mapping
from typing import Any

from robot_shop.pricing import money, to_cents
from robot_shop.protocol import make_error_reply, make_reply, read_task

CATALOG_KEY = "robotshop-catalog"  # --node-config key: absolute path to the store's CSV
STORE_KEY = "robotshop-store"  # --node-config key: store id (optional; else the CSV's)
REQUIRED_COLUMNS = ("product_id", "price")
CATALOG_COLUMNS = (
    "product_id",
    "store_id",
    "store_name",
    "product_name",
    "sku",
    "product_url",
    "price",
    "currency",
    "part_type",
    "primary_role",
)


def load_catalog(path: str) -> dict[str, dict[str, str]]:
    """Read the catalogue CSV into {product_id: row}; the first row per product_id wins.

    Raises OSError if the file can't be read, ValueError if a required column is missing.
    """
    with open(path, encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            raise ValueError(f"catalogue lacks column(s): {', '.join(missing)}")
        catalog: dict[str, dict[str, str]] = {}
        for row in reader:
            clean = {
                key: value.strip()
                for key, value in row.items()
                if isinstance(key, str) and isinstance(value, str)
            }
            product_id = clean.get("product_id", "")
            if product_id and product_id not in catalog:
                catalog[product_id] = clean
    return catalog


def quote_items(
    items: list[dict[str, Any]], catalog: Mapping[str, Mapping[str, str]]
) -> list[dict[str, Any]]:
    """Quote the task items this catalogue sells (C3 quote dicts, in task order).

    Items not in the catalogue, or whose price isn't a finite number >= 0, are skipped
    (not stocked).
    """
    quotes: list[dict[str, Any]] = []
    for item in items:
        product_id = item["product_id"]
        row = catalog.get(product_id)
        if row is None:
            continue
        cents = to_cents(row.get("price"))
        if cents is None:
            continue
        quotes.append(
            {
                "product_id": product_id,
                "name": row.get("product_name") or product_id,
                "sku": row.get("sku") or "",
                "qty": item["qty"],
                "unit_price": money(cents),
                "currency": row.get("currency") or "USD",
                "url": row.get("product_url") or "",
            }
        )
    return quotes


def store_identity(
    catalog: Mapping[str, Mapping[str, str]], configured_store: Any = None
) -> tuple[str, str]:
    """(store_id, store_name): the node-config store id, else the CSV's first row.

    Raises ValueError if neither says which store this is.
    """
    first = next(iter(catalog.values()), None) or {}
    store_id = (
        configured_store.strip()
        if isinstance(configured_store, str) and configured_store.strip()
        else first.get("store_id", "")
    )
    if not store_id:
        raise ValueError(f"no {STORE_KEY} in --node-config and no store_id in the catalogue")
    return store_id, first.get("store_name") or store_id


def _describe(exc: Exception) -> str:
    """Error text for the master, without the node's local file path."""
    if isinstance(exc, OSError):
        return f"cannot read the catalogue ({exc.strerror or type(exc).__name__})"
    return f"{type(exc).__name__}: {exc}"[:300]


def build_reply(agent_prompt: str, node_config: Mapping[str, Any]) -> str:
    """Turn the worker's agent.prompt into the C3 payload string. Never raises."""
    try:
        task = read_task(agent_prompt)
    except Exception as exc:  # any malformed task gets a reply, not a crash
        return make_error_reply("BAD_TASK", str(exc)[:300])

    path = node_config.get(CATALOG_KEY)
    if not isinstance(path, str) or not path.strip():
        return make_error_reply(
            "NO_CATALOG", f"this node has no '{CATALOG_KEY}' in its --node-config"
        )
    try:
        catalog = load_catalog(path.strip())
        store_id, store_name = store_identity(catalog, node_config.get(STORE_KEY))
        return make_reply(store_id, store_name, quote_items(task["items"], catalog))
    except Exception as exc:  # unreadable or malformed catalogue
        return make_error_reply("CATALOG_ERROR", _describe(exc))


def summarize_reply(payload: str) -> str:
    """Short text the worker shows in its own run log."""
    try:
        data = json.loads(payload)
    except ValueError:
        return payload[:200]
    if data.get("ok"):
        return f"{data['store_id']}: quoted {len(data['quotes'])} part(s)"
    return f"{data.get('code')}: {data.get('message')}"
