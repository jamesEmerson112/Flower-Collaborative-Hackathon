# Exploring `@flwrlabs/collaborative-agent`

Hub page: https://flower.ai/apps/flwrlabs/collaborative-agent
Local copy: [`docs/collaborative-agent/`](collaborative-agent/). It is unmodified (`diff -r` against the extracted zip is clean). Keep it that way so it can be diffed against upstream.

Legend: **[src]** = read in the app or `flwr` 1.39.0 source. **[docs]** = Flower docs / Hub page. **[inference]** = our reading, not verified.

---

## Provenance

- Fetched 2026-09-29. App version **0.2.0**. The Hub page says 2 versions exist; `app_version: null` resolved to 0.2.0 (`resolved_by_compatibility: false`).
- Same method as the recipe: `POST https://api.flower.ai/v1/hub/fetch-zip` with `{"app_id": "@flwrlabs/collaborative-agent", "app_version": null, "flwr_version": "1.39.0"}`, then download the presigned `zip_url`. The zip's top-level folder is `collaborative-agent/`, which is what `flwr new` would create.
- Files (7): `.gitignore`, `LICENSE` (Apache-2.0), `README.md`, `pyproject.toml`, `agent/__init__.py`, `agent/agent_app.py` (51 lines), `agent/utils.py` (98 lines).

---

## What the app does (observed in source)

One AgentApp. The same `main()` runs on the SuperLink and on SuperNodes (see Grid usage) **[src]**:

1. It builds an OpenAI client from `FLWR_RUNTIME_BASE_URL` / `FLWR_RUNTIME_API_KEY`, which the runtime injects. `max_retries=0`.
2. `_conversation()` (`agent/utils.py`) rebuilds the chat history from **`agent.events.get_trace()`**. It keeps user/assistant messages and the assistant output of `response.completed` events. It appends **`agent.prompt`** as the user turn only if the trace doesn't already contain it for this run. The runtime emits that user message before `main()` runs. It goes out through a batched background publisher, so it may or may not reach the trace in time; the `current_prompt_seen` check covers both cases. It does not use `context.state` or run config.
3. Tools: `[*agent.grid.tools(), *agent.connectors.tools(["filesystem"])]`.
4. Loop of up to `MAX_TOOL_ROUNDS = 20` (hardcoded). Each round is one **streamed** Responses API call (`reasoning={"effort": "medium"}`) that forwards `output_text.delta` / `reasoning_summary_text.delta` events. If a round has no tool calls, it emits the `response.completed` event and returns. After 20 rounds it raises `RuntimeError`.
5. System instructions = `AGENT_COLLABORATION_INSTRUCTIONS + INSTRUCTIONS`. The first tells the model to reply with `push_reply_message` exactly once when the prompt contains `src_node_id`, and otherwise to answer the user. The second says to use Grid tools, not invent results, and not send raw data.

| `pyproject.toml` key | Value |
|---|---|
| `dependencies` | `flwr>=1.38.0,<2.0` (no `[agent]` extra), `openai>=2.16.0,<3.0.0` |
| `flwr-version-target` | `1.38.0` (we read 1.39.0 source) |
| `display-name` | `"Clinical Analytics Agent"` (!) |
| `[tool.flwr.app.components] agentapp` | `agent.agent_app:app` |
| `[tool.flwr.app.config]` | **none**: no run-config keys at all |
| Model | hardcoded `MODEL = "openai/gpt-5.6-terra"` in `agent/utils.py` |

The `[agent]` extra only adds `browser-use` and `trafilatura` (`flwr-1.39.0.dist-info/METADATA`). This app doesn't need them **[src]**.

---

## Grid usage

### Q1: Does it use `agent.grid`? Yes, as its main tool set **[src]**

```python
connector_tools = agent.connectors.tools(["filesystem"])   # except ValueError: []
tools = [*agent.grid.tools(), *connector_tools]
...
agent.connectors.call(item) if item.get("name") in connector_tool_names else agent.grid.call(item)
```

- The app routes by name: anything that isn't a connector tool goes to `agent.grid.call`. `RuntimeAgentGrid.call` raises `ValueError("Unsupported Grid tool ...")` for names outside its role's set (`flwr/supercore/task_process/agent/grid.py`).
- `agent.grid.call` itself emits `function_call` / `function_call_output` events, so Grid activity shows up in the trace and the chat UI.
- The `filesystem` connector (`flwr/supercore/task_process/connector/filesystem/`) exposes `filesystem_list_directory` and `filesystem_read_file` (UTF-8, up to 1 MiB). It builds its tools **at import time** and returns **zero tools** unless `FLWR_FILESYSTEM_ALLOWED_DIRS` is set to existing absolute dirs in the AgentApp process. The app's `except ValueError` only catches an *unknown* connector ref (`registry.get_connector_tools`), which could happen on an older runtime without `filesystem` **[inference]**. It does not catch the env var being unset; that case silently produces no tools.

### Q2: Same code, both roles? Yes. The runtime picks the role, not the app **[src]**

- **Same FAB on every node.** When a SuperNode receives a message for a run it doesn't know, it pulls that run's FAB (`get_fab(run_info.fab_hash, run_id)`) and creates an `AGENT_APP` task with the same `fab_hash`. It creates **one task per incoming message** (`flwr/supernode/start_client_internal.py`, `_pull_and_store_message`).
- **Tool set by node id.** `RuntimeAgentGrid.__init__` checks `node_id == SUPERLINK_NODE_ID` (`= 1`, `flwr/common/constant.py`). On the SuperLink you get `get_nodes`, `push_messages`, `pull_messages`. On a SuperNode you get only `push_reply_message`.
- **Prompt shape.** The SuperLink's initial instruction is a `system`-type message (`create_user_prompt_message` in `flwr/server/superlink/linkstate/utils.py`), so `message_to_prompt` returns the raw user text. `push_messages` sends `message_type="query"`, so a worker's prompt is compact JSON (`flwr/supercore/task_process/agent/run_agentapp.py`).
- The app never reads `context.node_id`. It relies on (a) the tools it is handed and (b) the system instruction "`src_node_id` in the prompt ⇒ reply via `push_reply_message`".

### Q3: How a worker reads the task and replies **[src]**

- `agent.prompt` = `{"message_id":"…","src_node_id":"1","payload":"<task text>"}`. The app passes it to the model **verbatim** as the user message. There is no JSON parsing in code; the model interprets it.
- The model calls `push_reply_message(payload=...)`. The runtime fills in `dst_node_id` = the instruction's `src_node_id` and `reply_to_message_id`, sets a 6 h TTL, then clears the stored instruction metadata. A second call returns the error `"No instruction message to reply to…"`.
- If the worker task **fails**, the SuperNode stores an error reply `"AgentApp failed before replying."` (`flwr/supernode/nodestate/in_memory_nodestate.py`, `finish_task`). The master's `pull_messages` then returns an `error` entry and doesn't wait for the full timeout.
- The error reply is scoped **per run, not per task**. `_store_error_replies({run_id}, …)` error-replies every message *this SuperNode* has retrieved for that run and not yet answered, and links each one via `Message(error, reply_to=msg)`, so `pull_messages` clears them from pending **[src]**. If the master sends two messages to the same node in one run and one worker task crashes, the other in-flight message probably gets the error reply too **[inference]**.
- If the worker model finishes **without** calling `push_reply_message`, we found no code that sends a reply automatically **[inference]**. The master would only see `pending_message_ids` after its timeout.
- Worker memory: on a SuperNode, `get_trace()` returns only the AgentApp events *stored on that SuperNode* for the run series (`flwr/supernode/servicer/runtime/runtime_handlers.py`, `get_run_series_events`). Workers don't see the master's transcript.
- SuperNodes also mount the `/v1/runtime` responses router (`flwr/supernode/main.py`), so workers call the model the same way the master does.

### Master side (what the model is expected to do; nothing is hardcoded)

`get_nodes(sample_size)` → `push_messages([{dst_node_id, payload, reply_to_message_id: null}, …])` → `pull_messages(message_ids, timeout ≤ 300)` → answer the user. The model drives all orchestration **[src]**.

---

## Our read (not from the docs)

- **Best base so far for the master/sub-node plan.** The Grid loop, role handling and worker reply are already done. It is ~150 lines, so it's easy to fork.
- **Main constraint:** one run = one FAB on every node, so sub-nodes can only differ through **node-local** inputs. Those are the node's files (via `FLWR_FILESYSTEM_ALLOWED_DIRS`), `context.node_config` (set by the SuperNode operator with `--node-config`, `flwr/supernode/cli/flower_supernode.py`), and `get_nodes`' `name`/`location`. We don't control any of these on hackathon SuperNodes. Specialised workers therefore have to come from the master's **payload** (role/task in the message text) or from code branches keyed on `node_config`/data. This is a question for mentors.
- The `"Clinical Analytics Agent"` display name, the `filesystem` connector, and the "never send raw data" rule suggest the intended demo: each SuperNode holds private (clinical) files, workers analyse them locally, and only summaries go back to the master **[inference]**.
- Role detection lives in the prompt. A fork should branch in **code** on `context.node_id == 1` (or on whether `get_nodes` is in `agent.grid.tools()`), giving master and worker separate instructions and budgets. A 20-round worker loop is generous.
- Worth porting from the recipe: run-config keys (`agent.model`, `agent.max-tool-turns`) and the `web_search`/`web_fetch` connectors if the master needs the web.

### Differences vs `hackathon-collab-agent-recipe/`

| | `collaborative-agent` 0.2.0 | `hackathon-collab-agent-recipe` 0.2.0 |
|---|---|---|
| `agent.grid` | **yes**: all role tools | no |
| Connectors | `filesystem` (env-gated) | `web_search`, `web_fetch` |
| Input | `agent.prompt` | run config `agent.input` |
| Memory | `agent.events.get_trace()` | `context.state.config_records["items"]` |
| Run config | none (model hardcoded `gpt-5.6-terra`) | `model` (`gpt-5.6-sol`), `input`, `max-tool-turns` |
| Loop | streamed every round, max 20 | non-streamed tool rounds (max 2, ≤10) + final streamed call |
| flwr pin | `flwr>=1.38.0`, target 1.38.0 | `flwr[agent]>=1.35.0`, target 1.35.0 |

---

## Running it

The app README has **no run instructions**. The Hub page only shows `flwr new @flwrlabs/collaborative-agent` **[docs]**.

**Use `flwr chat`, not `flwr run`.** In 1.39.0, `flwr run` (`flwr/cli/run/run.py`) builds a `StartRunRequest` without `user_prompt`. The SuperLink rejects AgentApp runs that have no prompt with `AGENTAPP_USER_PROMPT_REQUIRED` (`flwr/superlink/servicer/control/control_handlers.py`) **[src]**. Only `flwr chat` sets `user_prompt` (`flwr/cli/chat/chat_app.py`, `start_chat_run`). The "Run an AgentApp on SuperGrid" guide also uses `flwr chat` + `/load` **[docs]**. We assume SuperGrid runs this same check **[inference]**.

```shell
cd docs/collaborative-agent
uv sync
uv run flwr build                       # sanity check
uv run flwr login supergrid             # interactive
uv run flwr federation list supergrid   # find the hackathon federation
uv run flwr chat
# inside chat:
/federation @<account>/<federation-name>   # personal federation likely has no SuperNodes
/load .                                    # builds and selects this AgentApp
Ask the nodes in this federation to ...    # the prompt becomes agent.prompt on the SuperLink
```

Debug:

```shell
uv run flwr list --run-id <run-id> supergrid
uv run flwr log <run-id> supergrid --show
uv run flwr stop <run-id> supergrid
```

- `/connector` selection in chat is only allowed in the personal federation **[src]**. That shouldn't matter here, because the app requests `filesystem` directly.
- For each message a SuperNode receives, the runtime automatically starts a worker **task**, not a new run. The task uses the same FAB and `run_id` (`create_task(..., run_id=message.metadata.run_id)`). So a worker's `context.run_id` equals the master's, and `flwr list` shows no separate worker runs. No per-node deploy step exists in the app or the docs we read **[src + docs]**.

### README discrepancies

- The README (and Hub description) says agents can "sample other agents…, push messages to them, and pull their replies". That's true only on the SuperLink. SuperNode agents get only `push_reply_message`.
- `display-name = "Clinical Analytics Agent"` doesn't match the app name or description.
- Prompt bugs in `agent/utils.py`:
  - The two instruction strings are joined with no separator (`"…reply directly to the user.Use the available Grid tools…"`).
  - `"…do not invent results." "EVER send raw data in a message…"` is missing both a space and, almost certainly, the "N" of **NEVER**. As written, the rule reads like an instruction to send raw data.
- `agent/__init__.py` docstring says "A minimal Flower AgentApp"; `agent_app.py` says "…that involves SuperNodes".

---

## References

- AgentApp runtime explainer: https://flower.ai/docs/agent/explanations/agentapp-runtime.html (mentions `agent.grid` in one line only; nothing on SuperNodes or Grid tools).
- Run an AgentApp on SuperGrid: https://flower.ai/docs/agent/how-to-guides/run-on-supergrid.html (`flwr chat` + `/load`, pinned to `flwr==1.39.0`).
- Use agents and federations: https://flower.ai/docs/agent/how-to-guides/use-agents-and-federations.html (`/federation`, `@publisher/agent <prompt>`).
- Sibling notes: [collab-agent-recipe.md](collab-agent-recipe.md). Brief: [hackathon-brief.md](hackathon-brief.md).
- `flwr` 1.39.0 modules cited: `flwr/agentapp/base.py`, `flwr/supercore/task_process/agent/{grid,run_agentapp,session}.py`, `flwr/supercore/task_process/connector/{registry.py,filesystem/}`, `flwr/supernode/start_client_internal.py`, `flwr/supernode/nodestate/in_memory_nodestate.py`, `flwr/superlink/servicer/control/control_handlers.py`, `flwr/cli/run/run.py`, `flwr/cli/chat/chat_app.py`.

## Next steps

- [ ] `uv sync`, then `uv run flwr --version`. The pin allows 1.38.x, and these notes are based on 1.39.0.
- [ ] Baseline in `flwr chat`: `/federation` to the hackathon federation, `/load collaborative-agent`, and a prompt like "Ask every node what data it has and summarise." Check the trace for `get_nodes` → `push_messages` → `pull_messages`.
- [ ] Ask mentors:
  - Do hackathon SuperNodes run AgentApps (warm pools / preloaded FABs)?
  - Is `FLWR_FILESYSTEM_ALLOWED_DIRS` set, and what data is there?
  - Do nodes have a `name`/`location` or `node_config` we can key on?
- [ ] Fork into our own app:
  - Branch master/worker in code on `context.node_id`.
  - Fix the instruction strings.
  - Guard `agent.grid.call`. Bad model arguments (unknown tool name, `sample_size < 1`, `timeout > 300`) raise `ValueError` in `flwr/supercore/task_process/agent/grid.py`, and the app doesn't catch it, so one bad call fails the task. Return an error `function_call_output` instead, the way the recipe does for connectors.
  - Add run-config keys (model, rounds).
  - Optionally add `web_search`/`web_fetch` for the master.
