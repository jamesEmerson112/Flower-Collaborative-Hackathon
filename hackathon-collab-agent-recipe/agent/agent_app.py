"""A collaborative research AgentApp for Flower."""

from __future__ import annotations

import json
import os
from typing import Any

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import ConfigRecord, Context
from openai import OpenAI

TOOL_REFS = ("web_search", "web_fetch")
DEFAULT_MAX_TOOL_TURNS = 2
MAX_TOOL_TURNS_LIMIT = 10

app = AgentApp()


def message_text(content: Any) -> str:
    """Normalize stored Open Responses message content to plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                raise TypeError("Message content parts must be objects")
            value = part.get("text", part.get("refusal"))
            if not isinstance(value, str):
                raise TypeError(
                    "Message content parts must contain text or refusal"
                )
            parts.append(value)
        return "\n".join(parts)
    raise TypeError("Message content must be text or a list of content parts")


def conversation_messages(context: Context) -> list[dict[str, Any]]:
    """Replay only user and assistant messages from the run series."""
    messages: list[dict[str, Any]] = []
    items_record = context.state.config_records.get("items")
    items = items_record.get("json", []) if items_record is not None else []
    for item_json in items:
        item = json.loads(item_json)
        if item.get("type") != "message":
            continue
        role = item.get("role")
        if role not in {"user", "assistant"}:
            continue
        messages.append(
            {
                "type": "message",
                "role": role,
                "content": message_text(item.get("content")),
            }
        )
    return messages


def append_assistant_message(context: Context, text: str) -> None:
    """Persist the final assistant message for the next run in the series."""
    message = {"type": "message", "role": "assistant", "content": text}
    with context.locked():
        items_record = context.state.config_records.setdefault(
            "items", ConfigRecord({"json": []})
        )
        items = items_record.get("json")
        if not isinstance(items, list):
            raise TypeError("Context items must be a list")
        items.append(json.dumps(message))


def connector_error_output(
    tool_call: dict[str, Any], exc: Exception
) -> dict[str, Any]:
    """Return a connector error that the model can handle on its next turn."""
    return {
        "type": "function_call_output",
        "call_id": tool_call["call_id"],
        "output": json.dumps({"error": str(exc)}),
    }


def configured_string(context: Context, name: str) -> str:
    """Read and validate a required non-empty string run-config value."""
    value = context.run_config.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value.strip()


def configured_tool_turns(context: Context) -> int:
    """Read and validate the bounded tool-turn count."""
    value = context.run_config.get("agent.max-tool-turns", DEFAULT_MAX_TOOL_TURNS)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("agent.max-tool-turns must be an integer")
    if not 0 <= value <= MAX_TOOL_TURNS_LIMIT:
        raise ValueError(
            f"agent.max-tool-turns must be between 0 and {MAX_TOOL_TURNS_LIMIT}"
        )
    return value


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    """Research the configured prompt with a bounded connector loop."""
    prompt = configured_string(context, "agent.input")
    model = configured_string(context, "agent.model")
    max_tool_turns = configured_tool_turns(context)

    client = OpenAI(
        base_url=os.environ["FLWR_RUNTIME_BASE_URL"],
        api_key=os.environ["FLWR_RUNTIME_API_KEY"],
    )
    input_items = conversation_messages(context)
    if not any(
        item["role"] == "user" and item["content"].strip() == prompt
        for item in input_items
    ):
        input_items.append(
            {"type": "message", "role": "user", "content": prompt}
        )

    tools = agent.connectors.tools(TOOL_REFS)
    allowed_tool_names = {
        tool["name"] for tool in tools if isinstance(tool.get("name"), str)
    }

    for _ in range(max_tool_turns):
        response = client.responses.create(
            model=model,
            input=input_items,
            instructions=(
                "Research the user's question using public sources when useful. "
                "Request independent tool calls together. Prefer primary sources, "
                "track source URLs, and never invent evidence."
            ),
            tools=tools,
            tool_choice="auto",
        )
        response_output = [item.to_dict() for item in response.output]
        tool_calls = [
            item for item in response_output if item.get("type") == "function_call"
        ]
        if not tool_calls:
            break

        function_outputs: list[dict[str, Any]] = []
        for tool_call in tool_calls:
            if tool_call.get("name") not in allowed_tool_names:
                function_outputs.append(
                    connector_error_output(
                        tool_call,
                        RuntimeError(
                            f"Tool {tool_call.get('name')!r} was not exposed"
                        ),
                    )
                )
                continue
            try:
                arguments = tool_call.get("arguments")
                if isinstance(arguments, str):
                    arguments = json.loads(arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool call arguments must be a JSON object")
                function_outputs.append(agent.connectors.call(tool_call))
            except (RuntimeError, ValueError) as exc:
                function_outputs.append(connector_error_output(tool_call, exc))

        input_items.extend(response_output)
        input_items.extend(function_outputs)

    stream = client.responses.create(
        model=model,
        input=input_items,
        instructions=(
            "Answer from the available evidence. Cite source URLs when available, "
            "mention failed source access, distinguish inference from sourced fact, "
            "and do not invent results."
        ),
        stream=True,
    )

    output_text = []
    for event in stream:
        agent.events.emit(event.to_dict())
        if event.type in {"error", "response.failed"}:
            raise RuntimeError(f"Model response failed: {event}")
        if event.type == "response.output_text.delta":
            output_text.append(event.delta)

    final_text = "".join(output_text)
    append_assistant_message(context, final_text)
    print(final_text)
