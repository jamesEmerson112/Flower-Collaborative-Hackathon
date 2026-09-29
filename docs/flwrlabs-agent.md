# Exploring `@flwrlabs/agent`

Hub page: https://flower.ai/apps/flwrlabs/agent (title "Flower AgentApp")
Local copy: [`agent/`](../agent/). It is unmodified; keep it that way so it can be diffed against upstream. The package is nested, so the code lives in `agent/agent/`.

---

## Provenance

- Fetched 2026-09-29. App version **0.4.0**, and the Hub returned `resolved_by_compatibility: false` for `flwr_version` 1.39.0.
- We used the same method as [collab-agent-recipe.md](collab-agent-recipe.md): `POST https://api.flower.ai/v1/hub/fetch-zip` with `{"app_id": "@flwrlabs/agent", "app_version": null, "flwr_version": "1.39.0"}`, then downloaded the presigned zip. That is the request `flwr new @flwrlabs/agent` makes.
- The zip contains 6 files under `agent/`: `.gitignore`, `LICENSE` (Apache-2.0), `README.md`, `pyproject.toml`, `agent/__init__.py`, `agent/agent_app.py` (104 lines). We extracted it, ran `cp -R` to the repo root, and confirmed with `diff -r` that the copy is identical.

---

## What the app does (observed in source)

This is the minimal AgentApp template. All of its logic is in `agent/agent_app.py`:

1. **Entry point.** `app = AgentApp()` and `@app.main() def main(agent: AgentSession, context: Context)`. `pyproject.toml` registers it as `[tool.flwr.app.components] agentapp = "agent.agent_app:app"`.
2. **Prompt.** It reads only **`agent.prompt`**. It has no `[tool.flwr.app.config]` section and never reads `context.run_config`.
3. **History.** `_conversation()` rebuilds user and assistant turns from **`agent.events.get_trace()`**, which returns the events of every run in the current run series. It does not use `context.state`.
   - Events are grouped by `run_id`. Each run's user turn comes from its `message`/`role=user` event, and its assistant turn is the concatenated `response.output_text.delta` (and `refusal.delta`) text, kept only if a `response.completed` follows. Runs with `error`, `response.failed` or `response.incomplete` drop their assistant text.
   - The Flower runtime emits the `{"type":"message","role":"user","content": prompt}` event itself before `main` runs (`flwr/supercore/task_process/agent/run_agentapp.py`). That is why the app checks `current_prompt_seen` and appends `agent.prompt` only when the trace doesn't already contain it.
4. **Model call.** It creates `OpenAI(base_url=FLWR_RUNTIME_BASE_URL, api_key=FLWR_RUNTIME_API_KEY, max_retries=0)`; Flower injects both values at runtime. It makes **one** streamed `client.responses.create(model=MODEL, input=<conversation>, stream=True)` call. `MODEL = "openai/gpt-5.6-sol"` is hard-coded, and there are no tools and no tool loop.
5. **Streaming.** Every event is forwarded as `agent.events.emit(event.to_dict())`. On `error` or `response.failed` it raises `RuntimeError`. At the end it `print`s the joined output text, which goes to the run logs. It returns nothing, and nothing is written back to `context.state`.

| `pyproject.toml` key | Value |
|---|---|
| `version` | `0.4.0` |
| `dependencies` | `flwr>=1.38.0,<2.0` (**no `[agent]` extra**), `openai>=2.16.0,<3.0.0` |
| `requires-python` | `>=3.11,<4.0` |
| `[tool.flwr.app] flwr-version-target` | `1.38.0` |
| `[tool.flwr.app] fab-include` | `agent/**/*.py`, `LICENSE` |
| `[tool.flwr.app.components] agentapp` | `agent.agent_app:app` |
| `[tool.flwr.app.config]` | *(absent)* |

The `flwr` 1.39.0 `METADATA` shows that the `[agent]` extra only adds `browser-use[core]` and `trafilatura`. We haven't tested whether an app that uses connectors needs those packages on its own side.

---

## Grid usage

**None.** The app never touches `agent.grid` or `agent.connectors`. It is a single-agent chat loop. For the Grid tools API and the SuperLink/SuperNode tool split, see [collab-agent-recipe.md](collab-agent-recipe.md#grid-tools-api-read-from-flwr-1390-source).

### Facts from `flwr` 1.39.0 source that matter for master/sub-node

- **The master and the workers run the same FAB.** When a SuperNode receives a message for run X, it fetches that run's FAB (`run_info.fab_hash`) and creates an `AGENT_APP` task from it (`flwr/supernode/start_client_internal.py`). A preloaded (warm) AgentApp must have the same FAB hash, or the task raises "Task FAB does not match the preloaded AgentApp" (`run_agentapp.py::_prepare_task_app`). A master AgentApp therefore cannot run a *different* worker AgentApp on the SuperNodes. It has to be **one app that branches on its role**.
- **Each message a SuperNode receives starts one AgentApp task.** `pull_prompt` expects exactly one instruction. For a normal (`"query"`) message, `agent.prompt` is the compact JSON string `{"message_id","src_node_id","payload"}`. Only system messages arrive as the bare payload (`run_agentapp.py::message_to_prompt`).
- **No automatic reply on success.** A SuperNode inserts an error reply (`"AgentApp failed before replying."`) only when the AgentApp task **FAILED** or its token expired (`flwr/supernode/nodestate/in_memory_nodestate.py::finish_task` / `_on_task_tokens_expired`). We found no automatic reply when the task completes successfully.
- **`push_reply_message` works only once per task.** It clears `_instruction_metadata` after the first use (`flwr/supercore/task_process/agent/grid.py`).
- **`get_trace()` on a SuperNode** returns the events of every *local* AgentApp task in the same run series (`flwr/supernode/servicer/runtime/runtime_handlers.py::get_run_series_events`). On the SuperLink it returns only the primary task of each run in the series (`flwr/superlink/servicer/runtime/runtime_handlers.py`).
- SuperNodes also serve the `/v1/runtime` Responses endpoint (`flwr/supernode/main.py` includes `responses_router`), so a worker's model call should work the same way it does on the SuperLink.
- `SUPERLINK_NODE_ID = 1` (`flwr/common/constant.py`). The Grid tool set is chosen by `context.node_id == SUPERLINK_NODE_ID`.

---

## Our read (inference, not from the docs)

**Q4: would it work unmodified as a sub-node worker?** It would *run*, because the model call works on a SuperNode, but it would **never answer the master**. It produces text and completes successfully without calling `push_reply_message`. We infer that the master's `pull_messages` would keep returning that message ID in `pending_message_ids` until its timeout (300 s or less).

What would have to change, in one FAB:

1. **Branch on role.** Take the worker path when `context.node_id != 1`, or equivalently when `agent.grid.tools()` contains only `push_reply_message`. The master path lives in the same file (`get_nodes` → `push_messages` → `pull_messages`).
2. **Unwrap the prompt on workers.** Use `json.loads(agent.prompt)["payload"]` and send that to the model instead of the raw JSON wrapper. Keep `message_id` and `src_node_id` if they're useful for logging.
3. **Reply explicitly.** After the stream completes, call `agent.grid.call({"type": "function_call", "call_id": "<any id>", "name": "push_reply_message", "arguments": json.dumps({"payload": text})})` once. It doesn't have to be a model tool call. Check the returned `output` for `error`.
4. **Fix history on workers.** `_conversation()` groups turns by `run_id`. Every message the master sends in one run shares that `run_id`, so on a SuperNode the second message's user turn **overwrites** the first. Either group by `task_id`, which trace rows include, or skip history on workers and send only the payload.
5. *(Optional)* Make `MODEL` a `[tool.flwr.app.config]` key so the model can be changed without a code edit.

**Q5: differences from `hackathon-collab-agent-recipe/`**

| | `@flwrlabs/agent` 0.4.0 | `hackathon-collab-agent-recipe` 0.2.0 |
|---|---|---|
| Prompt | `agent.prompt` | run config `agent.input` |
| History | `agent.events.get_trace()`, grouped by `run_id` | `context.state.config_records["items"]` |
| Tools | none | `web_search`, `web_fetch` connectors, tool loop (`max-tool-turns`) |
| Model calls | one streamed call | tool-loop calls plus a final streamed call |
| Model | hard-coded constant | run config `agent.model` |
| Run config | none | `model`, `input`, `max-tool-turns` |
| `flwr` dependency | `flwr>=1.38.0` (no extra), target 1.38.0 | `flwr[agent]>=1.35.0`, target 1.35.0 |
| `agent.grid` | not used | not used |

Because it reads `agent.prompt`, this template is the closer starting point for a worker. The recipe would first need its `agent.input` read switched to `agent.prompt`.

---

## Running it

The live docs (`how-to-guides/run-on-supergrid.html`, `tutorials/write-your-first-agentapp.html`) require Flower 1.39.0:

```shell
uvx --from flwr==1.39.0 flwr new @flwrlabs/agent   # we used fetch-zip instead
cd agent
uv sync
uv run flwr build
uv run flwr login supergrid        # interactive
uv run flwr chat                   # then at the chat prompt:
#   /load .
#   Explain Flower Agent in one sentence.
```

Other chat commands: `/new`, `/federation @<account>/<federation-name>`, `/connector`, `/history`, `/quit`. Use `@<publisher>/<agent> <prompt>` to pick a published agent. Every message starts one run, and the runs share a run series until `/new`, so `get_trace()` history accumulates.

To debug a run: `uvx --from flwr==1.39.0 flwr log <run-id> supergrid --show`. To stop one: `... flwr stop <run-id> supergrid`.

**Why `flwr chat` and not `flwr run` (from source):** in 1.39.0, `flwr run` builds `StartRunRequest` **without `user_prompt`** (`flwr/cli/run/run.py`). The SuperLink rejects an AgentApp run with an empty prompt (`AGENTAPP_USER_PROMPT_REQUIRED` in `flwr/superlink/servicer/control/control_handlers.py`). Only `flwr chat` sets `user_prompt` (`flwr/cli/chat/chat_app.py::start_chat_run`). This contradicts the `uv run flwr run . supergrid --stream` recipe in [collab-agent-recipe.md](collab-agent-recipe.md#running-it-from-the-recipe-readme), which will probably fail against a 1.39.0 SuperLink. We haven't tested either one. The app has no run-config keys, so any `--run-config` override would also be rejected, because unknown keys fail `check_keys=True`.

### README discrepancies

- The README and the Hub page give only `uv sync` / `uv run flwr build` and no run command. The run steps (`flwr chat` → `/load .`) are only in the docs.
- The docs tutorial's `agent_app.py` excerpt passes `input=agent.prompt`, with no history. The shipped 0.4.0 code passes the history rebuilt from `get_trace()` instead. The README describes the shipped behaviour correctly.
- The dependency pin is `flwr>=1.38.0` / target 1.38.0, while the docs say 1.39.0. `uv sync` should resolve 1.39.x, but check with `uv run flwr --version`.

---

## References

- Flower Agent docs index: https://flower.ai/docs/agent/
- Run an AgentApp on SuperGrid: https://flower.ai/docs/agent/how-to-guides/run-on-supergrid.html
- Write your first AgentApp: https://flower.ai/docs/agent/tutorials/write-your-first-agentapp.html
- AgentApp runtime explainer: https://flower.ai/docs/agent/explanations/agentapp-runtime.html. It mentions `agent.grid` but doesn't document its tools or SuperNode execution.
- Use agents and federations: https://flower.ai/docs/agent/how-to-guides/use-agents-and-federations.html
- Sibling notes: [collab-agent-recipe.md](collab-agent-recipe.md). Brief: [hackathon-brief.md](hackathon-brief.md)

## Next steps

- [ ] `uv sync` and `flwr login supergrid`, then run one baseline `flwr chat` → `/load ./agent` to confirm the template works as-is.
- [ ] Confirm that `flwr run` fails for AgentApps on SuperGrid (`AGENTAPP_USER_PROMPT_REQUIRED`) before anyone relies on it.
- [ ] Prototype the single-FAB master/worker branch (steps 1–4 above) from a copy of this template, not in `agent/`.
- [ ] Ask mentors: (a) do the hackathon SuperNodes accept arbitrary run FABs (cold install), or only warm pools preloaded with one `fab_hash`? (b) how is a master run started on the SuperLink of a federation that has SuperNodes? Is it `flwr chat` with `/federation`?
