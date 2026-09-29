"""Hello-nodes AgentApp: the master greets every SuperNode, and each node answers from its own local profile.

One FAB, two roles, chosen at run time:
- SuperLink (node_id 1): master. Lists online nodes, sends each one a task, collects the replies.
- SuperNode: worker. Reads its local profile (path set by the node's operator with --node-config)
  and replies "<greeting> <name>" exactly once.

There's no "James" in this code: the name comes from the node's own profile.json.
No model calls, so no API keys are needed.
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

SUPERLINK_NODE_ID = 1  # flwr.common.constant.SUPERLINK_NODE_ID
PULL_TIMEOUT_S = 60.0  # per pull_messages call; the Grid allows 0-300
PULL_BUDGET_S = 120.0  # total time the master waits for replies

app = AgentApp()


def grid(agent: AgentSession, name: str, **arguments: Any) -> dict[str, Any]:
    """Call one Grid tool from code (no model involved) and return its parsed output."""
    item = agent.grid.call(
        {
            "type": "function_call",
            "call_id": f"{name}-{uuid.uuid4().hex[:8]}",
            "name": name,
            "arguments": json.dumps(arguments),
        }
    )
    return json.loads(item["output"])


def say(agent: AgentSession, text: str) -> None:
    """Show text in flwr chat and end the response (the CLI needs a terminal event)."""
    agent.events.emit({"type": "response.output_text.delta", "delta": text})
    agent.events.emit({"type": "response.completed"})


def run_master(agent: AgentSession) -> None:
    """Fan out one greeting task per online SuperNode, then collect the replies."""
    nodes = grid(agent, "get_nodes", sample_size=None)["nodes"]
    if not nodes:
        say(agent, "No SuperNodes are online in this federation.")
        return

    task = json.dumps({"task": "greet", "prompt": agent.prompt})
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


def load_profile(context: Context) -> dict[str, Any]:
    """Read this node's local profile; the path comes from the operator's --node-config."""
    path = context.node_config.get("profile")
    if not isinstance(path, str) or not path:
        raise ValueError(
            "node-config key 'profile' is not set; start the SuperNode with "
            "--node-config 'profile=\"/abs/path/profile.json\"'"
        )
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run_worker(agent: AgentSession, context: Context) -> None:
    """Answer the master's task from local data, exactly once."""
    try:
        profile = load_profile(context)
        answer = f"{profile.get('greeting', 'Hello')} {profile['name']}"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        # Still reply, so the master learns why at once instead of waiting for the timeout.
        answer = f"PROFILE_ERROR: {exc}"

    out = grid(agent, "push_reply_message", payload=answer)
    if out["error"] is not None:
        raise RuntimeError(out["error"])
    say(agent, answer)


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Same code on every machine; the node id decides the role."""
    if context.node_id == SUPERLINK_NODE_ID:
        run_master(agent)
    else:
        run_worker(agent, context)
