"""The message contracts between the web UI, the master and the store workers (C1-C3).

Both roles import from here, so a format change happens in one place. No flwr import:
the unit tests run this module with a plain python3.

C1 request (the run's prompt text, from the web UI via the bridge):
    {"request": "Build this robot for me",
     "items": [{"product_id": "pololu-3500", "qty": 1, "name": "Romi chassis", "store_id": "pololu"}]}
    "name" and "store_id" are optional; store_id falls back to the product_id prefix before "-".
C2 task (master -> every targeted node, the push_messages payload):
    {"task": "quote", "items": [{"product_id": "pololu-3500", "qty": 1}]}
C3 reply (node -> master, the push_reply_message payload, sent exactly once):
    {"ok": true, "store_id", "store_name", "quotes": [{"product_id", "name", "sku", "qty",
                                                       "unit_price", "currency", "url"}]}
    or {"ok": false, "code": "NO_CATALOG" | "BAD_TASK" | "CATALOG_ERROR", "message": "..."}
"""

from __future__ import annotations

import json
from typing import Any

TASK_QUOTE = "quote"
DEFAULT_REQUEST = "Build this robot for me"
ERROR_CODES = ("NO_CATALOG", "BAD_TASK", "CATALOG_ERROR")
MAX_QTY = 100_000  # keeps cents and float totals far from overflow
STORE_NODE_PREFIX = "store-"  # store SuperNodes are named "store-<store_id>"

EXAMPLE_REQUEST = {
    "request": DEFAULT_REQUEST,
    "items": [
        {"product_id": "pololu-3500", "qty": 1, "name": "Romi chassis", "store_id": "pololu"},
        {"product_id": "adafruit-3777", "qty": 2, "name": "TT gearmotor", "store_id": "adafruit"},
    ],
}


def usage(reason: str = "") -> str:
    """Reply for a prompt that isn't a C1 request (e.g. plain text typed in flwr chat)."""
    text = (
        "Robot Shop prices robot parts across the store SuperNodes. Send the prompt as JSON:\n\n"
        "```json\n" + json.dumps(EXAMPLE_REQUEST, indent=2) + "\n```\n\n"
        "`qty` is a positive integer; `name` and `store_id` are optional."
    )
    return f"{text}\n\n(Could not read this prompt: {reason})" if reason else text


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-finite number {name} is not allowed")


def loads_strict(text: str) -> Any:
    """json.loads that rejects NaN/Infinity (Flower's event encoder would choke on them)."""
    return json.loads(text, parse_constant=_reject_constant)


def store_of(product_id: str) -> str:
    """Fallback store id: the product_id prefix before the first "-" (pololu-3500 -> pololu)."""
    return product_id.split("-", 1)[0]


def _valid_qty(qty: Any) -> bool:
    return isinstance(qty, int) and not isinstance(qty, bool) and 0 < qty <= MAX_QTY


def check_items(raw: Any, *, keep_meta: bool) -> list[dict[str, Any]]:
    """Validate an items list and merge duplicate product_ids by summing qty.

    keep_meta=True (C1) keeps "name" and "store_id" (always set, with fallbacks);
    keep_meta=False (C2) keeps only "product_id" and "qty". Raises ValueError.
    """
    if not isinstance(raw, list) or not raw:
        raise ValueError("'items' must be a non-empty list")
    merged: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"items[{index}] must be an object")
        product_id = item.get("product_id")
        if not isinstance(product_id, str) or not product_id.strip():
            raise ValueError(f"items[{index}].product_id must be a non-empty string")
        product_id = product_id.strip()
        qty = item.get("qty")
        if not _valid_qty(qty):
            raise ValueError(f"items[{index}].qty must be an integer from 1 to {MAX_QTY}")
        if product_id in merged:
            merged[product_id]["qty"] += qty
            if not _valid_qty(merged[product_id]["qty"]):
                raise ValueError(f"total qty of {product_id} is over {MAX_QTY}")
            continue
        entry: dict[str, Any] = {"product_id": product_id, "qty": qty}
        if keep_meta:
            name = item.get("name")
            store_id = item.get("store_id")
            entry["name"] = name.strip() if isinstance(name, str) and name.strip() else product_id
            entry["store_id"] = (
                store_id.strip()
                if isinstance(store_id, str) and store_id.strip()
                else store_of(product_id)
            )
        merged[product_id] = entry
    return list(merged.values())


def parse_request(prompt: str) -> tuple[str, list[dict[str, Any]]]:
    """Master side: read the C1 prompt. Returns (request_text, items); raises ValueError."""
    try:
        data = loads_strict(prompt)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"not JSON ({exc})") from None
    if not isinstance(data, dict):
        raise ValueError("the JSON must be an object with 'items'")
    request = data.get("request")
    request_text = request.strip() if isinstance(request, str) and request.strip() else DEFAULT_REQUEST
    return request_text, check_items(data.get("items"), keep_meta=True)


def make_task(items: list[dict[str, Any]]) -> str:
    """Master side: the C2 payload sent to every targeted node (product_id + qty only)."""
    return json.dumps(
        {
            "task": TASK_QUOTE,
            "items": [{"product_id": i["product_id"], "qty": i["qty"]} for i in items],
        },
        allow_nan=False,
    )


def read_task(agent_prompt: str) -> dict[str, Any]:
    """Worker side: unwrap the Grid envelope and return the validated C2 task.

    On a SuperNode, agent.prompt is {"message_id", "src_node_id", "payload"}, and payload
    is the string make_task() produced. Returns {"task": "quote", "items": [...]};
    raises ValueError if it isn't a quote task.
    """
    envelope = loads_strict(agent_prompt)
    if not isinstance(envelope, dict) or not isinstance(envelope.get("payload"), str):
        raise ValueError(f"not a Grid envelope: {str(agent_prompt)[:200]}")
    task = loads_strict(envelope["payload"])
    if not isinstance(task, dict) or task.get("task") != TASK_QUOTE:
        raise ValueError(f"not a quote task: {envelope['payload'][:200]}")
    return {"task": TASK_QUOTE, "items": check_items(task.get("items"), keep_meta=False)}


def make_reply(store_id: str, store_name: str, quotes: list[dict[str, Any]]) -> str:
    """Worker side: the C3 success payload (quotes may be empty)."""
    return json.dumps(
        {"ok": True, "store_id": store_id, "store_name": store_name, "quotes": quotes},
        allow_nan=False,
    )


def make_error_reply(code: str, message: str) -> str:
    """Worker side: the C3 failure payload. code is one of ERROR_CODES."""
    return json.dumps({"ok": False, "code": code, "message": message}, allow_nan=False)


def read_reply(payload: Any) -> dict[str, Any]:
    """Master side: parse and shape-check a C3 payload (str, or an already-parsed dict).

    Returns a normalized dict; quote entries are checked later by pricing.combine.
    Raises ValueError if the payload isn't a C3 reply.
    """
    data = loads_strict(payload) if isinstance(payload, str) else payload
    if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
        raise ValueError(f"not a store reply: {str(payload)[:200]}")
    if not data["ok"]:
        code = data.get("code")
        message = data.get("message")
        return {
            "ok": False,
            "code": code if isinstance(code, str) and code else "UNKNOWN",
            "message": message if isinstance(message, str) else "",
        }
    store_id = data.get("store_id")
    if not isinstance(store_id, str) or not store_id.strip():
        raise ValueError("store reply has no store_id")
    store_name = data.get("store_name")
    quotes = data.get("quotes")
    if not isinstance(quotes, list):
        raise ValueError("store reply 'quotes' must be a list")
    return {
        "ok": True,
        "store_id": store_id.strip(),
        "store_name": store_name.strip()
        if isinstance(store_name, str) and store_name.strip()
        else store_id.strip(),
        "quotes": quotes,
    }


def select_targets(nodes: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
    """Pick the nodes to ask: those named "store-*", or every node if none is.

    nodes is get_nodes' list of {"id": str, "name": str | None, "location": ...}.
    Returns (targets, targeted), where targeted says whether store names were used.
    """
    stores = [n for n in nodes if (n.get("name") or "").startswith(STORE_NODE_PREFIX)]
    return (stores, True) if stores else (list(nodes), False)


def reply_entry(message: dict[str, Any]) -> dict[str, Any]:
    """Turn one pull_messages item into a pricing.combine entry.

    Returns {"node_id": str, "reply": <read_reply dict>} or {"node_id": str, "error": str}.
    """
    node_id = str(message.get("src_node_id"))
    if message.get("error") is not None:
        return {"node_id": node_id, "error": str(message["error"])}
    try:
        return {"node_id": node_id, "reply": read_reply(message.get("payload"))}
    except (TypeError, ValueError) as exc:
        return {"node_id": node_id, "error": f"bad reply: {exc}"}
