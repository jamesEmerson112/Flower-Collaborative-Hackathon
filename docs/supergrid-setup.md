# SuperGrid setup for the team

Captured 2026-09-29 from the Flower docs and the `flwr` 1.39.0 source. Nothing here has been run yet.
Tags: **[docs]** Flower docs · **[src]** `flwr` 1.39.0 source · **[inference]** our reading, not verified.

---

## What SuperGrid is

- **Flower SuperGrid is Flower Labs' hosted federated-AI platform.** Flower's own comparison is that it "builds on the Flower Framework" the way GitHub builds on Git. It has been in Early Access since Sept 2025 **[docs]**.
- In the CLI, `supergrid` is just a named SuperLink connection pointing at Flower's hosted SuperLink. The default `~/.flwr/config.toml` has **[src]** `flwr/cli/constant.py`:
  ```toml
  [superlink.supergrid]
  address = "api.flower.ai"
  ```
- "Grid" comes from Flower's messaging API, `flwr.serverapp.Grid` (`get_nodes`, `push_messages`, `pull_messages`, `send_and_receive`). `agent.grid` exposes the same API to AgentApps as model tools **[src]**. It's the grid of machines, as in grid computing, **not** a CUDA/cuTile launch grid.

### GitHub analogy

| GitHub | Flower |
|---|---|
| Git (self-hosted) | Flower framework: run your own SuperLink |
| GitHub (hosted) | **SuperGrid**: Flower hosts the SuperLink |
| Actions control plane | SuperLink: schedules runs and routes messages |
| Self-hosted runners inside your network | **SuperNodes**: your machines, next to your data, connected outbound |
| Workflow / action package | FAB (app bundle) |
| Marketplace / public repos | **Flower Hub** |
| Account / org | Flower account / federation `@<owner>/<fed>` |

**GitHub is where the code lives; SuperGrid is where it runs.** They don't compete:

```
VS Code ──edit──► this GitHub repo (the app code)
                      │  flwr chat → /load .
                      ▼  (packages the folder into a FAB and submits it)
                 SuperGrid: Flower-hosted SuperLink
                      │  routes tasks
            ┌─────────┼─────────┐
       SuperNode   SuperNode   SuperNode   ← machines connected to our federation
```

Nothing is uploaded ahead of time. `/load .` bundles the local folder and submits it with each run. Publishing to Flower Hub is optional.

### Why SuperGrid instead of self-hosting

- **No server to run.** You don't host, secure or expose a SuperLink. It comes with TLS and Flower-account sign-in. SuperNodes connect **outbound** to `fleet-supergrid.flower.ai:443`, so laptops behind a firewall or home router work **[docs]**.
- **Federation management.** Register SuperNodes by public key, invite members, and add nodes to federations from the UI or the CLI **[docs]**.
- **Model access built in.** The runtime injects `FLWR_RUNTIME_BASE_URL` / `FLWR_RUNTIME_API_KEY`, so there are no provider keys in the app **[src]**.
- **Features the local SuperLink doesn't have:** account connectors (GitHub, Slack, Notion, Attio; personal federation only), the web chat UI, and run logs and history **[docs]**.
- **Hackathon:** the brief requires "the existing SuperGrid infrastructure".

---

## SuperNodes: machines, not projects

- A SuperNode has **no code of its own**. It's the `flower-supernode` process running on a machine and identified by a key pair. When a run reaches it, it downloads that run's FAB automatically **[src]** (`flwr/supernode/start_client_internal.py`).
- **Everyone works on the one app in this repo.** Teammates don't build separate "SuperNode projects".
- **SuperNodes never talk to each other.** Joining a federation lets the **SuperLink**, where the master agent runs, send your node tasks and receive its replies **[src]** (`grid.py`: SuperNodes get only `push_reply_message`).

```
your SuperNode ◄──task── SuperLink (master) ──task──► teammate's SuperNode
your SuperNode ──reply─► SuperLink (master) ◄─reply── teammate's SuperNode
your SuperNode  ✕──────── no direct link ────────✕  teammate's SuperNode
```

To get your node's output to a teammate's node, the **master relays it**: it collects your reply and sends it to their node as a new task.

**Why each teammate should run a node:** every node runs the same app, so what makes suppliers different has to be **node-local**: files (via `FLWR_FILESYSTEM_ALLOWED_DIRS`), `--node-config`, and name/location. A node per teammate gives each "supplier" its own private data. See [collaborative-agent.md](collaborative-agent.md).

---

## Step by step

### 1. Federation (owner, once)

```bash
flwr login supergrid                                   # opens the browser
flwr federation create <fed> supergrid --description "Hackathon orchestrator"   # deployment federation
flwr federation invite create <teammate> @<owner>/<fed> supergrid              # repeat per teammate
```

Teammates accept with `flwr federation invite accept @<owner>/<fed> supergrid`, or from their flower.ai profile page **[docs]**.

| Role | Can |
|---|---|
| Owner | Invite and remove members, archive the federation |
| Member | Launch runs, see other members' runs, leave, **connect SuperNodes** (deployment federations only) |

Other commands: `flwr federation list supergrid [--federation @<owner>/<fed>]`, `flwr federation invite list supergrid`, `flwr federation remove-account @<owner>/<fed> <account> supergrid`, `flwr federation archive @<owner>/<fed> supergrid` (can't be undone) **[docs]**.

### 2. SuperNode (each teammate)

| Step | What it does | Command |
|---|---|---|
| Key pair | Gives the node an identity | `mkdir -p ~/supernodes_keys && ssh-keygen -t ecdsa -b 384 -N "" -f ~/supernodes_keys/supernode-1` |
| Register | SuperGrid learns the node's public key | `flwr supernode register ~/supernodes_keys/supernode-1.pub supergrid` (or the UI at flower.ai/supernodes) |
| Find the ID | Needed to add the node to the federation | `flwr supernode list supergrid --verbose` |
| Add to federation | Runs in that federation can reach the node | `flwr federation add-supernode <supernode-id> @<owner>/<fed> supergrid` |
| Keep it running | Connects outbound and waits for tasks | see below |

```bash
flower-supernode \
    --superlink fleet-supergrid.flower.ai:443 \
    --auth-supernode-private-key ~/supernodes_keys/supernode-1
# or Docker: flwr/supernode:1.39.0 with the same flags, keys mounted read-only
```

- **Keep it online during the demo.** `get_nodes` returns only **online** nodes in the run's federation **[src]**. If a laptop sleeps, the master can't see that node.
- The node's environment needs the app's dependencies (`flwr`, `openai`), or `--allow-runtime-dependency-installation` **[docs]**.
- Per the hackathon brief, a SuperNode needs `FLWR_MODEL_API_KEY` (plus `FLWR_MODEL_API_ENDPOINT` for Nebius) to reach a model. See [hackathon-brief.md](hackathon-brief.md).
- Never share the private key (`supernode-1` without `.pub`).

### 3. Run the master (anyone in the federation)

```bash
cd <our-app-folder>
uv sync
uv run flwr chat
# at the chat prompt:
/federation @<owner>/<fed>
/load .
Ask each supplier for a quote on …
```

Monitor with `flwr list supergrid`, `flwr list --run-id <id> supergrid`, `flwr log <id> supergrid --show`, `flwr stop <id> supergrid`, or the dashboard at flower.ai/federations **[docs]**.

---

## AgentApp caveats (the framework docs are written for ServerApp/ClientApp apps)

- **Use `flwr chat`, not `flwr run`.** The "Run Flower Apps on SuperGrid" guide uses `flwr run . --federation …` with `--run-config` overrides. That's fine for classic FL apps, but the SuperLink rejects AgentApp runs without a user prompt (`AGENTAPP_USER_PROMPT_REQUIRED`), and `flwr run` doesn't send one **[src]** (`control_handlers.py`, `cli/run/run.py`). As a result, `--run-config` overrides can't reach an AgentApp either.
- **Use a Deployment federation, not a Simulation one.** The SuperLink only uses the simulation runtime for FABs that **aren't** AgentApps (`if sim_cfg and not is_agentapp_bundle`) **[src]**. An AgentApp in a simulation federation runs as a normal deployment with no simulated SuperNodes, so `get_nodes` would most likely return nothing **[inference]**.
- **Hub's web "Run" button:** documented for FL apps. Whether it works for AgentApps, which need a prompt, is unknown.

---

## Local development (optional)

For fast iteration on the master's logic without SuperGrid **[docs]** (`run-with-local-superlink`):

```bash
export FLWR_MODEL_API_KEY="<key>"          # or FLWR_MODEL_API_ENDPOINT for a custom Open Responses endpoint
uv run flower-superlink --insecure         # keep this terminal open
# ~/.flwr/config.toml:
#   [superlink.local-agent]
#   address = "127.0.0.1:8000"
#   insecure = true
export FLWR_CHAT_SUPERLINK=local-agent
uv run flwr chat
```

AgentApps run locally without SuperNodes. There's no sign-in, no account connectors, and no TLS, so use it for local development only. Testing Grid fan-out locally would also mean starting local `flower-supernode`s **[inference, untested]**.

## Editor

It's a normal Python project (`pyproject.toml` + `uv`), so any editor works:
1. Open the repo in VS Code.
2. Run `uv sync` and select `.venv` as the interpreter.
3. Run `flwr` in the integrated terminal. `flwr chat` is itself a terminal UI.

No extension is needed. We didn't find an official Flower VS Code extension, but we didn't search specifically.

---

## Open questions for mentors

- [ ] Do hackathon accounts have **deployment-federation access**, or should we join an existing hackathon federation?
- [ ] Can we attach our **own SuperNodes** (laptops / Nebius) to it, and does each node need its own `FLWR_MODEL_API_KEY`?
- [ ] Do the hackathon SuperNodes accept any run's FAB (cold install), or only preloaded apps?
- [ ] Does the Hub's web **Run** button support AgentApps?

## Sources

- [Announcing Flower SuperGrid](https://flower.ai/blog/2025-09-25-flower-supergrid/)
- [Run Flower Apps on SuperGrid](https://flower.ai/docs/framework/how-to-run-flower-apps-on-supergrid.html)
- [Create and manage federations](https://flower.ai/docs/framework/how-to-create-and-manage-federations.html)
- [Connect SuperNodes to SuperGrid](https://flower.ai/docs/framework/how-to-connect-supernodes-to-supergrid.html)
- [Authenticate SuperNodes](https://flower.ai/docs/framework/how-to-authenticate-supernodes.html)
- [Run AgentApps with a local SuperLink](https://flower.ai/docs/agent/how-to-guides/run-with-local-superlink.html)
- [Run an AgentApp on SuperGrid](https://flower.ai/docs/agent/how-to-guides/run-on-supergrid.html)
- [Flower CLI reference](https://flower.ai/docs/framework/ref-api-cli.html)
- `flwr` 1.39.0 source: `flwr/cli/constant.py`, `flwr/serverapp/grid/grid.py`, `flwr/cli/run/run.py`, `flwr/cli/federation/`, `flwr/cli/supernode/register.py`, `flwr/supernode/cli/flower_supernode.py`, `flwr/superlink/servicer/control/control_handlers.py`, `flwr/supercore/task_process/agent/grid.py`
- Related notes: [agentapp-api-reference.md](agentapp-api-reference.md) · [collaborative-agent.md](collaborative-agent.md) · [hackathon-brief.md](hackathon-brief.md)
