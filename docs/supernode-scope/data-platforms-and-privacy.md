# SuperNode scope: data platforms and privacy machinery

Captured 2026-09-29. Sources: the nine Flower Hub FABs (fetched through `api.flower.ai/v1/hub/fetch-zip` with `flwr_version=1.39.0`; each app's own `flwr` pin is noted per app), their Hub pages, the `molgenis-flwr-armadillo` helper repo on GitHub, and the `flwr` **1.39.0** source for how the mechanisms work inside. Nothing here was run.
Tags: **[src]** read in app or `flwr` source (file:line) · **[docs]** README, Hub page or Flower docs · **[inference]** our reading, not verified.
App paths are relative to each FAB root. `flwr/...` paths are relative to the 1.39.0 package.

All nine apps fetched and read. None skipped.

---

## Summary

In all nine apps, a SuperNode reaches data **only through app code running in the ClientApp process**. Flower has no data connector for S3, Armadillo, OMOP or FAISS. Access is always "app code plus a credential or path", and each app decides where that credential comes from. Only **Armadillo** is genuinely node-local: the platform starts the container, injects the endpoint as env, and pushes data into it in memory. The others are simulation-shaped even in "deployment mode". **aws-flwr-demo** puts its AWS keys in `run_config`, which ships in the FAB to every node. **fed-omop** makes every node, and the server, download the same Hugging Face dataset, and it never touches an OMOP database. **fedrag** hard-codes the corpus path relative to the installed package and checks the indexes on the *server's* disk. On privacy, Flower's native tools are SuperNode authentication (node identity only), TLS, FAB signature checks (`--trusted-entities`), SecAgg+ (the server learns only the sum and is assumed semi-honest) and DP mods (central DP trusts the server to add the noise). The two third-party crypto apps are weaker than they claim. In **he-flower-example** the aggregator creates and holds the CKKS secret key, so it could decrypt every individual update. **smpc-fl** is *not* peer-to-peer: every share goes through the ServerApp **in cleartext**, so the ServerApp can reconstruct each client's exact update. **No app has SuperNodes exchange data directly**, and relayed exchange happens only via ServerApp code. As shipped, every aggregation mechanism (SecAgg+, DP mods, HE, SMPC) is FL-only: they run as ClientApp mods on `MessageType.TRAIN` or as ServerApp workflows, while AgentApps have no mod hook and send string payloads as `query` messages. Three things work for our AgentApp **today**: node auth and FAB verification (infrastructure), and **node-side data minimisation** in the fedrag style. With that pattern the supplier's worker code decides what goes into the reply, and cost never does.

---

## What a node can plug into

| App | Node holds / connects to | How it's configured on the node | What leaves the node | Genuinely node-local? |
|---|---|---|---|---|
| quickstart-pytorch-armadillo | MOLGENIS **Armadillo** data station (OIDC-protected projects/resources). `POST /flower/push-data` copies a file into the container, which reads it into memory and deletes it [docs] | Armadillo starts the SuperExec container and injects the `ARMADILLO_URL` and `ARMADILLO_CONTAINER_NAME` env vars [docs]. The **OIDC token arrives in the task message** (run-config `armadillo-tokens` → `ConfigRecord`) [src] | Weights, `train_loss`, `num-examples`, eval metrics [src] | **Yes**, but the credential path runs through the centre |
| aws-flwr-demo | One **S3 object** via `boto3.get_object` [src] | AWS keys in **`run_config`** (`aws-access-key`, `aws-secret-access-key`, …), not `node_config` [src] | A dummy 1×1 array and counts [src] | **No.** Every node reads the same object and IID-partitions it by `partition-id` |
| fed-omop | **Nothing external.** The HF dataset `danimanjah/synthea_small` downloads at import time. The MIMIC-IV CSV path is commented out [src] | `partition-id` / `num-partitions` only [src] | Weights and metrics | **No.** "OMOP-CDM" is only the upstream schema of the published features |
| fedrag | **FAISS** `IndexIVFFlat` (L2), a JSONL chunk store and the MiniLM embedder [src] | Hard-coded `CORPUS_DIR = <package>/../data/corpus`. The **server** picks each node's `corpus_name` [src] | **Top-k raw chunk text** and L2 scores for each query [src] | Partly. Retrieval is local, but the corpus location and choice aren't node-controlled |
| supernode-authentication | Node key pair plus an on-disk HF dataset [src] | `--auth-supernode-private-key`, `--node-config 'dataset-path="…"'` [docs][src] | Weights and metrics | **Yes.** The canonical `node_config` pattern |
| flower-secure-aggregation, fl-dp-sa | Flower Datasets partitions (or `Mock` loaders in demo mode), plus **ephemeral SecAgg+ key pairs** in `context.state` [src] | `partition-id` / `num-partitions`, and mods on the ClientApp [src] | Masked, quantised vectors, encrypted key shares, and **cleartext metrics** [src] | n/a (demo data) |
| he-flower-example | Synthetic 4-dim vectors, plus the server's **CKKS public context**, sent in every task [src] | `partition-id` only. The server's config sets the mode [src] | A CKKS ciphertext, plus `update-norm` and `partition-id` in the clear [src] | n/a |
| smpc-fl | Full Keras MNIST on every node in deployment [src] | `partition-id` in simulation only [src] | **All N additive shares, in cleartext**, to the ServerApp [src] | n/a |

Operator-side controls that exist in 1.39.0 for any app type [src] `flwr/supernode/cli/flower_supernode.py`: `--node-config`, `--auth-supernode-private-key`, `--root-certificates`, `--trusted-entities`, `--isolation`, and `FLWR_FILESYSTEM_ALLOWED_DIRS` (the filesystem connector allowlist, `flwr/supercore/task_process/connector/filesystem/filesystem.py:35`).

---

## Privacy mechanisms

On SuperGrid, "the SuperLink" means the SuperLink and the ServerApp/master process **on Flower's hosted infrastructure** (see [../supergrid-setup.md](../supergrid-setup.md)). That's the trust boundary the "sees" column describes.

| Mechanism | Where | What it protects | Trust assumptions / what the SuperLink sees | FL-only or agent-usable |
|---|---|---|---|---|
| **SuperNode authentication** | supernode-authentication; required on SuperGrid | Only registered keys can use the Fleet API, and `node_id` is bound to the key on every RPC | ECDSA P-384 signature over the **ISO timestamp only**, not the request body, with a ~300 s window. Integrity and confidentiality come from TLS. The SuperLink sees all message content | **Agent-usable today** (transport layer) [src] |
| **TLS** | supernode-authentication | Transport | Terminates at the SuperLink, which sees plaintext payloads | Agent-usable |
| **FAB signature check** `--trusted-entities` | `flwr` 1.39.0 | The node refuses to run FABs not signed by operator-trusted Ed25519 keys | The SuperLink must supply `verifications`, including `valid_license`. Checked **before task creation for both `AGENT_APP` and `CLIENT_APP`** | Agent-usable in principle. Whether `/load .` FABs are signed is unknown [src] |
| **FAB-hash whitelist** (SuperExec plugin) | Armadillo helper | Only app hashes the operator has approved get launched | The node operator audits the code. Written for `flwr` 1.32's `ClientAppExecPlugin`. In 1.39 the hook is `AutoExecPlugin.launch_task(token, task)`, which covers `AGENT_APP` | Portable to AgentApps with a rewrite [src hook][inference port] |
| **SecAgg+** | flower-secure-aggregation, fl-dp-sa | Individual model updates (array records): the server learns only the **sum** and who dropped out | **Semi-honest server**: it relays public keys without authenticating them. Up to t−1 colluders tolerated. Clipping and quantisation apply. **Metrics leave in the clear** | **FL-only as shipped** (a `TRAIN`-only mod plus a `LegacyContext` workflow) [src] |
| **Central DP, client-side fixed clipping** | fl-dp-sa | The released model, against its downstream consumers | **The server is trusted to add the noise.** Without SecAgg it also sees clipped updates. No ε accountant in the app | FL-only (strategy wrapper plus a `TRAIN` mod) [src] |
| **Local DP** (`LocalDpMod`) | `flwr` 1.39.0 (no app here uses it) | Each client's update, against the server | No server trust. Costs utility | FL-only as a mod. The idea (noise on a numeric answer before replying) can be ported by hand [inference] |
| **CKKS HE, as shipped** | he-flower-example | Ciphertexts in transit and at rest in SuperLink state | **The ServerApp generates and holds the secret key** and receives individual ciphertexts, so it can decrypt any one of them. "Decrypts only the aggregate" is honest-code policy | FL-only as coded. Only meaningful if the decryption key lives outside the aggregator [src][inference] |
| **Additive secret sharing, as shipped** | smpc-fl | **Nothing against the ServerApp** | Shares travel in cleartext pickles through the ServerApp, which receives all N shares of every client | The relay pattern maps to AgentApps. This protocol gives no confidentiality [src] |
| **Node-side data minimisation** | fedrag | Everything except the reply (the rest of the corpus, the index) | The node returns only query-relevant items. The query goes to every node in plaintext, and the master sees the reply | **Agent-usable today.** It's exactly `push_messages` → `push_reply_message` [src] |

**Why the crypto rows are FL-only.** `secaggplus_mod`, `fixedclipping_mod` and `LocalDpMod` return early unless `message_type == MessageType.TRAIN`, and they convert FitIns/FitRes (`flwr/client/mod/secure_aggregation/secaggplus_mod.py:138,169`; `flwr/client/mod/centraldp_mods.py:54`; `flwr/client/mod/localdp_mod.py:106`). `flwr/agentapp` has no `mods` concept, and AgentApp Grid messages are `message_type="query"` with content `{"agent": {"text": <str>}}` (see [../agentapp-api-reference.md](../agentapp-api-reference.md) §2.3) [src]. A port to the AgentApp Grid is conceivable: the master runs each protocol stage as a push/pull round, bytes are base64'd, and per-node secrets live in `context.state`, which is node-local and persisted per task. But reply-once means each stage is a new message and a new task, and the auto error reply hits every unanswered message of the run on that node (§2.5), so one failed stage can kill a sibling [inference, unbuilt].

---

## Per-app notes

### 1. `@timmyjc/quickstart-pytorch-armadillo`: MOLGENIS Armadillo

v1.0.4 · `flwr>=1.32.0`, target 1.32.1 · FL ServerApp/ClientApp (FedAvg, CIFAR-10).

1. **Connects to:** a MOLGENIS Armadillo data station. `load_data(url, token, project, resource)` calls `POST /flower/push-data`. Armadillo checks the OIDC token and project permissions, copies the resource into the container at `/tmp/armadillo_data/`, and the helper reads it into memory and deletes the file [docs `loading-data.md`]. The app loads `data/cifar10_{train,test}.pt` from the project `test-flower` [src `pytorchexample/task.py:82-92`].
2. **Config:** in deployment there's no `node_config`. The client branches on whether `partition-id` is present [src `client_app.py:25-41`]. `get_node_url()` reads `ARMADILLO_URL`, which Armadillo injects [docs]. The researcher runs `armadillo-flwr-authenticate` (OIDC against each node) and then `armadillo-flwr-run`. That packs **all sites' tokens** into one run-config key, `armadillo-tokens` (base64 JSON `{sanitized-url: token}`) [docs README, src `pyproject.toml`]. The ServerApp forwards them: `train_config = ConfigRecord({"lr": lr, "project": project, **tokens})` [src `server_app.py:25,35-36`]. FedAvg sends the same config to every sampled node, so **every node receives every site's bearer token** [inference from the FedAvg broadcast; the app line is src]. Caveat: the app calls `get_node_token(msg)` with one argument, but the helper version we could read (`epic/flower` branch) has `get_node_token(msg, context)`, keyed on `node-name`. We didn't see the exact shipped helper.
   **Never leaves:** raw data, which lives only in container memory [docs]. **Leaves:** weights and metrics [src `client_app.py:53-60`].
3. **Mechanism:** Armadillo's OIDC plus per-project authorisation at the data API [docs], and a **FAB-hash whitelist**. The `armadillo-flwr-superexec` image runs `VerifiedClientAppExecPlugin`, which re-reads an Armadillo-maintained YAML file for every task and rejects any `task.fab_hash` not on it. An unreadable file rejects everything [src helper `verified_exec_plugin.py:47-68`]. Nothing protects the updates themselves: the SuperLink sees the plain weights, per-site metrics, and **every site's token**.
4. **Communication:** standard FedAvg (`strategy.start(grid=…)`). Clients reply with `Message(content, reply_to=msg)` [src]. No node-to-node traffic.
5. **Type:** FL. The *platform* pattern doesn't depend on the app type: the platform starts the container, injects the endpoint as env, and gates on a FAB hash. The whitelist hook exists in 1.39 as `AutoExecPlugin.launch_task(token, task)`, whose supported types include `AGENT_APP` [src `flwr/supercore/superexec/plugin/base_exec_plugin.py:63-82,126-133`].
6. **For suppliers:** this is the best "the supplier controls what runs" story: the operator approves an app hash, and data is pulled into memory for each task. Avoid its credential routing. Each supplier's secret belongs in *that* node's env or `node_config`, never in run-config or in messages.

### 2. `@dimitris/aws-flwr-demo`: S3

v1.0.1 · `flwr[simulation]==1.26.1` · FL ServerApp/ClientApp (a FedAvg skeleton with no real training).

1. **Connects to:** one S3 object (`iris.csv`) via `boto3.client('s3', …).get_object` [src `task.py:31-47`].
2. **Config:** credentials, region, bucket and key are all **`run_config`** keys from `pyproject.toml` [src `pyproject.toml`, `client_app.py:11-15`]. `run_config` is part of the FAB and run, so the secret travels through the SuperLink to every node [inference from Flower config semantics]. The README suggests a public-read bucket policy (`"Principal": "*"`) [docs]. Every node downloads the **same** object and IID-partitions it with `partition-id` [src `task.py:66-88`], so there's no silo. `train()` returns the received model unchanged [src `client_app.py:30-35`].
   **Never leaves:** rows (only counts do). The credential, though, is everywhere.
3. **Mechanism:** none.
4. **Communication:** FedAvg star.
5. **Type:** FL. Nothing to carry over except the lesson below.
6. **For suppliers:** an object store is a fine home for a supplier catalogue, but the credential must be node-local: a `--node-config` key naming a profile, or boto3's default chain (env or instance role) on the node host [inference].

### 3. `@danimanjah/fed-omop`: OMOP-CDM hospitals

v0.1.0 · `flwr[simulation]>=1.26.1` · FL ServerApp/ClientApp (FedAvg, ResMLP, 30-day readmission).

1. **Connects to:** no database. At import time `DATASET_SPECS` runs `instantiate_ds_and_get_features(dataset="synthea_small")`, which calls `load_dataset("danimanjah/synthea_small", "all")` in **every** process, server included [src `task_utils.py:67`, `dataset.py:52-61`]. The MIMIC-IV local-CSV path is commented out [src `task_utils.py:55-57`]. We found no SQL, OHDSI or CDM client anywhere in the package [src grep]. OMOP-CDM and FHIR describe the upstream Synthea preprocessing [docs `docs/synthea.md`].
2. **Config:** `partition-id` and `num-partitions`. The `iid`, `dirichlet` or `natural` partitioner (`hospital_id`) is chosen in `run_config` [src]. The `StandardScaler` is fit on the global training set, and the code carries a "/!\ valid only on simulation" comment [src `dataset.py:13-20`].
3. **Mechanism:** none. The ServerApp evaluates on the **global** test split (`load_global_data`) [src `server_app.py:62-80`], so the server holds data as well.
4. **Communication:** FedAvg star.
5. **Type:** FL.
6. **For suppliers:** the only transferable idea is a **shared schema**. OMOP-CDM lets hospitals answer the same query, and a common catalogue schema would let every supplier answer the same part request [inference]. A real deployment would need a node-local DSN in `node_config`, which this app doesn't show.

### 4. `@dimitris/fedrag`: federated RAG over node-local document stores

v1.0.2 · `flwr[simulation]>=1.26.1` · uses the ServerApp/ClientApp API but **doesn't train**: it's a query/response federation.

1. **Holds:** a FAISS `IndexIVFFlat` (`METRIC_L2`), JSONL chunk files and the `sentence-transformers/all-MiniLM-L6-v2` embedder [src `fedrag/retriever.py:17-33,117-162`]. The corpora (MedRAG: Textbooks, StatPearls, PubMed, Wikipedia) are prepared offline with `python -m data.prepare` [docs].
2. **Config:** `CORPUS_DIR = os.path.join(DIR_PATH, "../data/corpus")`, i.e. relative to the installed package [src `retriever.py:17-18`], with no `node_config` key. **The server decides which corpus each node serves**: `config_record["corpus_name"] = next(corpus_names_iter)`, round-robin [src `server_app.py:89-91`]. The ServerApp runs `index_exists(corpus_names)` against its **own** disk before starting [src `server_app.py:132`, `task.py:20-28`]. That's a simulation artefact, because it assumes the server and clients share a filesystem.
   **Never leaves:** the index and non-matching chunks. **Leaves:** the full text of the top-k chunks, plus their scores [src `client_app.py:28-46`].
3. **Mechanism:** no cryptography. Privacy comes from **data minimisation** (k chunks per question). The question goes to every node in plaintext [src `server_app.py:85-100`]. Server-side merging by raw L2 score only works because every node uses the same embedder. RRF (`k-rrf=60`) merges by rank [src `server_app.py:35-64`]. Confidential-compute (C-FedRAG) and HE-ANN (FRAG) versions are cited but not implemented [docs].
4. **Communication:** one `MessageType.QUERY` per node per question, via `grid.send_and_receive` [src `server_app.py:94-103`]. The client's `@app.query()` returns `Message(reply_record, reply_to=msg)` [src `client_app.py:12,49`]. The LLM (SmolLM2-1.7B via `transformers`) runs on the server. No node-to-node traffic. Performance: every message builds a new `Retriever()`, which reloads the embedding model [src `client_app.py:25`].
5. **Type:** a FL-API app, but structurally the same as AgentApp master/worker. AgentApp `push_messages` also sends `message_type="query"` ([../agentapp-api-reference.md](../agentapp-api-reference.md) §2.3). **It carries over directly.**
6. **For suppliers:** this is the template. The master broadcasts a part request. Each supplier retrieves over *its own* catalogue (FAISS, SQL or pandas) and replies with the top-k items and a quoted price, never the cost. Fixes for our version: take the catalogue path from `node_config` or `FLWR_FILESYSTEM_ALLOWED_DIRS`, let the node (not the master) choose what it serves, return structured JSON instead of raw text, and merge by rank or price rather than raw similarity scores.

### 5. `@flwrlabs/supernode-authentication`

v1.1.11 · `flwr>=1.36`, target 1.36.0 · FL ServerApp/ClientApp (plain FedAvg; the app contains **no auth code**) [src `authexample/server_app.py:27`].

1. **Holds:** an EC **SECP384R1** key pair in OpenSSH format, generated by `generate_creds.py` [src `generate_creds.py:124-150`] (the same thing as `ssh-keygen -t ecdsa -b 384` in our setup doc), and an on-disk dataset [src `client_app.py:30`].
2. **Config:** `flower-supernode --root-certificates ca.crt --auth-supernode-private-key keys/supernode_credentials_1 --node-config 'dataset-path="datasets/cifar10_part_1"'`. The SuperLink runs with `--enable-supernode-auth` plus TLS, and nodes are pre-registered with `flwr supernode register <pub>` [docs README]. The private key never leaves the node.
3. **Mechanism** [src 1.39.0]: `NodeAuthClientInterceptor` adds the public key, `now().isoformat()`, and `sign_message(private_key, timestamp.encode("ascii"))` to every unary Fleet RPC (`flwr/client/grpc_rere_client/node_auth_client_interceptor.py`). `NodeAuthServerInterceptor` verifies the signature, requires the timestamp to be within `TIMESTAMP_TOLERANCE = 300` s (plus a system-time tolerance), and then checks `request.node_id == get_node_id_by_public_key(pk)` (`flwr/server/superlink/fleet/grpc_rere/node_auth_server_interceptor.py`, `flwr/common/constant.py:154`). **It proves identity and binds the node ID. It doesn't sign the body**, so integrity relies on TLS, and without TLS a captured header could be replayed within the window [inference]. The SuperLink still sees all content.
4. **Communication:** FedAvg star.
5. **Type:** transport level, so it applies to AgentApp workers unchanged. SuperGrid requires it.
6. **For suppliers:** a supplier *is* a key pair, and the master sees an authenticated `src_node_id` plus the registered `name`/`location`. Quotes are attributable at the node level **only if you trust the SuperLink**, because payloads aren't end-to-end signed. A cheap upgrade: sign the quote JSON with a node-local key (path in `node_config`) and have the master verify it [inference].

### 6. `@flwrlabs/flower-secure-aggregation`: SecAgg+

v1.1.12 · `flwr>=1.36`, target 1.36.0 · FL (`LegacyContext` + `DefaultWorkflow(fit_workflow=SecAggPlusWorkflow…)`).

1. **Holds:** each round, two ephemeral SECP384R1 key pairs: `sk1` for the pairwise masks and `sk2` for encrypting shares. Both are stored in `ctxt.state` [src `flwr/client/mod/secure_aggregation/secaggplus_mod.py:310-343`, `flwr/supercore/primitives/asymmetric.py:29`].
2. **Config:** `ClientApp(client_fn, mods=[secaggplus_mod])` [src `secaggexample/client_app.py:86-91`]. `num-shares=3`, `reconstruction-threshold=2`, `max-weight=9000`. The workflow defaults are a clipping range of 8.0, quantisation 2^22 and a modulus of 2^32 [src `pyproject.toml`, `flwr/server/workflow/secure_aggregation/secaggplus_workflow.py:124-145`]. Demo mode forces client 0 to drop out [src `workflow_with_log.py:79-85`].
3. **Mechanism:** SecAgg+ runs in four stages: setup, share keys, collect masked vectors, unmask [src workflow `:95-102`]. Pairwise keys come from ECDH plus HKDF, and shares are encrypted with Fernet [src `flwr/common/secure_aggregation/crypto/symmetric_encryption.py:26-56`; mod `:390-398,423-424`]. The server forwards encrypted key shares as opaque ciphertexts [src workflow `:443-468`] and only ever sees public keys, ciphertexts, masked vectors, the unmasked **sum** and the dropout set. Trust caveats: public keys are relayed **unauthenticated** (`ConfigRecord({str(nid): state.nid_to_publickeys[nid] …})`, workflow `:408-413`), so the model is a semi-honest server, and an active server could substitute keys [inference]. Also, the mod only clears `array_records` (mod `:173-174`), so **MetricRecords and `num_examples` go out in the clear**.
4. **Communication:** logically node-to-node (each ciphertext is addressed to a peer), physically a **star through the ServerApp**. This is the *correct* way to build relayed peer-to-peer.
5. **Type:** **FL-only as shipped** (the mod handles `TRAIN` only and needs FitRes conversion, mod `:138,169`). An AgentApp port would be a hand-rolled four-round protocol over the Grid [inference, unbuilt].
6. **For suppliers:** it only applies to **aggregate statistics** where the master should learn a sum and nothing per supplier, e.g. total stock of part X across suppliers. It doesn't fit quote selection, where the master must see each price. It also needs 3 or more nodes and integer or quantised values.

### 7. `@flwrlabs/fl-dp-sa`: central DP plus SecAgg+

v1.1.11 · `flwr>=1.36`, target 1.36.0 · FL (designed for 100 simulated nodes, 3 rounds).

1. **Holds:** MNIST partitions, plus the SecAgg+ ephemeral keys as above.
2. **Config:** `mods=[secaggplus_mod, fixedclipping_mod]`. The outer mod runs first, so updates are clipped *before* masking [src `fl_dp_sa/client_app.py:45-51`]. The server uses `DifferentialPrivacyClientSideFixedClipping(FedAvg, noise_multiplier=0.2, clipping_norm=10, num_sampled_clients=20)` wrapped in `SecAggPlusWorkflow(num_shares=7, reconstruction_threshold=4)` [src `server_app.py:56-76`].
3. **Mechanism:** central DP with client-side clipping. Clients clip to C, and the server adds Gaussian noise to the securely aggregated sum in `aggregate_fit` (stdev from `noise_multiplier`, `clipping_norm`, `num_sampled_clients`) [src `flwr/server/strategy/dp_fixed_clipping.py:202,300-325`]. **Trust:** the server is trusted to add the noise, so DP protects the *released model*, not the updates, from the server. SecAgg does the latter. There's no ε accountant in the app, and fit metrics (`train_loss`, `val_accuracy`, …) come back in the clear [src `server_app.py:13-27`]. The variant that doesn't trust the server, `LocalDpMod(clipping_norm, sensitivity, epsilon, delta)`, exists in 1.39.0 [src `flwr/client/mod/localdp_mod.py:34-80`].
4. **Communication:** star.
5. **Type:** FL-only as shipped. The idea carries over: a worker can add calibrated noise to a numeric answer before `push_reply_message` [inference].
6. **For suppliers:** good for "publish market stats without exposing any one supplier's number", such as noisy stock levels or a noisy benchmark cost. Useless for binding quotes, since you don't add noise to a price you have to honour.

### 8. `@mohammad/he-flower-example`: CKKS via TenSEAL

v1.0.0 · `flwr[simulation]>=1.26.1` · FL on the Message API (no mods). Default `mode = "plain"`.

1. **Holds:** synthetic update vectors [src `task.py:107-121`] and the server's **public** CKKS context, which comes in every train message [src `server_app.py:71-72`].
2. **Config:** run-config `mode` (`plain` | `he_ckks`), `ckks-poly-modulus-degree=8192`, `ckks-coeff-mod-bit-sizes="60,40,40,60"`, scale 2^40 [src `pyproject.toml`]. Nothing node-specific apart from `partition-id`.
3. **Mechanism:** clients call `ts.ckks_vector(public_context, update)` [src `task.py:161-166`]. The server sums the vectors homomorphically and decrypts the total [src `task.py:169-185`]. **Trust model:** the ServerApp *creates and keeps* the secret context (`create_ckks_secret_context` in `main`, `server_app.py:152-157`) and is also the party receiving each ciphertext, so **it can decrypt any single client's update**. "Decrypts only the aggregate" [docs] depends on the code behaving, not on cryptography. HE here only makes ciphertexts in transit or at rest in SuperLink state opaque to anyone without the ServerApp's in-memory key [inference]. On SuperGrid, that key holder is the infrastructure operator [inference]. Further gaps: the server chooses the mode in config and can silently downgrade to `plain` (`client_app.py:27,69-78`). `update-norm` and `partition-id` go out as cleartext metrics (`client_app.py:47-53`). The public context isn't authenticated.
4. **Communication:** star, `grid.send_and_receive` on `TRAIN` messages [src `server_app.py:174`].
5. **Type:** FL, but mod-free, so porting is easy mechanically: it's just bytes (base64 in an AgentApp payload). The key-custody flaw would come along with it. A sound design needs threshold or multi-key CKKS, or a decryptor that never sees individual ciphertexts [inference].
6. **For suppliers:** it could total encrypted quantities, but under CKKS you can't cheaply compare or take the minimum of encrypted prices. Not worth it for the hackathon.

### 9. `@synthema/smpc-fl`: "P2P SMPC" (additive secret sharing)

v1.0.1 · `flwr[simulation]==1.26.1`, TensorFlow · FL on the Message API with custom `@app.query("…")` handlers.

1. **Holds:** full Keras MNIST on every node in deployment [src `smpc_fl/client_app.py:36-53`].
2. **Config:** no node config beyond `partition-id` / `num-partitions` in simulation [src `client_app.py:46-53`].
3. **Mechanism as claimed:** "additive secret-sharing-based P2P SMPC … no single entity sees individual client updates" [docs README/Hub]. **What the code does** [src]:
   - The client splits each tensor into N shares: shares 1…N−1 are `np.random.uniform(-1, 1)` and the last is `value - sum(shares)` [`smpc_client.py:13-33`]. It then pickles the **whole** map `{recipient_lid: share}` into a `ConfigRecord` and returns it to the server [`client_app.py:73-91`].
   - The server stores `shares_by_sender[sender_lid] = payload["shares_by_recipient"]` [`server_app.py:88`], so it holds **all N shares of every client**. Summing over recipients gives back the exact `local_weights`. **The privacy claim is false against the ServerApp**, and against anything that can read SuperLink state, since the pickles are plaintext.
   - Other weaknesses: the shares are floats from a bounded uniform over ℝ, not uniform mod p, so they aren't information-theoretically hiding [inference]. The server runs `pickle.loads` on bytes from the clients (`server_app.py:86`) and the clients do the same on bytes from the server (`client_app.py:98`), which is an RCE path in both directions. The final `weighted_average` weights per-*recipient* partial sums by *sender* sample counts (`server_app.py:124-136`), which equals FedAvg only when every count is the same [inference from the arithmetic].
4. **Node-to-node verdict: NO, not directly and not end-to-end.** There's no socket or gRPC code beyond `flwr`. The only code that addresses a node is the ServerApp (`dst_node_id=node_id`, with `message_type="query.local_train"` at `server_app.py:63-70` and `"query.aggregate_shares"` at `:109-116`, both sent through `grid.send_and_receive` at `:72,118`). Clients only ever call `Message(reply, reply_to=message)` (`client_app.py:91,112`). "P2P" is a logical topology **relayed in cleartext through the ServerApp**. The README says as much: "Share exchange is orchestrated via ServerApp message relay" [docs]. This matches the Flower rule that SuperNodes can only reply.
5. **Type:** FL, mod-free. The relay pattern maps directly onto AgentApp master/worker, where the master turns node A's reply into a new task for node B [inference]. To make it private, each share has to be encrypted to its recipient with a pairwise key, as SecAgg+ does, so that the relay can't read it.
6. **For suppliers:** it's the canonical example of *relayed P2P* in our architecture, and a warning: if the master relays, the master (and Flower's infrastructure) sees everything unless payloads are end-to-end encrypted to the recipient node.

---

## Takeaways for our supplier nodes

1. **It's a star. There are no supplier-to-supplier channels.** Across all nine apps, and in 1.39.0 generally, SuperNodes only reply. Any "negotiation" between suppliers is a sequence of master-relayed rounds, and the master runs on SuperGrid. Design every flow as master ↔ node.
2. **The one mechanism we can use today is node-side data minimisation (the fedrag pattern).** Keep the supplier's cost sheet node-local, in files under `FLWR_FILESYSTEM_ALLOWED_DIRS` or keys in `--node-config`. Have the worker compute the quote **deterministically in Python** and reply with a schema that has no cost or margin field. It needs no extra infrastructure and it's the only guarantee enforced in code on the node we control. If the operator doesn't want the cost sheet going to their model provider, keep it out of the LLM prompt as well: worker model calls go to *that node's* configured provider, `api.flower.ai` by default ([../agentapp-api-reference.md](../agentapp-api-reference.md) §5.5).
3. **Identity comes free, integrity doesn't.** SuperNode auth, which SuperGrid already requires, gives the master an authenticated `src_node_id` plus the registered name and location, which is enough to attribute each quote to a supplier. For quotes that hold up even against the SuperLink, sign the quote JSON with a node-local key and verify it in the master (about 20 lines) [inference].
4. **Credentials stay on the node.** Don't copy aws-flwr-demo (secrets in `pyproject` run-config) or Armadillo (every site's token broadcast in task messages).
5. **Operator control over code is possible but may fight our dev loop.** `--trusted-entities` (a FAB signature check that also applies to `AGENT_APP` tasks) or an Armadillo-style FAB-hash whitelist would let us say "a supplier only runs audited code". Either would probably reject each fresh `/load .` build (see Open questions).
6. **SecAgg, DP and HE fit only aggregate market statistics**, e.g. "total units of part X available" or "mean lead time", never per-supplier quotes. For a demo, local-DP noise on a stock count before `push_reply_message` is cheap to add. A full SecAgg+ port over the AgentApp Grid isn't worth the time.
7. **Suppliers are already sealed from each other.** Nodes never see each other's replies unless the master relays them. What's left to decide is how much the **master** (and so Flower's infrastructure) learns, and that comes down to item 2.

## Open questions

- Does SuperGrid attach `verifications` (including `valid_license`) to FABs submitted with `flwr chat` → `/load .`? If not, a node started with `--trusted-entities` answers every task with `FAB_VERIFICATION_ERROR` (`flwr/supernode/start_client_internal.py:357-380`).
- Can a SuperGrid-connected node run its own SuperExec (`--isolation process`) with a custom `AutoExecPlugin` subclass, such as a FAB-hash whitelist?
- Who at Flower can read SuperLink message payloads and AgentApp traces on SuperGrid? Is LinkState encrypted at rest, and how long is anything kept after the destructive pull?
- On a SuperGrid laptop node without `FLWR_MODEL_API_KEY`, which provider handles `/v1/runtime/responses`? That decides where a supplier worker's prompts end up.
- Is master-to-node end-to-end payload encryption on Flower's roadmap? We found no sign of it in 1.39.0.
- Armadillo: which helper version provides the one-argument `get_node_token(msg)`, and do nodes really receive all sites' tokens? Ask the maintainers; we couldn't see the shipped version.
- Out of scope for the hackathon, but worth knowing: picking the lowest price without the master seeing the losing bids would need secure comparison (garbled circuits or MPC). None of the Hub apps attempt it.
