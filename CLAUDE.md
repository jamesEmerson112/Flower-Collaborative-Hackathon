# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose and plan

Team repo for the **Flower Collaborative Hackathon**. The challenge: show several Flower Agents collaborating on **SuperGrid**. Our design is **one AgentApp (one FAB)** that runs as the **master on the SuperLink** and as a **worker on every SuperNode**. The master fans tasks out with the Grid tools (`get_nodes` → `push_messages` → `pull_messages`), and each worker answers from **node-local private data** selected by its operator with `--node-config`. Suppliers each hold a private catalogue (one `docs/robot-parts-stores/data/by-store/<store>.json` per supplier node), compute quotes in Python, and reply with only what the master needs. `SuperNode_James/hello-app` proves this pattern with a greeting instead of a quote.
**Decision (2026-09-29): one LLM, on the master only.** It plans the parts list from the user's words and combines the offers. Workers do plain-code retrieval (`search_catalog` on the node's catalogue) with no model, so nodes need no model key. Revisit worker LLMs only if stores' data formats diverge or the demo needs "each store is its own agent". The design rationale is in `docs/artifacts/robot-build-relay/` (the simulated demo). Team federation: **`@efebahadirgur/Spartan`** (deployment federation; members can attach SuperNodes).

## Repo map

- `docs/`: team notes, and the **first place to look** before answering questions or searching the web.
  - `hackathon-brief.md`: the organizers' brief, model-endpoint setup, open mentor questions, and the **index of all links and artifacts**.
  - `agentapp-api-reference.md`: the dev reference for `flwr` 1.39.0 (AgentApp API, Grid tools, delivery semantics, model access, packaging, CLI, Hub API, error codes, an untested master/worker sketch in §10, and discrepancies in §11).
  - `supergrid-setup.md`: what SuperGrid is, federation and SuperNode setup, AgentApp caveats, and local dev.
  - `collab-agent-recipe.md`, `collaborative-agent.md`, `flwrlabs-agent.md`: source walkthroughs of the three Hub apps. `collaborative-agent` is the only one that uses `agent.grid`.
  - `supernode-scope/`: 28 Hub apps studied. `README.md` has the findings that shape our build and the anti-patterns to avoid.
  - `robot-parts-stores/`: the supplier dataset (8 stores, 95 items). `stores.json` is the source of truth, and `build.py` regenerates `index.html` and `data/`.
    - `classified/` (added by the user or a teammate, not by Claude): the same 95 items researched further, with robot roles, component types, images, evidence and CAD links. It has **one identically formatted CSV per store** (`by-store/`), plus `all_parts.csv`, `schema.json` and `taxonomy.json`. This may be the better per-node worker catalogue.
    - `cad/` (also not ours): CAD assets for 50 of the 95 products. The downloads (`originals/`, `extracted/`, about 930 MB) are git-ignored; only the manifest and CSVs are tracked.
  - `robot-builder/`: **the user's side project ("Robot Workshop", a Vite browser builder). Ignore it:** don't read, edit or build it unless the user asks. Its `node_modules/` and `dist/` are git-ignored.
  - `artifacts/robot-build-relay/`: source of the **Robot Build Relay** artifact, a simulated supplier-quote run over the 8 stores. `page.template.html` plus `build.py`, which injects `stores.json` and runs `node --check`. Rebuild, then republish `robot-build-relay.html`.
  - `agent/`, `collaborative-agent/`, `hackathon-collab-agent-recipe/`: **unmodified copies of Flower Hub apps**, kept for diffing against upstream. **Never edit them.**
  - `private/`: **git-ignored.** `runpod-supernode.md` is the private runbook with our identifiers (Flower account, node ID, pod ID and cost, SSH commands), a from-scratch RunPod SuperNode procedure, teardown and gotchas. It contains no secrets. Read it before touching the pod.
- `SuperNode_James/`: our first SuperNode experiment (read its `README.md`).
  - `node/`: turns a machine into SuperNode "james". `start-supernode.sh` plus the local `profile.json`, with no app code.
  - `hello-app/`: the minimal master/worker AgentApp, split by role so two people can work in parallel. `hello_app/agent_app.py` is only the role switch. `master.py` runs on the SuperLink and `worker.py` on each SuperNode. `protocol.py` is the task/reply contract between them, and `common.py` holds `grid()` / `say()`. The node's name comes only from `profile.json`, never from the code.
  - `master-ui/`: a browser front end for the master. `bridge.py` is a stdlib localhost server that does what `flwr chat` does, using flwr 1.39.0's CLI internals (`build_local_agent`, `start_chat_run`, `StreamRunEvents`), and streams every run event as NDJSON. `index.html` shows the answer plus the Grid calls `flwr chat` hides. Verified end to end with `curl` on the pod; the page itself hasn't been opened in a browser yet.

## Commands

There is no test suite, linter or CI. The only check is a live run through `flwr chat`. The repo path contains spaces, so quote it in `cd`.

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
- **Each model request is its own task, not one shared model.** `responses.create` becomes a MODEL task on the machine that made it (`routers/runtime/responses.py:188`), using that machine's `FLWR_MODEL_API_KEY` / endpoint (`task_process/model/provider.py:79–92`). SuperNodes host the endpoint too (`supernode/main.py:81`), so workers can have their own LLM (as `collaborative-agent` does). The docs say "each Responses request creates a Flower model task", so use `max_retries=0`. Calls share no memory. **Our 3 pod nodes have no `FLWR_MODEL_API_KEY`**, so worker model calls would fail there.
- **`push_messages` takes a per-message `dst_node_id` and `payload`** (`task_process/agent/grid.py:118–136`), so the master can send each node a different task or prompt.
- **`flwr chat` takes no arguments** (`def chat() -> None`). It talks protobuf over HTTPS (`api.flower.ai/v1/control/start-run`, then `stream-run-events`) using the `flwr login` tokens in `~/.flwr`. A browser can't do that directly, which is why `master-ui/bridge.py` exists.
- **Everything else is read from the `flwr` 1.39.0 source, and most of it hasn't been run live.** Treat the notes as strong hypotheses and record the result when something is tested. Verified live so far: SuperNode registration and add-to-federation, a node coming online, device-flow login, the license requirement, and a **full master→worker Grid round trip** (`hello-app`, one node, then 3 of ours on one pod plus 4 teammate nodes), **several SuperNodes on one machine via different `--port`s**, including `flwr chat` → `/load .` running a local app on SuperGrid.

## Conventions

- **Notes go in `docs/`.** Write them to files, and link new material from the index in `hackathon-brief.md`.
- **Tag claims by provenance:** **[src]** (`flwr` 1.39.0 or app source, with the module cited), **[docs]** (flower.ai docs, with the date fetched), **[inference]** (our reading, unverified).
- **Keep the three Hub app copies under `docs/` byte-for-byte pristine.** Fork into a new folder instead.
- Private data must stay on the node (in a `--node-config` path), never in the FAB or in `run_config`. Match replies by `message_id` / `src_node_id`, not by list position. See supernode-scope/README "Anti-patterns".
- **The venue network is slow.** `uvx --from flwr` stalled downloading wheels there. To fetch a Hub app without the `flwr` CLI, `POST https://api.flower.ai/v1/hub/fetch-zip` with `{"app_id":"@pub/app","app_version":null,"flwr_version":"1.39.0"}` and download the returned `zip_url`. See api-ref §8 and collab-agent-recipe "Provenance".
- Set `publisher` in an app's `pyproject.toml` to your Flower username (the user's is **`zerocks2503`**). FABs are capped at 10 MB.

## Current state (2026-09-29, snapshot for /compact)

**Live infrastructure: 3 of our SuperNodes on one RunPod pod.** The full details and the repeatable procedure are in `docs/private/runpod-supernode.md` (git-ignored).
- Pod `fibicm4cy4pj0c` ("complicated_indigo_gecko"): CPU, 2 vCPU / 4 GB, **$0.07/hr**, EUR-IS-1, image `runpod/base:0.7.0-ubuntu2004`. Created by the user. **Stop it when you're done** (it was still RUNNING at the last check). The user's other two pods are EXITED and not ours to touch.
- **Access only through the RunPod proxy:** `ssh -i ~/.ssh/id_ed25519 fibicm4cy4pj0c-6441181d@ssh.runpod.io`.
  - The direct TCP address `157.157.221.30:13080` is blocked by the venue network.
  - The Bash sandbox blocks SSH, so those calls need `dangerouslyDisableSandbox`.
  - The proxy needs `-tt` with commands fed on stdin, and has **no SCP**, so files go over as a base64 heredoc (tar of `SuperNode_James`, excluding `.venv`/`uv.lock`/`.env`).
- On the pod: `/root/SuperNode_James` (the refactored copy, including `master-ui/`), uv, Python 3.11.13, `flwr` 1.39.0 in `hello-app/.venv`, and `flwr` logged in as `zerocks2503`. Keys are in `~/supernodes_keys/supernode-{james,James_2_Pod1,James_3_Pod1}`.
- **SuperNodes, all online and in `@efebahadirgur/Spartan`, owner `zerocks2503`:** `james` = `9674070929710601496` (port 9094, PID 2081); `James_2_Pod1` = `3446080994785355467` (port 9095, PID 3053); `James_3_Pod1` = `8936488704647726645` (port 9096, PID 3063). Profiles are in `SuperNode_James/node/profile.json` and `node/<name>/profile.json`. About 135 MB each (measured).
- **Spartan also has 4 teammate SuperNodes:** `motor-a`, `motor-b`, `camera-a` and `battery-a` (IDs `6111386887060621717`, `13119347499498202955`, `14444646481831250541`, `3342843433609131587`). They now have profiles, and every Spartan run executes on them too.
- **tmux session `flower`** on the pod: `0:login`, `1:node` (james, log `/tmp/supernode.log`), `2:chat` (`flwr chat` with Spartan and `/load .`), `3:James_2_Pod1` and `4:James_3_Pod1` (logs `/tmp/supernode-<name>.log`), and `5:ui`, where **`master-ui/bridge.py` is still running on the pod's `127.0.0.1:8765`** (log `/tmp/bridge.log`, reachable only inside the pod). The user watches with `tmux attach -t flower`.
- **Latest verified run (through `master-ui` on the pod, with curl):** `say hello` → **`Asked 7 SuperNode(s)`, 7/7 replies** (`Hello James`, `Hello James_2_Pod1`, `Hello James_3_Pod1`, `Hello from motor-a`…), with `get_nodes` / `push_messages` / `pull_messages` visible in the event stream, then `response.completed` and `done` with `terminal_seen: true`.

**Local Mac:** `flwr` 1.39.0 is now installed in `SuperNode_James/hello-app/.venv` (Python 3.13). The bridge imports and builds the FAB there (`@zerocks2503/hello-nodes`, about 11 KB). It's unconfirmed whether the user has run `flwr login supergrid` on the Mac (there was no `~/.flwr` at the last check).

**Tooling:** the Runpod Claude Code plugin (`runpod@runpod`) is installed and signed in, so the Runpod MCP tools (`list-pods`, `get-pod`, `pod-action`…) are available. Creating pods costs money: state the price and confirm first.

**Artifacts** (private until shared from each page's Share menu; all links are in `docs/hackathon-brief.md`)
- Trace Explorer, API Reference, 3D "Head Office & Stores", the Flower Concept Map, and **Robot Build Relay** (https://claude.ai/artifact/N6JoZqpwvv1iZ63vPJezNK).
- Only Robot Build Relay has its source in the repo. The others' sources were in a past session's scratchpad and are gone; republishing them means rebuilding from the docs.

**Git**
- `798fa2e` "successfully deploy a supernode" is committed and pushed (by the user).
- **Uncommitted since then:** the `hello-app` role split (`master.py`, `worker.py`, `protocol.py`, `common.py`), `start-supernode.sh` overrides (`SUPERNODE_NAME` / `SUPERNODE_PROFILE` / `SUPERNODE_PORT`), `node/James_2_Pod1/` and `node/James_3_Pod1/`, `master-ui/`, `docs/artifacts/`, plus README, `CLAUDE.md` and `hackathon-brief.md` edits. The user's side project `docs/robot-builder/` (ignore it) and the `robot-parts-stores/classified/`, `cad/` and README additions are also untracked or modified. Git would add only about 1 MB of those; the big assets are ignored. Commit only when the user asks.

**Next (agreed direction; not started)**
- **Build the supplier app** under the one-LLM decision: fork `hello-app`.
  - `protocol.py` gets a `quote` task: `{"task": "quote", "parts": [{category, qty, need, max_price}], "budget"}`, and a fixed offer reply format.
  - `worker.py` reads `--node-config catalog="…"` and runs a plain-code `search_catalog`, then replies with offers only. Consider `classified/by-store/*.csv` as the catalogue.
  - `master.py` makes two model calls: plan (user text → task JSON, with the category vocabulary in `instructions`) and combine (offers → answer). Its fallback is the deterministic combine logic in `docs/artifacts/robot-build-relay/page.template.html` (`combine()`).
  - Give the 3 pod nodes real store catalogues.
- **Check first:** whether the master's model calls work on SuperGrid with no setup on our side. The master runs on Flower's SuperLink; untested. Model ID to try: `openai/gpt-5.6-sol`. Endeavor's ID is unverified (maybe `flower-endeavor-v1.0`).
- The master UI page hasn't been opened in a browser yet.
- Open mentor questions are in `hackathon-brief.md` and `supernode-scope/README.md`.

## Secrets

- **Never read, print or commit `.env`.** The root `.env` holds a model key. `start-supernode.sh` sources `node/.env` or the root `.env` without printing values.
- SuperNode private keys live **outside the repo** by default (`~/supernodes_keys/`). Never commit them: only the `.pub` gets registered. The root `.gitignore` covers `.env*`, `*.pem`, `*.key`, `.venv/`, `*.fab` and **`docs/private/`**. `node/.gitignore` adds `supernode-*` (except `*.pub`). Put any note containing account, pod or connection details in `docs/private/`, and never the key values themselves.
- Commits: no Claude/Anthropic model attribution or `Co-Authored-By` lines (the user's global rule).
