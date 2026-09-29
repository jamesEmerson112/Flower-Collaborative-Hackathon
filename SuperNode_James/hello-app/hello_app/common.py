"""Helpers both roles use: call a Grid tool from code, and show text in flwr chat."""

from __future__ import annotations

import json
import uuid
from typing import Any

from flwr.agentapp import AgentSession


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
