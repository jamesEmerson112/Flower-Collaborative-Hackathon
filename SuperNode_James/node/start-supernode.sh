#!/usr/bin/env bash
# Turn this machine into the SuperNode "james" (or any other name, see the overrides below).
# There's no app code here: the node only needs Flower, a key, and its local data (profile.json).
#
# Usage:
#   ./start-supernode.sh supergrid   # join Flower's hosted SuperLink (needs a registered key, see README)
#   ./start-supernode.sh local       # join a SuperLink on this machine (flower-superlink --insecure)
#
# Optional overrides, for starting another node with this same script:
#   SUPERNODE_NAME=alice        node name (default: james); also picks the default key file
#   SUPERNODE_KEY=/path/key     private key (default: ~/supernodes_keys/supernode-<name>)
#   SUPERNODE_PROFILE=/path     local profile (default: profile.json next to this script)
#   SUPERNODE_PORT=9095         local Runtime API port (default: 9094); each node on one machine needs its own
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAME="${SUPERNODE_NAME:-james}"
PROFILE="${SUPERNODE_PROFILE:-$HERE/profile.json}"
KEY="${SUPERNODE_KEY:-$HOME/supernodes_keys/supernode-$NAME}"
PORT="${SUPERNODE_PORT:-9094}"
MODE="${1:-supergrid}"

# The app reads these through context.node_config on this node only.
NODE_CONFIG="profile=\"$PROFILE\" node-name=\"$NAME\""

# Load model credentials (FLWR_MODEL_API_KEY, optional FLWR_MODEL_API_ENDPOINT) from the first
# .env found: node/.env, then the repo root. Values are never printed. Both files are git-ignored.
for ENV_FILE in "$HERE/.env" "$HERE/../../.env"; do
  if [ -f "$ENV_FILE" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    echo "Loaded model credentials from $(cd "$(dirname "$ENV_FILE")" && pwd)/.env"
    break
  fi
done

if ! command -v flower-supernode >/dev/null 2>&1; then
  echo "flower-supernode not found. Install Flower first (pip install -U flwr) or activate ../hello-app/.venv." >&2
  exit 1
fi

case "$MODE" in
  supergrid)
    if [ ! -f "$KEY" ]; then
      echo "Private key not found at $KEY. Create and register it first (README, step B1-B2)." >&2
      exit 1
    fi
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
  *)
    echo "Usage: $0 [supergrid|local]" >&2
    exit 2
    ;;
esac
