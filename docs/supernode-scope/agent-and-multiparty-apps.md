# What a SuperNode can be: agent-based and multi-party coordinator apps

Captured 2026-09-29 from Flower Hub app bundles and the `flwr` 1.39.0 source. Nothing was run.
Tags: **[src]** read in the app's code (or `flwr` 1.39.0 where stated) · **[docs]** app README or Hub page · **[inference]** our reading, not verified.
File references are relative to each app's root folder. "Our §N" means that section of [../agentapp-api-reference.md](../agentapp-api-reference.md). Sibling notes: `devices-and-edge.md`, `data-platforms-and-privacy.md`. Background: [../supergrid-setup.md](../supergrid-setup.md), [../agentapp-api-reference.md](../agentapp-api-reference.md), [../collaborative-agent.md](../collaborative-agent.md).

## Summary

We studied seven Hub apps and four companion bundles (11 in total). **None of them uses the AgentApp Grid tools** (`get_nodes` / `push_messages` / `pull_messages` / `push_reply_message`). Every app that actually coordinates parties is a classic **ServerApp + ClientApp** that fans out with `Grid.send_and_receive`. The AgentApps we found (`soteria-assessor-agent`, `vanna-agent`, `manufacturer-agent`, `jurisdiction-agent`, the unregistered `review_panel`) all run single-process with no Grid at all. So there is **no example in the wild of our exact pattern**, a master AgentApp driving worker AgentApps over `agent.grid`; `@flwrlabs/collaborative-agent` is still the only reference for it. The topology is **always a star**. There's **no node-to-node messaging** anywhere, which confirms our notes. The richest flow is a two-hop exchange through the coordinator (rare-disease's targeted follow-up, bloomkit's relay of lyrics to downstream nodes).

Across the apps a SuperNode is **an organisation's trust boundary**: a hospital, a freight party, a manufacturer, an FX desk. It holds private rows, whether JSONL records, a technical file, a party's contracts, or trading history, and sometimes a local model. It answers with a **projection**: a traffic light, a threshold bit, an allowlisted summary, or a model update. Roles come from operator `--node-config` keys (`party`, `site-name`, `data-dir`, `agent-profile`) or, in the weaker apps, from the simulation-only `partition-id`.

The most transferable ideas are:
1. Send **one bundled message per node** carrying the whole ask.
2. Let **node-config select both data and behaviour**, and fail closed when it's wrong.
3. Use **allowlist/scalar egress contracts with typed refusals**.
4. Run a **deterministic projection before any model** sees node data.

The main anti-patterns are shipping private data inside the FAB, deriving roles from `partition-id`, and matching replies to nodes by list position.

Versions fetched with `POST /v1/hub/fetch-zip` (`flwr_version: "1.39.0"`): soteria 0.3.0, soteria-assessor-agent 0.1.1, rare-disease-consult-network 0.2.2, vanna-federation 0.1.0, local-node 0.1.0, gapcheck 0.2.0, Helmsman 1.0.0, bloomkit 0.1.2. Companions: vanna-agent 0.1.0, manufacturer-agent 0.1.3, jurisdiction-agent 0.1.2. **None was skipped.** Every app targets `flwr` 1.35.0 or older (bloomkit `>=1.13`, Helmsman 1.20), so the platform claims they make have to be checked against 1.39.0 (see [Contradictions](#contradictions-with-our-notes-and-version-drift)).

---

## 1. `@kaiser-data/soteria` (+ `soteria-assessor-agent`)

Freight-rail incident response. Each party (carrier, supplier, customer) runs a node, and an assessor decides on measures without learning raw values.

1. **Type:** ServerApp (`soteria.assessor_app:app`) + ClientApp (`soteria.party_app:app`) **[src]** `pyproject.toml:44-46`. The LLM step is a **separate AgentApp FAB** in `agent/` (also published as `@kaiser-data/soteria-assessor-agent`, which is byte-identical to `agent/` **[src]**, diffed). It's split because a FAB with an `agentapp` component never runs its ServerApp **[docs]** `pyproject.toml:39-43`, `docs/RISKS.md:34-39`, which still holds in 1.39.0 **[src]** `flwr/superlink/servicer/control/control_handlers.py:2243`.
2. **What a SuperNode is:** one **company**: carrier (which also speaks as the `intake` and `legal` roles), supplier, or customer **[src]** `data/s1/s1_case.json` `federations`. It holds that party's records (contracts, stock, network segments) and **no model**. A projection is a function, not inference **[src]** `party_app.py:11-13`.
3. **Operator config:** `--node-config 'party="customer_c1_frischemarkt" case="s1"'` **[src]** `party_app.py:5-6,143,151`. No env vars or model key on nodes. Party data is **shipped inside the FAB** (`fab-include` includes `data/parties/*.json`, `data/contracts/*.json`) **[src]** `pyproject.toml:25-37`. Local 3-node federation script, all on one machine **[docs]** README.
4. **Communication:** star, **one round**. The assessor sends `query.ask_fields` to every node with the whole ask plan in one message **[src]** `assessor_app.py:322-360`. Wire format: `RecordDict{"soteria.ask": ConfigRecord{asker, case_id, fields: [str], reasons: [str]}}`. The reply is one `ConfigRecord` per field under `soteria.answer.NNN`, with keys `role, field, visibility, value, scope, code, flags` **[src]** `wire.py:142-188`. Privacy works as "three bolts":
   - the node loads only its own rows (`cases.py::raw_records_for_party`);
   - a need-to-know matrix projects each field to `raw / coarse / ampel / schwelle / flag / none` per asker, loaded from JSON (`data/schema/field_catalogue.json`, `matrix.py:302`);
   - `fact_record` rejects non-scalar values before they reach the wire (`wire.py:51-87`) **[src]**.

   Bundling cut the run from 69–127 s (13 messages × 3 nodes, each starting a ClientApp process) to 3–6 s **[docs]** `docs/RISKS.md:10-26`.
5. **Node identity and roles:** the `party` node-config key is looked up in the case file's `federations[]`. An unknown party raises, which becomes a typed refusal. A `case` mismatch makes the node refuse with `quota`, so **the operator can veto coordinator requests** **[src]** `party_app.py:151-165`. The coordinator never maps node ids to parties. It learns roles from `payload.role` in replies and computes `parties_missing` from what didn't contribute **[src]** `assessor_app.py:211-219`.
6. **Reuse:**
   - Bundled ask: `wire.py:130-188`, `party_app.py:200-239`.
   - Typed refusal instead of an exception ("a node that crashes looks like silence"): `party_app.py:68-79`, with the vocabulary in `envelope.py:45-55`.
   - Scalar-only egress guard: `wire.py:51-87`.
   - Side-channel check: the reference unit (`scope`) passes through the same matrix as the value, `party_app.py:48-65,118-123`.
   - Disagreement detection when two nodes hold the same field: `assessor_app.py:168-183`.
   - Model output under guardrails: strict JSON parse, unknown measures rejected, rule-based safety floor re-added, labelled `decided_by = llm | policy_fallback`: `llm.py:124-142,188-229`.
   - **Don't reuse:** the ServerApp calls the AgentApp via `subprocess` `flwr run <bundle> --run-config agent.input_b64=...` and scrapes a `SOTERIA_LLM` line from stdout **[src]** `llm.py:176-185`, `agent/soteria_assessor_agent/agent_app.py:55-81`. That's the cost of two FABs.

## 2. `@zenos/rare-disease-consult-network`

A clinician's case fans out to hospitals. Each hospital searches its own records and its own agent reads its notes, then an adversarial panel attacks the candidates.

1. **Type:** ServerApp + ClientApp **[src]** `pyproject.toml:92-94`. `review_panel/agent_app.py` is an `AgentApp` (five blind reviewers in a thread pool, no Grid), but it's **not registered** as a component and is reused only as a library (`build_client`, `json_call`) **[src]**.
2. **What a SuperNode is:** one **hospital**. It holds its patient records (`<site>.jsonl`, with free-text notes) and runs a **site agent** that calls an LLM locally to summarise its own matching notes **[src]** `consult/client_app.py:95-154`.
3. **Operator config:** `--node-config site-name="hospital_1" records-path="/data/hospital_1.jsonl" partition-id=0 num-partitions=5`, `--isolation subprocess`. There's one Docker container per hospital, which mounts **only its own file read-only** plus its own key, and gets `env_file: ../.env` for `OPENAI_API_KEY` **[src]** `docker/compose.yml:17-45`. A ServerApp or ClientApp gets no Flower model credentials, so the key comes from env, `.env`, or run-config `panel.api-key`, which "travels with the run and is visible in its metadata" **[src]** `review_panel/model.py:54-79`, `pyproject.toml:52-55`. The full corpus is excluded from the FAB, but a **sampled corpus is shipped** in it for SuperGrid simulation **[src]** `pyproject.toml:16-28`. The venue blocked 9092/9093, so they fell back to "SuperGrid's simulation federation over 443" **[docs]** README.
4. **Communication:** star, **two hops**:
   - `query.consult` to every node;
   - after ranking, `query.followup` to **only the sites that reported the target disease** (falling back to all).

   Payload: `RecordDict{"consult": ConfigRecord{"payload": <json str>}}` **[src]** `consult/protocol.py:16-37`. Timeout 90 s; a missing reply is counted as `missing`, never as "found nothing" **[src]** `consult/server_app.py:34,150-176`. Privacy: an **allowlist** `_strip_for_wire` (disease, top_scores, case_count, shared/absent symptoms, demographic_notes), so `record_id` and `text` never leave. The site agent's prompt forbids individual-level detail **[src]** `consult/client_app.py:79-92,122-134`. Identical Jaccard scoring runs at every site so scores are comparable **[docs]** README.
5. **Node identity and roles:** `site-name` from node-config, else `hospital_{partition-id+1}` **[src]** `consult/client_app.py:51-62`. The data path comes from the `records-path` node-config (it "wins outright"), else from run-config `consult.data-dir` + site name **[src]** `:65-76`. The site identifies itself in the reply payload (`"site"`).
6. **Reuse:**
   - Allowlist egress: `consult/client_app.py:79-92`.
   - "Lose the prose, not the site": if the model fails, the node still returns deterministic scores, `:184-189`.
   - Explicit "no data" reply: `:173-175`.
   - Targeted second hop: `consult/server_app.py:364-382`.
   - Honest accounting of silent nodes: `:171-176`.
   - Calibration canary: a known-false candidate goes through refutation, **[docs]** README.
   - **Bug, don't copy:** the follow-up target list is `node_ids[i] for i, r in enumerate(reports)` **[src]** `consult/server_app.py:369-373`. But `reports` is in **reply-arrival order** with failed replies dropped (`send_and_receive` pulls against a *set* of ids, **[src]** `flwr/superlink/grid/inmemory_grid.py:149-178`), so the follow-up can go to the wrong hospitals. Key replies by `src_node_id` instead.

## 3. `@melapre/vanna-federation` (+ `vanna-agent`)

Five FX desks federate-train an XGBoost execution model. Only model updates leave a desk.

1. **Type:** ServerApp + ClientApp, classic FL with `FedXgbBagging` **[src]** `pyproject.toml:26-28`, `server_app.py:17,152-211`. The sister `@melapre/vanna-agent` is a separate AgentApp **[docs]** README: "Flower will not put an AgentApp in the same FAB as a ServerApp/ClientApp". vanna-agent uses **no Grid**. It reads a `provider_evidence.json` that was **copied into its own FAB** as a static artifact **[src]** `vanna-agent/vanna_agent/agent_app.py:22,155`, so the two bundles are bridged by hand.
2. **What a SuperNode is:** one **trading desk**. It holds private execution history (synthetic, generated deterministically per partition), trains local trees, and returns model bytes **[src]** `client_app.py:24-76`.
3. **Operator config:** only `partition-id` **[src]** `client_app.py:26`, which the simulation runtime injects. On a real SuperNode without `--node-config partition-id=N` this raises `KeyError` **[inference]**. It persists partitions to a **CWD-relative** `artifacts/desk_partitions` **[src]** `persistence.py:19-23`. Deps: `numpy`, `xgboost>=3.2` **[src]**. SuperGrid deployment "needs 5 real SuperNodes" **[docs]**.
4. **Communication:** star, multi-round FedXgbBagging (3 rounds by default). The payload is `ArrayRecord` (model bytes as a `uint8` array) + `MetricRecord` **[src]** `client_app.py:70-75`. Privacy check: `validate_shared_payload` rejects prohibited **key names** (`client_id`, `uti`, `position`…) in metrics **[src]** `privacy.py:8-61`. It checks keys, not values **[src]**.
5. **Node identity and roles:** `partition-id` → `DESK_A..E` **[src]** `desk_config.py:92-97`. There are no roles; all nodes are symmetric.
6. **Reuse:** little. A denylist of key names (`privacy.py:58-61`) is weaker than the allowlists in apps 1, 2, 4 and 5. It's a counter-example of a two-FAB split joined by a copied file.

## 4. `@alpozaydin/local-node` (+ `manufacturer-agent`, `jurisdiction-agent`)

A regulator sends a public rulebook, and the manufacturer's node assesses its own technical file.

1. **Type:** ServerApp + ClientApp **[src]** `pyproject.toml:25-27`. The two sibling Hub apps are **AgentApps without Grid**: `manufacturer-agent` gets the technical file from FAB fixtures or `agent.technical-file-b64` run-config; `jurisdiction-agent` gets claims through `agent.claims-b64` **[src]** their `pyproject.toml` and `agent_app.py`.
2. **What a SuperNode is:** one **manufacturer**. It holds `technical_file.json` (evidence + a `_confidential` section) and **no model** **[src]** `local_node/client_app.py:1-10`. README: "the component that touches the secrets has no model in it" **[docs]**.
3. **Operator config:** `--node-config 'data-dir="/path"'` (required; if missing, the node replies with an `Error` message) **[src]** `local_node/client_app.py:82-91`. Deps: `flwr[simulation]` only. No private data in the FAB, only public rulebooks **[src]** `pyproject.toml:20`.
4. **Communication:** star, one round, `query.assess`. Payload: `ConfigRecord{"json": <str>}` under `request` / `reply` **[src]** `server_app.py:46-53`, `client_app.py:96,120-121`. Privacy:
   - an **egress contract** `validate_claim` (fixed keys, types, status enum, 200-char note cap, forbidden-string scan against the `_confidential` section) **[src]** `schema.py:57-109,112-131`;
   - a **minimum-sufficient** rule: a threshold clause is answered with one bit (`measured=None`) **[src]** `client_app.py:55-69`;
   - a hard-coded `documents_transmitted: 0`.
5. **Node identity and roles:** the manufacturer name comes from the file itself, in the reply payload **[src]** `client_app.py:114`. The coordinator "does not hold a roster" **[src]** `server_app.py:3-5`.
6. **Reuse:**
   - Egress contract: `local_node/schema.py:57-109`. Caveat: `confidential_strings` only collects strings longer than 3 characters, so numeric secrets aren't scanned (`:112-131`, **[src]**).
   - Minimum-sufficient disclosure: `client_app.py:60-66`.
   - Ledger in `context.state` (series-scoped, node-local): `manufacturer-agent/mfr_agent/agent_app.py:154-167`.
   - "Model never sees what it must not disclose" via `disclosable_view`: `mfr_agent/agent_app.py:85-87`.
   - **Don't copy:** local-node's ClientApp rebuilds the ledger from the **coordinator's** payload (`client_app.py:97`), and the server always sends `""` (`server_app.py:46-48`). The coordinator can therefore reset the budget, and `Ledger.adjudicate` is never called on the node **[src]**. So the README's "refuses the second one" isn't enforced by this bundle.

## 5. `@npztech/gapcheck`

A UK Responsible Person sends one checklist to every manufacturer. Each node returns a status per requirement, and no document crosses the network.

1. **Type:** ServerApp + ClientApp **[src]** `pyproject.toml:22-24`. Its "agents" are rule-based device-profile classes, not LLMs **[src]** `gapcheck_app/agents/`.
2. **What a SuperNode is:** one **manufacturer**. It holds its technical-file folder and chooses which device agent assesses it **[src]** `client_app.py:1-13`.
3. **Operator config:** `data-dir` (required), `node-name`, `display-name`, `agent-profile` (`sterile | electronic | class1`; if unset, the generic agent) **[src]** `client_app.py:39-70`, README table. Deps: `flwr` only. The FAB contains 5 Python files and no data **[docs]**. Note: the ServerApp runs from the FAB install dir under `~/.flwr/apps/`, so output paths must be absolute **[docs]** `pyproject.toml:33-37`.
4. **Communication:** star, one round, `query.gap_check` with `ConfigRecord{"json": rubric}` out and `ConfigRecord{"json": findings}` back **[src]** `server_app.py:79-88`, `client_app.py:100-103`. The findings are id, requirement, status, and a note from a **fixed sentence set**: no text, no filenames **[src]** `gap_check.py:175-194`.
5. **Node identity and roles:** **node-config selects the behaviour class.** `load_agent(profile)` looks it up in a `PROFILES` registry; unset gives the generic agent, and **an unknown value is refused** ("silently scoring against the wrong rubric is worse than not answering") **[src]** `agents/__init__.py:37-62`, `client_app.py:57-65`. The node declares its own identity (`node-name`, falling back to the folder name) in the payload, and the server sorts results by it **[src]** `client_app.py:67-70`, `server_app.py:108`.
6. **Reuse:**
   - A profile registry keyed by node-config, failing closed: `agents/__init__.py:26-62`.
   - A base class with `resolve_applicability` / `extra_checks` hooks: `agents/base.py`.
   - Explicit `Error` reply when config is missing: `client_app.py:39-55`.
   - Fixed-vocabulary findings: `gap_check.py:175-194`.

## 6. `@beothuk/Helmsman`

An ICLR 2026 multi-agent framework (LangGraph) that **generates** Flower FL codebases.

1. **Type:** **not a runnable Flower app.** `pyproject.toml` declares no `[tool.flwr.app.components]` (7 lines: name, version, license, publisher) **[src]**. The WebFetch summariser called it an "AgentApp", but neither the source nor the README supports that. It runs as `python agenticFL_workflow.py` **[docs]**.
2. **What a SuperNode is:** nothing, at runtime. The generated code uses **simulated** clients whose data is a `FederatedDataset` partition picked by `context.node_config["partition-id"]` **[src]** `src/workflow/coding_graph.py:635-681`. The evaluator loop calls `flwr.simulation.run_simulation` locally **[src]** `coding_graph.py:1812-1815`.
3. **Operator config:** conda, Python 3.12, CUDA 12.9, `flwr[simulation]==1.20.0`, and API keys for Google, OpenAI, Anthropic, Voyage, Cohere and Tavily **[docs]** README.
4. **Communication:** multi-agent coordination happens **in-process** as a LangGraph state machine (planner → reflection → human approval → supervisor → coder/tester pairs → evaluator/debugger) **[src]** `planning_graph.py:426-434`, `coding_graph.py:2651-2660`. No Flower messaging between agents.
5. **Node identity and roles:** only in the generated code, via `partition-id`.
6. **Reuse:** nothing for runtime. At most the planner → human-approval → supervisor loop as a UX idea. Out of scope for our cluster.

## 7. `@jaik7/bloomkit`

A "fully local creative studio": three nodes (lyrics, music, poster) run small local models.

1. **Type:** ServerApp + ClientApp **[src]** `pyproject.toml:30-32`. It uses legacy APIs (`flwr.common.RecordSet`, `ConfigsRecord`, `flwr.server.Grid`, `msg.create_reply`), which 1.39.0 still exports through `flwr.compat` shims **[src]** `flwr/common/__init__.py:72-89`.
2. **What a SuperNode is:** a **specialist worker with its own model and compute**: `Qwen2.5-0.5B-Instruct` (lyrics), `musicgen-small` (music), an SVG template with optional SD-Turbo (poster). Everything is on CPU with about 800 MB of Hugging Face weights, and there are no API keys **[docs]** README, **[src]** `agents/*.py`.
3. **Operator config:** `--node-config "partition-id=N num-partitions=3"` **[docs]** README. Env: `LYRICS_MODE=template`, `USE_SD_TURBO=1` **[src]** `agents/lyrics_agent.py:25`, `agents/poster_agent.py:56`. Deps: `torch`, `transformers`, `accelerate`, `fastapi`, `uvicorn` **[src]**. Outputs are written to the **node's** package dir `outputs/` **[src]** `task.py:6-7`.
4. **Communication:** star with a **two-stage relay through the coordinator**:
   - stage 1 broadcasts `requested_role="lyrics"` to all nodes, and non-lyrics nodes reply with an empty result;
   - stage 2 broadcasts `requested_role="downstream"` **with the lyrics text inlined**, and music and poster nodes use it.

   **[src]** `server_app.py:30-67`, `client_app.py:35-38`. Payload: `ConfigsRecord` `brief{theme, artist, requested_role, lyrics}` → `result{role, path, preview, text}`. The README says nodes answer "with the generated artifact bytes", but the code returns **only a path string and a preview**. The WAV and SVG stay on the node's disk, so the coordinator's `manifest.json` points at paths on other machines **[src vs docs]** `client_app.py:43-59`.
5. **Node identity and roles:** `ROLES[partition-id % 3]` **[src]** `task.py:10-12`. **Bug:** `_node_index` uses `node_config.get("partition-id", 0)`, so on a real node without that key **every node becomes `lyrics`**; the `node_id % 3` fallback is unreachable **[src]** `client_app.py:16-21`. The coordinator doesn't know who has which role; it **broadcasts, and nodes self-filter** **[src]**.
6. **Reuse:** the relay shape (one node's output → coordinator → other nodes' input, `server_app.py:30-59`) is the only worked example of it and maps onto our master relay. Broadcast-and-self-filter (`client_app.py:35-38`) works when the master doesn't know roles, but costs one task per node per stage.

---

## Comparison

| App | Flower type | `flwr` target | SuperNode is | Holds | Operator knobs | Pattern | Role / identity from | Private data in FAB? | Model on node? |
|---|---|---|---|---|---|---|---|---|---|
| soteria | ServerApp+ClientApp (+ separate AgentApp FAB) | 1.35 | freight party (carrier, supplier, customer) | party records, contracts | `party`, `case` | star, 1 bundled round | `party` node-config → case file | **Yes, all parties'** | No (by design) |
| rare-disease | ServerApp+ClientApp (unregistered AgentApp lib) | 1.35 | hospital | patient JSONL + notes | `site-name`, `records-path`, Docker, `.env` key | star, 2 hops (targeted follow-up) | `site-name` / `partition-id` | Sampled corpus only | Yes, own `OPENAI_API_KEY` |
| vanna-federation | ServerApp+ClientApp (+ separate AgentApp FAB) | 1.35 | FX desk | execution history | `partition-id` only | star, multi-round FedXgbBagging | `partition-id` | No (generated on node) | No (XGBoost only) |
| local-node | ServerApp+ClientApp (+ 2 AgentApp FABs, no Grid) | 1.35 | manufacturer | technical file | `data-dir` | star, 1 round | file content in reply | No | No (by design) |
| gapcheck | ServerApp+ClientApp | 1.35 | manufacturer | technical-file folder | `data-dir`, `node-name`, `display-name`, `agent-profile` | star, 1 round | node-config, self-declared | No | No (rules) |
| Helmsman | none (not a FAB) | 1.20 (generated) | simulated client | FederatedDataset partition | n/a | in-process LangGraph | `partition-id` (generated code) | n/a | n/a |
| bloomkit | ServerApp+ClientApp (legacy API) | ≥1.13 | specialist creative worker | local HF models, outputs | `partition-id`, `LYRICS_MODE`, `USE_SD_TURBO` | star, 2-stage relay | `partition-id % 3` | No | Yes, local weights |
| *our plan* | AgentApp (single FAB) | 1.39 | supplier | private catalogue | `--node-config` + node-local file | star, master fan-out / fan-in (+ relay) | node-config (+ `get_nodes` name) | **Must be No** | Yes, `FLWR_RUNTIME_*` (AgentApp only) |

Notes: "Model on node" means Flower-runtime model access. In 1.39.0 the responses endpoint accepts only `AGENT_APP` tasks **[src]** `flwr/supercore/routers/runtime/responses.py:138`, so a ClientApp that wants a model must bring its own key (rare-disease) or run weights locally (bloomkit). Our AgentApp workers are the only design here that gets the Flower-hosted model on the node.

---

## Contradictions with our notes, and version drift

| Claim in an app | 1.39.0 reality | Verdict |
|---|---|---|
| Soteria: "`AgentSession` has only `responses`, `connectors`, `events`, **no Grid**" (checked in 1.36) **[docs]** plan doc line 2499, `docs/RISKS.md:41-44` | `agent.grid` exists, with the role-filtered tools **[src]** our §2.1 | **Stale.** That's the reason Soteria and the others built ServerApp/ClientApp. |
| local-node: "node-facing Runtime endpoints are gated to `TaskType.SERVER_APP`" **[docs]** README | Gate is `task.type != TaskType.AGENT_APP → 401` **[src]** `responses.py:138` | **Wrong gate**, same conclusion: no Flower model for ClientApps (or ServerApps). |
| Soteria runs the AgentApp with `flwr run <dir> supergrid --run-config 'agent.input_b64=…'` **[src]** `llm.py:176-185` | `flwr run` sends no `user_prompt`, so the run fails with `AGENTAPP_USER_PROMPT_REQUIRED` (44) **[src]** our §7.3 | **No contradiction proven.** It targets 1.35, falls back to rules on any failure, and RISKS.md never reports a successful SuperGrid model run. |
| rare-disease compose uses `--superlink supergrid.flower.ai:9092` **[src]** `docker/compose.yml:35` | Our notes: `fleet-supergrid.flower.ai:443` **[docs]** | Likely an older or venue-specific address; they reported 9092/9093 blocked. Use 443. |
| Node-to-node messaging | None in any app **[src]** | **Confirms** our star-only notes. |
| "A FAB with `agentapp` never runs the ServerApp" **[docs]** Soteria `RISKS.md:34-39` (quotes 1.36 `control_handlers.py:2159`) | Same in 1.39.0: `return TaskType.AGENT_APP if "agentapp" in components else TaskType.SERVER_APP` **[src]** `flwr/superlink/servicer/control/control_handlers.py:2243` | Confirms. It rules out a hybrid ServerApp+AgentApp single FAB. |

---

## Patterns to reuse

Mapped onto the master (SuperLink AgentApp) / supplier (SuperNode AgentApp) plan.

1. **One bundled message per supplier.** Put every BOM line into one `push_messages` payload and get back one reply with per-line results. In our runtime each message creates one `AGENT_APP` task (process start, FAB check, model calls) **[src]** our §2.5. Soteria measured roughly 11–21× per case from bundling ClientApp messages (s1 69.1→6.4 s, s2 126.9→6.2 s, s3 68.0→3.2 s) **[docs]** `soteria/docs/RISKS.md:10-14`. Refs: `soteria/wire.py:130-188`, `soteria/party_app.py:179-239`.
2. **Node-config chooses data and behaviour, and fails closed.** For example `--node-config 'supplier-id="acme" catalogue-path="/abs/acme.json" profile="fasteners"'`. Read it with `context.node_config` inside `main` (populated for SuperNode tasks, **[src]** our §1.3). A missing path or unknown profile should be an explicit error reply, not a guess. Refs: `gapcheck_app/agents/__init__.py:37-62`, `gapcheck_app/client_app.py:39-70`, `local_node/client_app.py:82-91`, `consult/client_app.py:65-76`.
3. **Keep the catalogue out of the FAB.** Every node receives the whole FAB, so anything in `fab-include` is visible to every supplier. That's Soteria's weakness (`pyproject.toml:25-37`). Use absolute, operator-chosen paths (gapcheck), and mount only that file read-only in Docker (`rare-disease docker/compose.yml:43-45`). If a dev fixture has to ship, exclude it from the published FAB.
4. **Project deterministically before any model call.** Plain Python reads the catalogue and computes `{part, in_stock: bool, qty_band, unit_price, lead_time_days}`. The worker's model (if any) sees only that view. Refs: `mfr_agent/agent_app.py:85-87` (`disclosable_view`), `soteria/party_app.py:97-127`. Soteria and local-node go further and put no model at all on the secret-holding node.
5. **An allowlist egress contract on the reply.** Use fixed keys and types, an enum status, a bounded free-text note, and a scan of the serialised reply for confidential catalogue strings (cost price, margin, sub-supplier names). Add numeric secrets explicitly, which local-node misses. Refs: `local_node/schema.py:57-131`, `consult/client_app.py:79-92`, `soteria/wire.py:51-87`.
6. **Typed refusals, never silence or a crash.** Use a small vocabulary (`unknown_part`, `out_of_stock`, `not_disclosed`, `bad_request`, `no_catalogue`) and reply through `push_reply_message` even on internal errors. In an AgentApp, raising triggers the automatic `"AgentApp failed before replying."` error to **all** unanswered messages of that run on the node **[src]** our §2.5. Refs: `soteria/party_app.py:68-79`, `soteria/envelope.py:45-55`, `consult/client_app.py:173-175,184-189`.
7. **Minimum-sufficient disclosure.** When the master only needs "can you supply ≥ N by date D?", answer with a bit or a band, not the stock level. Refs: `local_node/client_app.py:55-69`; Soteria's `ampel` / `schwelle` projections (`docs/MATRIX.md`).
8. **Match replies by id, not position.** Key fan-in on `message_id → dst_node_id` from `push_messages`, cross-check `src_node_id`, and carry `supplier-id` in the payload for display. The counter-example is `consult/server_app.py:369-373`.
9. **Separate "didn't reply" from "can't supply".** Report timeouts, rejects and errors separately from real negatives. Refs: `consult/server_app.py:171-176`, `soteria/assessor_app.py:211-229`, `gapcheck_app/server_app.py:92-106`.
10. **Relay and targeted second hop.** Round 1 broadcasts the RFQ. Round 2 goes only to the chosen suppliers (reserve or confirm), or relays one supplier's output to another as a new task. Refs: `bloomkit/server_app.py:30-59` (relay), `consult/server_app.py:364-382` (targeted follow-up).
11. **Model decisions under code guardrails.** The master's LLM choice is parsed strictly and checked against the quotes it actually received, with a deterministic fallback (for example, cheapest feasible). Label every decision `decided_by: llm | fallback`. Refs: `soteria/llm.py:124-142,188-229`.
12. **Node-local disclosure memory, if needed.** Keep a per-supplier budget or ledger in `context.state` on the SuperNode, never in coordinator payloads. Refs: `mfr_agent/agent_app.py:154-167` (good), `local_node/client_app.py:97` (resettable by the coordinator). Our notes: SuperNode `state` persists from every task, last writer wins **[inference]** §1.3.
13. **Single FAB, confirmed.** Soteria (subprocess `flwr run`) and vanna (hand-copied `provider_evidence.json`) show what two FABs cost. Branching on `context.node_id == 1` inside one AgentApp avoids both.

## Open questions

- **Endeavor model id.** Soteria defaults to `model = "flower-endeavor-v1.0"` **[src]** `soteria/pyproject.toml:53`, `agent/pyproject.toml:29`. It's a candidate for the "Endeavor" id our notes list as unknown, but unverified on SuperGrid. Ask mentors.
- **`node_config` in AgentApp worker tasks.** Our source reading says it's populated, but none of the 11 bundles shows it in an AgentApp; all node-config use here is in ClientApps. Smoke-test with one local SuperNode.
- **Plain file IO from the worker AgentApp.** Under SuperGrid or hackathon nodes, does the AgentApp process see the operator's filesystem (`--isolation subprocess`) or a container (`process` isolation) that needs mounts? rare-disease pins `--isolation subprocess` (`docker/compose.yml:40-41`). This decides between `open(catalogue-path)` and the `filesystem` connector plus `FLWR_FILESYSTEM_ALLOWED_DIRS`.
- **Fleet endpoint and venue ports.** Is `fleet-supergrid.flower.ai:443` current, and will the venue block 9092? rare-disease's fallback, the simulation federation, **probably wouldn't work for us**: an AgentApp in a simulation federation most likely gets no simulated nodes **[inference]** ([../supergrid-setup.md](../supergrid-setup.md), AgentApp caveats).
- **Hub limits.** rare-disease cites a Hub "1MB-per-file limit" **[docs]** `pyproject.toml:22-23`, on top of the 10 MB FAB cap. It matters only if we ship fixtures.
- **Worker model credentials.** Our workers' model calls use each SuperNode's provider config (`FLWR_MODEL_API_KEY`). Do hackathon nodes have it, or should the worker be model-free (Soteria / local-node style) with all LLM reasoning on the master?
