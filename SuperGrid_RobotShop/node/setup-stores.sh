#!/usr/bin/env bash
# Create, register and start the RobotShop store SuperNodes on this machine (made for the RunPod pod).
# Idempotent: run it again to fix whatever failed; finished steps are skipped or treated as success.
#
# Usage:
#   ./setup-stores.sh [--register-only | --start-only] [store ...]     (default: all 8 stores)
#     stores: adafruit sparkfun pololu servocity seeed dfrobot robotis waveshare
#
# Before running (on the pod):
#   . /root/SuperNode_James/hello-app/.venv/bin/activate    # puts flwr + flower-supernode on PATH
#   flwr login supergrid                                    # once; tokens live in the default ~/.flwr
#   cd /root/SuperGrid_RobotShop/node && ./setup-stores.sh
#
# Copying to the pod: ship ONLY this node/ folder (keys never leave the pod, app code never goes there):
#   tar -C SuperGrid_RobotShop -czf - node | base64      # on the Mac; unpack into /root/SuperGrid_RobotShop
#
# Per store <id>:
#   1. register phase (skipped by --start-only)
#      - key: ~/supernodes_keys/supernode-store-<id> (ecdsa P-384), created if missing
#      - `flwr supernode register <pub> supergrid --name store-<id> --format json` -> node ID.
#        If that fails (e.g. the key is already registered), the node is looked up through the
#        Control API by public key, then by name (`flwr supernode list --format json` has no names),
#        then in ~/supernodes_keys/store-node-ids.txt.
#      - `flwr federation add-supernode <node-id> @efebahadirgur/Spartan supergrid`;
#        "already part of the federation" (code 11) counts as success.
#      - records "<id> <node-id>" in ~/supernodes_keys/store-node-ids.txt
#   2. start phase (skipped by --register-only)
#      - tmux window store-<id> in session "flower" (created if missing) runs
#        ./start-store.sh <id> supergrid, logging to /tmp/store-<id>.log. Skipped if the window exists.
#
# Overrides: ROBOTSHOP_FEDERATION (default @efebahadirgur/Spartan), ROBOTSHOP_SUPERLINK (default supergrid).
# FLWR_HOME is deliberately NOT set here: flwr register/add need the login tokens in ~/.flwr.
# start-store.sh gives each node process its own FLWR_HOME.
set -uo pipefail   # no -e: one store's failure must not stop the others

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALL_STORES="adafruit sparkfun pololu servocity seeed dfrobot robotis waveshare"
EXTRA_STORES="hello-robot niryo pollen robotshop trossen unitree"  # pass by name, e.g. ./setup-stores.sh niryo pollen
FEDERATION="${ROBOTSHOP_FEDERATION:-@efebahadirgur/Spartan}"
SUPERLINK="${ROBOTSHOP_SUPERLINK:-supergrid}"
KEY_DIR="$HOME/supernodes_keys"
IDS_FILE="$KEY_DIR/store-node-ids.txt"
SESSION="flower"

usage() {
  sed -n '2,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

# ------------------------------------------------------------------ arguments
DO_REGISTER=1
DO_START=1
STORES=""
for arg in "$@"; do
  case "$arg" in
    --register-only) DO_START=0 ;;
    --start-only) DO_REGISTER=0 ;;
    -h | --help)
      usage
      exit 0
      ;;
    -*)
      echo "Unknown option '$arg'." >&2
      usage >&2
      exit 2
      ;;
    *)
      case " $ALL_STORES $EXTRA_STORES " in
        *" $arg "*) STORES="$STORES $arg" ;;
        *)
          echo "Unknown store '$arg'. Stores: $ALL_STORES" >&2
          exit 2
          ;;
      esac
      ;;
  esac
done
if [ "$DO_REGISTER" = 0 ] && [ "$DO_START" = 0 ]; then
  echo "--register-only and --start-only exclude each other." >&2
  exit 2
fi
STORES="${STORES:-$ALL_STORES}"

# ------------------------------------------------------------------ prerequisites
MISSING=""
if [ "$DO_REGISTER" = 1 ]; then
  command -v flwr >/dev/null 2>&1 || MISSING="$MISSING flwr"
  command -v ssh-keygen >/dev/null 2>&1 || MISSING="$MISSING ssh-keygen"
fi
if [ "$DO_START" = 1 ]; then
  command -v flower-supernode >/dev/null 2>&1 || MISSING="$MISSING flower-supernode"
  command -v tmux >/dev/null 2>&1 || MISSING="$MISSING tmux"
fi
if [ -n "$MISSING" ]; then
  echo "Missing on PATH:$MISSING" >&2
  echo "Activate the Flower venv first:  . /root/SuperNode_James/hello-app/.venv/bin/activate" >&2
  exit 1
fi

# Python with flwr (the venv's), for the Control API lookup; any python3 can parse JSON.
PY="python3"
if [ "$DO_REGISTER" = 1 ] && [ -x "$(dirname "$(command -v flwr)")/python" ]; then
  PY="$(dirname "$(command -v flwr)")/python"
fi

# A new tmux window gets the tmux server's environment, not ours: re-activate the venv inside it.
START_PREFIX=""
if [ "$DO_START" = 1 ]; then
  VENV_BIN="$(dirname "$(command -v flower-supernode)")"
  if [ -f "$VENV_BIN/activate" ]; then
    START_PREFIX=". $(printf '%q' "$VENV_BIN/activate") && "
  else
    START_PREFIX="export PATH=$(printf '%q' "$VENV_BIN"):\"\$PATH\" && "
  fi
fi

# ------------------------------------------------------------------ JSON helper (stdlib)
# modes: register-id (stdin) | add-status (stdin) | lookup <superlink> <pub-key-file> <name>
read -r -d '' PY_HELPER <<'PYEOF'
import json, re, sys

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
ID_KEYS = ("node-id", "node_id", "nodeId", "id")


def load(text):
    """The JSON object in the CLI output (tolerates colours and extra lines)."""
    text = ANSI.sub("", text)
    try:
        return json.loads(text)
    except ValueError:
        pass
    dec, objs, i = json.JSONDecoder(), [], text.find("{")
    while i != -1:
        try:
            obj, end = dec.raw_decode(text, i)
            objs.append(obj)
            i = text.find("{", end)
        except ValueError:
            i = text.find("{", i + 1)
    dicts = [o for o in objs if isinstance(o, dict)]
    with_success = [o for o in dicts if "success" in o]
    return (with_success or dicts or [None])[0]


def find_id(obj):
    if isinstance(obj, dict):
        for key in ID_KEYS:
            val = obj.get(key)
            if isinstance(val, int) and not isinstance(val, bool) or isinstance(val, str) and val.isdigit():
                return str(val)
        children = obj.values()
    elif isinstance(obj, list):
        children = obj
    else:
        return None
    for child in children:
        found = find_id(child)
        if found:
            return found
    return None


def register_id(text):
    obj = load(text)
    if isinstance(obj, dict) and obj.get("success") is False:
        return ""
    found = find_id(obj) if obj is not None else None
    if not found:
        m = re.search(r'"?node[-_]?id"?\s*[:=]\s*"?(\d+)', text, re.I) or re.search(
            r"SuperNode (\d+) registered", text)
        found = m.group(1) if m else ""
    return found


def add_status(text):
    obj = load(text)
    if isinstance(obj, dict) and obj.get("success") is True:
        return "ok"
    msg = str(obj.get("error-message", "")) if isinstance(obj, dict) else ANSI.sub("", text)
    if re.search(r"code:\s*11\b", msg) or "already" in msg.lower():
        return "already"
    if obj is None and "added to federation" in text:
        return "ok"
    return "fail"


def lookup(superlink, pub_path, name):
    """Find our node through the Control API: by public key, then by registered name."""
    from pathlib import Path
    from flwr.cli.flower_config import read_superlink_connection
    from flwr.cli.supernode.register import try_load_public_key
    from flwr.cli.utils import init_http_client_from_connection
    from flwr.proto.control_pb2 import ListNodesRequest  # pylint: disable=E0611

    key = try_load_public_key(Path(pub_path))
    client = init_http_client_from_connection(read_superlink_connection(superlink))
    try:
        nodes = list(client.ListNodes(ListNodesRequest()).nodes_info)
    finally:
        client.close()
    live = [n for n in nodes if n.status not in ("unregistered", "deleted")]
    live.sort(key=lambda n: n.registered_at)
    match = [n for n in live if n.public_key == key] or [n for n in live if n.name == name]
    return str(match[-1].node_id) if match else ""


mode = sys.argv[1]
if mode == "register-id":
    print(register_id(sys.stdin.read()))
elif mode == "add-status":
    print(add_status(sys.stdin.read()))
elif mode == "lookup":
    try:
        print(lookup(*sys.argv[2:5]))
    except BaseException as exc:  # report, never crash the shell script
        print(f"    lookup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        print("")
PYEOF

indent() { sed 's/^/    /'; }

is_node_id() {
  case "$1" in
    "" | *[!0-9]*) return 1 ;;
    *) return 0 ;;
  esac
}

# ------------------------------------------------------------------ per-store steps
# Results for the summary, one "<store>|<node-id>|<federation>|<start>" line per store.
SUMMARY=""
FAILED=""
R_ID="-"
R_FED="-"
R_START="-"

register_store() {
  local store="$1" name="store-$1" key="$KEY_DIR/supernode-store-$1" out node_id status

  # 1. key
  if [ ! -f "$key" ]; then
    mkdir -p "$KEY_DIR" || return 1
    chmod 700 "$KEY_DIR" || return 1
    ssh-keygen -q -t ecdsa -b 384 -N "" -C "supernode-store-$store" -f "$key" || return 1
    echo "  key: created $key"
  else
    echo "  key: exists $key"
  fi
  if [ ! -f "$key.pub" ]; then
    ssh-keygen -y -f "$key" >"$key.pub" || return 1
    echo "  key: rebuilt $key.pub"
  fi

  # 2. register (exit codes are unreliable in --format json mode, so parse the output)
  echo "  flwr supernode register $key.pub $SUPERLINK --name $name --format json"
  out="$(flwr supernode register "$key.pub" "$SUPERLINK" --name "$name" --format json 2>&1)"
  printf '%s\n' "$out" | indent
  node_id="$(printf '%s' "$out" | "$PY" -c "$PY_HELPER" register-id)"
  if is_node_id "$node_id"; then
    echo "  registered: $name = $node_id"
  else
    echo "  no node ID from register (already registered?); looking it up via the Control API"
    node_id="$("$PY" -c "$PY_HELPER" lookup "$SUPERLINK" "$key.pub" "$name")"
    if is_node_id "$node_id"; then
      echo "  found via Control API: $name = $node_id"
    elif [ -f "$IDS_FILE" ]; then
      node_id="$(awk -v s="$store" '$1 == s { id = $2 } END { print id }' "$IDS_FILE")"
      if is_node_id "$node_id"; then
        echo "  found in $IDS_FILE: $name = $node_id"
      fi
    fi
  fi
  if ! is_node_id "$node_id"; then
    echo "  ERROR: no node ID for $name" >&2
    return 1
  fi
  R_ID="$node_id"

  # 3. record it
  local tmp
  tmp="$(mktemp "$KEY_DIR/.store-node-ids.XXXXXX")" || return 1
  {
    if [ -f "$IDS_FILE" ]; then awk -v s="$store" '$1 != s' "$IDS_FILE"; fi
    echo "$store $node_id"
  } >"$tmp" && mv "$tmp" "$IDS_FILE" || return 1

  # 4. add to the federation
  echo "  flwr federation add-supernode $node_id $FEDERATION $SUPERLINK --format json"
  out="$(flwr federation add-supernode "$node_id" "$FEDERATION" "$SUPERLINK" --format json 2>&1)"
  printf '%s\n' "$out" | indent
  status="$(printf '%s' "$out" | "$PY" -c "$PY_HELPER" add-status)"
  case "$status" in
    ok) R_FED="added" ;;
    already) R_FED="already in" ;;
    *)
      R_FED="FAILED"
      echo "  ERROR: could not add $node_id to $FEDERATION" >&2
      return 1
      ;;
  esac
  echo "  federation: $R_FED $FEDERATION"
}

start_store() {
  local store="$1" win="store-$1" windows cmd
  if [ ! -f "$KEY_DIR/supernode-store-$store" ]; then
    echo "  ERROR: no key at $KEY_DIR/supernode-store-$store; run ./setup-stores.sh --register-only $store first" >&2
    R_START="no key"
    return 1
  fi
  if ! tmux has-session -t "$SESSION" 2>/dev/null; then
    tmux new-session -d -s "$SESSION" -c "$HERE" || { R_START="FAILED"; return 1; }
    echo "  tmux: created session $SESSION"
  fi
  windows="$(tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null)" || windows=""
  case $'\n'"$windows"$'\n' in
    *$'\n'"$win"$'\n'*)
      echo "  tmux window $SESSION:$win exists; leaving it (log /tmp/$win.log). To restart: tmux kill-window -t $SESSION:$win"
      R_START="already running"
      return 0
      ;;
  esac
  cmd="${START_PREFIX}cd $(printf '%q' "$HERE") && ./start-store.sh $store supergrid 2>&1 | tee /tmp/$win.log"
  tmux new-window -d -t "$SESSION:" -n "$win" -c "$HERE" || { R_START="FAILED"; return 1; }
  tmux send-keys -t "$SESSION:$win" "$cmd" Enter || { R_START="FAILED"; return 1; }
  echo "  started in tmux $SESSION:$win (log /tmp/$win.log)"
  R_START="started"
}

# ------------------------------------------------------------------ main
echo "Stores:$([ "$STORES" = "$ALL_STORES" ] && echo " (all)") $STORES"
echo "Federation: $FEDERATION   SuperLink: $SUPERLINK   register=$DO_REGISTER start=$DO_START"
for store in $STORES; do
  echo
  echo "== store-$store"
  R_ID="-"
  R_FED="-"
  R_START="-"
  ok=1
  if [ "$DO_REGISTER" = 1 ]; then
    register_store "$store" || ok=0
  fi
  if [ "$DO_START" = 1 ]; then
    if [ "$ok" = 1 ]; then
      start_store "$store" || ok=0
    else
      R_START="skipped"
    fi
  fi
  [ "$ok" = 1 ] || FAILED="$FAILED $store"
  SUMMARY="$SUMMARY$store|$R_ID|$R_FED|$R_START"$'\n'
done

echo
echo "== summary"
printf '%-10s %-22s %-12s %s\n' "store" "node-id" "federation" "start"
printf '%s' "$SUMMARY" | while IFS='|' read -r s id fed st; do
  printf '%-10s %-22s %-12s %s\n' "$s" "$id" "$fed" "$st"
done
if [ "$DO_REGISTER" = 1 ] && [ -f "$IDS_FILE" ]; then
  echo "Node IDs recorded in $IDS_FILE"
fi
if [ "$DO_START" = 1 ]; then
  echo "Check: flwr supernode list $SUPERLINK --format json   (status \"online\");  tail -f /tmp/store-<id>.log"
fi
if [ -n "$FAILED" ]; then
  echo "FAILED:$FAILED  (fix, then re-run: ./setup-stores.sh$FAILED)" >&2
  exit 1
fi
echo "All done."
