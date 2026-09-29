# Exploring `@flwrlabs/hackathon-collab-agent-recipe`

Hub page: https://flower.ai/apps/flwrlabs/hackathon-collab-agent-recipe
Local copy: [`docs/hackathon-collab-agent-recipe/`](hackathon-collab-agent-recipe/). It is unmodified; keep it that way so it can be diffed against upstream.

---

## Provenance

- Fetched 2026-09-29. App version **0.2.0**.
- The normal command is `flwr new @flwrlabs/hackathon-collab-agent-recipe`. We didn't use it because `uvx --from flwr` stalled while downloading wheels on the venue network, so `flwr` isn't installed yet.
- Instead we made the same request `flwr new` makes internally: `POST https://api.flower.ai/v1/hub/fetch-zip` with `{"app_id": "@flwrlabs/hackathon-collab-agent-recipe", "app_version": null, "flwr_version": "1.39.0"}`. That returns a presigned zip URL. We downloaded the zip and extracted it, so the folder matches what `flwr new` would have produced.

---

## What the app does (observed in source)

A single AgentApp, `agent/agent_app.py`, that does web research:

1. It reads its prompt from run config `agent.input` and its model from `agent.model` (default `openai/gpt-5.6-sol`). Both defaults are set in `pyproject.toml`.
2. It builds an OpenAI client against `FLWR_RUNTIME_BASE_URL` / `FLWR_RUNTIME_API_KEY`. Flower injects both at runtime, so no provider key goes in the project.
3. It replays earlier **user/assistant** messages from `context.state.config_records["items"]`, which holds the conversation memory for the run series.
4. It gets tool schemas from `agent.connectors.tools(("web_search", "web_fetch"))`.
5. It runs a tool loop with the OpenAI **Responses API** (`client.responses.create`) for up to `agent.max-tool-turns` rounds (default 2, allowed range 0–10), executing calls with `agent.connectors.call(tool_call)`.
6. It makes a final **streamed** call and forwards each event to `agent.events.emit(...)`.
7. It tries to save the final answer back into `context.state` so the next run in the series can see it.

> **Bugs on `flwr` 1.39.0 (verified in source, not tested live):**
> - `append_assistant_message` uses `with context.locked():`, but `Context` (`flwr/app/message/context.py`) has no `locked()` method. After the answer has streamed to the UI, the task raises `AttributeError` and ends FAILED, and nothing is persisted. The 1.35.0 target may have had `locked()`; unverified.
> - Connector calls go through a child task that raises `TimeoutError` when no reply arrives (`flwr/supercore/task_process/agent/session.py`). The recipe catches only `(RuntimeError, ValueError)`, so a slow `web_fetch` fails the whole task.
> - Under `flwr chat` the typed prompt is ignored: chat sends no `override_config`, and the app reads only `agent.input` from run config **[inference from source]**.

| `pyproject.toml` key | Value |
|---|---|
| `dependencies` | `flwr[agent]>=1.35.0,<2.0`, `openai>=2.16.0,<3.0.0` |
| `[tool.flwr.app.components] agentapp` | `agent.agent_app:app` |
| `[tool.flwr.app.config.agent]` | `model`, `input`, `max-tool-turns` |

---

## Key finding: this recipe has no agent-to-agent collaboration

Despite its name, the recipe only uses **connectors** (`web_search`, `web_fetch`) and never touches **`agent.grid`**.
The brief's "sample other agents, send them messages, retrieve their responses" is the Grid API on `AgentSession`, and this template doesn't use it. Adding it is the work we still have to do.

### Grid tools API (read from `flwr` 1.39.0 source)

`AgentSession` (in `flwr/agentapp/base.py`) exposes `prompt`, `connectors`, `events` and **`grid`**.
`agent.grid` has the same `tools()` / `call(tool_call)` shape as connectors. The tool definitions live in `flwr/supercore/task_process/agent/grid.py`.

Which tools you get depends on **where the AgentApp runs**:

| Runs on | Grid tools available |
|---|---|
| **SuperLink** (orchestrator) | `get_nodes`, `push_messages`, `pull_messages` |
| **SuperNode** (worker) | `push_reply_message` only |

| Tool | Input | Output |
|---|---|---|
| `get_nodes` | `sample_size: int \| null` (null returns all nodes) | `{nodes: [{id, name, location}], num_available}` |
| `push_messages` | `messages: [{dst_node_id, payload, reply_to_message_id \| null}]` | `{results: [{message_id \| null, error \| null}]}`, one result per message, in order |
| `pull_messages` | `message_ids: [str]`, `timeout: 0–300 s` (0 checks once) | `{messages: [{message_id, reply_to_message_id, src_node_id, payload, error}], pending_message_ids}` |
| `push_reply_message` | `payload: str` | `{message_id \| null, error \| null}` (replies to the last instruction received) |

Node IDs are uint64 values passed as decimal strings.

How a SuperNode agent gets its input (`flwr/supercore/task_process/agent/run_agentapp.py`):
- `agent.prompt` holds the incoming instruction. For a normal message it is a compact JSON string, `{"message_id", "src_node_id", "payload"}`. For a system message it is just the payload.
- The recipe ignores `agent.prompt` and reads `agent.input` from run config. A worker that is meant to answer other agents would need to read `agent.prompt` instead.

### Our read (not from the docs)

- The architecture follows from the tool split: an **orchestrator AgentApp on the SuperLink** fans work out with `get_nodes` → `push_messages` → `pull_messages`, and **worker AgentApps on SuperNodes** answer with `push_reply_message`.
- **One FAB per run, both roles** (verified in `flwr/supercore/task_process/agent/run_agentapp.py`). A SuperNode installs the run's FAB, or uses a preloaded one only if its hash, `fab_id` and `fab_version` match; otherwise it raises `"Task FAB does not match the preloaded AgentApp."`. So master and workers are the same app and branch on role: `context.node_id == 1` (`SUPERLINK_NODE_ID`) means the master.
- The recipe's tool loop can host Grid tools unchanged. Concatenate `agent.grid.tools()` with the connector tools and route each `function_call` by name to `agent.grid.call` or `agent.connectors.call`.
- **Version caveat:** these notes come from `flwr` **1.39.0**. The recipe pins `flwr[agent]>=1.35.0,<2.0` with `flwr-version-target = "1.35.0"`. `uv sync` will probably resolve 1.39.x, but confirm with `uv run flwr --version` before relying on these schemas.

---

## Running it (from the recipe README)

Requirements: Python 3.11+, `uv`, and a SuperGrid account with Flower Agent access.

```shell
cd docs/hackathon-collab-agent-recipe   # the README says `cd collaborative-agent`; that name is stale
uv sync
uv run flwr build
uv run flwr login supergrid        # interactive; uses your Flower account
uv run flwr run . supergrid --stream
```

> **Caveat (verified in `flwr` 1.39.0 source, not tested live):** the SuperLink rejects an AgentApp run with an empty user prompt (`AGENTAPP_USER_PROMPT_REQUIRED`, in `flwr/superlink/servicer/control/control_handlers.py`). In the CLI, only `flwr chat` sets `user_prompt` (`flwr/cli/chat/chat_app.py`), so `flwr run` as written above will probably fail on 1.39.x. Try `flwr chat` → `/load .` instead, as the `@flwrlabs/agent` README does (see [flwrlabs-agent.md](flwrlabs-agent.md)).

Override the prompt for one run (from the README; **a dead path on 1.39.x**: `flwr run` can't start AgentApps, and `flwr chat` has no way to pass `--run-config`):

```shell
uv run flwr run . supergrid \
  --run-config 'agent.input="Compare two recent explanations of federated AI."' \
  --stream
```

Debug a failed run:

```shell
uv run flwr list supergrid
uv run flwr log <run-id> supergrid --show
```

### README discrepancies

- The README says `cd collaborative-agent`, but the folder is `hackathon-collab-agent-recipe`.
- The Hub web page shows `uv build flwr`, while the README says `uv run flwr build`. Treat the README as correct.

---

## References

- Collaborative agent tutorial (linked from the recipe README; **404 as of 2026-09-29**): https://flower.ai/docs/agent/tutorials/build-a-collaborative-agent.html
- AgentApp runtime explainer (live): https://flower.ai/docs/agent/explanations/agentapp-runtime.html
- Hackathon brief notes: [hackathon-brief.md](hackathon-brief.md)

## Next steps

- [ ] `uv sync` inside the folder once the network allows. It pulls about 40 MB of wheels, including grpcio, numpy and cryptography.
- [ ] `uv run flwr login supergrid` and do one baseline run of the recipe as-is.
- [ ] Read the tutorial above to see whether it already shows an orchestrator/worker example that uses `agent.grid`.
- [ ] Ask mentors: which SuperNodes in the hackathon federation run AgentApps, and how an orchestrator run on the SuperLink is launched.
