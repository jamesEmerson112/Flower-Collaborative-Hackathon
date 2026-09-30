# SuperGrid_RobotShop

The hackathon demo. You pick parts in **Robot Workshop** (a browser robot builder) and click Build. The request goes through a local **bridge** to **one AgentApp** on SuperGrid:

- The **master** runs on Flower's SuperLink. It sends a quote task to every store SuperNode (a node named `store-<id>`).
- Each **store node** holds only its own catalogue CSV, set by its operator with `--node-config robotshop-catalog=...`. It quotes the parts it sells from that file and replies once.
- The master combines the replies into per-store subtotals and totals, summed in integer cents.
- **One model call** writes the answer from the computed quote. The model never does the math, and if the call fails, a plain-code answer (`pricing.format_quote`) is used instead.

Workers make no model calls, so store nodes need no model key. Prices never ship in the frontend or in the FAB: they come only from the store nodes' replies.

## Architecture

```
Browser: Robot Workshop (web/)
  │ POST /api/run {"prompt": <C1 JSON>}               ▲ NDJSON: run → events → done
  ▼                                                   │
bridge.py (Mac, 127.0.0.1:8765) ── start-run / StreamRunEvents (flwr login tokens) ──┐
                                                                                     ▼
                 Flower SuperLink (SuperGrid): master.py (node_id 1)
                   get_nodes → keep the nodes named store-*
                   push_messages: C2 quote task to each
                   pull_messages every 5 s (90 s budget) → robotshop.progress events
                   combine() in integer cents → robotshop.quote event
                   one model call writes the answer (else format_quote) → response.completed
                          │ C2                                 ▲ C3 (exactly once per node)
                          ▼                                    │
        store-adafruit … store-waveshare (8 SuperNodes on the RunPod pod)
          worker.py (arrives in the run's FAB) + node/catalogs/<store>.csv (--node-config)
```

If no online node has a `store-*` name, the master asks every node. Nodes without a catalogue, such as teammates' nodes, answer `NO_CATALOG`.

## Layout

- `app/`: the AgentApp, which is the folder the bridge packages into the FAB (like `/load app`). The only dependency is `flwr` (see "Known limits").
  - `robot_shop/agent_app.py` is only the role switch: `context.node_id == 1` runs `master.py`, and any other node runs `worker.py`.
  - `protocol.py` holds the contracts C1–C3.
  - `pricing.py` has `combine()` (cents math) and `format_quote()`.
  - `catalog.py` does the worker's CSV lookup.
  - `llm.py` makes the model call.
  - `common.py` has `grid()`, `emit()` and `say()`.
  - `tests/` has stdlib `unittest` tests. The pure modules import no flwr, so any `python3` runs them.
- `node/`: node-local only, never in the FAB.
  - `catalogs/<store>.csv`: 8 stores, 102 items. `make_catalogs.py` generates them from `docs/robot-parts-stores/classified/by-store/`.
  - `start-store.sh <store> [supergrid|local]` starts one store node.
  - `setup-stores.sh` does keygen, register, add to Spartan and start in tmux for all 8.
- `web/`: a copy of `docs/robot-builder` (the user's Robot Workshop; the original is left alone), plus:
  - the components tray (`src/components.js`, `src/components-data.js`);
  - the quote panel (`src/quote.js`, `src/quote.css`);
  - `scripts/sync_data.py`, which refreshes `public/` from the repo's datasets.
- `bridge.py`: adapted from `SuperNode_James/master-ui/bridge.py`. It does what `flwr chat` does for one message and streams every run event as NDJSON. It also serves `web/dist` and the run cache.
- `cache/<key>.json`: recordings of successful live runs, written by the bridge (see "Cache mode").

## Contracts

All payloads are JSON strings. The source of truth is `app/robot_shop/protocol.py` (C1–C3) and the `pricing.py` docstring (the quote).

- **C1, the request** (the run's prompt text, sent by the web UI through the bridge):
  `{"request": "Build this robot for me", "items": [{"product_id": "pololu-3500", "qty": 1, "name": "Romi chassis", "store_id": "pololu"}]}`
  - `name` and `store_id` are optional. `store_id` falls back to the `product_id` prefix.
  - Duplicate IDs are merged by summing `qty`.
  - A prompt that isn't C1 (e.g. plain text in `flwr chat`) gets a usage reply that shows this format.
- **C2, the task** (master → each store node): `{"task": "quote", "items": [{"product_id", "qty"}]}`
- **C3, the reply** (node → master, sent exactly once):
  - success: `{"ok": true, "store_id", "store_name", "quotes": [{"product_id", "name", "sku", "qty", "unit_price", "currency", "url"}]}`. `quotes` covers only the parts in that node's catalogue.
  - failure: `{"ok": false, "code": "NO_CATALOG" | "BAD_TASK" | "CATALOG_ERROR", "message"}`
- **Events the master emits:**
  - `robotshop.progress` `{replied, expected, stores}` once after `push_messages` (replied 0), then after each pull;
  - `robotshop.quote` `{quote: Q}` before the answer text, where Q has these fields:
    - `lines`: each line has its store, `node_id`, `unit_price` and `subtotal`.
    - `unquoted`: each entry has a `code`: `no_store` ("no store sells it") or `not_stocked` (the store replied but doesn't stock the part).
    - `stores` (per-store subtotals), `totals` (per currency) and `nodes` (asked, targeted, replied, `NO_CATALOG` count, errors, timed out).
  - If two stores quote the same part, the first reply wins.
- **Fallback:** the answer text ends with a fenced `` ```robotshop-quote `` block holding the same Q. `web/src/quote.js` reads it if no `robotshop.quote` event arrived.
- **Bridge NDJSON:** `{"kind":"run",...}`, then `{"kind":"event","type","payload"}` for every event (Grid `function_call` items included), then `{"kind":"done","terminal_seen"}` or `{"kind":"error","message"}`. `POST /api/stop {"run_id"}` stops a run.

## Run it

### Mac: bridge and UI

```bash
# Once: log in (device flow), using the venv that has flwr 1.39.0
SuperNode_James/hello-app/.venv/bin/flwr login supergrid

# Bridge: 127.0.0.1:8765; --federation defaults to @efebahadirgur/Spartan; serves web/dist
SuperNode_James/hello-app/.venv/bin/python SuperGrid_RobotShop/bridge.py

# UI, dev mode: http://127.0.0.1:5175 (Vite proxies /api to 8765)
cd SuperGrid_RobotShop/web && python3 scripts/sync_data.py && npm run dev
# or build it once and open http://127.0.0.1:8765
npm run build
```

`sync_data.py` does three things:
- It rewrites `public/catalog.json` from `docs/robot-builder` with the prices removed.
- It writes `public/components.json` from `classified/all_parts.csv`.
- It copies the git-ignored `public/models/` and `public/thumbnails/` from `docs/robot-builder/public/`. Run it on a fresh clone before `npm run dev` or `npm run build`.

For a non-loopback `--host`, the bridge requires `BRIDGE_TOKEN`.

**Demo build (the user's favourite):**
- G1 torso (`unitree-g1-torso`)
- Reachy 2 head (`reachy2-head`)
- SO-101 arm (`seeed-100046482`)
- Ned2 arm (`niryo-ned2`)
- WAVE ROVER (`waveshare-wave-rover`)

Only Seeed and Waveshare have store nodes today, so the other 3 show as "no store sells it".

### Cache mode (the demo safety net; built 2026-09-30)

This feature was still being built when this README was written. Check `bridge.py` and `web/src/quote.js` if the details below differ.

- **Recording:** the bridge records every successful live run to `cache/<key>.json`.
  - `key` is the first 16 hex characters of the sha256 of the sorted `[product_id, qty]` pairs.
  - The bridge keeps draining a live run even if the page disconnects, so the recording completes.
- **Routes:** `POST /api/cache {prompt}` returns 200 with the cached run, or 404. `GET /api/cache/list` lists the cache.
- **Importing a curl recording:** `python bridge.py --import-ndjson <file> --prompt-json <file>`.
- **The "Cache mode" toggle** in the quote panel replays the last live run for the same build instantly. It is always labeled "Cached result — recorded from live SuperGrid run <id> at <time>".
- **In live mode**, after 30 s in Flower's queue, the panel offers "Show cached result now". Meanwhile it shows a live "Queued at Flower… m:ss" clock.

### Pod: the store SuperNodes

Ship only `node/` to the pod (the app code arrives with each run's FAB). The SSH and copy procedure is in the git-ignored `docs/private/runpod-supernode.md`.

```bash
. /root/SuperNode_James/hello-app/.venv/bin/activate && cd /root/SuperGrid_RobotShop/node && ./setup-stores.sh
#   --register-only | --start-only; optional store names (default: all 8)
```

- Ports are 9101–9108, in the order adafruit, sparkfun, pololu, servocity, seeed, dfrobot, robotis, waveshare.
- Keys are in `~/supernodes_keys/supernode-store-<id>`, and node IDs are recorded in `~/supernodes_keys/store-node-ids.txt`.
- Each node runs in tmux window `store-<id>` of session `flower`, with its log at `/tmp/store-<id>.log`.
- Each node process gets its own `FLWR_HOME` (`~/.flwr-store-<id>`). Nodes that share `~/.flwr` can race while installing the same FAB. `flwr login` tokens stay in `~/.flwr`.
- The script parses the CLI's JSON output, because `flwr ... --format json` exits 0 even on errors.

### Tests

```bash
python3 -m unittest discover -s SuperGrid_RobotShop/app/tests -t SuperGrid_RobotShop/app   # 36 tests
cd SuperGrid_RobotShop/web && npm test && npm run build
```

## Status (2026-09-29)

These were verified live, through the Mac bridge against the pod's store nodes:
- **The custom events `robotshop.progress` and `robotshop.quote` reach the bridge** through SuperGrid's `StreamRunEvents`. `flwr chat` ignores unknown event types (`flwr/cli/chat/chat_app.py:857–895`).
- **`get_nodes` returns each node's registered name** (for example `store-pololu`), so the master targets stores by name. Teammate nodes registered without a name return `null` (`flwr/supercore/task_process/agent/grid.py:332–351`).
- **A quote round trip with 2 store replies worked.** The master's fan-out plus both replies took 5.6 s.
- **The wait is Flower's run queue, not our code.** About 167 s passed from start-run to the first event.
  - `flwr list supergrid --run-id <id> --format json` shows the run sat in `pending` for 2 min 43 s (pending-at 23:56:12Z, starting-at 23:58:55Z).
  - `starting` → `running` took 2 s.
  - Flower also creates an isolated runtime env per run ("Created env for run", `flwr/supercore/superexec/dependency_installer.py:123`), but its `uv sync` takes only about 1.5 s.
- **A non-streamed Responses POST from the master got no response** (httpx `ReadTimeout` at 60 s), so that run's answer came from `format_quote`. All working Hub apps stream.

Changed since, but not yet verified live: `app/robot_shop/llm.py` now streams (`httpx.stream` with `"stream": true`, SSE). `TIMEOUT_S` is a read timeout between chunks, set short for the demo so the fallback comes quickly.

- **All 8 stores in one run [verified live 2026-09-30]:** run `3078610203486196846`, 8 of 8 `store-*` nodes answered (no errors, no timeouts), total **$205.78** for one part from each store; `niryo-ned2` listed as `no_store`. About 4.5 min in Flower's queue, then seconds for the stores.

Not verified yet:
- the UI end to end in a browser;
- a model-written answer;
- cache mode.

## Known limits

- **Latency:** about 3 minutes before the first event, spent in Flower's run queue. Cache mode is the fallback for a live demo.
- **Model call:** see Status. The plain-code answer covers every failure, so the quote is always correct.
- **App dependencies are `flwr` only.** SuperNodes don't install app dependencies (`RUNTIME_DEPENDENCY_INSTALL = False`, `flwr/common/constant.py:128`), and the SuperLink runs `uv sync` per run. `llm.py` uses `httpx`, which comes with flwr, instead of `openai`.
- **3D models are git-ignored.** `web/scripts/sync_data.py` copies them from `docs/robot-builder`.
- **Catalogue snapshot:** 8 stores and 102 items, as of `make_catalogs.py`'s last run.
- **Some body parts have no store.** 9 of the 19 body parts in the current `web/public/catalog.json` come from companies without a store node: Niryo, Pollen Robotics ×3, Elephant Robotics, Berkeley Humanoid Lite and Unitree ×3. The master lists them as "no store sells it" and leaves them out of the total. The count follows `docs/robot-builder`, whose catalogue `sync_data.py` copies.
- **Pending:**
  - the unified catalogue merge (`docs/prompts/unified-catalog-merge.txt`, run after the demo);
  - store nodes for 17 more companies on a second pod.
  After both, rerun `node/make_catalogs.py` and `web/scripts/sync_data.py`.
