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

**The point of the experiment:** `hello_app/agent_app.py` never mentions James. The name comes from `node/profile.json`, which only this node can read, and the operator selects it with `--node-config 'profile="…"'`. Give a teammate's node a different `profile.json` and the same app answers "Hello Alice". Supplier catalogues will work the same way.

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

## Files

| File | Purpose |
|---|---|
| `node/profile.json` | This node's local data: `{"name": "James", "greeting": "Hello"}` |
| `node/start-supernode.sh` | Runs `flower-supernode` with the key and `--node-config 'profile="…" node-name="james"'` (`supergrid` or `local` mode). Override the key path with `SUPERNODE_KEY=…` |
| `node/.gitignore` | Keeps private keys and `.env` out of git |
| `hello-app/pyproject.toml` | The FAB definition: one `agentapp` component, `flwr>=1.39.0`, `license = { file = "LICENSE" }` (required by FAB format 1). `publisher` = your Flower username |
| `hello-app/hello_app/agent_app.py` | Master: `get_nodes` → `push_messages` → `pull_messages` (keeps each reply, since replies are returned once). Worker: read the profile → `push_reply_message` once |

## Notes

- **Verified live on 2026-09-29** on a RunPod CPU pod (SuperNode `9674070929710601496` in `@efebahadirgur/Spartan`): `flwr chat` → `/load .` → `say hello` returned `Asked 1 SuperNode(s): • node 9674070929710601496: Hello James`. Option A (local SuperLink) is still untested.
- The master calls the Grid tools from code, not through a model, so the fan-out is deterministic and needs no API key.
- The worker always replies once, even on a bad profile. A silent worker would leave the master waiting until its timeout.
- Keep the SuperNode process running during a demo. The SuperLink treats a node as offline shortly after its heartbeat stops, and `get_nodes` only lists online nodes.
