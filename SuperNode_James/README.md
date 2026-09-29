# SuperNode_James

A first experiment: turn a machine into the SuperNode **"james"** and have it answer **"Hello James"** when our app asks.

This folder holds two different things, kept apart on purpose:

| Folder | What it is | Where it runs |
|---|---|---|
| [`node/`](node/) | What makes a machine a SuperNode: a start script, the node's **local data** (`profile.json`), and its config. **No app code.** | On James's machine: this laptop, Docker, RunPod, Nebius… |
| [`hello-app/`](hello-app/) | **The one app.** Runs as the **master on the SuperLink** and as a **worker on every SuperNode** | Sent with each run by `flwr chat` → `/load .` |

```
flwr chat → /load hello-app ──► SuperLink: hello-app as master
                                   │ push_messages: "greet"
                                   ▼
                     SuperNode "james": hello-app as worker
                        reads node/profile.json  (local, never sent)
                                   │ push_reply_message: "Hello James"
                                   ▼
                     master prints:  - node <id>: Hello James
```

**The point of the experiment:** the app code (`hello-app/hello_app/`) never mentions James. The name comes from `node/profile.json`, which only this node can read, and the operator selects it with `--node-config 'profile="…"'`. Give a teammate's node a different `profile.json` and the same app answers "Hello Alice". Supplier catalogues will work the same way.

---

## Prerequisites

- Python ≥ 3.11 and [`uv`](https://docs.astral.sh/uv/).
- Install Flower into the app's environment (this also provides `flower-superlink` and `flower-supernode`):
  ```bash
  cd SuperNode_James/hello-app
  uv sync
  source .venv/bin/activate
  ```
- Model credentials go in a git-ignored `.env` (`node/.env` or the repo root) as `FLWR_MODEL_API_KEY=…` (plus `FLWR_MODEL_API_ENDPOINT=…` for Nebius). `start-supernode.sh` loads it automatically; for a local `flower-superlink`, run `set -a; . ../../.env; set +a` first. **Not** `FLWR_RUNTIME_API_KEY`: Flower injects that one per task.
- The hello app makes **no model calls**, so no model API key is needed. For a real app, set the model env vars on the node machine before starting the SuperNode (Flower AI: `FLWR_MODEL_API_KEY`; Nebius Token Factory: also `FLWR_MODEL_API_ENDPOINT`). See [../docs/hackathon-brief.md](../docs/hackathon-brief.md).

## Option A: try it locally (no SuperGrid)

Everything on one machine, in three terminals (all with `.venv` activated). This path is **untested**: it follows the Flower local-SuperLink guide and the `flwr` 1.39.0 defaults.

```bash
# Terminal 1: a local SuperLink (control plane)
flower-superlink --insecure

# Terminal 2: turn this machine into SuperNode "james"
cd SuperNode_James/node
./start-supernode.sh local          # connects to 127.0.0.1:9092

# Terminal 3: run the app
#   one-time: add to ~/.flwr/config.toml
#     [superlink.local-agent]
#     address = "127.0.0.1:8000"
#     insecure = true
cd SuperNode_James/hello-app
export FLWR_CHAT_SUPERLINK=local-agent
flwr chat
#   /load .
#   say hello
```

Expected answer in chat:

```
Asked 1 SuperNode(s):
- node <id>: Hello James
```

## Option B: a real SuperNode on SuperGrid

**Our team federation: `@efebahadirgur/Spartan`** (owner: efebahadirgur). Members can connect SuperNodes to it (deployment federations only), so we don't need to create a federation.

**B1. Create the node's key pair.** This is the node's identity, not SSH access to a machine.
```bash
mkdir -p ~/supernodes_keys
ssh-keygen -t ecdsa -b 384 -N "" -C "supernode-james" -f ~/supernodes_keys/supernode-james
```
The private key (`supernode-james`) never leaves this machine. The public key (`.pub`) gets registered. `-C` replaces the default `<username>@<hostname>` comment, so the registered key doesn't reveal your login or machine name. Use a fresh key pair like this one, not your personal `~/.ssh` keys.

**B2. Register it with SuperGrid, then add it to a federation.**
```bash
flwr login supergrid
flwr supernode register ~/supernodes_keys/supernode-james.pub supergrid   # or the UI at flower.ai/supernodes
flwr supernode list supergrid --verbose                                    # note the SuperNode ID
flwr federation add-supernode <supernode-id> @efebahadirgur/Spartan supergrid
```

**B3. Start the node and keep it running.** It connects outbound to `fleet-supergrid.flower.ai:443`; no inbound ports are needed.
```bash
cd SuperNode_James/node
./start-supernode.sh supergrid
```

**B4. Run the app from anywhere** (any member of the federation):
```bash
cd SuperNode_James/hello-app
flwr chat
#   /federation @efebahadirgur/Spartan
#   /load .
#   say hello
```
Every online node in the federation answers with its own profile. Nodes without a `profile` config reply `PROFILE_ERROR: …` instead of staying silent.

---

## Working as a team (SuperLink dev + SuperNode dev)

Both roles live in **one app**, because every SuperNode downloads the app package of the run it's serving. So you split the work by file, not by project:

| File | Owner | Runs on |
|---|---|---|
| `hello_app/protocol.py` | **Both. Agree on it first.** It defines the task format (`make_task` / `read_task`) and says replies are plain text | both |
| `hello_app/master.py` | SuperLink dev | SuperLink (`node_id == 1`) |
| `hello_app/worker.py` | SuperNode dev | every SuperNode |
| `hello_app/common.py` | shared, rarely touched | both (`grid()` and `say()`) |
| `hello_app/agent_app.py` | shared, rarely touched | both (role switch only) |
| `node/` | SuperNode dev | the SuperNode machine only, **never packaged** |

- The only coupling between `master.py` and `worker.py` is `protocol.py`. To add a task type, add a constant and builder there, send it from `master.py`, and handle it in `worker.py`'s `answer()`.
- **Trap:** the worker code a node runs is whatever was in the folder loaded with `/load .`, **not** the code on the node's disk. Pull `main` before running `/load .`, or the nodes run your stale `worker.py`.

## Adding more SuperNodes

The app isn't tied to one SuperNode. Each run goes to **every online node in the federation you picked**, and `get_nodes` finds them all. To add a node, repeat Option B with a **new name and a new key**. The Flower docs say: "Do not reuse a key pair across multiple SuperNodes."

| Where the new node runs | What changes |
|---|---|
| **Another machine** (a teammate's laptop, another pod) | Nothing in the code. Copy `node/`, change `profile.json` (e.g. `{"name": "Alice"}`), generate `~/supernodes_keys/supernode-alice` (B1), register it and add it to Spartan (B2), then start it with `SUPERNODE_NAME=alice ./start-supernode.sh supergrid` |
| **The same machine** as another node | The same steps, plus a free local port. Each `flower-supernode` opens a Runtime HTTP API on `127.0.0.1:9094` by default, so the second one needs another port: `SUPERNODE_NAME=alice SUPERNODE_PROFILE=/abs/alice.json SUPERNODE_PORT=9095 ./start-supernode.sh supergrid` **[src]** `flwr/supernode/cli/flower_supernode.py` `--port`, `supercore/constant.py`. **Verified live:** 3 nodes on one pod, on ports 9094–9096 |

`start-supernode.sh` overrides: `SUPERNODE_NAME` (default `james`; also picks the key `~/supernodes_keys/supernode-<name>`), `SUPERNODE_KEY`, `SUPERNODE_PROFILE`, and `SUPERNODE_PORT` (default `9094`).

With two nodes online, `say hello` should answer `Asked 2 SuperNode(s):` with one line per node, each from its own `profile.json`.

---

## Files

| File | Purpose |
|---|---|
| `node/profile.json` | This node's local data: `{"name": "James", "greeting": "Hello"}` |
| `node/start-supernode.sh` | Runs `flower-supernode` with the key, `--port` and `--node-config 'profile="…" node-name="james"'` (`supergrid` or `local` mode). Override with `SUPERNODE_NAME` / `SUPERNODE_KEY` / `SUPERNODE_PROFILE` / `SUPERNODE_PORT` |
| `node/.gitignore` | Keeps private keys and `.env` out of git |
| `hello-app/pyproject.toml` | The FAB definition: one `agentapp` component, `flwr>=1.39.0`, `license = { file = "LICENSE" }` (required by FAB format 1). `publisher` = your Flower username |
| `hello-app/hello_app/agent_app.py` | Entry point. Picks the role: `node_id == 1` runs `run_master`, anything else runs `run_worker` |
| `hello-app/hello_app/master.py` | Master: `get_nodes` → `push_messages` → `pull_messages` (keeps each reply, since replies are returned once) → one summary line per node |
| `hello-app/hello_app/worker.py` | Worker: `read_task` → `answer()` (read the profile, build the greeting) → `push_reply_message` exactly once, even on errors |
| `hello-app/hello_app/protocol.py` | The master/worker contract: `TASK_GREET`, `make_task()`, `read_task()` (unwraps the Grid envelope) |
| `hello-app/hello_app/common.py` | `grid()` (call a Grid tool from code) and `say()` (show text in `flwr chat` and end the response) |

## Notes

- **Verified live on 2026-09-29** on a RunPod CPU pod (SuperNode `9674070929710601496` in `@efebahadirgur/Spartan`): `flwr chat` → `/load .` → `say hello` returned `Asked 1 SuperNode(s): • node 9674070929710601496: Hello James`. Option A (local SuperLink) is still untested. The role-split version (`master.py` / `worker.py` / `protocol.py` / `common.py`) was then verified live with 3 SuperNodes on the same pod: `say hello` returned `Asked 7 SuperNode(s)`, with `Hello James`, `Hello James_2_Pod1` and `Hello James_3_Pod1` from ours, plus `PROFILE_ERROR` from 4 teammate nodes that have no `profile` node-config.
- The master calls the Grid tools from code, not through a model, so the fan-out is deterministic and needs no API key.
- The worker always replies once, even on a bad profile. A silent worker would leave the master waiting until its timeout.
- Keep the SuperNode process running during a demo. The SuperLink treats a node as offline shortly after its heartbeat stops, and `get_nodes` only lists online nodes.
