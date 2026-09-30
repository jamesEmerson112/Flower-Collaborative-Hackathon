#!/usr/bin/env bash
# Start one RobotShop store SuperNode. The node holds only its key and its private catalogue
# (catalogs/<store>.csv, read by the app's worker through context.node_config); the worker code
# arrives with each run's FAB. Store workers need no model key, so no .env is sourced here.
#
# Usage:
#   ./start-store.sh <store> [supergrid|local]
#     <store>     adafruit | sparkfun | pololu | servocity | seeed | dfrobot | robotis | waveshare
#     supergrid   join Flower's hosted SuperLink (default; the key must be registered, see setup-stores.sh)
#     local       join a SuperLink on this machine (flower-superlink --insecure at 127.0.0.1:9092)
#
# Needs flower-supernode on PATH (e.g. `. /root/SuperNode_James/hello-app/.venv/bin/activate`).
#
# Optional overrides:
#   SUPERNODE_NAME=...       node name (default: store-<store>); must match the registered name
#   SUPERNODE_KEY=/path      private key (default: ~/supernodes_keys/supernode-store-<store>)
#   SUPERNODE_PORT=9110      local Runtime API port (default: fixed per store, 9101-9108)
#   SUPERNODE_CATALOG=/path  catalogue CSV (default: catalogs/<store>.csv next to this script)
#   FLWR_HOME_OVERRIDE=/dir  Flower home for this node (default: ~/.flwr-store-<store>)
#
# Each store node gets its own FLWR_HOME: nodes sharing ~/.flwr can race while installing the
# same FAB (install_from_fab returns early once the folder exists). Only the supernode process
# sees it; `flwr login` tokens stay in the default ~/.flwr.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STORE="${1:-}"
MODE="${2:-supergrid}"

usage() {
  echo "Usage: $0 <adafruit|sparkfun|pololu|servocity|seeed|dfrobot|robotis|waveshare|hello-robot|niryo|pollen|robotshop|trossen|unitree> [supergrid|local]" >&2
}

# Fixed port map (bash 3.2 compatible, no associative arrays).
case "$STORE" in
  adafruit)  DEFAULT_PORT=9101 ;;
  sparkfun)  DEFAULT_PORT=9102 ;;
  pololu)    DEFAULT_PORT=9103 ;;
  servocity) DEFAULT_PORT=9104 ;;
  seeed)     DEFAULT_PORT=9105 ;;
  dfrobot)   DEFAULT_PORT=9106 ;;
  robotis)   DEFAULT_PORT=9107 ;;
  waveshare) DEFAULT_PORT=9108 ;;
  # Extra companies (priced ones from docs/robot-parts-stores/expansion), meant for a second machine.
  hello-robot) DEFAULT_PORT=9109 ;;
  niryo)       DEFAULT_PORT=9110 ;;
  pollen)      DEFAULT_PORT=9111 ;;
  robotshop)   DEFAULT_PORT=9112 ;;
  trossen)     DEFAULT_PORT=9113 ;;
  unitree)     DEFAULT_PORT=9114 ;;
  "")
    usage
    exit 2
    ;;
  *)
    echo "Unknown store '$STORE'." >&2
    usage
    exit 2
    ;;
esac

case "$MODE" in
  supergrid | local) ;;
  *)
    echo "Unknown mode '$MODE'." >&2
    usage
    exit 2
    ;;
esac

NAME="${SUPERNODE_NAME:-store-$STORE}"
KEY="${SUPERNODE_KEY:-$HOME/supernodes_keys/supernode-store-$STORE}"
PORT="${SUPERNODE_PORT:-$DEFAULT_PORT}"
CATALOG="${SUPERNODE_CATALOG:-$HERE/catalogs/$STORE.csv}"
STORE_FLWR_HOME="${FLWR_HOME_OVERRIDE:-$HOME/.flwr-store-$STORE}"

if [ ! -f "$CATALOG" ]; then
  echo "Catalogue not found at $CATALOG. Run: python3 $HERE/make_catalogs.py" >&2
  exit 1
fi
# The worker opens this path on the node, so it must be absolute.
CATALOG="$(cd "$(dirname "$CATALOG")" && pwd)/$(basename "$CATALOG")"

if ! command -v flower-supernode >/dev/null 2>&1; then
  echo "flower-supernode not found. Activate a Flower venv first, e.g." >&2
  echo "  . /root/SuperNode_James/hello-app/.venv/bin/activate" >&2
  exit 1
fi

if [ "$MODE" = supergrid ] && [ ! -f "$KEY" ]; then
  echo "Private key not found at $KEY. Create and register it first: ./setup-stores.sh --register-only $STORE" >&2
  exit 1
fi

# The app reads these through context.node_config on this node only.
NODE_CONFIG="robotshop-catalog=\"$CATALOG\" robotshop-store=\"$STORE\" node-name=\"$NAME\""

mkdir -p "$STORE_FLWR_HOME"
export FLWR_HOME="$STORE_FLWR_HOME"
echo "Starting $NAME (store=$STORE port=$PORT mode=$MODE FLWR_HOME=$FLWR_HOME catalog=$CATALOG)"

case "$MODE" in
  supergrid)
    exec flower-supernode \
      --superlink fleet-supergrid.flower.ai:443 \
      --auth-supernode-private-key "$KEY" \
      --port "$PORT" \
      --node-config "$NODE_CONFIG"
    ;;
  local)
    exec flower-supernode \
      --insecure \
      --superlink 127.0.0.1:9092 \
      --port "$PORT" \
      --node-config "$NODE_CONFIG"
    ;;
esac
