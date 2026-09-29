# What a SuperNode can be

Captured 2026-09-29 from 28 Flower Hub apps (source downloaded through the Hub API), the Flower docs, and the `flwr` 1.39.0 source. Nothing was run. The three detailed files were written in parallel, one per topic:

| File | Covers |
|---|---|
| [agent-and-multiparty-apps.md](agent-and-multiparty-apps.md) | soteria, rare-disease-consult-network, vanna-federation, local-node, gapcheck, Helmsman, bloomkit (+4 companion agents): roles, node config, message patterns, code to reuse |
| [devices-and-edge.md](devices-and-edge.md) | dronesar-fl, aifes (MCU), fedscene, ev-truck, fedler-farms, bouquetfl, quickstart-mlx, forest-monitoring: hardware floor, runtime footprint, intermittency |
| [data-platforms-and-privacy.md](data-platforms-and-privacy.md) | Armadillo, S3, fed-omop, fedrag, SuperNode auth, SecAgg+, DP, homomorphic encryption, smpc-fl: what nodes plug into, and how much privacy each mechanism really gives |

Related: [../supergrid-setup.md](../supergrid-setup.md) · [../agentapp-api-reference.md](../agentapp-api-reference.md) · Concept map artifact: https://claude.ai/artifact/Eyr5RcuZdx2yj6MQ57BtyC

---

## The short answer

**A SuperNode is one party's trust boundary, running as a Python process.** It holds something that party won't hand over, runs whatever app a run sends it, and replies with a **projection**: a summary, a score, a quote, or a model update. The raw data stays behind.

| Dimension | Range seen on the Hub | Details in |
|---|---|---|
| **Who** it represents | A hospital, freight carrier, manufacturer, FX desk, farm, drone, camera fleet, truck, or a teammate's laptop | agent-and-multiparty, devices-and-edge |
| **What** it holds | JSONL records, technical files, contracts, trading history, sensor or telemetry data, images, document indexes (RAG), local models | all three |
| **Smallest** machine | A 64-bit Linux single-board computer (Raspberry Pi 4/5/Zero 2). `flwr` 1.39 needs Python ≥ 3.11, gRPC, cryptography, SQLAlchemy, FastAPI and uv | devices-and-edge |
| **Not possible** | A microcontroller. The one MCU app bypasses SuperNodes entirely (raw MQTT to the ServerApp); the Flower-native design is a gateway SuperNode next to the MCUs | devices-and-edge |
| **Largest** | GPU servers and cloud containers (ResNet-18 / LLM fine-tuning nodes). Size is driven by the app's ML stack, not by `flwr` | devices-and-edge |
| **How it's told apart** | Operator `--node-config` keys (`data-dir`, `party`, `site-name`, `agent-profile`). Weaker apps use the simulation-only `partition-id` | agent-and-multiparty |
| **What it plugs into** | Only what app code on the node opens (a path, an S3 key, an Armadillo endpoint, a FAISS index). Flower has no built-in data connectors for these | data-platforms-and-privacy |
| **Who it talks to** | Only the coordinator (SuperLink / ServerApp). **No app has nodes talk to each other.** smpc-fl's "P2P" is relayed, in cleartext, through the ServerApp | all three |

## Findings that affect our build

1. **Nobody uses AgentApp Grid tools yet.** Every multi-party Hub app is a classic ServerApp + ClientApp using `send_and_receive`. The agent apps run as a single process. `collaborative-agent` is still the only public example of our master/worker-over-`agent.grid` design, which makes our entry distinctive.
2. **Model access is AgentApp-only.** `flwr/supercore/routers/runtime/responses.py:138` rejects model calls from anything that isn't an AgentApp task (verified). A ClientApp can't use Flower-hosted models, so the AgentApp route is the right one.
3. **Send one bundled message per supplier** carrying the whole request. Soteria measured this at 11–21× faster than one message per field, and in our runtime each message starts a separate worker task.
4. **Pick data and behaviour with `--node-config`, and fail closed.** Each supplier operator starts their node with, e.g., `--node-config 'data-dir="/abs/by-store/pololu.json" node-name="pololu"'`. The worker refuses to run if the key is missing, instead of silently guessing.
5. **Minimise data on the node before any model sees it.** The worker computes the quote in Python from its local catalogue and replies in a fixed format with no cost or margin field. This is the fedrag-style pattern, and it's the privacy mechanism that works in AgentApps today. SecAgg+, DP and HE are FL-only as shipped: AgentApps have no mod hook and send plain-text payloads.
6. **Keep SuperNodes online.** The SuperLink marks a node offline about 60 s after its last heartbeat. Sleeping laptops, or a Nebius endpoint that scales to zero, drop out of `get_nodes`.
7. **An AgentApp node is light.** No torch is needed, so a laptop or the `flwr/supernode` container (about 125 MB, alpine) is enough.

## Anti-patterns to avoid (seen in real Hub apps)

- **Private data inside the FAB.** Soteria and ev-truck ship data in the app bundle, so every node receives every party's files.
- **Credentials in `run_config`.** aws-flwr-demo ships AWS keys to every node; the Armadillo app sends every site's token to every node.
- **Matching replies to nodes by list position.** rare-disease-consult-network does this, so follow-ups can go to the wrong node. Match on `message_id` / `src_node_id` instead.
- **Roles from `partition-id`.** That key only exists in simulation. bloomkit gives every real node the same role when it's unset.
- **Crypto that trusts the coordinator.** In he-flower-example the aggregator holds the decryption key; smpc-fl relays cleartext shares. Read the trust model, not the README claim.

## Open questions (carried into the mentor list)

- Does `--trusted-entities` (a node-side signed-FAB check, which also covers AgentApp tasks) reject `/load .` builds?
- `flower-endeavor-v1.0` appears in Soteria as a model id. Is that the Endeavor id (bonus points)? Unverified.
- Do hackathon SuperNodes stay warm, or scale to zero?
