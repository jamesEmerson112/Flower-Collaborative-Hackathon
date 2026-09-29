"""SuperNode side (the worker): answer the master's task from this node's local data.

Owner: whoever builds the SuperNode logic. The data comes from the node's operator
(--node-config), never from this code, so the same file answers differently on each node.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from flwr.agentapp import AgentSession
from flwr.app import Context

from hello_app.common import grid, say
from hello_app.protocol import TASK_GREET, read_task


def load_profile(context: Context) -> dict[str, Any]:
    """Read this node's local profile; the path comes from the operator's --node-config."""
    path = context.node_config.get("profile")
    if not isinstance(path, str) or not path:
        raise ValueError(
            "node-config key 'profile' is not set; start the SuperNode with "
            "--node-config 'profile=\"/abs/path/profile.json\"'"
        )
    return json.loads(Path(path).read_text(encoding="utf-8"))


def answer(task: dict[str, Any], context: Context) -> str:
    """Turn one task into reply text. Add new task types here."""
    if task["task"] != TASK_GREET:
        return f"UNKNOWN_TASK: {task['task']!r}"
    try:
        profile = load_profile(context)
        return f"{profile.get('greeting', 'Hello')} {profile['name']}"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f"PROFILE_ERROR: {exc}"


def run_worker(agent: AgentSession, context: Context) -> None:
    """Answer the master's task from local data, exactly once."""
    try:
        reply = answer(read_task(agent.prompt), context)
    except (ValueError, KeyError, TypeError) as exc:
        reply = f"BAD_TASK: {exc}"

    # Always reply, so the master learns why at once instead of waiting for the timeout.
    out = grid(agent, "push_reply_message", payload=reply)
    if out["error"] is not None:
        raise RuntimeError(out["error"])
    say(agent, reply)
