"""SuperLink side (the master): ask every online SuperNode, then collect the replies.

Owner: whoever builds the SuperLink logic. Talks to workers only through protocol.py.
"""

from __future__ import annotations

import time
from typing import Any

from flwr.agentapp import AgentSession

from hello_app.common import grid, say
from hello_app.protocol import make_task

PULL_TIMEOUT_S = 60.0  # per pull_messages call; the Grid allows 0-300
PULL_BUDGET_S = 120.0  # total time the master waits for replies


def run_master(agent: AgentSession) -> None:
    """Fan out one greeting task per online SuperNode, then collect the replies."""
    nodes = grid(agent, "get_nodes", sample_size=None)["nodes"]
    if not nodes:
        say(agent, "No SuperNodes are online in this federation.")
        return

    task = make_task(agent.prompt)
    outgoing = [
        {"dst_node_id": node["id"], "payload": task, "reply_to_message_id": None}
        for node in nodes
    ]
    results = grid(agent, "push_messages", messages=outgoing)["results"]
    pending = [r["message_id"] for r in results if r["message_id"]]
    rejected = [n["id"] for n, r in zip(nodes, results) if not r["message_id"]]

    # A reply can be pulled only once, so keep what each call returns.
    replies: list[dict[str, Any]] = []
    deadline = time.monotonic() + PULL_BUDGET_S
    while pending and (remaining := deadline - time.monotonic()) > 0:
        out = grid(
            agent,
            "pull_messages",
            message_ids=pending,
            timeout=min(PULL_TIMEOUT_S, remaining),
        )
        replies.extend(out["messages"])
        pending = out["pending_message_ids"]

    lines = [f"Asked {len(nodes)} SuperNode(s):"]
    for reply in replies:
        if reply["error"] is None:
            lines.append(f"- node {reply['src_node_id']}: {reply['payload']}")
        else:
            lines.append(f"- node {reply['src_node_id']}: ERROR {reply['error']}")
    lines += [f"- node {node_id}: message not accepted" for node_id in rejected]
    lines += [f"- no reply for message {message_id} (timed out)" for message_id in pending]
    say(agent, "\n".join(lines))
