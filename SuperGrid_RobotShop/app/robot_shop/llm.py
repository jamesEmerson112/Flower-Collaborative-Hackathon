"""The master's one model call: turn the computed quote into a short friendly answer.

The numbers are always computed in code (pricing.py); the model only writes prose around
them. Any failure returns None and the master falls back to pricing.format_quote().

Uses httpx (already a flwr dependency) against Flower's Responses endpoint instead of the
openai package: the FAB declares no extra dependencies, because SuperNodes don't install
them and a failed install on the SuperLink would kill the run before main().
Flower injects FLWR_RUNTIME_BASE_URL / FLWR_RUNTIME_API_KEY per task; never set them.

The call streams (SSE), like every Flower Hub app. The runtime route accepts both modes
(flwr 1.39.0 supercore/routers/runtime/responses.py:105-112), but a non-streamed request
sends nothing until the model task has launched and the model has finished, which blew our
60 s client timeout live. Streaming at least delivers text as it arrives and lets us keep
what we have on response.incomplete.
"""

from __future__ import annotations

import json
import os
from typing import Any

MODEL = "openai/gpt-5.6-sol"
# Read timeout, in seconds, between two chunks of the SSE stream (not a total deadline).
# The first chunk waits for the model task to launch AND the model's first output token:
# the model task buffers response.created / in_progress until the first text delta
# (flwr supercore/task_process/model/task.py:81-85). The server itself allows 300 s
# (responses.py:72-73). Lower this to fall back to format_quote() sooner.
TIMEOUT_S = 30.0  # demo setting: cap the wait before the plain-code fallback (source allows longer; 90 s gives the model more time)
# was: TIMEOUT_S = 90.0

INSTRUCTIONS = """\
You are a friendly purchasing assistant for a robot builder. You get JSON with the
customer's request and a quote that code has already computed from the stores' replies.

Write the answer in under 150 words (markdown is fine):
- Say which store supplies which parts, with each store's subtotal.
- Give the total per currency.
- Mention every part in "unquoted" by name, with its reason (e.g. no store sells it).
- If nothing was quoted, say so and suggest checking that the store nodes are online.

Use only the numbers that appear in the quote JSON, copied exactly. Never add, multiply,
convert or compute new prices or totals. Don't invent stores, parts, prices or links."""


def extract_text(data: Any) -> str | None:
    """Text of a Responses API result: output_text if present, else the joined
    output[].content[].text parts whose type is "output_text". None if there's none."""
    if not isinstance(data, dict):
        return None
    text = data.get("output_text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    messages: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        parts = [
            part["text"]
            for part in item.get("content") or []
            if isinstance(part, dict)
            and part.get("type") == "output_text"
            and isinstance(part.get("text"), str)
        ]
        if parts:
            messages.append("".join(parts))
    joined = "\n\n".join(messages).strip()
    return joined or None


def _parse_event(event_name: str | None, data_lines: list[str]) -> dict[str, Any] | None:
    """One SSE frame -> event dict (type from the JSON, else the `event:` name).
    None for an empty frame or `[DONE]`; raises ValueError on non-JSON data."""
    data = "\n".join(data_lines)
    if not data.strip() or data.strip() == "[DONE]":
        return None
    event = json.loads(data)
    if not isinstance(event, dict):
        raise ValueError(f"SSE data is not a JSON object: {data[:200]}")
    if not isinstance(event.get("type"), str) and event_name:
        event["type"] = event_name
    return event


def _iter_sse(lines: Any) -> Any:
    """Yield event dicts from an iterator of SSE text lines (without line terminators)."""
    event_name: str | None = None
    data_lines: list[str] = []
    for raw in lines:
        line = raw.rstrip("\r")
        if not line:  # blank line ends a frame
            event = _parse_event(event_name, data_lines)
            if event is not None:
                yield event
            event_name, data_lines = None, []
        elif line.startswith(":"):  # SSE comment / keep-alive
            continue
        elif line.startswith("data:"):
            data_lines.append(line[5:].removeprefix(" "))
        elif line.startswith("event:"):
            event_name = line[6:].strip()
    event = _parse_event(event_name, data_lines)  # a last frame without the blank line
    if event is not None:
        yield event


def _error_reason(event: dict[str, Any]) -> str:
    """Short human reason from an error / response.failed / response.incomplete event."""
    response = event.get("response") if isinstance(event.get("response"), dict) else {}
    error = event.get("error") or response.get("error")
    if isinstance(error, dict):
        return f"{error.get('code') or ''} {error.get('message') or ''}".strip()
    if event.get("message"):
        return f"{event.get('code') or ''} {event.get('message')}".strip()
    details = response.get("incomplete_details")
    if isinstance(details, dict) and details.get("reason"):
        return str(details["reason"])
    return json.dumps(event)[:300]


def write_answer(request_text: str, quote: dict[str, Any]) -> str | None:
    """One streamed Responses call (SSE); returns the answer text, or None on any failure."""
    try:
        base_url = os.environ["FLWR_RUNTIME_BASE_URL"].rstrip("/")
        api_key = os.environ["FLWR_RUNTIME_API_KEY"]
        import httpx  # lazy: keeps the pure modules importable without flwr/httpx

        deltas: list[str] = []
        with httpx.stream(
            "POST",
            f"{base_url}/responses",
            headers={"Authorization": f"Bearer {api_key}", "Accept": "text/event-stream"},
            json={
                "model": MODEL,
                "instructions": INSTRUCTIONS,
                "input": json.dumps({"request": request_text, "quote": quote}),
                "stream": True,
            },
            timeout=httpx.Timeout(connect=10.0, read=TIMEOUT_S, write=10.0, pool=10.0),
        ) as response:
            if not 200 <= response.status_code < 300:
                response.read()  # a streamed body must be read before .text
                print(f"[robot-shop] model call HTTP {response.status_code}: {response.text[:400]}", flush=True)
                return None
            for event in _iter_sse(response.iter_lines()):
                kind = event.get("type")
                if kind == "response.output_text.delta":
                    if isinstance(event.get("delta"), str):
                        deltas.append(event["delta"])
                elif kind == "response.completed":
                    text = "".join(deltas).strip() or extract_text(event.get("response"))
                    if not text:
                        print(f"[robot-shop] model call returned no text: {json.dumps(event)[:400]}", flush=True)
                    return text or None
                elif kind == "response.incomplete":
                    text = "".join(deltas).strip()
                    print(f"[robot-shop] model call incomplete ({_error_reason(event)}); "
                          f"{'using partial text' if text else 'no text'}", flush=True)
                    return text or None
                elif kind in ("response.failed", "error"):
                    print(f"[robot-shop] model call failed: {kind}: {_error_reason(event)[:300]}", flush=True)
                    return None
        print(f"[robot-shop] model call stream ended before a terminal event "
              f"({len(deltas)} deltas received)", flush=True)
        return None
    except Exception as exc:  # noqa: BLE001 (the plain-code answer covers every failure)
        print(f"[robot-shop] model call failed: {type(exc).__name__}: {str(exc)[:300]}", flush=True)
        return None
