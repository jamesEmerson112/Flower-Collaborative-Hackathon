"""Robot Shop AgentApp: store SuperNodes quote robot parts from their private catalogues.

One FAB, two roles, chosen at run time. This file only picks the role:
- SuperLink (node_id 1): master.py. Asks the "store-*" nodes for quotes, combines them in
  code, and makes the run's one model call to write the answer.
- SuperNode: worker.py. Quotes from its local catalogue (path set by the node's operator
  with --node-config) and replies exactly once. No model calls.
- protocol.py is the message contract, pricing.py the money math, catalog.py the
  catalogue lookup, llm.py the model call, common.py the Grid/event helpers.
"""

from __future__ import annotations

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context

from robot_shop.master import run_master
from robot_shop.worker import run_worker

SUPERLINK_NODE_ID = 1  # flwr.common.constant.SUPERLINK_NODE_ID

app = AgentApp()


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Same code on every machine; the node id decides the role."""
    if context.node_id == SUPERLINK_NODE_ID:
        run_master(agent)
    else:
        run_worker(agent, context)
