"""SuperNode side (the worker): quote the master's task from this node's private catalogue.

The catalogue path comes from the node's operator (--node-config
'robotshop-catalog="/abs/path/<store>.csv" robotshop-store="<store>"'), never from this
code, so the same file answers differently on each store node. Nodes without a catalogue
(e.g. teammates' nodes) answer NO_CATALOG. No model calls here, so nodes need no key.
"""

from __future__ import annotations

from flwr.agentapp import AgentSession
from flwr.app import Context

from robot_shop.catalog import (  # noqa: F401 (load_catalog/quote_items re-exported)
    build_reply,
    load_catalog,
    quote_items,
    summarize_reply,
)
from robot_shop.common import grid, say


def run_worker(agent: AgentSession, context: Context) -> None:
    """Reply to the master exactly once (C3), then log a short summary."""
    reply = build_reply(agent.prompt, context.node_config)

    # Always reply, so the master learns why at once instead of waiting for the timeout.
    out = grid(agent, "push_reply_message", payload=reply)
    if out["error"] is not None:
        raise RuntimeError(out["error"])
    say(agent, summarize_reply(reply))
