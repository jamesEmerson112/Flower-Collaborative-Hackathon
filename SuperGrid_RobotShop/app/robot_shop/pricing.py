"""Combine the store replies into one quote (C4), and render it as plain text.

Pure code, no flwr import. All money is summed in integer cents; every amount in the
quote is a finite float rounded to 2 dp (Flower's event encoder is strict JSON).

combine() takes `replies` in arrival order, one entry per node, in one of two shapes:
    {"node_id": "<decimal uint64 str>", "reply": <protocol.read_reply() dict>}
    {"node_id": "<decimal uint64 str>", "error": "<why there's no usable reply>"}
protocol.reply_entry() builds these from pull_messages items; the master adds
{"node_id", "error": "message not accepted"} for each push the SuperLink rejected.
Only the first entry per node_id counts.

The quote Q (C4, emitted as {"type": "robotshop.quote", "quote": Q}):
    {"request": str,
     "lines":    [{"product_id", "name", "sku", "qty", "unit_price", "currency", "subtotal",
                   "url", "store_id", "store_name", "node_id"}],          # request order
     "unquoted": [{"product_id", "name", "qty", "store_id", "code", "reason"}],
                 # code "no_store": no ok reply from a store with that store_id
                 #      ("no store sells it");
                 # code "not_stocked": that store replied ok but didn't quote it
                 #      ("<store name> doesn't stock it")
     "stores":   [{"store_id", "store_name", "node_id", "subtotal", "currency", "items"}],
                 # one per (node, currency) that won at least one line; items = its line count
     "totals":   {"USD": 45.85},
     "nodes":    {"asked", "targeted", "stores_replied", "no_catalog",
                  "errors": [{"node_id", "message"}], "timed_out"}}
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

REASON_NO_STORE = "no store sells it"
DEFAULT_CURRENCY = "USD"


def to_cents(value: Any) -> int | None:
    """Price -> integer cents, or None unless it's a finite number >= 0.

    Goes through Decimal(str(value)), so 10.95 is exactly 1095 cents.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        amount = Decimal(str(value).strip())
        if not amount.is_finite() or amount < 0:
            return None
        return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError, ArithmeticError):
        return None


def money(cents: int) -> float:
    """Integer cents -> float with 2 dp (3285 -> 32.85)."""
    return round(cents / 100, 2)


def _merge_items(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Request items keyed by product_id, in order, duplicates summed (defensive)."""
    merged: dict[str, dict[str, Any]] = {}
    for item in items:
        product_id = item["product_id"]
        if product_id in merged:
            merged[product_id]["qty"] += item["qty"]
            continue
        merged[product_id] = {
            "product_id": product_id,
            "qty": item["qty"],
            "name": item.get("name") or product_id,
            "store_id": item.get("store_id") or product_id.split("-", 1)[0],
        }
    return merged


def combine(
    request_text: str,
    items: list[dict[str, Any]],
    replies: list[dict[str, Any]],
    asked: int,
    timed_out: int,
    targeted: bool = False,
) -> dict[str, Any]:
    """Build the quote Q from the request items and the node replies (see module docstring).

    asked: messages pushed; timed_out: accepted messages with no reply by the deadline;
    targeted: whether the master picked nodes by their "store-" name.
    """
    wanted = _merge_items(items)
    won: dict[str, tuple[dict[str, Any], int]] = {}  # product_id -> (line, subtotal cents)
    ok_store_names: dict[str, str] = {}  # store_id -> store_name, from ok replies
    errors: list[dict[str, str]] = []
    stores_replied = 0
    no_catalog = 0
    seen_nodes: set[str] = set()

    for entry in replies:
        node_id = str(entry.get("node_id"))
        if node_id in seen_nodes:
            continue
        seen_nodes.add(node_id)
        reply = entry.get("reply")
        if not isinstance(reply, dict):
            errors.append({"node_id": node_id, "message": str(entry.get("error") or "no reply")})
            continue
        if not reply.get("ok"):
            if reply.get("code") == "NO_CATALOG":
                no_catalog += 1
            else:
                code = str(reply.get("code") or "UNKNOWN")
                detail = str(reply.get("message") or "")
                errors.append({"node_id": node_id, "message": f"{code}: {detail}" if detail else code})
            continue

        stores_replied += 1
        store_id = str(reply.get("store_id") or "unknown")
        store_name = str(reply.get("store_name") or store_id)
        ok_store_names.setdefault(store_id, store_name)
        for quote in reply.get("quotes") or []:
            if not isinstance(quote, dict):
                continue
            product_id = quote.get("product_id")
            if product_id not in wanted or product_id in won:
                continue  # not asked for, or an earlier reply already won it
            unit_cents = to_cents(quote.get("unit_price"))
            if unit_cents is None:
                continue
            qty = wanted[product_id]["qty"]
            subtotal_cents = unit_cents * qty
            line = {
                "product_id": product_id,
                "name": str(quote.get("name") or wanted[product_id]["name"]),
                "sku": str(quote.get("sku") or ""),
                "qty": qty,
                "unit_price": money(unit_cents),
                "currency": str(quote.get("currency") or DEFAULT_CURRENCY),
                "subtotal": money(subtotal_cents),
                "url": str(quote.get("url") or ""),
                "store_id": store_id,
                "store_name": store_name,
                "node_id": node_id,
            }
            won[product_id] = (line, subtotal_cents)

    lines: list[dict[str, Any]] = []
    unquoted: list[dict[str, Any]] = []
    store_cents: dict[tuple[str, str, str], dict[str, Any]] = {}
    total_cents: dict[str, int] = {}
    for product_id, item in wanted.items():
        if product_id not in won:
            store_id = item["store_id"]
            if store_id in ok_store_names:
                code, reason = "not_stocked", f"{ok_store_names[store_id]} doesn't stock it"
            else:
                code, reason = "no_store", REASON_NO_STORE
            unquoted.append(
                {
                    "product_id": product_id,
                    "name": item["name"],
                    "qty": item["qty"],
                    "store_id": store_id,
                    "code": code,
                    "reason": reason,
                }
            )
            continue
        line, cents = won[product_id]
        lines.append(line)
        key = (line["node_id"], line["store_id"], line["currency"])
        group = store_cents.setdefault(
            key,
            {
                "store_id": line["store_id"],
                "store_name": line["store_name"],
                "node_id": line["node_id"],
                "cents": 0,
                "currency": line["currency"],
                "items": 0,
            },
        )
        group["cents"] += cents
        group["items"] += 1
        total_cents[line["currency"]] = total_cents.get(line["currency"], 0) + cents

    stores = [
        {
            "store_id": g["store_id"],
            "store_name": g["store_name"],
            "node_id": g["node_id"],
            "subtotal": money(g["cents"]),
            "currency": g["currency"],
            "items": g["items"],
        }
        for g in store_cents.values()
    ]
    return {
        "request": request_text,
        "lines": lines,
        "unquoted": unquoted,
        "stores": stores,
        "totals": {currency: money(cents) for currency, cents in total_cents.items()},
        "nodes": {
            "asked": asked,
            "targeted": bool(targeted),
            "stores_replied": stores_replied,
            "no_catalog": no_catalog,
            "errors": errors,
            "timed_out": timed_out,
        },
    }


def _amount(value: float, currency: str) -> str:
    return f"{value:.2f} {currency}"


def format_quote(quote: dict[str, Any]) -> str:
    """Plain-text answer used when the model call fails (and for flwr chat)."""
    out: list[str] = [f"Quote for: {quote.get('request', '')}"]
    for store in quote["stores"]:
        out.append("")
        out.append(
            f"{store['store_name']}: subtotal {_amount(store['subtotal'], store['currency'])}"
        )
        for line in quote["lines"]:
            if (line["node_id"], line["store_id"], line["currency"]) != (
                store["node_id"],
                store["store_id"],
                store["currency"],
            ):
                continue
            out.append(
                f"  {line['qty']} x {line['name']} ({line['sku'] or line['product_id']}): "
                f"{_amount(line['unit_price'], line['currency'])} each, "
                f"{_amount(line['subtotal'], line['currency'])}"
            )
    if quote["unquoted"]:
        out.append("")
        out.append("Not quoted:")
        for item in quote["unquoted"]:
            out.append(f"  {item['qty']} x {item['name']}: {item['reason']}")
    out.append("")
    if quote["totals"]:
        out.append(
            "Total: "
            + " + ".join(_amount(value, currency) for currency, value in sorted(quote["totals"].items()))
        )
    else:
        out.append("Total: no store quoted any of these parts.")
    nodes = quote["nodes"]
    out.append(
        f"Stores: {nodes['stores_replied']} of {nodes['asked']} asked node(s) replied with a catalogue"
        f" ({nodes['no_catalog']} had no catalogue, {len(nodes['errors'])} error(s),"
        f" {nodes['timed_out']} timed out)."
    )
    for error in nodes["errors"]:
        out.append(f"  node {error['node_id']}: {error['message']}")
    return "\n".join(out)
