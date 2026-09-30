"""SuperLink side (the master): ask the store nodes for quotes, combine them, answer.

Flow: parse the C1 prompt -> get_nodes -> push the C2 task to every "store-*" node (or to
every node if none has that name) -> poll pull_messages, emitting robotshop.progress ->
pricing.combine -> emit robotshop.quote (C4) -> one model call writes the text (or
pricing.format_quote) -> say(text + a fenced robotshop-quote JSON block).
"""

from __future__ import annotations

import json
import time
from typing import Any

from flwr.agentapp import AgentSession

from robot_shop.common import emit, grid, say
from robot_shop.llm import write_answer
from robot_shop.pricing import combine, format_quote
from robot_shop.protocol import make_task, parse_request, reply_entry, select_targets, usage

PULL_POLL_S = 5.0  # per pull_messages call, so progress events flow while stores answer
PULL_BUDGET_S = 90.0  # total time the master waits for replies
SUPERLINK_NODE_ID = "1"
T0 = time.monotonic()


def log(step: str) -> None:
    """Timing line for `flwr log <run-id> supergrid --show` (the master's stdout)."""
    print(f"[robot-shop] {time.monotonic() - T0:6.1f}s {step}", flush=True)


def quote_block(quote: dict[str, Any]) -> str:
    """Fallback for UIs that never see the robotshop.quote event (parsed by web/src/quote.js)."""
    return "\n\n```robotshop-quote\n" + json.dumps(quote, separators=(",", ":")) + "\n```"


def run_master(agent: AgentSession) -> None:
    """Fan the quote task out to the store nodes, collect the replies, answer once."""
    global T0
    T0 = time.monotonic()
    log("master started")
    try:
        request_text, items = parse_request(agent.prompt)
    except ValueError as exc:
        say(agent, usage(str(exc)))
        return

    nodes = grid(agent, "get_nodes", sample_size=None)["nodes"]
    if not nodes:
        say(agent, "No SuperNodes are online in this federation, so no store can quote.")
        return
    targets, targeted = select_targets(nodes)
    log(f"get_nodes: {len(nodes)} online, {len(targets)} targeted (store names: {targeted})")

    task = make_task(items)
    outgoing = [
        {"dst_node_id": node["id"], "payload": task, "reply_to_message_id": None}
        for node in targets
    ]
    results = grid(agent, "push_messages", messages=outgoing)["results"]

    # push_messages results line up with `outgoing`; replies are matched by src_node_id.
    entries: list[dict[str, Any]] = []
    pending: list[str] = []
    for node, result in zip(targets, results):
        if result.get("message_id"):
            pending.append(result["message_id"])
        else:
            entries.append({"node_id": str(node["id"]), "error": "message not accepted"})
    expected = len(pending)  # accepted messages: the replies we can actually wait for
    replied = 0
    ok_stores: list[str] = []
    emit(agent, "robotshop.progress", replied=0, expected=expected, stores=[])
    log(f"push_messages: {expected} accepted")

    # A reply can be pulled only once, so keep what each call returns.
    deadline = time.monotonic() + PULL_BUDGET_S
    while pending and (remaining := deadline - time.monotonic()) > 0:
        try:
            out = grid(
                agent,
                "pull_messages",
                message_ids=pending,
                timeout=min(PULL_POLL_S, remaining),
            )
        except Exception as exc:  # still answer with what arrived so far
            entries.append({"node_id": SUPERLINK_NODE_ID, "error": f"pull_messages failed: {exc}"})
            break
        for message in out["messages"]:
            entry = reply_entry(message)
            entries.append(entry)
            replied += 1
            reply = entry.get("reply")
            if reply and reply.get("ok"):
                ok_stores.append(reply["store_id"])
        pending = list(out["pending_message_ids"])
        emit(agent, "robotshop.progress", replied=replied, expected=expected, stores=list(ok_stores))

    log(f"pull done: {replied} replied, {len(pending)} pending")
    quote = combine(
        request_text,
        items,
        entries,
        asked=len(outgoing),
        timed_out=len(pending),
        targeted=targeted,
    )
    emit(agent, "robotshop.quote", quote=quote)  # before the text, so the UI can draw the table

    text = write_answer(request_text, quote)
    log("model answer ok" if text else "model answer failed; using format_quote")
    text = text or format_quote(quote)
    say(agent, text + quote_block(quote))
