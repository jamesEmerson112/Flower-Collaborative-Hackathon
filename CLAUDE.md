# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose and plan

Team repo for the **Flower Collaborative Hackathon**. The challenge: show several Flower Agents collaborating on **SuperGrid**. Our design is **one AgentApp (one FAB)** that runs as the **master on the SuperLink** and as a **worker on every SuperNode**. The master fans tasks out with the Grid tools (`get_nodes` → `push_messages` → `pull_messages`), and each worker answers from **node-local private data** selected by its operator with `--node-config`. Suppliers each hold a private catalogue (one `SuperGrid_RobotShop/node/catalogs/<store>.csv` per store node), compute quotes in Python, and reply with only what the master needs. **`SuperGrid_RobotShop/` is the demo that does this** (read its `README.md`); `SuperNode_James/hello-app` proved the pattern with a greeting.
**Decision (2026-09-29): one LLM, on the master only.** In `SuperGrid_RobotShop` the parts list comes from the Robot Workshop UI, code does all the money math, and the model only writes the answer (plain-code fallback). Workers look parts up in their catalogue with plain code and no model, so nodes need no model key. Revisit worker LLMs only if stores' data formats diverge or the demo needs "each store is its own agent". The design rationale is in `docs/artifacts/robot-build-relay/` (the simulated demo). Team federation: **`@efebahadirgur/Spartan`** (deployment federation; members can attach SuperNodes).

## Repo map

- `docs/`: team notes, and the **first place to look** before answering questions or searching the web.
  - `hackathon-brief.md`: the organizers' brief, model-endpoint setup, open mentor questions, and the **index of all links and artifacts**.
  - `agentapp-api-reference.md`: the dev reference for `flwr` 1.39.0 (AgentApp API, Grid tools, delivery semantics, model access, packaging, CLI, Hub API, error codes, an untested master/worker sketch in §10, and discrepancies in §11).
  - `supergrid-setup.md`: what SuperGrid is, federation and SuperNode setup, AgentApp caveats, and local dev.
  - `collab-agent-recipe.md`, `collaborative-agent.md`, `flwrlabs-agent.md`: source walkthroughs of the three Hub apps. `collaborative-agent` is the only one that uses `agent.grid`.
  - `supernode-scope/`: 28 Hub apps studied. `README.md` has the findings that shape our build and the anti-patterns to avoid.
  - `robot-parts-stores/`: the supplier dataset (8 stores; 102 items in the working tree, 95 at `a136f14`). `stores.json` is the source of truth, and `build.py` regenerates `index.html` and `data/`.
    - `classified/` (added by the user or a teammate, not by Claude): the same 95 items researched further, with robot roles, component types, images, evidence and CAD links. It has **one identically formatted CSV per store** (`by-store/`), plus `all_parts.csv`, `schema.json` and `taxonomy.json`. It is the source of `SuperGrid_RobotShop/node/catalogs/`.
    - `cad/` (also not ours): CAD assets for 50 of the 95 products. The downloads (`originals/`, `extracted/`, about 930 MB) are git-ignored; only the manifest and CSVs are tracked.
  - `robot-builder/`: **the user's side project ("Robot Workshop", a Vite browser builder). Ignore it:** don't read, edit or build it unless the user asks. Its `node_modules/` and `dist/` are git-ignored. The demo's copy lives in `SuperGrid_RobotShop/web/`.
  - `prompts/`: prompts to run later. `unified-catalog-merge.txt` merges the parts datasets into one 25-company catalogue; **run it only after the demo is verified.**
  - `artifacts/robot-shop-architecture/`: source of the **Robot Shop Architecture** artifact (a single animated HTML page). Republish it to https://claude.ai/artifact/QgPoQycHv5NHPZNbzMSPNH to update the page.
  - `artifacts/robot-build-relay/`: source of the **Robot Build Relay** artifact, a simulated supplier-quote run over the 8 stores. `page.template.html` plus `build.py`, which injects `stores.json` and runs `node --check`. Rebuild, then republish `robot-build-relay.html`.
  - `agent/`, `collaborative-agent/`, `hackathon-collab-agent-recipe/`: **unmodified copies of Flower Hub apps**, kept for diffing against upstream. **Never edit them.**
  - `private/`: **git-ignored.** `runpod-supernode.md` is the private runbook with our identifiers (Flower account, node ID, pod ID and cost, SSH commands), a from-scratch RunPod SuperNode procedure, teardown and gotchas. It contains no secrets. Read it before touching the pod.
- `SuperNode_James/`: our first SuperNode experiment (read its `README.md`).
  - `node/`: turns a machine into SuperNode "james". `start-supernode.sh` plus the local `profile.json`, with no app code.
  - `hello-app/`: the minimal master/worker AgentApp, split by role so two people can work in parallel. `hello_app/agent_app.py` is only the role switch. `master.py` runs on the SuperLink and `worker.py` on each SuperNode. `protocol.py` is the task/reply contract between them, and `common.py` holds `grid()` / `say()`. The node's name comes only from `profile.json`, never from the code.
  - `master-ui/`: a browser front end for the master. `bridge.py` is a stdlib localhost server that does what `flwr chat` does, using flwr 1.39.0's CLI internals (`build_local_agent`, `start_chat_run`, `StreamRunEvents`), and streams every run event as NDJSON. `index.html` shows the answer plus the Grid calls `flwr chat` hides. Verified end to end with `curl` on the pod. Its successor is `SuperGrid_RobotShop/bridge.py`.
- `SuperGrid_RobotShop/`: **the hackathon demo** (read its `README.md`). Robot Workshop sends a parts list through a bridge to one AgentApp. The master asks the `store-<id>` SuperNodes for quotes, then combines them in integer cents.
  - `app/`: the AgentApp (the FAB). `robot_shop/` holds `agent_app.py` (role switch), `master.py`, `worker.py`, `protocol.py` (contracts C1–C3), `pricing.py` (cents math, `format_quote`), `catalog.py` (worker CSV lookup), `llm.py` (the one model call) and `common.py`. Unit tests are in `tests/`. The only dependency is `flwr`.
  - `node/`: node-local only, never in the FAB. `catalogs/<store>.csv` covers 14 stores with the same 10 columns. The original 8 (102 items) are generated by `make_catalogs.py` from `classified/by-store/`. The 6 extra ones (`hello-robot`, `niryo`, `pollen`, `robotshop`, `trossen`, `unitree`) were built from `robot-parts-stores/expansion/all_parts.csv`, with `pollen-robotics` renamed to `pollen` to match the builder's `storeId`. Only priced rows are quotable. `start-store.sh` starts one store node (ports 9101–9114), and `setup-stores.sh` does keygen, register, add to Spartan and start in tmux for the 8 by default, or the extra stores by name (`EXTRA_STORES`).
  - `web/`: a copy of `docs/robot-builder`, plus the components tray (`components.js`, `components-data.js`) and the quote panel (`quote.js`, `quote.css`). `scripts/sync_data.py` refreshes `public/` and copies the git-ignored models.
  - `bridge.py`: the `master-ui` bridge adapted to serve `web/dist` and the run cache (`cache/`).

## Commands

There is no linter or CI. `SuperGrid_RobotShop` has unit tests (below); everything else is checked by a live run. The repo path contains spaces, so quote it in `cd`.

```bash
# Install Flower into an app's env (uv.lock pins flwr 1.39.0); also provides flower-superlink / flower-supernode
cd SuperNode_James/hello-app && uv sync && source .venv/bin/activate

# Run an AgentApp on SuperGrid (from the app folder)
flwr chat
#   /federation @efebahadirgur/Spartan
#   /load .
#   <prompt text>          # each message is one run; /new starts a fresh series

# Start a SuperNode (needs flower-supernode on PATH, so activate hello-app/.venv first)
cd SuperNode_James/node
./start-supernode.sh supergrid   # outbound to fleet-supergrid.flower.ai:443; key at ~/supernodes_keys/supernode-james (override: SUPERNODE_KEY=...)
./start-supernode.sh local       # to a local `flower-superlink --insecure` at 127.0.0.1:9092

# Local SuperLink chat (untested): add to ~/.flwr/config.toml
#   [superlink.local-agent]
#   address = "127.0.0.1:8000"
#   insecure = true
export FLWR_CHAT_SUPERLINK=local-agent && flwr chat

# Master UI in the browser (needs hello-app/.venv active and `flwr login supergrid`)
python SuperNode_James/master-ui/bridge.py        # → http://127.0.0.1:8765  (--app-dir, --port; BRIDGE_TOKEN for a non-loopback --host)

# Regenerate the supplier dataset after editing stores.json (stdlib only; paths resolve from __file__, so any cwd works)
python3 docs/robot-parts-stores/build.py

# RobotShop demo (Mac; needs `flwr login supergrid` once)
SuperNode_James/hello-app/.venv/bin/python SuperGrid_RobotShop/bridge.py   # :8765, --federation defaults to Spartan, serves web/dist + cache/
cd SuperGrid_RobotShop/web && python3 scripts/sync_data.py && npm run dev   # http://127.0.0.1:5175 (proxies /api to 8765); or `npm run build` → http://127.0.0.1:8765
python3 -m unittest discover -s SuperGrid_RobotShop/app/tests -t SuperGrid_RobotShop/app
cd SuperGrid_RobotShop/web && npm test && npm run build
python3 SuperGrid_RobotShop/node/make_catalogs.py   # regenerate node/catalogs/ from classified/by-store/

# RobotShop store nodes (on the pods; ship only node/)
. /root/SuperNode_James/hello-app/.venv/bin/activate && cd /root/SuperGrid_RobotShop/node && ./setup-stores.sh   # pod 1; --register-only | --start-only; logs /tmp/store-<id>.log
. /root/venv/bin/activate && cd /root/SuperGrid_RobotShop/node && ./start-store.sh <id> supergrid   # pod 2, one extra store (see RobotShop README "Extra stores on a second machine")
```

Monitor runs with `flwr list supergrid`, `flwr log <run-id> supergrid --show` and `flwr stop <run-id> supergrid`. SuperNode registration steps are in `SuperNode_James/README.md` (Option B) and `supergrid-setup.md` §2.

## Hard-won facts (verify against the cited doc before changing course)

"api-ref" = `docs/agentapp-api-reference.md`, and "supergrid-setup" = `docs/supergrid-setup.md`.

- **Launch AgentApps with `flwr chat` → `/load .`, never `flwr run`.** `flwr run` sends no user prompt, so the SuperLink rejects it with `AGENTAPP_USER_PROMPT_REQUIRED` (44). As a result, `--run-config` overrides can't reach an AgentApp; only the pyproject defaults apply. See api-ref §7.3 and §6.2, and supergrid-setup "AgentApp caveats".
- **One FAB per run, so the app branches on role.** SuperNodes fetch the run's own FAB, so master and workers are the same code: `context.node_id == 1` means the SuperLink (master), and anything else is a worker. See api-ref §2.1 and §2.5, and `hello_app/agent_app.py` (role switch).
- **SuperNodes never talk to each other.** Workers get only `push_reply_message`, and the master relays anything node-to-node. See supergrid-setup "SuperNodes: machines, not projects" and api-ref §2.1.
- **Delivery rules:** a worker must call `push_reply_message` exactly once (nothing is sent automatically on success). `pull_messages` is destructive, so keep every reply as it arrives. Worker `agent.prompt` is a JSON envelope `{"message_id","src_node_id","payload"}`. See api-ref §2.5 and §2.6.
- **Model env vars come in two layers.** The node operator sets `FLWR_MODEL_API_KEY`, plus `FLWR_MODEL_API_ENDPOINT` for Nebius (it must end in `/responses`). The app reads `FLWR_RUNTIME_BASE_URL` / `FLWR_RUNTIME_API_KEY`, which Flower injects per task. **Never set `FLWR_RUNTIME_API_KEY` yourself.** See api-ref §5.1 vs §5.5, and hackathon-brief "Configuring a SuperNode's model endpoint".
- **Use a deployment federation, not a simulation one.** AgentApps skip the simulation runtime, so `get_nodes` would most likely return nothing. See supergrid-setup "AgentApp caveats".
- **The master must emit `response.completed`** (or `response.incomplete`). Otherwise `flwr chat` reports that the run ended early. It doesn't render `function_call` events. See api-ref §4.5 and the hello app's `say()`.
- `/load .` rebuilds the FAB before every prompt, so code edits don't need another `/load`. See api-ref §7.2.
- The Hub copies pin `flwr` 1.38.0 or 1.35.0. `context.locked()` (used by the recipe) **does not exist in 1.39.0**, so don't port it. See api-ref header, §1.3 and §11.
- `get_nodes` lists only **online** nodes. A node drops out about 60 s after its last heartbeat, so keep SuperNodes running during demos. See supernode-scope/README finding 6.
- **`fab-format-version = 1` requires a license file.** `[project].license = { file = "LICENSE" }` (or `LICENSE.md`), with the file at the app root and in `fab-include`. Without it, `/load .` fails and chat **silently stays on Flower's default agent**, which answers plain "Hello." **[verified live on the pod]** See `flwr/supercore/fab_format_version.py`.
- **`flwr login` on a headless box uses the OIDC device flow.** It prints `https://account.flower.ai/realms/flower/device?user_code=XXXX-XXXX`; open that in any browser and the CLI finishes on its own **[verified live]**.
- **Worker code ships with the app, never with the node.** Each SuperNode downloads the run's FAB from the SuperLink the first time it sees a message for that run, installs it and runs `main()` as a worker (`supernode/start_client_internal.py:344–409`, `run_agentapp.py:365`). A node holds only its key, its data and `flower-supernode`. **[verified live: teammate nodes ran our `worker.py` and replied with its `PROFILE_ERROR` string]** A node started with `--trusted-entities` rejects unsigned FABs with an error reply (`:356–381`); nobody in Spartan uses it.
- **The FAB only contains real files inside the app folder.** `collect_files` skips symlinks and anything outside the root (`flwr/cli/utils.py:539`), so worker code can't be pulled in from a sibling folder. The app you `/load` must contain master **and** worker code.
- **Each model request is its own task, not one shared model.** `responses.create` becomes a MODEL task on the machine that made it (`routers/runtime/responses.py:188`), using that machine's `FLWR_MODEL_API_KEY` / endpoint (`task_process/model/provider.py:79–92`). SuperNodes host the endpoint too (`supernode/main.py:81`), so workers can have their own LLM (as `collaborative-agent` does). The docs say "each Responses request creates a Flower model task", so use `max_retries=0`. Calls share no memory. **Our pod nodes have no `FLWR_MODEL_API_KEY`**, so worker model calls would fail there (RobotShop workers make none).
- **`push_messages` takes a per-message `dst_node_id` and `payload`** (`task_process/agent/grid.py:118–136`), so the master can send each node a different task or prompt.
- **`flwr chat` takes no arguments** (`def chat() -> None`). It talks protobuf over HTTPS (`api.flower.ai/v1/control/start-run`, then `stream-run-events`) using the `flwr login` tokens in `~/.flwr`. A browser can't do that directly, which is why `master-ui/bridge.py` and `SuperGrid_RobotShop/bridge.py` exist.
- **Custom event types reach the bridge.** The master's `robotshop.progress` and `robotshop.quote` events come through SuperGrid's `StreamRunEvents`, and `flwr chat` ignores unknown types (`flwr/cli/chat/chat_app.py:857–895`, render loop). **[verified live 2026-09-29]**
- **`get_nodes` returns each node's registered name** (for example `store-pololu`; teammate nodes registered without a name return `null`), so the master can target nodes by name (`task_process/agent/grid.py:332–351`, `_get_nodes`). **[verified live 2026-09-29]**
- **Run start latency is Flower's queue, not our code.**
  - It was about 167 s from start-run to the first event.
  - `flwr list supergrid --run-id <id> --format json` showed 2 min 43 s in `pending`, then 2 s from `starting` to `running`.
  - Flower creates an isolated runtime env per run ("Created env for run", `supercore/superexec/dependency_installer.py:123`), but its `uv sync` takes about 1.5 s.
  - The master's own fan-out plus 2 store replies took 5.6 s.
  **[verified live 2026-09-29]**
- **A non-streamed Responses POST from the SuperLink-side master got no response** (httpx `ReadTimeout` at 60 s). All working Hub apps use `stream=True`. `SuperGrid_RobotShop/app/robot_shop/llm.py` now streams (SSE, with `TIMEOUT_S` as the read timeout between chunks); that version hasn't been run live yet. **[verified live 2026-09-29 for the timeout]**
- **Put `[robot-shop]` print lines in the master.** They appear in `flwr log <run-id> supergrid --show`, with timings. **[verified live 2026-09-29]**
- **`flwr ... --format json` exits 0 even on errors**, so `setup-stores.sh` parses stdout. **[verified live 2026-09-29]**
- **SuperNodes don't install app dependencies** (`RUNTIME_DEPENDENCY_INSTALL = False`, `flwr/common/constant.py:128`); the SuperLink runs `uv sync`. Keep app dependencies to `flwr` only; `httpx` comes with flwr. **[src for SuperNodes; the SuperLink's per-run `uv sync` seen live 2026-09-29]**
- **SuperGrid can drop every node while the processes stay alive.** SuperGrid returned `StatusCode.INTERNAL "Internal server error."` to the SuperNodes, and all our nodes went offline with their processes still running. Restarting them (`tmux kill-window` for each `store-<id>`, then `./setup-stores.sh --start-only`) brought them back online. Check `flwr` node status before a demo, not just `ps`. **[verified live 2026-09-30]**
- **Everything else is read from the `flwr` 1.39.0 source, and most of it hasn't been run live.** Treat the notes as strong hypotheses and record the result when something is tested. Verified live so far:
  - SuperNode registration and add-to-federation, a node coming online, device-flow login, and the license requirement;
  - a **full master→worker Grid round trip** (`hello-app`, one node, then 3 of ours on one pod plus 4 teammate nodes);
  - **several SuperNodes on one machine via different `--port`s**;
  - `flwr chat` → `/load .` running a local app on SuperGrid;
  - a **RobotShop quote round trip** through the Mac bridge (2 store replies, custom events, name targeting), then 8/8 stores in one run;
  - **14 store SuperNodes on two pods**, registered and added to Spartan from the Mac with keys generated on the pod (only the `.pub` left it).

## Conventions

- **Notes go in `docs/`.** Write them to files, and link new material from the index in `hackathon-brief.md`.
- **Tag claims by provenance:** **[src]** (`flwr` 1.39.0 or app source, with the module cited), **[docs]** (flower.ai docs, with the date fetched), **[inference]** (our reading, unverified).
- **Keep the three Hub app copies under `docs/` byte-for-byte pristine.** Fork into a new folder instead.
- Private data must stay on the node (in a `--node-config` path), never in the FAB or in `run_config`. Match replies by `message_id` / `src_node_id`, not by list position. See supernode-scope/README "Anti-patterns".
- **The venue network is slow.** `uvx --from flwr` stalled downloading wheels there. To fetch a Hub app without the `flwr` CLI, `POST https://api.flower.ai/v1/hub/fetch-zip` with `{"app_id":"@pub/app","app_version":null,"flwr_version":"1.39.0"}` and download the returned `zip_url`. See api-ref §8 and collab-agent-recipe "Provenance".
- Set `publisher` in an app's `pyproject.toml` to your Flower username (the user's is **`zerocks2503`**). FABs are capped at 10 MB.

## Hackathon result (2026-09-30)

The hackathon is over. We didn't win, but the demo worked. `SuperGrid_RobotShop` quoted robot builds live on SuperGrid from **14 store SuperNodes on two machines**.
- The master sent the quote task only to the nodes named `store-*`. **14/14 answered**, with per-currency totals: the favourite build came to **$388.99 + €3,990**.
- Cache mode replayed recorded live runs whenever Flower's queue (2–4 min) or its errors got in the way.
- Everything is committed. The architecture diagram is https://claude.ai/artifact/QgPoQycHv5NHPZNbzMSPNH (Flower + Nebius wording; the machines were RunPod pods).

## Current state (archived, 2026-09-30)

**Nothing is running.**
- The Mac bridge is stopped.
- All 14 store SuperNodes were shut down cleanly.
- **Both RunPod pods are stopped** by the user: pod 1 `fibicm4cy4pj0c` ($0.07/hr) and pod 2 `j4c8ksd68ykygs` ($0.08/hr).
- Every SuperNode is **still registered** and in `@efebahadirgur/Spartan`, and shows offline.
- The private details (SSH, keys, procedures) are in `docs/private/runpod-supernode.md` (git-ignored). The user's other pods are not ours to touch.

**Registered SuperNodes (all offline):**
- **Pod 1, ports 9101–9108:**
  - adafruit `9218589532074956174`
  - sparkfun `1488711584180952523`
  - pololu `18118764492044682673`
  - servocity `13756845717059552733`
  - seeed `8154894932540289281`
  - dfrobot `2948423303319067329`
  - robotis `16073326398896412165`
  - waveshare `18238716053767830266`
- **Pod 2, ports 9109–9114:**
  - hello-robot `9801082392364761173`
  - niryo `18394969287714527068`
  - pollen `14616609307484587852`
  - robotshop `7777637153266000561`
  - trossen `107545347103705936`
  - unitree `18143218857839472111`
- **Hello nodes:** `james` `9674070929710601496`, `James_2_Pod1` `3446080994785355467`, `James_3_Pod1` `8936488704647726645`.
- **Teammates' nodes:** `motor-a`, `motor-b`, `camera-a` and `battery-a` (not ours). Their names don't start with `store-`, so the master doesn't ask them.

**To bring it back:**
1. Start the pods, with the RunPod console or the Runpod MCP `pod-action`; the user created them, so ask first.
2. **If `/root` survived the stop** (the keys in `~/supernodes_keys/` and `/root/SuperGrid_RobotShop/node`):
   - pod 1: `. /root/SuperNode_James/hello-app/.venv/bin/activate && cd /root/SuperGrid_RobotShop/node && ./setup-stores.sh --start-only`;
   - pod 2: activate `/root/venv`, then run `./start-store.sh <id> supergrid` for each of the 6 extra stores in tmux.
3. **If it didn't survive:** copy `SuperGrid_RobotShop/node` over again, create new keys, register them (`--name store-<id>`), add them to Spartan, start them, and unregister the old IDs.
4. On the Mac: `SuperNode_James/hello-app/.venv/bin/python SuperGrid_RobotShop/bridge.py`, then open http://127.0.0.1:8765.
5. Check with `flwr supernode list supergrid --format json`.

**Local Mac:** `flwr` 1.39.0 is in `SuperNode_James/hello-app/.venv`, with `flwr login supergrid` done. `SuperGrid_RobotShop/cache/` holds 4 recorded live runs:
- both favourite builds, 14 stores each;
- the 8-store build, $205.78;
- Romi + 2× TT motor + Ned2, $45.85.

**Tooling:** the Runpod Claude Code plugin is installed. Creating pods costs money: state the price and confirm first.

**Artifacts** (private until shared; all links are in `docs/hackathon-brief.md`): Trace Explorer, API Reference, 3D "Head Office & Stores", the Flower Concept Map, Robot Build Relay (source in `docs/artifacts/robot-build-relay/`) and the RobotShop architecture diagram. Robot Build Relay and the architecture diagram have their sources in the repo (`docs/artifacts/robot-build-relay/`, `docs/artifacts/robot-shop-architecture/`); the others don't.

**Git:**
- `a136f14` "new stuff" has an uninformative message. It covered the hello-app split, `master-ui`, the Robot Build Relay source, the classified and CAD data, and robot-builder; `f715532`'s message describes it. It was left unamended by the user's choice.
- `f715532` added `SuperGrid_RobotShop` (8 stores).
- `b6114c8` was the brief link.
- `590b30f` added 14 stores.
- Then the wrap-up commit.
- Git ignores `web/node_modules/`, `web/dist/`, `web/public/models/` and `web/public/thumbnails/`.

**If work resumes (none is in progress):**
1. Run the full 25-company catalogue merge (`docs/prompts/unified-catalog-merge.txt`), then add nodes for the 11 unpriced companies, rerun `node/make_catalogs.py` and `web/scripts/sync_data.py`.
2. Get a model-written answer. The master's streamed call on the SuperLink timed out at 30 s live, so ask Flower whether SuperLink-side model calls need setup, and confirm the Endeavor model ID.
3. Remove the stale hello nodes from SuperGrid (`flwr supernode unregister <id> supergrid`) if they're no longer wanted.
4. Re-run `python3 docs/artifacts/robot-build-relay/build.py` before republishing that artifact (102 items now).

Open mentor questions are in `hackathon-brief.md` and `supernode-scope/README.md`.

## Secrets

- **Never read, print or commit `.env`.** The root `.env` holds a model key. `start-supernode.sh` sources `node/.env` or the root `.env` without printing values.
- SuperNode private keys live **outside the repo** by default (`~/supernodes_keys/`). Never commit them: only the `.pub` gets registered. The root `.gitignore` covers `.env*`, `*.pem`, `*.key`, `.venv/`, `*.fab` and **`docs/private/`**. `node/.gitignore` adds `supernode-*` (except `*.pub`). Put any note containing account, pod or connection details in `docs/private/`, and never the key values themselves.
- Commits: no Claude/Anthropic model attribution or `Co-Authored-By` lines (the user's global rule).
