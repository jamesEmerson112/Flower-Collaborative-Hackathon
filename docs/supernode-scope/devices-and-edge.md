# What a SuperNode can be: physical devices and edge deployments

Captured 2026-09-29 from Flower Hub app bundles, the Flower docs, Docker Hub and the `flwr` 1.39.0 source. Nothing was run.
Tags: **[src]** read in the app's code, or in `flwr` 1.39.0 / Docker Hub metadata where stated · **[docs]** app README, Hub page or Flower/vendor docs · **[inference]** our reading, not verified.
File references are relative to each app's root folder. Sibling notes: `agent-and-multiparty-apps.md`, `data-platforms-and-privacy.md`. Background: [../supergrid-setup.md](../supergrid-setup.md), [../collaborative-agent.md](../collaborative-agent.md).

## Summary

A SuperNode is a CPython process, and the smallest machine that can host one is set by `flwr` itself rather than by the app. `flwr` 1.39.0 needs **Python ≥ 3.11**. It pulls in `grpcio`, `cryptography`, `sqlalchemy`, `fastapi`/`uvicorn` and `uv`, and at runtime it spawns a `flower-superexec` child plus one process per task **[src]** (`flwr-1.39.0.dist-info/METADATA`, `supernode/start_client_internal.py`). In practice the floor is a **64-bit Linux SBC**: Flower's embedded example names a Raspberry Pi 5, 4 or Zero 2 **[docs]**, and the `flwr/supernode` images ship for `linux/arm64` **[src: Docker Hub]**.

**A microcontroller can't be a SuperNode.** The one MCU app on the Hub (`@fraunhofer-ims/aifes-gesture-recognition`) doesn't use SuperNodes at all. Its ESP32 devices train a 259-parameter network on-device and exchange raw float32 weights with a *ServerApp* over a public MQTT broker. Its ClientApp is an empty stub, and SuperNodes receive nothing.

The other seven apps are simulation-first. Their drones, cameras, trucks, farms and forests are personas mapped to `partition-id`, running on public or synthetic data. Only three (`fedscene`, `ev-truck`, `forest`) define a real deployment `--node-config` data path, and one of those has a README/code key mismatch. None of them shows evidence of running on real edge hardware.

The node's footprint comes from the ML stack, not from `flwr`:
- **sklearn/numpy:** `dronesar`, `ev-truck`. These fit on a Pi.
- **PyTorch:** `fedler`, `forest`, `fedscene`, `bouquetfl`. The first two use tiny models; `fedscene` and `bouquetfl` train ResNet-18.
- **MLX:** Apple silicon only, and native macOS rather than Docker.
- **Bytes per round per direction** range from 48 B (`dronesar`) to about 47 MB (ResNet-18).

Intermittency is handled by the Flower transport, not by the apps. A SuperNode retries its connection indefinitely by default. The SuperLink marks it offline about 60 s after its last heartbeat, and sends offline nodes' replies back as `NODE_UNAVAILABLE` errors **[src]**. Only `ev-truck` (FedProx plus an `update-bytes` metric) and `bouquetfl` (OOM fallback) add anything at app level.

**For the hackathon:** an AgentApp SuperNode doesn't load torch. It's network-bound: LLM calls go out via `FLWR_MODEL_API_*`. So the smallest viable node for us is anything that runs Python 3.11 + `flwr` + `openai` with outbound 443, such as a laptop, a `flwr/supernode:1.39.0` container (alpine, ~122–125 MB compressed) or a Nebius container that stays up. The catch is that it has to be **long-lived**.

Apps fetched with `POST /v1/hub/fetch-zip` (`flwr_version: "1.39.0"`): dronesar-fl 0.1.0, aifes-gesture-recognition 0.0.11, fedscene 1.0.0, ev-truck-predictive-maintenance 0.2.3, fedler-farms 0.1.0, bouquetfl 1.0.0, quickstart-mlx 1.1.12, forest-monitoring-example 1.0.0. **None was skipped.**

---

## The spectrum: smallest to largest node

| Tier | Example hardware | Can it host `flower-supernode`? | Apps here (as designed → as actually runnable) |
|---|---|---|---|
| **0. MCU** | M5StickC Plus2: ESP32-PICO-V3-02, 2×240 MHz, 2 MB PSRAM, 8 MB flash, 2.4 GHz Wi-Fi **[docs: M5Stack]**. The ESP32 family has ~520 KB on-chip SRAM **[inference: Espressif datasheet]** | **No.** There's no CPython, and `flwr` needs Python ≥ 3.11 + gRPC + TLS + SQLAlchemy + an HTTP server **[src]**. The MCU needs a gateway, and even then only if the app is written for one **[inference]** | **aifes-gesture-recognition**: the MCU trains on-device, but talks MQTT and bypasses Flower's Fleet API entirely **[src]** |
| **1. SBC** | Raspberry Pi Zero 2 / 4 / 5, 64-bit Raspberry Pi OS Lite or Ubuntu Server, ≥ 32 GB µSD **[docs: embedded-devices example]**. Jetson Orin via container **[inference]** | **Yes.** The docs run `flower-supernode --insecure --superlink=SUPERLINK_IP:9092 --node-config="dataset-path=..."` on the Pi **[docs]**. The `flwr/supernode:1.39.0` image is multi-arch amd64/arm64 **[src: Docker Hub]** | Would fit: **dronesar** (sklearn, 6 floats), **ev-truck** (sklearn, 33 floats), **forest** (torch, 1.5 k params), **fedler** (torch, 62 k params) **[inference from src model sizes]** |
| **2. Laptop / Apple silicon** | Any x86-64/arm64 laptop; M-series Mac for MLX | Yes. This is the default in every README | **quickstart-mlx** (Metal, native macOS only **[inference]**), plus everything in tier 1 |
| **3. Vehicle / drone / camera gateway** | In-vehicle PC, depot server, NVR/edge box, Jetson Orin-class with 8 GB+ **[inference]** | Yes, if it runs 64-bit Linux + Python 3.11 | **fedscene** (ResNet-18 at 224² needs a GPU box in practice **[inference]**), **ev-truck** (its code comment says "SuperNodes on cellular networks at remote mine sites" **[src]**), **dronesar** (persona only) |
| **4. GPU server / cloud** | NVIDIA workstation, cloud VM, Kubernetes | Yes. SuperExec also has a `--executor kubernetes` mode that launches tasks as pods **[src]** `supercore/cli/flower_superexec.py`, `supercore/constant.py: ExecutorType` | **bouquetfl** (needs NVIDIA + CUDA MPS + sudo + systemd; it *emulates* smaller tiers on one big box), **fedscene** at scale |

**Jetson caveat:** a team on the NVIDIA forum ran Flower on a Xavier NX. On a Jetson Nano (JetPack 4 / Ubuntu 18.04, `l4t-pytorch:r32.7.1` container) they couldn't install the Flower version they needed, so they **fell back to hand-written MQTT** **[docs: NVIDIA forum]**. With 1.39 needing Python ≥ 3.11, even JetPack 6 (Ubuntu 22.04, Python 3.10) needs a separate interpreter or container. Its torch wheels also have to match that Python ABI **[inference]**.

### What crosses the wire per round (one direction)

| App | Model | Params | Bytes / round | Evidence |
|---|---|---|---|---|
| dronesar | `SGDClassifier` (1×5 coef + intercept) | 6 | 48 B (float64) | **[src]** `dronesar/task.py` |
| aifes | 60→4→3 dense (sigmoid, softmax) | 259 | 1,036 B + 12 B header, float32 | **[src]** `fl_server_mqtt.py`, `fl_comm_mqtt.h.md` |
| ev-truck | `LogisticRegression`, `max-features=32` | 33 | 264 B (logged as `update-bytes`) | **[src]** `client_app.py` |
| forest | 2-layer Conv2d time-series CNN | ~1,457 | ~5.8 KB | **[inference from src]** `task.py`, default config |
| mlx | MLP 784→32→32→10 | 26,506 | ~106 KB | **[inference from src]** `task.py` |
| fedler | 1-D CNN (64/64 filters, k=5) + FC 64 | ~62,082 | ~248 KB | **[inference from src]** `model.py` |
| fedscene | torchvision ResNet-18, 10 classes | ~11.2 M | ~45 MB | **[inference from src]** `task.py` |
| bouquetfl | `timm` ResNet-18 with its default 1000-class head, trained on CIFAR-10 | ~11.7 M | ~47 MB | **[inference from src]** `task/cifar10.py` |

`flwr` splits arrays into 5 MiB chunks (`FLWR_PRIVATE_MAX_ARRAY_CHUNK_SIZE`, env-overridable) and caps gRPC messages at 2 GB **[src]** `common/constant.py`, `supercore/grpc.py`. A ResNet-18 update is therefore ~9 chunks each way per round, which matters on a cellular link and doesn't matter on a LAN **[inference]**.

---

## 1. `@kariminem/dronesar-fl` (0.1.0)

Five search-and-rescue drones from different agencies train a shared survivor detector. Each agency's terrain produces a different false positive.

1. **What the node is:** a drone, one per agency (Park Service, Coast Guard, Fire Dept, Mountain Rescue, Volunteer Corps) **[docs]** README. In code it's `partition-id % 5` **[src]** `task.py: DRONE_AGENCIES`. It's designed for a SuperGrid **simulation** federation (`flwr run . supergrid --federation <your-simulation-federation>`), so it has no physical nodes **[docs]**.
2. **What it holds:** five derived "cue" scores per detection (thermal band, size, motion, silhouette, gait). These are *synthetic*, generated from seed `2000 + partition_id`. Only `coef_`/`intercept_` and scalar metrics leave the node **[src]** `client_app.py`, `task.py: load_data`. Caveat: the ServerApp **regenerates each drone's "mission candidates" on the server** (`load_mission_candidates(pid)`) to build its dispatch JSON. The "footage never leaves" claim is therefore a demonstration of the mechanism, not a real data flow **[src]** `server_app.py`.
3. **Footprint:** `flwr[simulation]>=1.37`, `scikit-learn>=1.6.1`, `numpy`. There's no GPU, and the per-node work is one `partial_fit` epoch on 240 rows **[src]** `pyproject.toml`, `client_app.py`. That would fit a Pi Zero 2 class device if it were deployed **[inference]**. `flower-supernode` would run on the drone's companion computer or a ground-station gateway, not on the flight controller **[inference]**.
4. **Configure/launch:** nothing is documented for deployment. The code reads `partition-id` and `num-partitions` unconditionally, so a real SuperNode would need `--node-config "partition-id=0 num-partitions=5"` **[src]**. The run config has `num-server-rounds=40` **[src]**.
5. **Intermittency/heterogeneity:** it handles extreme non-IID data through **one local SGD epoch per round** plus feature centring, because train-to-convergence and then average collapses to ~50 % accuracy **[docs]** README, `task.py: create_model`. It does nothing for dropouts. `FedAvg(fraction_train=1.0)` keeps the default `min_available_nodes=2` **[src]** (`serverapp/strategy/fedavg.py`).
6. **Type:** ServerApp + ClientApp. A companion AgentApp, `swarm-sar-commander`, consumes the `##FL_RESULT##` JSON **[docs]** README, Hub page.

## 2. `@fraunhofer-ims/aifes-gesture-recognition` (0.0.11)

Gesture recognition trained on an M5StickC Plus2 with AIfES (Fraunhofer's C library for on-device training). It's the only true MCU app in the set.

1. **What the node is:** an **ESP32 microcontroller** (M5StickC Plus2) with an MPU6886 IMU **[docs]** README, M5Stack. It is **not a SuperNode**. `client_app.py` is `app = ClientApp()` with no handlers, and a comment says "The actual clients are the AIfES-based microcontrollers" **[src]**. The ServerApp ignores `grid` and calls `run_mqtt_server()` **[src]** `server_app.py`.
2. **What it holds:** 15 IMU recordings (3 gestures × 5 samples × 20 timesteps × 3 axes = 60 features), which stay in device RAM. It sends float32 weights in a binary packet (`struct '<III'`: round, count, num_examples, then 259 floats) **[src]** `0_Flower_AIfES_MQTT.ino.md`, `fl_comm_mqtt.h.md`.
3. **Footprint:**
   - **Device:** Arduino IDE firmware using the AIfES, `M5StickCPlus2` and `PubSubClient` libraries. Training is Adam (lr 0.1) for 1000 epochs on 15 samples, and parameter and training memory are `malloc`'d on the heap **[src]** `aifes_f32_fnn.h.md`. The MQTT buffer is 1600 B **[src]** `fl_comm_mqtt.h.md`.
   - **Coordinator:** `torch==2.8.0`, `torchvision`, `paho-mqtt`, `flwr[simulation]>=1.24`, Python ≥ 3.10, even though the model is only 259 floats **[src]** `pyproject.toml`. Aggregation reuses the **legacy** `flwr.server.strategy.FedAvg.aggregate_fit` with fake `FitRes`/`DummyClientProxy` objects. These still exist in 1.39 through `flwr.compat` **[src]**.
   - So `flower-supernode` runs **nowhere**. The "proxy" is the MQTT broker plus the ServerApp process.
4. **Configure/launch:** Wi-Fi SSID and password, broker (default `broker.hivemq.com:1883`) and topic prefix `demo/fl` are **compile-time `#define`s** on the device and module constants on the server. There's no auth (`MQTT_USERNAME=''`), no TLS, and a MAC-derived client ID `esp32-XXXXXX` **[src]**. The `.ino`/`.h` files are shipped as `.ino.md`/`.h.md` because a FAB only includes `*.py, *.toml, *.md, *.yaml, *.yml, *.json, *.jsonl` **[src]** `flwr/common/constant.py: FAB_INCLUDE_PATTERNS`, **[docs]** README.
5. **Intermittency:**
   - The global model is published with **`retain=True`**, so a device that joins late gets the latest model: a store-and-forward pattern suited to MCUs **[src]**.
   - Rounds are synchronous: the server aggregates when ≥ `MIN_CLIENTS=2` updates arrive and rejects stale-round updates with an ACK error **[src]**.
   - The device waits 45 s (`FL_MQTT_WAIT_TIMEOUT_MS`) for a newer global model, then continues with its local model **[src]**.
   - `run_mqtt_server()` loops until SIGINT/SIGTERM, so the **Flower run never finishes on its own** **[src]**.
   - Anyone on the public broker who knows the topic can inject or poison weights **[inference]**.
6. **Type:** ServerApp (MQTT coordinator) + a stub ClientApp. It's FL, but outside Flower's messaging.

**Answer to "can an MCU run a SuperNode?"** No. Every Flower route to an MCU is a **gateway**:
- **This app's route:** MQTT to the ServerApp. It works, but it discards Flower's node identity, auth and Grid.
- **The Flower-native design:** a SuperNode on a Pi or laptop whose ClientApp bridges to one or more MCUs over MQTT, serial or BLE. It pushes the global weights down and returns the MCU's update as the reply. That's also where hierarchical, pre-aggregated FL would go **[inference]**.

A Flower Discuss thread from Jul–Aug 2026 mentions a student ESP32 client that its author agreed to publish on the Hub. The architecture isn't stated in the thread **[docs]**.

## 3. `@sony-ai/fedscene` (1.0.0)

A fleet of edge cameras (retail, campus, smart-city intersections) learns scene classification on a Places365 subset.

1. **What the node is:** one camera, or realistically the camera site's edge box. The README says "simulating a fleet of distributed edge cameras" **[docs]**.
2. **What it holds:** a Hugging Face `datasets` directory of images, loaded with `load_from_disk(data-path)`. It trains ResNet-18 locally and returns the full `state_dict`. Raw images never leave **[src]** `task.py`, `client_app.py`.
3. **Footprint:** `torch==2.8.0`, `torchvision==0.23.0`, `flwr-datasets[vision]` **[src]**. The ClientApp uses `cuda:0` when available and CPU otherwise **[src]**. Transforms are Resize 256 → CenterCrop 224 with batch 32, SGD with momentum, 1 local epoch **[src]**.
   - Training ResNet-18 at 224² with batch 32 needs several GB of activation memory. That's a tier-3 box (Jetson Orin / x86 + GPU), not a Pi **[inference]**.
   - The ServerApp also downloads the HF test split for centralised evaluation, so it needs torch and internet access **[src]** `task.py: load_centralized_testset`.
4. **Configure/launch** **[docs]** README:
   ```bash
   flwr-datasets create dpdl-benchmark/places365-mini-sample-hard --num-partitions 2 --out-dir demo_data
   flower-supernode --insecure --superlink <SUPERLINK-FLEET-API> \
       --node-config="data-path=/path/to/demo_data/partition_0"
   ```
   It picks simulation or deployment mode by checking whether `partition-id` and `num-partitions` are in `node_config`, which is a clean pattern **[src]**. Run config: `fraction-train=0.5`, `fraction-evaluate=0.5`, `local-epochs=1`, `learning-rate=0.1`, `batch-size=32` **[src]**.
5. **Intermittency/heterogeneity:** `fraction-train=0.5` samples half the online nodes per round, which is the only concession **[src]**. A ~45 MB update each way per round is the heaviest payload in the set **[inference]**.
6. **Type:** ServerApp + ClientApp (FedAvg).

## 4. `@priyanshu10/ev-truck-predictive-maintenance` (0.2.3)

Predictive maintenance on the public Scania Component X heavy-truck dataset. Each node is a fleet depot.

1. **What the node is:** a **fleet depot or gateway**, not an ECU. Comments talk about depots ("a mining operation with 25 % failure rate vs highway fleet with 4 %") and "SuperNodes on cellular networks at remote mine sites" **[src]** `client_app.py`, `constants.py`.
2. **What it holds:** the Scania CSVs (`train_operational_readouts.csv`, `train_tte.csv`), or a prepared CSV. It keeps the latest readout per vehicle and trains logistic regression on the first `max-features` anonymised columns **[docs]** `docs/data.md`, **[src]** `data.py`. It returns 33 float64 values **[src]**.
3. **Footprint:** `flwr>=1.31,<1.32`, `scikit-learn`, `numpy>=2`, `joblib`, plus `mlflow` and `boto3` for the ServerApp's registry and S3 upload. There's no GPU **[src]** `pyproject.toml`. Deployment mode **streams the 1.14 GB operational CSV** on the node (partition 0 of 1) **[src]** `data.py: load_local_data`, **[docs]** `scripts/preprocess_for_supergrid.py`. That's I/O-bound but fine on a Pi 4/5 with enough storage **[inference]**.
4. **Configure/launch** **[docs]** `docs/supergrid.md`:
   ```bash
   flower-supernode --superlink fleet-supergrid.flower.ai:443 \
     --auth-supernode-private-key ~/supernodes_keys/supernode-1 \
     --node-config "data-path='/data/scania-component-x'" \
     [--allow-runtime-dependency-installation]
   ```
   The README recommends "a prebuilt environment or container" for repeatable runs **[docs]**.
5. **Intermittency, bandwidth, heterogeneity:**
   - `strategy=fedprox` is manual FedProx: after an sklearn fit it applies `w ← (1-μ)·w_local + μ·w_global` **[src]**.
   - `partition-strategy=dirichlet` gives non-IID splits, and `update-bytes` is logged "because bandwidth is limited" **[src]**.
   - `min-available-clients=3` is passed to all three `min_*_nodes` settings, so a run blocks until three nodes are online **[src]** `server_app.py`.
6. **Type:** ServerApp + ClientApp. The "federated analyst" is an offline Gemini 2.5 Flash script over the metrics, **not an AgentApp** **[src]** `agent/federated_analyst.py`.

**Edge-relevant anti-pattern:** the SuperGrid simulation runtime has no node-local data. To get around that, the app **embeds 5,000 vehicles of Scania data in the FAB** as gzip + base64 in `embedded_data/_chunk_0.py` (~830 KB), split into files under 1 MB **[src]**. The limits it works around are real: `flwr app publish` rejects files over 1 MB, bundles over 10 MB or more than 1,000 files **[src]** `flwr/cli/app_cmd/publish.py`, `supercore/constant.py`, and `FAB_MAX_SIZE` is 10 MB **[src]**. The run config also has fields for `aws-access-key-id`/`aws-secret-access-key`, which would broadcast secrets to every node **[src]** `pyproject.toml`.

## 5. `@soil-ai-lab/fedler-farms` (0.1.0)

Soil clay and carbon prediction from Sentinel-2 bare-soil features across farms, based on a 2026 JAG paper.

1. **What the node is:** a **farm**, meaning a farm office PC or co-op server **[docs]** README ("Keeps all local soil data on-premise").
2. **What it holds:** in practice, nothing local. Both simulation and deployment **download the HF dataset** `soil-ai-lab/farms_sentinel_demo` and select a `NaturalIdPartitioner(partition_by="farm")` partition **[src]** `dataset.py`, `client_app.py`. The README names a different dataset (`dummy-soil-dataset`) **[docs]**. The "on-premise" claim describes the paper's setup, not this code **[inference]**.
3. **Footprint:** `torch>=2.0`, `pandas`, `scikit-learn`, `scipy`, `numpy<2`, and a ~62 k-parameter 1-D CNN. It uses CUDA if present and CPU otherwise **[src]**. It would fit a Pi 4 on CPU **[inference]**. It uses the **legacy** `NumPyClient`/`client_fn` and `server_fn`/`ServerAppComponents` APIs, still available through `flwr.compat` in 1.39 **[src]**.
4. **Configure/launch:** the README's deployment recipe starts each SuperNode with `--insecure --superlink 127.0.0.1:9092 --clientappio-api-address 127.0.0.1:910x`. **That flag is rejected in 1.39** ("this option is no longer supported; use `--host` and `--port` instead") **[src]** `supernode/cli/flower_supernode.py: _unsupported_runtime_api_address`.
   - Without `partition-id`, the client falls back to `abs(hash(str(node_id))) % num-clients` **[src]**.
   - Python's `str` hash is salted per interpreter, and each task runs in a new process, so a farm's partition can **change between rounds** and two farms can collide **[inference]**.
5. **Heterogeneity:** it uses early stopping on local validation, and FedAvg with `min_*_clients = num-clients = 3`, so a run waits for all three **[src]** `server_app.py`, `task.py`.
6. **Type:** ServerApp + ClientApp (legacy API).

## 6. `@arnogeimer/bouquetfl` (1.0.0)

A hardware-heterogeneity **emulator**. One NVIDIA box pretends to be many weaker client devices.

1. **What the node is:** an **emulated device** drawn from the Steam Hardware Survey (a GPU/CPU/RAM profile per client), sampled so it's never stronger than the host **[docs]** README, **[src]** `bouquetfl/utils/sampler.py` (`cuda_cores <= local`, `clock <= local`, …).
2. **What it holds:** a CIFAR-10 partition (`SizePartitioner`/Dirichlet from `flwr-datasets`) and the hardware profile the server sent in `train_config["hardware_config"]` **[src]** `scripts/server_app.py`, `task/cifar10.py`.
3. **Footprint:** Ubuntu 22.04 with systemd, an NVIDIA GPU with CUDA and **MPS**, `cpupower`, **sudo**, and Python 3.12 exactly (`>=3.12,<3.13`). It pins `ray==2.31.0` and uses `timm`, `torch>=2.7` and `numba` **[docs]** README, **[src]** `pyproject.toml`. How it throttles each client **[src]** `core/emulation_engine.py`, `core/training_worker.py`:

   | Resource | Mechanism |
   |---|---|
   | GPU clocks | `nvidia-smi` clock locking |
   | GPU compute | MPS `CUDA_MPS_ACTIVE_THREAD_PERCENTAGE` |
   | GPU memory | `torch.cuda.set_per_process_memory_fraction` |
   | CPU cores | `sched_setaffinity` |
   | CPU frequency | `cpupower` |
   | RAM | `systemd-run --scope -p MemoryMax=<n>G` |

   The model is hard-coded to `.cuda()`, with no CPU path **[src]** `task/cifar10.py`.
4. **Configure/launch:** simulation only. It reads `partition-id` **[src]**. The ServerApp profiles **its own** host (`get_all_local_info()`: `nvidia-smi`, `psutil`, `/etc/os-release`) and passes that to clients, so the ServerApp and ClientApps must share one physical machine **[src]**. Custom profiles go in `config/federation_client_hardware.toml` **[docs]**.
   - It asks for the **sudo password with `input()`** and stores it in a **plaintext keyring file** (`keyrings.alt.file.PlaintextKeyring`) **[src]** `core/power_clock_tools.py`.
   - That prompt would hang a headless SuperNode, and it's unacceptable on a shared node **[inference]**.
5. **Heterogeneity** is the whole point: it measures per-client `data_load_time`, `train_time` and `oom`. On OOM it returns the unmodified global model with `num_examples=0` so FedAvg can still proceed **[src]** `scripts/client_app.py`.
6. **Type:** ServerApp + ClientApp (simulation).

## 7. `@flwrlabs/quickstart-mlx` (1.1.12)

Flower's official MLX quickstart: MNIST with a two-layer MLP on Apple silicon.

1. **What the node is:** a **Mac** (Apple silicon laptop or desktop) **[docs]** Hub page ("designed for Apple Silicon").
2. **What it holds:** an MNIST IID partition downloaded from HF through `flwr-datasets` on each node. It returns ~106 KB of weights **[src]** `task.py`.
3. **Footprint:** `mlx==0.29.4` and `flwr-datasets[vision]` **[src]**.
   - MLX runs on Metal, so the SuperNode has to run **natively on macOS**. Docker on a Mac runs a Linux VM with no Metal access, so the `flwr/supernode` image can't accelerate it **[inference]**.
   - Plain `mlx` on Linux would also need MLX's CPU/CUDA backend extras **[inference, verify]**.
4. **Configure/launch:** the README defers to the generic Deployment Engine and Docker guides **[docs]**. The code reads `partition-id`/`num-partitions` unconditionally, so a real node needs `--node-config "partition-id=0 num-partitions=2"` **[src]**. The ServerApp uses the default `FedAvg()` (`min_available_nodes=2`) **[src]**.
5. **Intermittency:** not addressed.
6. **Type:** ServerApp + ClientApp.

## 8. `@johannes/forest-monitoring-example` (1.0.0)

Timber-volume regression from 40-year satellite time series (Horizon Europe MoniFun/PathFinder projects).

1. **What the node is:** a forestry organisation or inventory site holding its own plots **[docs]** README, **[inference]**.
2. **What it holds:** an `.npz` file with `X_train/y_train/X_val/y_val` (19 features × 40 years) plus scaler parameters (`target_mean/std`). It returns ~1.5 k CNN parameters and **sufficient statistics** (`sse`, `sum_y`, `sum_y2`, `sum_pred`), so the server computes a global R²/RMSE without seeing predictions **[src]** `client_app.py`, `server_app.py`. That's a good pattern for small nodes **[inference]**.
3. **Footprint:** `torch==2.7.1`, `torchvision`, `scikit-learn`, `pandas`, `joblib`. It uses CUDA if present **[src]**. It's tiny and fits a Pi **[inference]**.
4. **Configure/launch** **[docs]** README:
   ```bash
   flower-supernode --insecure --superlink <SUPERLINK-FLEET-API> \
       --node-config='client-id="CID_1" data-path="/path/to/demo_data/client_1_demo_data.npz"'
   ```
   - **The code reads `processed-data-npz`, not `data-path`**, so the README command raises `KeyError` in deployment **[src]** `client_app.py: _get_npz_path`. The README also uses typographic quotes (’ ”), which break shell parsing **[docs]**.
   - In simulation, every virtual client loads the **same** `sim-data` file, so there's no partitioning **[src]**.
   - Data comes from Zenodo record 18929115 **[docs]**.
5. **Intermittency:** `FedAvg(min_available_nodes=1, min_train_nodes=1, min_evaluate_nodes=1)` runs with whatever is online. It's the most tolerant of the set, though the unused run-config `min-available-nodes=2` suggests otherwise **[src]**. Local early stopping uses patience 3 **[src]** `task.py`.
6. **Type:** ServerApp + ClientApp.

---

## Cross-cutting: how `flwr` 1.39 behaves on an edge node

All of this is **[src]** from `flwr` 1.39.0 unless marked otherwise.

- **Process model:**
  - `flower-supernode` connects **outbound** over gRPC (`grpc-rere` by default, or `--grpc-adapter`) and polls for work every 3 s when idle (`start_client_internal.py`).
  - With the default `--isolation subprocess`, it spawns `flower-superexec`, which starts one process per ClientApp or AgentApp task.
  - It serves a Runtime HTTP API on `--host 127.0.0.1 --port 9094` by default, so there are **no inbound ports** unless you move it for `--isolation process` (Docker).
- **Reconnect and liveness:**
  - `--max-retries` and `--max-wait-time` default to `None`, so the node retries forever with capped exponential backoff (`supercore/retry/grpc_retry.py`).
  - Heartbeats go out every ~30 s (`HEARTBEAT_DEFAULT_INTERVAL`). The SuperLink sets `online_until = now + 2 × interval` and tags the node `OFFLINE` after that (`in_memory_linkstate.py`).
  - Messages for an offline node come back as `ErrorCode.NODE_UNAVAILABLE`.
  - The new-API strategies loop in `sample_nodes` until `min_available_nodes` are online (default 2), and `Strategy.start(timeout=3600)` bounds each round.
  - *So a node that loses connectivity for more than ~60 s mid-round drops out of that round rather than stalling it, but a federation below `min_available_nodes` blocks* **[inference]**.
- **Transport security:** TLS is on by default. `--insecure` turns it off, and `--root-certificates` takes a custom CA. The two are mutually exclusive (`supercore/grpc.py`). `--auth-supernode-private-key` takes an ECDSA key in SSH format. `--trusted-entities` pins which FAB signers the node accepts.
- **Dependencies:**
  - `--allow-runtime-dependency-installation` runs `python -m uv sync --no-install-package flwr` into `$FLWR_HOME/runtime-envs/<run_id>` (default `~/.flwr`). The env is deleted when the run ends. `uv` is a hard dependency of `flwr`, so it's already present (`supercore/superexec/dependency_installer.py`).
  - For torch apps on a Pi or a metered link, this can mean GB-scale downloads per cold run, softened only by uv's cache. **Pre-bake the image instead** **[inference]**.
- **Containers:**
  - `flwr/supernode:1.39.0` is the **alpine3.22 / py3.13** variant (~125 MB amd64, ~122 MB arm64 compressed). There are `-py3.11/3.12/3.13-ubuntu24.04` variants at ~211–228 MB **[src: Docker Hub API]**.
  - `flwr/superexec:1.39.0` is Ubuntu-based (~225 MB). The 1.39 Docker quickstart runs the SuperNode with `--isolation process --host 0.0.0.0 --port 9094` and a separate app image `FROM flwr/superexec:1.39.0`, which `pip install`s the app deps and connects with `--runtime-api-address supernode-1:9094` **[docs]**.
- **What a FAB can carry:** only `*.py, *.toml, *.md, *.yaml, *.yml, *.json, *.jsonl` files and `/LICENSE`, within ≤ 10 MB (`common/constant.py`). Firmware, weights or data have to be smuggled in as text (AIfES, ev-truck) or live on the node and be referenced through `--node-config` (fedscene, forest, ev-truck deployment).

## What this means for a hackathon SuperNode (laptop / Docker / Nebius Serverless)

Our app is an **AgentApp**. A worker does LLM calls and file reads, not training, so none of the ML-stack weight above applies. What matters is Python ≥ 3.11, `flwr` 1.39 + `openai`, outbound 443 to `fleet-supergrid.flower.ai`, and **staying up**.

- **Laptop** (what we'll most likely use):
  - Run it natively in a venv (`uv sync`) with `flower-supernode --superlink fleet-supergrid.flower.ai:443 --auth-supernode-private-key <key>`. There's no `--insecure`: SuperGrid is TLS with a public CA, so no `--root-certificates` is needed **[docs + inference]**.
  - Export `FLWR_MODEL_API_KEY` (plus `FLWR_MODEL_API_ENDPOINT` for Nebius Token Factory) and `FLWR_FILESYSTEM_ALLOWED_DIRS=<abs dir>` for supplier files **[docs]** `../hackathon-brief.md`, `../collaborative-agent.md`.
  - Stop the machine sleeping, e.g. `caffeinate -i` on macOS. Sleeping for more than ~60 s marks the node offline and hides it from `get_nodes` **[src + inference]**.
- **Docker** (reproducible, and the right way to run several "suppliers" on one box):
  - Use `flwr/supernode:1.39.0` (multi-arch), with keys mounted read-only and env passed with `-e`.
  - With the default subprocess isolation, the tasks run *inside* the SuperNode container. The alpine image doesn't contain `openai`, so either build a thin image `FROM flwr/supernode:1.39.0` with `pip install openai`, or use `--allow-runtime-dependency-installation`. The documented 1.39 alternative is `--isolation process` plus a `flwr/superexec`-based image **[docs + inference]**.
  - Give each container its own key pair and `--node-config`, e.g. `--node-config "supplier='acme-servos' region='eu'"`, read through `context.node_config` **[src]**.
  - Don't copy `--clientappio-api-address` from older Hub READMEs; 1.39 rejects it **[src]**.
- **Nebius Serverless:**
  - The brief promises a guide ("Spinning up a Flower SuperNode on a Nebius Serverless AI endpoint"), but the link is still TBD **[docs]** `../hackathon-brief.md`.
  - A SuperNode is a **long-lived outbound poller**, not a request handler: it polls every 3 s and heartbeats every 30 s **[src]**. Any scale-to-zero or idle-kill policy makes it look offline, so configure min replicas ≥ 1 and don't expose an HTTP endpoint **[inference]**.
  - Inject the private key as a secret file, not baked into the image **[inference]**.
  - A GPU only helps if the node hosts its own model. For Token Factory calls, CPU is enough **[inference]**.
- **Optional "edge" flourish:** one supplier node on a Raspberry Pi 5 (arm64 image, 64-bit OS) would show that "a SuperNode can be any device". For an AgentApp that's cheap, because there's no torch **[inference]**.
- **Patterns to borrow from these apps:**
  - Switch data source and role on **explicit `node_config` keys** and fail loudly if one is missing (fedscene's check; forest's key mismatch shows why).
  - Return **aggregates, not rows** (forest's sufficient statistics).
  - Never use `partition-id`, `hash(node_id)` or list position for identity (fedler).
  - Keep secrets and data **out of the FAB and run config** (ev-truck).

## Open questions

- [ ] Can a SuperGrid-hosted ServerApp open outbound non-HTTPS connections, such as AIfES's MQTT to `broker.hivemq.com:1883`? If not, the MCU app can't run on SuperGrid as published.
- [ ] Does a 1.39 SuperNode accept FABs whose `flwr-version-target` is much older (ev-truck targets 1.31 and pins `<1.32`)? Runtime install skips the `flwr` requirement **[src]**, but we haven't checked whether there's a compatibility gate.
- [ ] Nebius Serverless: can it run an always-on, outbound-only container with min replicas ≥ 1, mounted secrets, and no public endpoint? Who pays for idle time?
- [ ] Is there an official gateway/bridge pattern for MCUs? The ESP32 client promised on Flower Discuss (Aug 2026) hasn't been located on the Hub yet.
- [ ] Jetson: which JetPack plus Python ≥ 3.11 plus CUDA-enabled torch combination is supported? Is there a Flower-published L4T image, or only community `jetson-containers`?
- [ ] How long does `--allow-runtime-dependency-installation` cold-start take for a torch app on a Pi 5 over Wi-Fi? Does the uv cache survive between runs in the container images?
- [ ] Do hackathon SuperNodes (if organisers provide them) have `FLWR_FILESYSTEM_ALLOWED_DIRS` and `FLWR_MODEL_API_*` set, and can we pass `--node-config` to them? This repeats [../supergrid-setup.md](../supergrid-setup.md#open-questions-for-mentors).

## Sources

- Hub apps (via `api.flower.ai/v1/hub/fetch-zip`) and Hub pages: [dronesar-fl](https://flower.ai/apps/kariminem/dronesar-fl/), [aifes-gesture-recognition](https://flower.ai/apps/fraunhofer-ims/aifes-gesture-recognition/), [fedscene](https://flower.ai/apps/sony-ai/fedscene/), [ev-truck-predictive-maintenance](https://flower.ai/apps/priyanshu10/ev-truck-predictive-maintenance/), [fedler-farms](https://flower.ai/apps/soil-ai-lab/fedler-farms/), [bouquetfl](https://flower.ai/apps/arnogeimer/bouquetfl/), [quickstart-mlx](https://flower.ai/apps/flwrlabs/quickstart-mlx/), [forest-monitoring-example](https://flower.ai/apps/johannes/forest-monitoring-example/)
- Flower docs: [Embedded devices example](https://flower.ai/docs/examples/embedded-devices.html) ([README](https://github.com/adap/flower/blob/main/examples/embedded-devices/README.md)), [Docker quickstart](https://flower.ai/docs/framework/docker/tutorial-quickstart-docker.html), [Docker index](https://flower.ai/docs/framework/docker/index.html)
- Docker Hub tag API: `hub.docker.com/v2/repositories/flwr/{supernode,superexec}/tags` (1.39.0)
- Vendor and community: [M5StickC Plus2 specs](https://docs.m5stack.com/en/core/M5StickC%20PLUS2), [NVIDIA forum: Flower on Jetson Nano](https://forums.developer.nvidia.com/t/federated-learning-using-flower-on-jetson-nano-with-gpus/270557), [Flower Discuss: Implementing an MCU client](https://discuss.flower.ai/t/implementing-an-mcu-client/1266)
- `flwr` 1.39.0: `supernode/cli/flower_supernode.py`, `supernode/start_client_internal.py`, `supercore/superexec/dependency_installer.py`, `supercore/cli/flower_superexec.py`, `supercore/constant.py`, `supercore/grpc.py`, `common/constant.py`, `server/superlink/linkstate/in_memory_linkstate.py`, `serverapp/strategy/{fedavg,strategy,strategy_utils}.py`, `cli/app_cmd/publish.py`, `flwr-1.39.0.dist-info/METADATA`
