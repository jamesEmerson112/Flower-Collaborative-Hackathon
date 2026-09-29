# Flower AgentApp API Reference (flwr 1.39.0)

A working reference for writing AgentApps that collaborate over the Grid: one orchestrator on the SuperLink fans tasks out to workers on SuperNodes and collects the replies.
Read directly from the `flwr` **1.39.0** wheel source and the three example apps in this repo. Nothing here was run live.

**Provenance tags:** [src] = read in 1.39.0 source or example-app source (module cited). [docs] = https://flower.ai/docs/agent/ (fetched 2026-09-29). [inference] = our reading, not verified.
**Role tags:** [SuperLink] = orchestrator task (`context.node_id == 1`). [SuperNode] = worker task. [both] = same behaviour on both.

> **Version caveat.** The example apps pin `flwr-version-target = "1.38.0"` (`agent/`, `collaborative-agent/`) or `"1.35.0"` (`hackathon-collab-agent-recipe/`). Everything below is from **1.39.0**, which is also what the docs pin (`uvx --from flwr==1.39.0`). After `uv sync`, check `uv run flwr --version` before relying on a schema. One confirmed drift: `Context.locked()`, used by the recipe, does not exist in 1.39.0 (see [Context](#13-context)).

---

## 1. AgentApp authoring API

### 1.1 `AgentApp` and `@app.main()`

```python
from flwr.agentapp import AgentApp, AgentSession   # also exports AgentConnectors, AgentEvents, AgentGrid, LoadAgentAppError
from flwr.app import Context, ConfigRecord

app = AgentApp()

@app.main()
def main(agent: AgentSession, context: Context) -> None:
    ...
```

| Item | Contract | Prov. |
|---|---|---|
| `AgentApp()` | No constructor args. Holds one main fn. | [src] `flwr/agentapp/agent_app.py` |
| `@app.main()` | Must be called (`app.main()`, not `app.main`). Registering a second main raises `ValueError("AgentApp main function is already registered.")`. | [src] `flwr/agentapp/agent_app.py` |
| `main(agent, context)` | Type `AgentAppCallable = Callable[[AgentSession, Context], None]`. Called with keyword args `agent=`, `context=`. Return value ignored. | [src] `flwr/agentapp/base.py`, `supercore/task_process/agent/run_agentapp.py` |
| Success | `main` returns → events flushed → task `COMPLETED`. | [src] `run_agentapp.py` |
| Failure | Any exception → task `FAILED` with details `"AgentApp failed with exception: <msg>"`. On a SuperNode this triggers an automatic error reply (see [2.5](#25-delivery-semantics)). | [src] `run_agentapp.py` |
| Component ref | `pyproject.toml` → `[tool.flwr.app.components] agentapp = "<module>:<attr>"`; the attr must be an `AgentApp` instance, else `LoadAgentAppError`. | [src] `run_agentapp.py::_load_agentapp_component` |

**Task lifecycle around `main`** [both] [src] `run_agentapp.py::_AgentAppTaskLifecycle.run`:

1. `PullTaskInput` → `Context`, `Run`, `Fab`.
2. `pull_prompt()` pulls **exactly one** instruction message (else `RuntimeError("Expected exactly one initial AgentApp instruction.")`) and builds `agent.prompt`.
3. Runtime emits `{"type":"message","role":"user","content": prompt}` into the trace.
4. FAB installed (or preloaded FAB verified: hash, `fab_id`, `fab_version` must match, else `"Task FAB does not match the preloaded AgentApp."`).
5. `context.run_config` = pyproject defaults fused with run overrides.
6. `FLWR_RUNTIME_BASE_URL` / `FLWR_RUNTIME_API_KEY` (and `SSL_CERT_FILE` if a cert path is set) written to `os.environ`.
7. Cold path only: the app module is imported **now**. Preloaded apps were imported earlier, before step 6.
8. `main(agent=..., context=...)`; then `events.close()` flushes; `PushTaskOutput` sends status and the (possibly mutated) `Context` back.

Consequence: read `FLWR_RUNTIME_*` inside `main`, never at module import time. The preloaded-app docstring says so explicitly ("app imports must not require task-scoped Runtime values") [src].

### 1.2 `AgentSession`

All abstract in `flwr/agentapp/base.py`; runtime implementations in `supercore/task_process/agent/{session,grid}.py` [src].

| Member | Signature | Returns | Notes | Role |
|---|---|---|---|---|
| `agent.prompt` | property → `str` | Incoming instruction text | SuperLink: raw user text. SuperNode: compact JSON envelope (see [2.6](#26-agentprompt-shape)). [src] | [both] |
| `agent.connectors.tools(names)` | `(names: Sequence[str]) -> list[dict]` | Function-tool schemas, flattened across refs | Unknown ref raises `ValueError("Unsupported connector '<ref>'.")`. [src] `session.py`, `connector/registry.py` | [both] |
| `agent.connectors.call(tool_call)` | `(tool_call: dict) -> dict` | `{"type":"function_call_output","call_id",...,"output": <json str>}` | Needs `name`, `call_id`, `arguments` (str or dict). Emits trace events. Raises on failure (see [3.4](#34-failure-modes)). [src] | [both] |
| `agent.events.emit(event)` | `(event: dict) -> None` | — | `event["type"]` must be a non-empty str, else `ValueError`. Async, batched publish. [src] | [both] |
| `agent.events.get_trace()` | `() -> list[dict]` | Trace rows (see [4.2](#42-trace-row-shape)) | Scope differs by role (see [4.4](#44-get_trace-scope)). [src] | [both] |
| `agent.grid.tools()` | `() -> list[dict]` | Role-filtered Grid tool schemas | 3 tools on SuperLink, 1 on SuperNode. [src] `grid.py` | [both] |
| `agent.grid.call(tool_call)` | `(tool_call: dict) -> dict` | `{"type":"function_call_output","call_id",...,"output": <json str>}` | Tool not in role set → `ValueError("Unsupported Grid tool '<name>'.")`. Emits trace events. [src] `grid.py` | [both] |

`tool_call` is the Responses API `function_call` item. `item.to_dict()` from the OpenAI SDK works as-is; so does a hand-built dict:

```python
{"type": "function_call", "call_id": "any-unique-id", "name": "push_reply_message",
 "arguments": json.dumps({"payload": "..."})}   # arguments may also be a dict
```

### 1.3 `Context`

`flwr/app/message/context.py` is a plain `@dataclass` [src].

| Field | Type | SuperLink value | SuperNode value | Prov. |
|---|---|---|---|---|
| `run_id` | `int` | Current run | **Same `run_id` as the master's run** (worker tasks belong to the master's run, not a new run) | [src] `supernode/start_client_internal.py` |
| `node_id` | `int` | `1` (`SUPERLINK_NODE_ID`, `flwr/common/constant.py`) | The SuperNode's uint64 id | [src] `server/superlink/linkstate/linkstate.py`, `start_client_internal.py` |
| `node_config` | `dict[str, bool\|int\|float\|str]` | `{}` | Operator's `flower-supernode --node-config 'k="v" n=1'` | [src] `linkstate.py`, `supernode/cli/flower_supernode.py` |
| `run_config` | same type | pyproject `[tool.flwr.app.config]` flattened + run overrides | Same | [src] `run_agentapp.py` (`get_fused_config_from_dir`) |
| `state` | `RecordDict` | Series-scoped memory | Series-scoped memory, **local to that node** | [src] see below |
| `series_id` | `int` | Run series id | Same | [src] |
| `locked()` | **does not exist in 1.39.0** | — | — | [src] grep of the whole package: no `def locked` |

**`context.state` persistence** [src]:
- The context is stored **per run series** (`set_run_series_context(series_id, ...)`) and handed to each task at `PullTaskInput`; the task's mutated context comes back with `PushTaskOutput`, including on failure.
- SuperLink persists it **only from the run's primary task** (`superlink/servicer/runtime/runtime_handlers.py::push_task_output`).
- SuperNode persists it from **every** task (`supernode/servicer/runtime/runtime_handlers.py::push_task_output`). Several worker tasks for the same run on one node each get a snapshot and write it back: last writer wins [inference].
- The recipe's `with context.locked():` will raise `AttributeError` on 1.39.0. It may exist in an older release [inference]; drop it, since each task already owns its context copy.

**`ConfigRecord` in `state`** [src] `flwr/app/message/configrecord.py`, `recorddict.py`:
- Values: `int | float | str | bytes | bool`, or a **homogeneous** list of one of those. Mixed lists raise `TypeError`.
- `state.config_records` is a write-through view, so `setdefault`, `[]=` and `del` hit the underlying `RecordDict`. In-place mutation of a stored list persists.

```python
# Pattern from hackathon-collab-agent-recipe/agent/agent_app.py, minus context.locked()
items = context.state.config_records.setdefault("items", ConfigRecord({"json": []}))
items["json"].append(json.dumps({"type": "message", "role": "assistant", "content": text}))
```

---

## 2. Grid tools

### 2.1 Role split

`RuntimeAgentGrid.__init__` sets `is_superlink = node_id == SUPERLINK_NODE_ID` (`== 1`) [src] `supercore/task_process/agent/grid.py`.

| Tool | [SuperLink] | [SuperNode] |
|---|---|---|
| `get_nodes` | yes | no |
| `push_messages` | yes | no |
| `pull_messages` | yes | no |
| `push_reply_message` | no | yes |

The SuperNode runtime also rejects `GetNodes` at the RPC layer (`RUNTIME_ENDPOINT_UNAVAILABLE`, 3005) [src] `supernode/servicer/runtime/runtime_handlers.py`.

All four schemas are `{"type":"function", "name", "description", "parameters", "output_schema", "strict": true}` with `additionalProperties: false`. Node ids are **uint64 as decimal strings** everywhere [src]. The non-standard `output_schema` key is passed straight to the provider; the Flower-hosted provider evidently accepts it because `collaborative-agent` ships this way. A strict third-party endpoint might reject it; strip it if so [inference].

### 2.2 `get_nodes` [SuperLink]

| Input | Type | Notes |
|---|---|---|
| `sample_size` | `integer \| null`, `minimum: 1`, **required** | `null` returns all nodes. `< 1` raises `ValueError("Grid sample size must be positive.")`. A sample is `random.sample(nodes, min(k, n))`. |

| Output | Type | Notes |
|---|---|---|
| `nodes[]` | `{id: str, name: str\|null, location: str\|null}` | `name`/`location` come from `flwr supernode register --name/--location` [src] `cli/supernode/register.py` |
| `num_available` | `int ≥ 0` | Total before sampling |

"Available" means `ONLINE` nodes filtered to the run's federation [src] `server/superlink/linkstate/in_memory_linkstate.py::get_nodes`.

### 2.3 `push_messages` [SuperLink]

| Input | Type | Notes |
|---|---|---|
| `messages[]` (`minItems: 1`) | `{dst_node_id: str, payload: str, reply_to_message_id: str\|null}`, all required | Use `null` for a new task. Payload is an opaque string, so JSON-encode structured tasks yourself. |

| Output | Type | Notes |
|---|---|---|
| `results[]` | `{message_id: str\|null, error: str\|null}` | One per input, **same order**. Rejected: `message_id: null, error: "Message was not accepted."` |

Messages go out as `message_type="query"`, `group_id=""`, and content `RecordDict({"agent": ConfigRecord({"text": payload})})`. New messages use the default TTL of **12 h** (`DEFAULT_TTL = 43200`, `flwr/app/constants.py`); replies get 6 h [src] `grid.py`. Sending to `dst_node_id="1"` (the SuperLink itself) is schema-legal, but we don't know what it does [inference]. Avoid it.

### 2.4 `pull_messages` [SuperLink] and `push_reply_message` [SuperNode]

**`pull_messages`**

| Input | Type | Notes |
|---|---|---|
| `message_ids[]` | `str`, `minItems: 1` | Ids returned by `push_messages` |
| `timeout` | `number`, `0 ≤ t ≤ 300` | Seconds. `0` checks once. Out of range raises `ValueError`. Polls every 0.25 s and returns early once all ids are answered. |

| Output | Type | Notes |
|---|---|---|
| `messages[]` | `{message_id, reply_to_message_id, src_node_id, payload: str\|null, error: str\|null}` | Exactly one of `payload`/`error` is non-null |
| `pending_message_ids[]` | `str` (sorted) | No reply before the timeout |

**`push_reply_message`**

| Input | Type | Notes |
|---|---|---|
| `payload` | `str` (min length 1) | Reply text |

| Output | Type | Notes |
|---|---|---|
| `message_id` | `str\|null` | Accepted reply id |
| `error` | `str\|null` | For example `"No instruction message to reply to. You may have already replied to it once."` |

The runtime fills in `dst_node_id` from the instruction's `src_node_id` and `reply_to_message_id` from its `message_id`, then sets `ttl = 21600` (6 h) [src] `grid.py::_push_reply_message`.

### 2.5 Delivery semantics

| Rule | Detail | Prov. |
|---|---|---|
| Reply once | `push_reply_message` clears `_instruction_metadata` after the first call; a second call returns the error above and sends nothing. | [src] `grid.py` |
| Reply TTL 6 h | Hard-coded `21600`, so a reply never outlives its 12 h instruction (the SuperLink rejects that). | [src] `grid.py` comment |
| Pull is destructive | The SuperLink `PullMessages` handler **deletes the instruction and its reply** once returned. A reply comes back **once**; pulling the same id again leaves it in `pending_message_ids` until the timeout. Accumulate results across pull calls. | [src] `superlink/servicer/runtime/runtime_handlers.py::pull_messages`, `in_memory_linkstate.py::delete_messages` |
| Pull timeout | 0–300 s per call. For longer waits, loop over calls. | [src] `grid.py` |
| No auto reply on success | A worker that returns without calling `push_reply_message` sends nothing. The master only sees the id stay pending. | [src] (no such code path found) |
| Auto error reply on FAILED only | When an `AGENT_APP` task finishes `FAILED` (or its token expires), the SuperNode stores `Error(UNKNOWN, "AgentApp failed before replying.")` as a reply. The master's pull then returns `payload: null, error: "AgentApp failed before replying."` without waiting for the timeout. | [src] `supernode/nodestate/in_memory_nodestate.py::finish_task`, `_on_task_tokens_expired` |
| Error-reply blast radius | That error reply goes to **every retrieved, still-unanswered message of the same run on that node**, not just the failed task's own message. One crashing worker task can error out a sibling task that is still working on the same node. | [src] `in_memory_nodestate.py::_store_error_replies` |
| One task per message | Each incoming message creates one `AGENT_APP` task (`create_task(..., run_id=message.metadata.run_id, fab_hash=run_info.fab_hash)`). Each task pulls one message (`limit=1`). N messages to one node means N concurrent-or-queued worker tasks. | [src] `supernode/start_client_internal.py::_pull_and_store_message`, `supernode/servicer/runtime/runtime_handlers.py::pull_messages` |
| Same FAB everywhere | The SuperNode fetches the **run's** FAB (`get_fab(run_info.fab_hash)`). A preloaded (warm) app must match hash, id and version. Master and workers are therefore one app that branches on role. | [src] `start_client_internal.py`, `run_agentapp.py::_prepare_task_app` |
| Worker concurrency | How many worker tasks one SuperNode runs in parallel depends on the deployment. | [inference] |

### 2.6 `agent.prompt` shape

`run_agentapp.py::message_to_prompt` [src]:

| Where | Incoming message type | `agent.prompt` |
|---|---|---|
| [SuperLink] | `"system"` (created by `create_user_prompt_message` from the user's chat input, `server/superlink/linkstate/utils.py`) | The raw user text |
| [SuperNode] | `"query"` (from `push_messages`) | Compact JSON: `{"message_id":"<id>","src_node_id":"1","payload":"<text>"}` |

```python
def unwrap_prompt(prompt: str) -> tuple[dict | None, str]:
    """Return (envelope, payload). System messages arrive bare."""
    try:
        env = json.loads(prompt)
        if isinstance(env, dict) and "src_node_id" in env and "payload" in env:
            return env, env["payload"]
    except ValueError:
        pass
    return None, prompt
```

Content keys on the wire are record `"agent"` and field `"text"` (`AGENT_MESSAGE_CONTENT_RECORD_KEY`, `AGENT_MESSAGE_TEXT_KEY`, `flwr/supercore/constant.py`) [src].

### 2.7 `grid.call` error behaviour

| Case | What happens | Prov. |
|---|---|---|
| Name not in role set | `ValueError` raised **before** any event is emitted | [src] |
| Bad args (`timeout > 300`, `sample_size < 1`, non-numeric `dst_node_id`) | `function_call` event emitted, then the exception propagates. **No `function_call_output` is emitted or returned.** | [src] `grid.py::call` |
| Rejected push | Normal return with `error` set in the result row | [src] |

A model-driven loop must catch the exception and synthesise a `function_call_output`. Otherwise the model's `function_call` is left without an output and the task fails. `collaborative-agent` does not catch it [src] `collaborative-agent/agent/agent_app.py`.

---

## 3. Connectors

### 3.1 API

```python
tools = agent.connectors.tools(["web_search", "web_fetch"])   # refs, not tool names
out   = agent.connectors.call(function_call_item)               # -> function_call_output item
```

`tools(names)` = `[tool for name in names for tool in get_connector_tools(name)]` [src] `supercore/task_process/agent/session.py`. `call()` lower-cases and strips the tool name, resolves tool name → connector ref, creates a child **CONNECTOR task** (a separate process or container) and waits up to **300 s** for its reply [src] `session.py::AgentRuntime`.

### 3.2 Registry (1.39.0)

`CONNECTORS = (web_search, web_fetch, browser_use, filesystem, *OAuth: attio, github, notion, slack)`, plus the pseudo-ref `start_automation` [src] `supercore/task_process/connector/registry.py`, `registry_generated.py`.

| Ref | Model-facing tool(s) and args | Gate / requirement | Prov. |
|---|---|---|---|
| `web_search` | `web_search(query: str)` | One of `FLWR_WEB_SEARCH_ENDPOINT` (proxy), `BRAVE_API_KEY`, `TAVILY_API_KEY`, `EXA_API_KEY` in the **connector** process env, checked in that order; else `RuntimeError`. Output `{"results":[{title,url,snippet}...]}`. | [src] `connector/web_search/` |
| `web_fetch` | `web_fetch(url: str)` | Optional `FLWR_WEB_FETCH_ENDPOINT` (proxy). The direct path needs `trafilatura` (the `flwr[agent]` extra) in the connector runtime. Blocks private/local hosts, 1 MiB body cap, 30 s timeout, ≤10 redirects. Output `{object:"web_fetch.response", status, url, final_url, status_code, content_type, content}`. | [src] `connector/web_fetch.py` |
| `browser_use` | `browser_use(task: str)` | Needs `browser-use` (the `flwr[agent]` extra). Default model `openai/gpt-5.5`. | [src] `connector/browser_use/` |
| `filesystem` | `filesystem_list_directory(path)`, `filesystem_read_file(path)` (absolute paths) | **`FLWR_FILESYSTEM_ALLOWED_DIRS`** = `os.pathsep`-separated (`:` on POSIX) list of existing absolute dirs. Evaluated **at import time**: unset or invalid gives **zero tools, silently**. Not on Windows. Read cap 1 MiB, UTF-8 only; list cap 1000 entries. Errors come back as output `{"error":{"code":...}}` (`access_denied`, `not_found`, `file_too_large`, `invalid_config`, ...), not as exceptions. | [src] `connector/filesystem/filesystem.py` |
| `attio` | `attio_identify`, `attio_get_workspace_member`, `attio_search_records`, `attio_list_meetings`, `attio_list_call_recordings`, `attio_get_call_transcript` | OAuth, `requires_credentials=True` | [src] `connector/attio/actions.py` |
| `github` | `github_search_code`, `github_get_file_contents(owner, repo, path)` | OAuth | [src] `connector/github/actions.py` |
| `notion` | `notion_search`, `notion_get_page`, `notion_get_page_property`, `notion_get_database`, `notion_get_block`, `notion_get_block_children`, `notion_list_users`, `notion_get_user`, `notion_get_self` | OAuth | [src] `connector/notion/actions.py` |
| `slack` | `slack_search_messages`, `slack_list_conversations`, `slack_get_conversation_history`, `slack_get_conversation_replies` | OAuth | [src] `connector/slack/actions.py` |
| `start_automation` | `start_automation(input: str, start_at: str, fixed_interval?: int ≥1 s, max_runs?: int ≥1)` | Handled by the AgentApp runtime, not a connector task. **SuperLink only.** | [src] `connector/automation.py`, `supernode/servicer/runtime/runtime_handlers.py` |

Tool names for OAuth connectors are `<ref>_<action>` [src] `connector/definition.py`. The docs call all account connectors read-only [docs] `explanations/use-connectors.html`.

### 3.3 Env gates and role limits

- Env vars are read in whichever process runs the code. `tools()` schemas are built in the **AgentApp** process; execution happens in the **connector** process. For `filesystem`, both need `FLWR_FILESYSTEM_ALLOWED_DIRS` [src]. On SuperGrid and hackathon SuperNodes these are operator-controlled, not app-controlled [inference].
- **OAuth connectors must be attached to the run** (`StartRunRequest.connector_refs`, set in `flwr chat` via `/connector`, which is only allowed in the `personal` federation). Otherwise `CreateTask` fails with `RUNTIME_CONNECTOR_NOT_AVAILABLE` (3010) [src] `supercore/servicer/runtime/runtime_handlers.py`, `cli/chat/chat_app.py`.
- **[SuperNode]:** OAuth connectors are unusable (`GetConnector` → `RUNTIME_CONNECTOR_CREDENTIALS_NOT_AVAILABLE`, 3001), and so is `start_automation` (`RUNTIME_AUTOMATION_CREATION_NOT_ALLOWED`, 3003). The built-in connectors go through the SuperNode's own `CreateTask` [src] `supernode/servicer/runtime/runtime_handlers.py`.

### 3.4 Failure modes

| Call | Failure | Behaviour | Prov. |
|---|---|---|---|
| `tools(["nope"])` | Unknown ref | `ValueError("Unsupported connector 'nope'.")`. The whole call fails, even if other refs are valid. | [src] `registry.py::get_connector_tools` |
| `tools(["filesystem"])` | Env unset/invalid | Returns `[]`, **no error** | [src] |
| `call(...)` | Connector raised (e.g. no search key) | Emits `function_call_output` with `{"error":{"code":"connector_error","message":"Connector execution failed."}}`, then **raises** `RuntimeError("Connector '<name>' failed: <msg>")` | [src] `session.py::call_connector_with_events`, `connector/task.py` |
| `call(...)` | No reply within 300 s | Raises **`TimeoutError`** (an `OSError` subclass, not a `RuntimeError`). The recipe's `except (RuntimeError, ValueError)` does not catch it. | [src] `session.py::_send_and_receive` |
| `call(...)` | Unknown tool name | The name is used as the ref, so child task creation fails with `CONNECTOR_NOT_FOUND` (39) and an exception propagates. The `function_call` event has already been emitted, but no output is. | [src] `supercore/servicer/runtime/runtime_handlers.py::_validate_create_task_request`, `session.py` |

---

## 4. Events and trace

### 4.1 `emit` contract [both]

- `emit(event)` requires `event["type"]` to be a non-empty `str`. It stores `TaskEvent(event=type, data=json.dumps(event))` [src] `session.py::RuntimeAgentEvents`.
- Publishing is **async**: a bounded queue (256, blocking `put`) feeds a daemon thread that flushes batches of ≤16 every ~50 ms. A publish failure is re-raised on the next `emit` as `RuntimeError("Failed to publish AgentApp events.")`. `emit` after close raises [src].
- Pending events are flushed after `main` returns (and with a 1 s cap in finalisation). Events you just emitted may not be visible yet to your own `get_trace()` call [src]. This is why the examples check `current_prompt_seen`.
- The server stamps `run_id` and `task_id` on every event [src] `supercore/servicer/runtime/runtime_handlers.py::push_task_events`.

### 4.2 Trace row shape

`get_trace()` returns `list[dict]` [src] `session.py::get_trace`, `proto/task_pb2.pyi`:

| Key | Type | Meaning |
|---|---|---|
| `id` | `int` | Event id (monotonic cursor) |
| `timestamp` | `str` | Server timestamp |
| `run_id` | `int` | Run that produced it |
| `task_id` | `int` | Task that produced it. Distinguishes concurrent worker tasks within one run. |
| `event` | `str` | Equals `data["type"]` |
| `data` | `dict` | The emitted event object, JSON-decoded |

### 4.3 Events the runtime emits itself

| Emitter | Event `data` | When | Prov. |
|---|---|---|---|
| Task bootstrap | `{"type":"message","role":"user","content": <agent.prompt>}` | Before `main` runs. On a SuperNode, `content` is the JSON envelope. | [src] `run_agentapp.py` |
| `agent.grid.call` | `{"type":"function_call","call_id","name","arguments": <compact json>}` then `{"type":"function_call_output","call_id","output": <compact json>}` | Around every Grid tool call (the output only if no exception) | [src] `grid.py` |
| `agent.connectors.call` | same pair; the output is the generic `connector_error` object on failure | Around every connector call | [src] `session.py` |
| `start_automation` | same pair; the error code is `automation_error` | | [src] |
| Model calls | **Nothing.** Each `responses.create` runs as a child MODEL task whose stream events are stored under that task, not your trace. | Forward them with `emit(event.to_dict())` | [src] `supercore/routers/runtime/responses.py` |

### 4.4 `get_trace` scope

| Role | Returns | Prov. |
|---|---|---|
| [SuperLink] | Events of the **primary task of every run in the series**, which means the master's own events across chat turns | [src] `superlink/servicer/runtime/runtime_handlers.py::get_run_series_events` |
| [SuperNode] | Events of **all `AGENT_APP` tasks stored on this node** whose run shares the series: every worker task this node has run for this conversation | [src] `supernode/servicer/runtime/runtime_handlers.py::get_run_series_events` |

- Workers never see the master's transcript, and the master never sees workers' events; only the reply payloads cross. Events are stored locally [src]; that no forwarding path exists is [inference].
- The `agent/` template groups history by `run_id`. On a SuperNode, all messages of one master run share a `run_id`, so group by `task_id` there [src + inference].

### 4.5 What `flwr chat` (CLI) needs from the event stream [SuperLink]

`cli/chat/chat_app.py::_run_prompt_sync`, `cli/constant.py` [src]:

| Event type | CLI behaviour |
|---|---|
| `response.output_text.delta` | Rendered as the answer (`data["delta"]`) |
| `response.reasoning_summary_text.delta` | Rendered in a collapsible "Reasoning" block |
| `response.tool_call.started` / `.completed` with `connector_ref == "web_search"` | Rendered as a "Web search" block. **Nothing in 1.39.0 emits these.** |
| `error`, `response.failed` | Chat shows the error |
| `response.completed`, `response.incomplete` | Terminal. **Required**: without one, the CLI reports "Chat run ended before the agent response completed." |
| `function_call` / `function_call_output` | **Not rendered by the CLI.** They are in the trace; the web UI may show them [inference]. |

For text you produce outside an SDK stream, emit the docs pattern [docs] `how-to-guides/use-openai-sdk.html`:

```python
agent.events.emit({"type": "response.output_text.delta", "delta": text})
agent.events.emit({"type": "response.completed"})
```

---

## 5. Model access

### 5.1 Env injection [both]

| Var | Value | Prov. |
|---|---|---|
| `FLWR_RUNTIME_BASE_URL` | `{http\|https}://{runtime_api_address}/v1/runtime` | [src] `run_agentapp.py::_set_runtime_environment` |
| `FLWR_RUNTIME_API_KEY` | The task's own token, scoped to this task and not a provider key | [src] |
| `SSL_CERT_FILE` | Set if the runtime has a root cert path | [src] |

Both SuperLink and SuperNode mount the `/v1/runtime/responses` router, so workers call the model the same way as the master [src] `superlink/main.py`, `supernode/main.py`. The endpoint "is scoped to the running AgentApp. It is not a public API" [docs].

### 5.2 Client pattern

```python
client = OpenAI(
    base_url=os.environ["FLWR_RUNTIME_BASE_URL"],
    api_key=os.environ["FLWR_RUNTIME_API_KEY"],
    max_retries=0,   # each request creates a model task; SDK retries would duplicate it [docs]
)

# Streaming + tools + reasoning (collaborative-agent/agent/utils.py)
stream = client.responses.create(
    model="openai/gpt-5.6-terra",
    reasoning={"effort": "medium"},
    instructions=INSTRUCTIONS,
    input=input_items,          # str or list of Responses input items
    tools=tools,                # grid + connector schemas
    stream=True,
)
for event in stream:
    if event.type in {"response.output_text.delta", "response.reasoning_summary_text.delta"}:
        agent.events.emit(event.to_dict())
    elif event.type == "response.completed":
        response = event.response          # .output holds function_call items
    elif event.type in {"error", "response.failed"}:
        raise RuntimeError(f"Model response failed: {event}")
```

The non-streamed tool loop is in `hackathon-collab-agent-recipe/agent/agent_app.py`: `response.output` → `item.to_dict()` → filter `type == "function_call"` → call → extend `input` with both the outputs and the call items [src].

### 5.3 Accepted request fields and limits

| Rule | Detail | Prov. |
|---|---|---|
| Allowed fields | `model, input, stream, tools, tool_choice, reasoning, previous_response_id, instructions, max_output_tokens, metadata, text` | [src] `supercore/routers/runtime/responses.py`, [docs] `agentapp-runtime.html` |
| Anything else | **HTTP 400 `unsupported_parameter`**, e.g. `temperature`, `top_p`, `parallel_tool_calls`, `store`, `include`, `truncation`, `user` | [src] |
| Validation | `model`: non-empty str. `input`: str or list of objects. | [src] `supercore/json_message/model_message.py` |
| `previous_response_id` | Accepted by the runtime, but "The default model provider at `api.flower.ai` does not currently support continuing with `previous_response_id`." Rebuild `input` from history instead. | [docs] `agentapp-runtime.html` |
| Per-call deadline | 300 s → 504 `model_response_timeout` | [src] `responses.py` |
| Model task launch | 300 s default (operator env `FLWR_MODEL_TASK_LAUNCH_TIMEOUT`) → 504 `model_task_launch_timeout` | [src] |
| Auth | Exactly one `Authorization: Bearer <task token>`, and only for `AGENT_APP` tasks → else 401 `invalid_api_key` | [src] |

### 5.4 Model ids seen

| Id | Where | Prov. |
|---|---|---|
| `openai/gpt-5.6-sol` | `agent/agent/agent_app.py`, recipe `agent.model` default, docs examples | [src] [docs] |
| `openai/gpt-5.6-terra` | `collaborative-agent/agent/utils.py` | [src] |
| `openai/gpt-5.5` | Default model of the `browser_use` connector | [src] `connector/browser_use/browser_use.py` |
| "Endeavor" | Bonus model in the brief; id unknown, ask mentors | [inference] |

Ids use the OpenRouter `vendor/model` format (per the brief).

### 5.5 Operator-side provider env (SuperLink / SuperNode host, not the app)

| Var | Meaning | Prov. |
|---|---|---|
| `FLWR_MODEL_API_KEY` | Provider key. With no endpoint set, the default is `https://api.flower.ai/v1/responses` and the key is required. | [src] `supercore/task_process/model/provider.py`, brief |
| `FLWR_MODEL_API_ENDPOINT` | Any Open-Responses-compatible URL; **must end in `/responses`**, e.g. Nebius `https://api.tokenfactory.tf-ca1.nebius.com/v1/responses` | [src], brief |
| `FLWR_MODEL_API_TIMEOUT` | Provider HTTP timeout, default 180 s, min 1 s | [src] |

The model task runs on the node that serves the request, so a worker's model calls use **that SuperNode's** provider config [src + inference].

---

## 6. Packaging

### 6.1 `pyproject.toml`

| Key | Req. | Meaning | Prov. |
|---|---|---|---|
| `[project] name`, `version` | yes | `fab_id = "<publisher>/<name>"`, `fab_version = version`. App id is `@<publisher>/<name>`. | [src] `flwr/common/config.py` |
| `[project] description`, `license` | warn | `description` shows as app description. `license = { file = "LICENSE" }` is required by fab-format 1. | [src] |
| `[project] dependencies` | fab v1 | Must list `flwr` with a `>=` lower bound. Use `flwr[agent]` only if the app's runtime needs `browser-use`/`trafilatura`. | [src] `supercore/fab_format_version.py`, dist METADATA |
| `[tool.flwr.app] publisher` | yes | Your Flower account name | [src] |
| `display-name` | no | UI name | [src] `get_app_presentation_metadata` |
| `color` | no | UI color token, e.g. `"emerald"` | [src], `collaborative-agent/pyproject.toml` |
| `fab-format-version` | no (default 0) | `0` = lenient. `1` = strict: `flwr-version-target` required, ≥ the `flwr>=` bound and inside the spec; root license file must exist and be included in the FAB. | [src] `fab_format_version.py` |
| `flwr-version-target` | fab v1 | e.g. `"1.39.0"`. Ignored under v0. | [src] |
| `fab-include` / `fab-exclude` | no | Non-empty lists of gitignore-style patterns. Built-in includes: `**/*.py *.toml *.md *.yaml *.yml *.json *.jsonl /LICENSE`. | [src] `flwr/common/constant.py` |
| `[tool.flwr.app.components] agentapp` | yes | `"pkg.module:app"`. Its presence makes this an AgentApp bundle, so no `serverapp`/`clientapp` is needed. | [src] `validate_fields_in_config` |
| `[tool.flwr.app.config.*]` | no | Run-config defaults (below) | [src] |

### 6.2 Run config

```toml
[tool.flwr.app.config.agent]      # nested tables flatten with "."
model = "openai/gpt-5.6-sol"      # → context.run_config["agent.model"]
max-tool-turns = 2                # → context.run_config["agent.max-tool-turns"]
```

- Values: `bool | int | float | str`, or nested tables of those. **No lists or arrays**: `ValueError` at validation [src] `common/config.py::_validate_run_config`, `flatten_dict`.
- Overrides are fused with `fuse_dicts(check_keys=True)`. An **unknown key** fails `StartRun` with `INVALID_RUN_CONFIG` (15). Override **types are not checked**, so validate in code as the recipe does [src] `superlink/servicer/control/control_handlers.py::start_run`.
- **There is no override path for AgentApps in 1.39.0.** `flwr chat` sends no `override_config` (`cli/chat/chat_app.py::start_chat_run`), and `flwr run -c` can't start an AgentApp (see [7.3](#73-why-flwr-run-fails-for-agentapps)). In practice run config is **the pyproject defaults**; edit and `/load` again [src].

### 6.3 `flwr build`

- Validates `pyproject.toml`, applies `.gitignore` plus include/exclude rules, and rewrites `pyproject.toml` without `[tool.flwr.federations]` [src] `cli/build.py`.
- Writes `<publisher>.<name>.<version-with-dashes>.<sha256[:8]>.fab` to the CWD and prints `🎊 Successfully built <file>` [src].
- The FAB is a zip with a CONTENT manifest (`path,sha256,size_bits`). Max **10 MB** (`FAB_MAX_SIZE`); the SuperLink refuses larger ones [src].
- The directory name must be a valid project name (`validate_project_name`) [src].

---

## 7. CLI

### 7.1 Commands

| Command | Use | Prov. |
|---|---|---|
| `flwr new @pub/app[==x.y.z]` | Download a Hub app into `./<app>` via the Hub API (§8). With no arg it lists the recommended apps. Its success hint `flwr run <app> --stream` is **wrong for AgentApps**. | [src] `cli/new/new.py` |
| `flwr build [--app PATH]` | Build the FAB (§6.3) | [src] |
| `flwr login [SUPERLINK]` | Interactive login (`supergrid` → `api.flower.ai`) | [src] `cli/login/login.py`, [docs] |
| `flwr chat` | Interactive AgentApp runs. Connection from `FLWR_CHAT_SUPERLINK` (default `supergrid`). | [src] `cli/chat/chat.py` |
| `flwr list [SUPERLINK] [--run-id N] [--limit N] [--format json]` | Runs / one run's details (alias `ls`) | [src] `cli/ls.py` |
| `flwr log RUN_ID [SUPERLINK] [--stream\|--show]` | Logs (streams by default) | [src] `cli/log.py` |
| `flwr stop RUN_ID [SUPERLINK]` | Stop a run | [src] `cli/stop.py` |
| `flwr federation list [SUPERLINK] [--federation @acct/name] [--verbose]` | Federations; with `--federation`, shows members, nodes and runs | [src] `cli/federation/ls.py` |
| `flwr supernode register --name --location` | Sets the `name`/`location` that `get_nodes` returns | [src] `cli/supernode/register.py` |

### 7.2 `flwr chat` input

| Input | Effect | Prov. |
|---|---|---|
| `/help` | List commands | [src] `cli/constant.py` |
| `/load <path>` | Build and select a local AgentApp (must define `components.agentapp`). **The FAB is rebuilt before every prompt**, so code edits are picked up without another `/load`. A changed hash starts a new series. | [src] `cli/chat/chat_local_agent.py`, `chat_app.py::_run_prompt` |
| `/federation [@acct/name]` | Switch federation. Resets agent to `@flwrlabs/flwr-agent`, clears connectors and series. | [src] |
| `/connector [name\|clear]` | Attach an OAuth connector to runs. **Only in the `personal` federation.** | [src] |
| `/new` | New conversation (new run series, so `get_trace` and `state` start fresh) | [src] |
| `/history` | Browse or continue earlier series in this federation | [src] |
| `/quit` (or Ctrl-C) | Exit. Ctrl-C during a run stops it. | [src] |
| `@publisher/agent <prompt>` | Select a published agent in this federation, then send the prompt | [src] `_extract_agent_selection`, [docs] |
| any other text | `StartRun(user_prompt=text, app_spec/fab, series_id, connector_refs)`, then stream events | [src] `start_chat_run` |

Each chat message is **one run**. Runs share a series until `/new` [src].

### 7.3 Why `flwr run` fails for AgentApps

`flwr run` builds `StartRunRequest(fab, override_config, federation, override_federation_config, app_spec)` with **no `user_prompt`** [src] `cli/run/run.py`. The SuperLink then raises:

```text
AGENTAPP_USER_PROMPT_REQUIRED (44): "AgentApp run requested without a user prompt."
```

The check is `if primary_task_type == TaskType.AGENT_APP and not user_prompt` [src] `superlink/servicer/control/control_handlers.py::start_run`. Use `flwr chat` → `/load .`, as the docs do [docs] `run-on-supergrid.html`. We assume the SuperGrid deployment runs the same check [inference].

---

## 8. Flower Hub HTTP API

Base URL `FLWR_SUPERGRID_API_URL`, default `https://api.flower.ai/v1` [src] `supercore/constant.py`.

| Endpoint | Request | Response | Prov. |
|---|---|---|---|
| `POST /hub/fetch-zip` | JSON `{"app_id": "@pub/app", "app_version": "x.y.z" \| null, "flwr_version": "1.39.0"}` | `200 {"zip_url": "<presigned>", "verifications"?: [...], "note"?: str}`; we also observed `resolved_by_compatibility`. `404 {"detail": {"available_app_versions": [...]}}` or plain detail. | [src] `supercore/utils.py::request_download_link`; observed in `docs/collab-agent-recipe.md` |
| `GET /hub/apps?tag=recommended` | `accept: application/json` | `{"apps": [{"app_id": "@pub/app", ...}]}` (the CLI reads only `app_id`) | [src] `cli/new/new.py::fetch_recommended_apps` |

```bash
curl -s -X POST https://api.flower.ai/v1/hub/fetch-zip \
  -H 'Content-Type: application/json' \
  -d '{"app_id":"@flwrlabs/collaborative-agent","app_version":null,"flwr_version":"1.39.0"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["zip_url"])'
```

---

## 9. Error codes

The ones relevant to AgentApp development, from `supercore/error/catalog.py` (numbers from `supercore/error/base.py`) [src].

| Code | Name | gRPC / HTTP | Typical cause |
|---|---|---|---|
| 12 | `FEDERATION_NOT_SPECIFIED` | FAILED_PRECONDITION / 412 | No federation on run start |
| 2 | `FEDERATION_NOT_FOUND_OR_NO_PERMISSION` | NOT_FOUND / 404 | Wrong `/federation` or not a member |
| 14 | `FAILED_TO_CREATE_RUN` | INTERNAL / 500 | Run creation failed |
| 15 | `INVALID_RUN_CONFIG` | FAILED_PRECONDITION / 412 | Unknown override key, bad FAB config |
| 16 / 17 | `RUN_ID_NOT_FOUND` / `RUN_SERIES_ID_NOT_FOUND` | NOT_FOUND / 404 | Stale id in `log`/`stop`/`/history` |
| 18 | `RUN_ALREADY_FINISHED` | FAILED_PRECONDITION / 412 | `stop` on a finished run |
| 33 | `INVALID_APP_SPEC` | FAILED_PRECONDITION / 412 | Bad `@pub/app` or id mismatch |
| 34 / 35 | `FAB_DOWNLOAD_LINK_FAILURE` / `FAB_DOWNLOAD_FAILURE` | FAILED_PRECONDITION / 412 | Hub/stored app fetch failed |
| 36 | `ACCOUNT_AUTHENTICATION_FAILED` | UNAUTHENTICATED / 401 | Re-run `flwr login` |
| 38 / 39 / 40 | `INVALID_CONNECTOR_REQUEST` / `CONNECTOR_NOT_FOUND` / `CONNECTOR_FAILURE` | 400 / 404 / 500 | OAuth connector setup |
| 42 | `INVALID_AUTOMATION_REQUEST` | INVALID_ARGUMENT / 400 | Bad `start_automation` args |
| **44** | **`AGENTAPP_USER_PROMPT_REQUIRED`** | INVALID_ARGUMENT / 400 | `flwr run` on an AgentApp (§7.3) |
| 1001 | `RUNTIME_VERSION_INCOMPATIBLE` | FAILED_PRECONDITION / 412 | CLI/runtime version mismatch |
| 1008 | `RUNTIME_AUTHENTICATION_FAILED` | UNAUTHENTICATED / 401 | Task token invalid or expired |
| 3001 | `RUNTIME_CONNECTOR_CREDENTIALS_NOT_AVAILABLE` | PERMISSION_DENIED / 403 | OAuth connector on a SuperNode |
| 3002 | `RUNTIME_TASK_START_FAILED` | FAILED_PRECONDITION / 412 | Task activation failed |
| 3003 | `RUNTIME_AUTOMATION_CREATION_NOT_ALLOWED` | PERMISSION_DENIED / 403 | `start_automation` on a SuperNode |
| 3005 | `RUNTIME_ENDPOINT_UNAVAILABLE` | PERMISSION_DENIED / 403 | e.g. `GetNodes` from a SuperNode task |
| 3006 / 3007 / 3008 | `RUNTIME_TASK_CREATION_FAILED` / `_NOT_ALLOWED` / `RUNTIME_INVALID_TASK_CREATION_REQUEST` | 500 / 403 / 412 | Child task (model/connector) creation. An unknown connector tool name gives 39 `CONNECTOR_NOT_FOUND`. |
| 3009 | `RUNTIME_INVALID_TASK_MESSAGE` | FAILED_PRECONDITION / 412 | Task message mismatch |
| 3010 | `RUNTIME_CONNECTOR_NOT_AVAILABLE` | PERMISSION_DENIED / 403 | OAuth connector not attached to the run |
| 3011 / 3012 | `RUNTIME_RUN_SERIES_CONTEXT_NOT_FOUND` / `RUNTIME_FAB_NOT_FOUND` | NOT_FOUND / 404 | Node state missing context or FAB |
| 3013 / 3014 | `RUNTIME_INVALID_MESSAGE_COUNT` / `RUNTIME_MESSAGE_RUN_ID_MISMATCH` | 400 / 403 | SuperNode push not exactly one message, or wrong run |

These are **not** `ApiErrorCode`s but come back as strings:
- Grid: `"Message was not accepted."`, `"No instruction message to reply to. ..."`, `"AgentApp failed before replying."`.
- Responses endpoint JSON errors: `unsupported_parameter`, `invalid_request`, `invalid_api_key`, `model_task_failed`, `model_response_timeout`, `model_task_launch_timeout` [src].

---

## 10. Pattern: single-FAB master/worker (UNTESTED)

> **UNTESTED sketch** built from the 1.39.0 APIs above; it has never been run. The orchestration is programmatic, not model-driven, so fan-out, the pull budget and reply-once are guaranteed by code. The master's synthesis is streamed so `flwr chat` gets a terminal event.

```python
"""UNTESTED: single-FAB master/worker AgentApp for flwr 1.39.0."""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any

from flwr.agentapp import AgentApp, AgentSession
from flwr.app import Context
from openai import OpenAI

SUPERLINK_NODE_ID = 1          # flwr.common.constant.SUPERLINK_NODE_ID
MODEL = "openai/gpt-5.6-sol"   # better: a [tool.flwr.app.config] key
PULL_BUDGET_S = 600.0          # total fan-in wait across pull_messages calls (each ≤ 300 s)

app = AgentApp()


def _client() -> OpenAI:
    # FLWR_RUNTIME_* are injected just before main(); never read them at import time.
    return OpenAI(base_url=os.environ["FLWR_RUNTIME_BASE_URL"],
                  api_key=os.environ["FLWR_RUNTIME_API_KEY"], max_retries=0)


def _grid(agent: AgentSession, name: str, **arguments: Any) -> dict[str, Any]:
    """Programmatic Grid call. Raises on bad args (no function_call_output is emitted then)."""
    item = agent.grid.call({"type": "function_call", "call_id": f"{name}-{uuid.uuid4().hex[:8]}",
                            "name": name, "arguments": json.dumps(arguments)})
    return json.loads(item["output"])


def _say(agent: AgentSession, text: str) -> None:
    """Emit text plus a terminal event so the flwr chat CLI renders and finishes."""
    agent.events.emit({"type": "response.output_text.delta", "delta": text})
    agent.events.emit({"type": "response.completed"})


# ---------------------------------------------------------------- master (SuperLink)
def run_master(agent: AgentSession, context: Context) -> None:
    user_task = agent.prompt                                  # raw user text on the SuperLink
    nodes = _grid(agent, "get_nodes", sample_size=None)["nodes"]
    if not nodes:
        _say(agent, "No SuperNodes are online in this federation.")
        return

    # Fan-out: one message per node. A planner could give each node a different subtask.
    outgoing = [{"dst_node_id": n["id"],
                 "payload": json.dumps({"task": user_task, "node_name": n["name"]}),
                 "reply_to_message_id": None} for n in nodes]
    results = _grid(agent, "push_messages", messages=outgoing)["results"]
    pending = [r["message_id"] for r in results if r["message_id"]]
    rejected = [n["id"] for n, r in zip(nodes, results) if not r["message_id"]]

    # Fan-in: replies are returned exactly once, so accumulate across calls.
    replies: list[dict[str, Any]] = []
    deadline = time.monotonic() + PULL_BUDGET_S
    while pending and (remaining := deadline - time.monotonic()) > 0:
        out = _grid(agent, "pull_messages", message_ids=pending, timeout=min(300.0, remaining))
        replies.extend(out["messages"])
        pending = out["pending_message_ids"]

    ok = [{"node": r["src_node_id"], "answer": r["payload"]} for r in replies if r["error"] is None]
    failed = [{"node": r["src_node_id"], "error": r["error"]} for r in replies if r["error"] is not None]

    stream = _client().responses.create(
        model=MODEL,
        instructions=("Combine the worker answers into one reply for the user. "
                      "Name failed or silent nodes. Do not invent results."),
        input=json.dumps({"task": user_task, "answers": ok, "failed": failed,
                          "timed_out": pending, "rejected": rejected}),
        stream=True,
    )
    for event in stream:                                      # includes response.completed
        agent.events.emit(event.to_dict())
        if event.type in {"error", "response.failed"}:
            raise RuntimeError(f"Model response failed: {event}")


# ---------------------------------------------------------------- worker (SuperNode)
def run_worker(agent: AgentSession, context: Context) -> None:
    try:                                                      # {"message_id","src_node_id","payload"}
        payload = json.loads(agent.prompt)["payload"]
    except (ValueError, KeyError, TypeError):
        payload = agent.prompt                                # system-type message: bare payload
    try:
        task = json.loads(payload)["task"]
    except (ValueError, KeyError, TypeError):
        task = payload

    try:
        response = _client().responses.create(
            model=MODEL,
            instructions=f"You are worker node {context.node_id}. Answer concisely.",
            input=task,
        )
        answer = response.output_text or "(empty answer)"
    except Exception as exc:                                  # still reply: the master learns why at once
        answer = f"WORKER_ERROR: {type(exc).__name__}: {exc}"

    out = _grid(agent, "push_reply_message", payload=answer)  # exactly once per task
    if out["error"] is not None:
        raise RuntimeError(out["error"])
    _say(agent, answer)                                       # optional: readable worker trace


@app.main()
def main(agent: AgentSession, context: Context) -> None:
    if context.node_id == SUPERLINK_NODE_ID:
        run_master(agent, context)
    else:
        run_worker(agent, context)
```

**Model-driven variant (tool routing).** If the model drives the Grid tools instead, as in `collaborative-agent`, route each call through a guard so that no `function_call` is left without an output:

```python
def call_tool(agent: AgentSession, item: dict, connector_names: set[str]) -> dict:
    try:
        if item["name"] in connector_names:
            return agent.connectors.call(item)   # raises RuntimeError / TimeoutError after emitting
        return agent.grid.call(item)             # raises ValueError (bad args / wrong role)
    except Exception as exc:
        return {"type": "function_call_output", "call_id": item["call_id"],
                "output": json.dumps({"error": f"{type(exc).__name__}: {exc}"})}
```

Pair it with role-specific tool lists (`agent.grid.tools()` already filters by role) and role-specific instructions keyed on `context.node_id`. Don't rely on the prompt containing `src_node_id`, which is what `collaborative-agent` does.

---

## 11. Discrepancies with existing notes and example apps

| Claim / code | 1.39.0 reality | Prov. |
|---|---|---|
| Recipe uses `with context.locked():` | `Context` has no `locked()`, so the recipe raises `AttributeError` after its final stream | [src] `flwr/app/message/context.py` |
| `collab-agent-recipe.md`: override prompt with `flwr run ... --run-config` | `flwr run` can't start AgentApps, and `flwr chat` sends no run-config overrides. Only pyproject defaults apply. | [src] §6.2, §7.3 |
| `collaborative-agent.md`: Grid events "show up in the trace and the chat UI" | The trace is correct. The **`flwr chat` CLI** doesn't render `function_call*` events. | [src] `cli/chat/chat_app.py` |
| Notes: auto error reply covers "the failed task" | It covers **all** retrieved, unanswered messages of that run on that node | [src] `in_memory_nodestate.py::_store_error_replies` |
| `flwr new` success hint `flwr run <app> --stream` | Fails for AgentApps (`AGENTAPP_USER_PROMPT_REQUIRED`) | [src] `cli/new/new.py` |
| Recipe catches `(RuntimeError, ValueError)` around `connectors.call` | A 300 s connector timeout raises `TimeoutError`, which escapes | [src] `session.py` |
| `collaborative-agent` calls `agent.grid.call` unguarded | A bad model arg (e.g. `timeout: 600`) raises and fails the task | [src] `grid.py` |
