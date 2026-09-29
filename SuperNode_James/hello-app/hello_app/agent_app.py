"""Hello-nodes AgentApp: the master greets every SuperNode, and each node answers from its own local profile.

One FAB, two roles, chosen at run time. This file only picks the role:
- SuperLink (node_id 1): master.py. Lists online nodes, sends each one a task, collects the replies.
- SuperNode: worker.py. Reads its local profile (path set by the node's operator with --node-config)
  and replies "<greeting> <name>" exactly once.
- protocol.py is the task/reply format both sides agree on; common.py holds shared Grid helpers.

There's no "James" in this code: the name comes from the node's own profile.json.
No model calls, so no API keys are needed.
"""

from __future__ import annotations

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

from hello_app.master import run_master
from hello_app.worker import run_worker

SUPERLINK_NODE_ID = 1  # flwr.common.constant.SUPERLINK_NODE_ID

app = AgentApp()


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Same code on every machine; the node id decides the role."""
    if context.node_id == SUPERLINK_NODE_ID:
        run_master(agent)
    else:
        run_worker(agent, context)
