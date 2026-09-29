# Master UI

A browser front end for the master: `flwr chat` in a web page, plus a live view of the Grid calls the master makes.

```
browser (index.html) ──fetch──► bridge.py (localhost) ──protobuf/HTTPS──► SuperGrid SuperLink
                     ◄─NDJSON──                     ◄──run events───── └ master.py fans out to
                                                                          every online SuperNode
```

**Why there's a bridge:** a web page can't call SuperGrid directly. The Control API speaks protobuf over HTTPS (`POST api.flower.ai/v1/control/start-run`, then `stream-run-events`), it needs the tokens `flwr login` saved in `~/.flwr`, and browser CORS rules would block a local page anyway. `bridge.py` does what `flwr chat` does for each message, using flwr's own CLI helpers, and streams the run's events back to the page.

## Run it (on your Mac)

```bash
cd SuperNode_James/hello-app
uv sync && source .venv/bin/activate     # installs flwr 1.39.0
flwr login supergrid                     # once; opens the browser
python ../master-ui/bridge.py            # → http://127.0.0.1:8765
```

Open http://127.0.0.1:8765, keep the federation on `@efebahadirgur/Spartan`, and send `say hello`. Every online SuperNode answers, and the right-hand panel shows `get_nodes` → `push_messages` → `pull_messages` as they happen.

| Option | Default | Meaning |
|---|---|---|
| `--app-dir PATH` | `../hello-app` | The AgentApp sent with every run (same as `/load PATH`). It's re-packaged for every message, so code edits apply on the next send |
| `--port N` | `8765` | Local port |
| `--superlink NAME` | `$FLWR_CHAT_SUPERLINK` or `supergrid` | Connection name from `~/.flwr/config.toml` |
| `--host ADDR` | `127.0.0.1` | Only change this together with `BRIDGE_TOKEN` (below) |

**Security:** the bridge starts runs in your federations **as you**, using your `flwr login`. It listens on localhost only. It refuses a non-loopback `--host` unless `BRIDGE_TOKEN` is set, and then every `/api/*` call must send that token (the page picks it up from `?token=…` in its URL). Anyone with the URL and token can start runs on the team federation, so don't expose it casually.

## Files

| File | What it does |
|---|---|
| `bridge.py` | Stdlib HTTP server. `GET /` serves `index.html` (re-read on each request, so edit and reload). `GET /api/info` returns the app id and your federations. `POST /api/run` packages the app (`build_local_agent`), starts the run (`start_chat_run`), and streams every event as NDJSON. `POST /api/stop` stops a run |
| `index.html` | One file, no libraries. Federation picker, conversation, a Stop button, "New conversation" (like `/new`), and the run-event log. `renderAnswer()` turns `- node <id>: <reply>` lines into a node list with ok/error dots |

NDJSON lines from `/api/run`, one JSON object per line:

```text
{"kind": "run", "run_id": …, "series_id": …, "app_id": "@zerocks2503/hello-nodes"}
{"kind": "event", "type": "function_call", "payload": {"name": "get_nodes", "arguments": "…"}}
{"kind": "event", "type": "response.output_text.delta", "payload": {"delta": "Asked 7 SuperNode(s): …"}}
{"kind": "event", "type": "response.completed", "payload": {…}}
{"kind": "done", "terminal_seen": true}          # or {"kind": "error", "message": "…"}
```

## Ideas to try yourself

- **Show nodes before the answer:** parse the `function_call_output` of `get_nodes` in `logEvent()` and draw each node as a card that lights up when its reply arrives.
- **Timing per run step:** timestamp each `function_call` / `function_call_output` pair to show how long the fan-out and fan-in took.
- **History:** add a `GET /api/history` route using `ListRunSeries` / `ListRunSeriesEvents` (see `flwr/cli/chat/chat_history.py`), and let the page reopen an old conversation.
- **Richer answers:** once the master replies with JSON (e.g. supplier quotes), change `renderAnswer()` to draw a table instead of text lines.

## Status

- **Verified 2026-09-29, end to end with `curl` on the RunPod pod.** `/api/info` listed the federations. `/api/run` with `say hello` in Spartan streamed the prompt, `get_nodes` / `push_messages` / `pull_messages` with their outputs, the answer `Asked 7 SuperNode(s)` (our 3 nodes plus the teammates' `motor-a`, `motor-b`, `camera-a` and `battery-a`), `response.completed`, then `done` with `terminal_seen: true`.
- The page passed a syntax check (`node --check`) but hasn't been opened in a browser yet.
- `bridge.py` imports flwr **1.39.0 internals** (`flwr.cli.chat.*`, `flwr.cli.utils`), so it may need small changes after a `flwr` upgrade.
