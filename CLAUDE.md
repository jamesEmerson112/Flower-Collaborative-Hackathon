# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose and plan

Team repo for the **Flower Collaborative Hackathon**. The challenge: show several Flower Agents collaborating on **SuperGrid**. Our design is **one AgentApp (one FAB)** that runs as the **master on the SuperLink** and as a **worker on every SuperNode**. The master fans tasks out with the Grid tools (`get_nodes` → `push_messages` → `pull_messages`), and each worker answers from **node-local private data** selected by its operator with `--node-config`. Suppliers each hold a private catalogue (one `docs/robot-parts-stores/data/by-store/<store>.json` per supplier node), compute quotes in Python, and reply with only what the master needs. `SuperNode_James/hello-app` proves this pattern with a greeting instead of a quote. Team federation: **`@efebahadirgur/Spartan`** (deployment federation; members can attach SuperNodes).

## Repo map

- `docs/`: team notes, and the **first place to look** before answering questions or searching the web.
  - `hackathon-brief.md`: the organizers' brief, model-endpoint setup, open mentor questions, and the **index of all links and artifacts**.
  - `agentapp-api-reference.md`: the dev reference for `flwr` 1.39.0 (AgentApp API, Grid tools, delivery semantics, model access, packaging, CLI, Hub API, error codes, an untested master/worker sketch in §10, and discrepancies in §11).
  - `supergrid-setup.md`: what SuperGrid is, federation and SuperNode setup, AgentApp caveats, and local dev.
  - `collab-agent-recipe.md`, `collaborative-agent.md`, `flwrlabs-agent.md`: source walkthroughs of the three Hub apps. `collaborative-agent` is the only one that uses `agent.grid`.
  - `supernode-scope/`: 28 Hub apps studied. `README.md` has the findings that shape our build and the anti-patterns to avoid.
  - `robot-parts-stores/`: the supplier dataset (8 stores, 95 items). `stores.json` is the source of truth, and `build.py` regenerates `index.html` and `data/`.
  - `agent/`, `collaborative-agent/`, `hackathon-collab-agent-recipe/`: **unmodified copies of Flower Hub apps**, kept for diffing against upstream. **Never edit them.**
  - `private/`: **git-ignored.** `runpod-supernode.md` is the private runbook with our identifiers (Flower account, node ID, pod ID and cost, SSH commands), a from-scratch RunPod SuperNode procedure, teardown and gotchas. It contains no secrets. Read it before touching the pod.
- `SuperNode_James/`: our first SuperNode experiment (read its `README.md`).
  - `node/`: turns a machine into SuperNode "james". `start-supernode.sh` plus the local `profile.json`, with no app code.
  - `hello-app/`: the minimal master/worker AgentApp. The node's name comes only from `profile.json`, never from the code.

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

# Regenerate the supplier dataset after editing stores.json (stdlib only; paths resolve from __file__, so any cwd works)
python3 docs/robot-parts-stores/build.py
```

Monitor runs with `flwr list supergrid`, `flwr log <run-id> supergrid --show` and `flwr stop <run-id> supergrid`. SuperNode registration steps are in `SuperNode_James/README.md` (Option B) and `supergrid-setup.md` §2.

## Hard-won facts (verify against the cited doc before changing course)

"api-ref" = `docs/agentapp-api-reference.md`, and "supergrid-setup" = `docs/supergrid-setup.md`.

- **Launch AgentApps with `flwr chat` → `/load .`, never `flwr run`.** `flwr run` sends no user prompt, so the SuperLink rejects it with `AGENTAPP_USER_PROMPT_REQUIRED` (44). As a result, `--run-config` overrides can't reach an AgentApp; only the pyproject defaults apply. See api-ref §7.3 and §6.2, and supergrid-setup "AgentApp caveats".
- **One FAB per run, so the app branches on role.** SuperNodes fetch the run's own FAB, so master and workers are the same code: `context.node_id == 1` means the SuperLink (master), and anything else is a worker. See api-ref §2.1 and §2.5, and `hello_app/agent_app.py`.
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
- **Everything else is read from the `flwr` 1.39.0 source, and most of it hasn't been run live.** Treat the notes as strong hypotheses and record the result when something is tested. Verified live so far: SuperNode registration and add-to-federation, a node coming online, device-flow login, the license requirement, and a **full master→worker Grid round trip** (`hello-app`, one node), including `flwr chat` → `/load .` running a local app on SuperGrid.

## Conventions

- **Notes go in `docs/`.** Write them to files, and link new material from the index in `hackathon-brief.md`.
- **Tag claims by provenance:** **[src]** (`flwr` 1.39.0 or app source, with the module cited), **[docs]** (flower.ai docs, with the date fetched), **[inference]** (our reading, unverified).
- **Keep the three Hub app copies under `docs/` byte-for-byte pristine.** Fork into a new folder instead.
- Private data must stay on the node (in a `--node-config` path), never in the FAB or in `run_config`. Match replies by `message_id` / `src_node_id`, not by list position. See supernode-scope/README "Anti-patterns".
- **The venue network is slow.** `uvx --from flwr` stalled downloading wheels there. To fetch a Hub app without the `flwr` CLI, `POST https://api.flower.ai/v1/hub/fetch-zip` with `{"app_id":"@pub/app","app_version":null,"flwr_version":"1.39.0"}` and download the returned `zip_url`. See api-ref §8 and collab-agent-recipe "Provenance".
- Set `publisher` in an app's `pyproject.toml` to your Flower username (the user's is **`zerocks2503`**). FABs are capped at 10 MB.

## Current state (2026-09-29, snapshot for /compact)

**Live infrastructure: SuperNode_James runs on a RunPod pod.** The full details and the repeatable procedure are in `docs/private/runpod-supernode.md` (git-ignored).
- Pod `fibicm4cy4pj0c` ("complicated_indigo_gecko"): CPU, 2 vCPU / 4 GB, **$0.07/hr**, EUR-IS-1, image `runpod/base:0.7.0-ubuntu2004`. Created by the user. **Stop it when you're done.** The user's other two pods are EXITED and not ours to touch.
- **Access only through the RunPod proxy:** `ssh -i ~/.ssh/id_ed25519 fibicm4cy4pj0c-6441181d@ssh.runpod.io`.
  - The direct TCP address `157.157.221.30:13080` is blocked by the venue network.
  - The Bash sandbox blocks SSH, so those calls need `dangerouslyDisableSandbox`.
  - The proxy needs `-tt` with commands fed on stdin, and has **no SCP**, so files go over as a base64 heredoc.
- On the pod:
  - `/root/SuperNode_James`, with uv, Python 3.11.13 and `flwr` 1.39.0 in `hello-app/.venv`.
  - The node key at `~/supernodes_keys/supernode-james`.
  - `flwr` logged in to SuperGrid as `zerocks2503`.
- **SuperNode `9674070929710601496`** (owner `zerocks2503`) is registered, **in `@efebahadirgur/Spartan`**, and **online**. `flower-supernode` runs as PID 2081.
- **tmux session `flower`** on the pod: window 0 `login`, window 1 `node` (the node process, log at `/tmp/supernode.log`), window 2 `chat` (`flwr chat` open with Spartan selected). The user watches with `tmux attach -t flower`.
- **✅ End-to-end test passed (verified live).** In the pod's chat window, `/load .` printed `Loaded @zerocks2503/hello-nodes from /root/SuperNode_James/hello-app`, then `say hello` returned `Asked 1 SuperNode(s): • node 9674070929710601496: Hello James`. The master ran on the SuperLink, `get_nodes` → `push_messages` → worker `push_reply_message` → `pull_messages` all worked, and the name came from the node-local `profile.json`. Spartan had exactly one online node at that moment.

**Tooling added this session**
- The Runpod Claude Code plugin (`runpod@runpod`) is installed and OAuth-signed-in, so the Runpod MCP tools (`list-pods`, `get-pod`, `pod-action`…) are available. Creating pods costs money: state the price and confirm first.

**Artifacts** (private until shared from each page's Share menu; all links are in `docs/hackathon-brief.md`)
- Trace Explorer, API Reference, 3D "Head Office & Stores", and the Flower Concept Map.
- Sources for the explorer and concept map live in the session scratchpad and are lost after the session. Republishing means rebuilding from these docs.

**Not done / pending**
- **Nothing is committed or pushed.** Today's changes are uncommitted: `docs/` (moved apps and new docs), `SuperNode_James/`, `.gitignore`, `CLAUDE.md`. The user hasn't approved a commit yet. `git status` shows the apps' old root paths as deleted; `git add -A` records them as renames, and `.env` is ignored.
- The local Mac `uv sync` in `SuperNode_James/hello-app` never finished (slow Wi-Fi), so there's no local `flwr`.
- Build the real supplier app: fork the hello pattern, give each supplier node `--node-config data-dir=…/by-store/<store>.json`, compute quotes in Python, and reply with no cost field. Open mentor questions are in `hackathon-brief.md` and `supernode-scope/README.md` (the Endeavor model id may be `flower-endeavor-v1.0`, unverified).

## Secrets

- **Never read, print or commit `.env`.** The root `.env` holds a model key. `start-supernode.sh` sources `node/.env` or the root `.env` without printing values.
- SuperNode private keys live **outside the repo** by default (`~/supernodes_keys/`). Never commit them: only the `.pub` gets registered. The root `.gitignore` covers `.env*`, `*.pem`, `*.key`, `.venv/`, `*.fab` and **`docs/private/`**. `node/.gitignore` adds `supernode-*` (except `*.pub`). Put any note containing account, pod or connection details in `docs/private/`, and never the key values themselves.
- Commits: no Claude/Anthropic model attribution or `Co-Authored-By` lines (the user's global rule).
