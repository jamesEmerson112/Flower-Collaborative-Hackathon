"""The message contract between the master and the workers.

Both sides import from here, so a change to the task format happens in one place.
Agree on this file first; after that, master.py and worker.py can change independently.

Task (master -> worker): JSON {"task": "greet", "prompt": "<the user's chat text>"}
Reply (worker -> master): plain text, e.g. "Hello James", or "<CODE>: <reason>" on failure.
"""

from __future__ import annotations

import json
from typing import Any

TASK_GREET = "greet"


def make_task(prompt: str) -> str:
    """Master side: build the payload sent to every SuperNode."""
    return json.dumps({"task": TASK_GREET, "prompt": prompt})


def read_task(agent_prompt: str) -> dict[str, Any]:
    """Worker side: unwrap the Grid envelope and return the task dict.

    On a SuperNode, agent.prompt is {"message_id", "src_node_id", "payload"}, and
    payload is the string make_task() produced. Raises ValueError if it isn't a task.
    """
    envelope = json.loads(agent_prompt)
    task = json.loads(envelope["payload"]) if isinstance(envelope, dict) else None
    if not isinstance(task, dict) or "task" not in task:
        raise ValueError(f"not a task payload: {agent_prompt[:200]}")
    return task
