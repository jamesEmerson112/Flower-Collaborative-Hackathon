"""RobotShop bridge between the Robot Workshop page (web/) and Flower's SuperLink.

A browser can't call SuperGrid directly: the Control API speaks protobuf over HTTPS and
needs the tokens that `flwr login` saved in ~/.flwr. This small server does what
`flwr chat` does for one message, using flwr's own CLI helpers, and streams the run's
events back to the page as NDJSON (one JSON object per line). Every run packages the
RobotShop AgentApp (app/) into a FAB, like `/load app`.

Run it with the Python that has flwr installed (SuperNode_James/hello-app/.venv), after
`flwr login supergrid`:
    python bridge.py                      # then open http://127.0.0.1:8765
                                          # (serves web/dist; build it with `npm run build` in web/,
                                          #  or use `npm run dev`, which proxies /api here)

Routes:
    GET  /api/info    {"app_dir", "app_id", "superlink", "federation", "federations": [...]}
    GET  /<path>      static files from web/dist ("/" -> index.html); 404 outside dist
    POST /api/run     {"prompt", "federation"?, "series_id"?}  ->  NDJSON stream:
                        (federation defaults to --federation, "@efebahadirgur/Spartan")
                        {"kind": "run", "run_id", "series_id", "app_id"}
                        {"kind": "event", "type", "payload"}     (every event, incl. Grid tool calls)
                        {"kind": "done", "terminal_seen": bool}  or  {"kind": "error", "message"}
    POST /api/stop    {"run_id"}  ->  {"stopped": bool}
    POST /api/cache   {"prompt"}  (same JSON string as /api/run)  ->  200 the cached run for this
                        build (see "Cache mode"), 404 {"error": "no cached run for this build"},
                        or 400 if the prompt has no items
    GET  /api/cache/list          ->  {"runs": [{"key", "saved_at", "run_id", "request", "items"}]}
                                      newest first

Cache mode: SuperGrid can queue a run for minutes, so every LIVE run that ends with
terminal_seen true and a "robotshop.quote" event is saved to cache/<key>.json, where the key
is cache_key(items) of the prompt's build. The page can then replay the last live run for the
same build instantly (labelled as cached). A run keeps draining after the page disconnects, so
an abandoned run still refreshes the cache. The file is
    {"key", "saved_at" (UTC, ...Z), "run_id" (string, exact), "request", "items": [[pid, qty], ...],
     "lines": [every NDJSON line object of the run, in order]}
Import a run recorded with curl (same rules; exits without serving):
    python bridge.py --import-ndjson run.ndjson --prompt-json body.json   # body.json = {"prompt": "..."}

Uses flwr 1.39.0 internals (flwr.cli.chat.*), so it may need small changes after an upgrade.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import sys
import tempfile
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import click
from flwr.cli.chat.chat_app import format_failure_event, parse_task_event, start_chat_run
from flwr.cli.chat.chat_local_agent import build_local_agent
from flwr.cli.constant import CHAT_FAILURE_EVENTS, CHAT_TERMINAL_EVENTS
from flwr.cli.flower_config import read_superlink_connection
from flwr.cli.utils import init_http_client_from_connection
from flwr.proto.control_pb2 import (  # pylint: disable=E0611
    ListFederationsRequest,
    StopRunRequest,
    StreamRunEventsRequest,
)

HERE = Path(__file__).resolve().parent
LOOPBACK = {"127.0.0.1", "localhost", "::1"}
DIST = HERE / "web" / "dist"
CACHE_DIR = HERE / "cache"
QUOTE_EVENT = "robotshop.quote"
DEFAULT_FEDERATION = "@efebahadirgur/Spartan"

# Python's MIME table depends on the platform; module scripts must be served as JavaScript.
for _ext, _type in {
    ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
    ".html": "text/html", ".json": "application/json", ".svg": "image/svg+xml",
    ".png": "image/png", ".glb": "model/gltf-binary", ".gltf": "model/gltf+json",
    ".wasm": "application/wasm",
}.items():
    mimetypes.add_type(_type, _ext)


# ---------------------------------------------------------------------- cache mode
def canonical_items(items: list[dict[str, Any]]) -> list[list[Any]]:
    """The build as sorted [[product_id, qty], ...], duplicate product_ids merged (qty summed)."""
    merged: dict[str, int] = {}
    for item in items:
        pid = str(item["product_id"])
        merged[pid] = merged.get(pid, 0) + int(item.get("qty", 1))
    return sorted([pid, qty] for pid, qty in merged.items())


def cache_key(items: list[dict[str, Any]]) -> str:
    """16 hex chars identifying a build: same products and quantities -> same key, any order."""
    canon = json.dumps(canonical_items(items), separators=(",", ":"))
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def _prompt_object(prompt_str: Any) -> dict[str, Any] | None:
    try:
        data = json.loads(prompt_str) if isinstance(prompt_str, str) else None
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def items_from_prompt(prompt_str: Any) -> list[dict[str, Any]] | None:
    """The items of a /api/run prompt ({"request", "items": [...]}), or None if it has none.

    None also for free text, a malformed item (no product_id) or a qty that isn't an integer.
    """
    data = _prompt_object(prompt_str)
    items = data.get("items") if data else None
    if not isinstance(items, list) or not items:
        return None
    for item in items:
        if not isinstance(item, dict) or item.get("product_id") in (None, ""):
            return None
        try:
            int(item.get("qty", 1))
        except (TypeError, ValueError):
            return None
    return items


def request_from_prompt(prompt_str: Any) -> str:
    data = _prompt_object(prompt_str)
    request = data.get("request") if data else None
    return request if isinstance(request, str) else ""


def check_recordable(lines: list[dict[str, Any]]) -> str | None:
    """Why this run can't be cached, or None if it can (shared by live runs and --import-ndjson)."""
    if not any(line.get("kind") == "run" and line.get("run_id") is not None for line in lines):
        return "no run line with a run_id"
    if not any(line.get("kind") == "done" and line.get("terminal_seen") is True for line in lines):
        return "the run did not end with terminal_seen true"
    if not any(line.get("kind") == "event" and line.get("type") == QUOTE_EVENT for line in lines):
        return f"no {QUOTE_EVENT} event"
    return None


def write_cache(prompt_str: str, lines: list[dict[str, Any]], cache_dir: Path = CACHE_DIR) -> tuple[str, Path]:
    """Save a finished run as cache_dir/<key>.json (atomic). Raises ValueError if it isn't cacheable."""
    items = items_from_prompt(prompt_str)
    if not items:
        raise ValueError("the prompt has no items")
    reason = check_recordable(lines)
    if reason:
        raise ValueError(reason)
    run_line = next(line for line in lines if line.get("kind") == "run" and line.get("run_id") is not None)
    key = cache_key(items)
    record = {
        "key": key,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "run_id": str(run_line["run_id"]),  # a Python int, so the 64-bit id survives exactly
        "request": request_from_prompt(prompt_str),
        "items": canonical_items(items),
        "lines": lines,
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{key}.json"
    # A unique temp name per writer: two runs of the same build may finish at the same time.
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=cache_dir, prefix=f".{key}.",
                                     suffix=".tmp", delete=False) as tmp:
        json.dump(record, tmp)
        tmp.write("\n")
    try:
        os.chmod(tmp.name, 0o644)  # NamedTemporaryFile creates 0600
        os.replace(tmp.name, path)
    except OSError:
        os.unlink(tmp.name)
        raise
    return key, path


def list_cache(cache_dir: Path = CACHE_DIR) -> list[dict[str, Any]]:
    """Summaries of every cached run, newest first; unreadable files are skipped."""
    runs = []
    for path in cache_dir.glob("*.json") if cache_dir.is_dir() else []:
        if path.name.startswith("."):
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            runs.append({k: record[k] for k in ("key", "saved_at", "run_id", "request", "items")})
        except (OSError, ValueError, KeyError, TypeError) as exc:
            sys.stderr.write(f"[bridge] cache: skipping {path.name}: {exc}\n")
    runs.sort(key=lambda run: str(run["saved_at"]), reverse=True)
    return runs


def import_ndjson(ndjson_path: Path, prompt_json_path: Path, cache_dir: Path = CACHE_DIR) -> tuple[str, Path]:
    """CLI helper: cache a run recorded with curl from /api/run (same rules as a live run)."""
    lines = []
    for number, text in enumerate(ndjson_path.read_text(encoding="utf-8").splitlines(), 1):
        if text.strip():
            try:
                line = json.loads(text)
            except ValueError as exc:
                raise ValueError(f"{ndjson_path}:{number}: not JSON ({exc})") from None
            if not isinstance(line, dict):
                raise ValueError(f"{ndjson_path}:{number}: not a JSON object")
            lines.append(line)
    body = json.loads(prompt_json_path.read_text(encoding="utf-8"))
    prompt = body.get("prompt") if isinstance(body, dict) else None
    if not isinstance(prompt, str):
        raise ValueError(f'{prompt_json_path} must be a /api/run body: {{"prompt": "<JSON string>"}}')
    # Best-effort sanity check: warn if the recorded quote is for different products than the prompt.
    items = items_from_prompt(prompt) or []
    for line in lines:
        payload = line.get("payload")
        if line.get("type") == QUOTE_EVENT and isinstance(payload, dict) and isinstance(payload.get("quote"), dict):
            quote = payload["quote"]
            quoted = {str(entry.get("product_id")) for part in ("lines", "unquoted")
                      for entry in quote.get(part) or [] if isinstance(entry, dict)}
            wanted = {pid for pid, _ in canonical_items(items)}
            if quoted and quoted != wanted:
                sys.stderr.write(f"warning: the quote covers {sorted(quoted)} but the prompt asks for "
                                 f"{sorted(wanted)}\n")
            break
    return write_cache(prompt, lines, cache_dir)


class Bridge(BaseHTTPRequestHandler):
    """One instance per HTTP request; settings live on the server object."""

    server: "BridgeServer"

    # ------------------------------------------------------------------ routing
    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        route = urlsplit(self.path).path
        if route == "/api/info":
            if self._authorized():
                self._json(200, self._info())
        elif route == "/api/cache/list":
            if self._authorized():
                self._json(200, {"runs": list_cache(self.server.cache_dir)})
        else:
            self._static(route)

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        body = self._read_json()
        route = urlsplit(self.path).path
        if route == "/api/run":
            self._run(body)
        elif route == "/api/stop":
            self._json(200, {"stopped": self._stop(int(body.get("run_id", 0)))})
        elif route == "/api/cache":
            self._cached(body)
        else:
            self._json(404, {"error": "not found"})

    # ------------------------------------------------------------------ cache mode
    def _cached(self, body: dict[str, Any]) -> None:
        """Reply with the cached run for this prompt's build (the file as saved), or 404."""
        items = items_from_prompt(body.get("prompt"))
        if not items:
            self._json(400, {"error": "the prompt has no items"})
            return
        path = self.server.cache_dir / f"{cache_key(items)}.json"
        try:
            data = path.read_bytes()
        except FileNotFoundError:
            self._json(404, {"error": "no cached run for this build"})
            return
        self._send(200, data, "application/json")

    def _record(self, prompt: str, lines: list[dict[str, Any]]) -> None:
        """Save a finished live run to the cache if it qualifies; never raises."""
        try:
            if items_from_prompt(prompt) is None:
                reason = "the prompt has no items"
            else:
                reason = check_recordable(lines)
            if reason:
                sys.stderr.write(f"[bridge] cache: run not cached ({reason})\n")
                return
            key, path = write_cache(prompt, lines, self.server.cache_dir)
            sys.stderr.write(f"[bridge] cache: saved {key} -> {path}\n")
        except Exception as exc:  # pylint: disable=broad-except
            sys.stderr.write(f"[bridge] cache: write failed: {type(exc).__name__}: {exc}\n")

    # ------------------------------------------------------------------ Flower calls
    def _client(self):
        """A fresh Control API client per request (two requests can be in flight at once)."""
        return init_http_client_from_connection(read_superlink_connection(self.server.superlink))

    def _info(self) -> dict[str, Any]:
        client = self._client()
        try:
            federations = [f.name for f in client.ListFederations(ListFederationsRequest()).federations]
        except click.ClickException as exc:
            federations, error = [], exc.format_message()
        else:
            error = None
        finally:
            client.close()
        return {
            "app_dir": str(self.server.app_dir),
            "app_id": self._app_id(),
            "superlink": self.server.superlink,
            "federation": self.server.federation,
            "federations": federations,
            "error": error,
        }

    def _app_id(self) -> str | None:
        try:
            return build_local_agent(self.server.app_dir).app_spec
        except click.ClickException:
            return None

    def _run(self, body: dict[str, Any]) -> None:
        """Start one run (= one chat message) and stream its events to the page.

        Every line is also kept so a finished run can be cached. If the page disconnects, the
        bridge stops writing but keeps draining the run to its end, so the cache still refreshes.
        """
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        lines: list[dict[str, Any]] = []
        self._client_gone = False
        client = self._client()
        try:
            prompt = str(body.get("prompt", "")).strip()
            if not prompt:
                raise click.ClickException("Empty prompt.")
            # Same as /load <dir>: package the app folder into a FAB, rebuilt on every message.
            agent = build_local_agent(self.server.app_dir)
            run_id, series_id = start_chat_run(
                client,
                prompt,
                body.get("federation") or self.server.federation or None,
                body.get("series_id"),
                fab_hash=agent.fab_hash,
                fab_content=agent.fab_content,
            )
            self._emit(lines, {"kind": "run", "run_id": run_id, "series_id": series_id,
                               "app_id": agent.app_spec})

            terminal_seen = False
            for res in client.StreamRunEvents(StreamRunEventsRequest(run_id=run_id)):
                event_type, payload = parse_task_event(res.task_event)
                self._emit(lines, {"kind": "event", "type": event_type, "payload": payload})
                if event_type in CHAT_FAILURE_EVENTS:
                    raise click.ClickException(format_failure_event(payload))
                terminal_seen = terminal_seen or event_type in CHAT_TERMINAL_EVENTS
            self._emit(lines, {"kind": "done", "terminal_seen": terminal_seen})
            self._record(prompt, lines)
        except click.ClickException as exc:
            self._emit(lines, {"kind": "error", "message": exc.format_message()})
        except Exception as exc:  # pylint: disable=broad-except
            self._emit(lines, {"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
        finally:
            client.close()

    def _emit(self, lines: list[dict[str, Any]], obj: dict[str, Any]) -> None:
        """Keep a line for the cache and send it, unless the page has gone (then just keep it)."""
        lines.append(obj)
        if self._client_gone:
            return
        try:
            self._line(obj)
        except OSError as exc:  # BrokenPipe/ConnectionReset, or e.g. EPROTOTYPE on macOS
            self._client_gone = True
            sys.stderr.write(f"[bridge] page disconnected ({type(exc).__name__}); "
                             "draining the run for the cache\n")

    def _stop(self, run_id: int) -> bool:
        client = self._client()
        try:
            return bool(client.StopRun(request=StopRunRequest(run_id=run_id)).success)
        except click.ClickException:
            return False
        finally:
            client.close()

    # ------------------------------------------------------------------ static files
    def _static(self, url_path: str) -> None:
        """Serve the built page from web/dist; anything resolving outside dist is a 404."""
        if not DIST.is_dir():
            self._json(404, {"error": "web/dist not built; run npm run build in web/ or use npm run dev"})
            return
        root = DIST.resolve()
        try:
            target: Path | None = (root / unquote(url_path).lstrip("/")).resolve()
        except (OSError, ValueError):  # e.g. an embedded NUL byte
            target = None
        if target is not None and target.is_dir():
            target = target / "index.html"
        if target is None or not target.is_relative_to(root) or not target.is_file():
            self._json(404, {"error": "not found"})
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in ("application/json", "image/svg+xml"):
            content_type += "; charset=utf-8"
        self._send(200, target.read_bytes(), content_type)

    # ------------------------------------------------------------------ HTTP helpers
    def _authorized(self) -> bool:
        token = self.server.token
        if token and self.headers.get("X-Bridge-Token") != token:
            self._json(401, {"error": "missing or wrong X-Bridge-Token"})
            return False
        return True

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        try:
            data = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            data = {}
        return data if isinstance(data, dict) else {}

    def _send(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, obj: Any) -> None:
        self._send(status, json.dumps(obj).encode(), "application/json")

    def _line(self, obj: Any) -> None:
        self.wfile.write(json.dumps(obj).encode() + b"\n")
        self.wfile.flush()

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write(f"[bridge] {self.address_string()} {fmt % args}\n")


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr: tuple[str, int], app_dir: Path, superlink: str, token: str | None,
                 federation: str | None, cache_dir: Path = CACHE_DIR):
        super().__init__(addr, Bridge)
        self.app_dir, self.superlink, self.token = app_dir, superlink, token
        self.federation, self.cache_dir = federation, cache_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--app-dir", type=Path, default=HERE / "app",
                        help="AgentApp folder sent with every run (like /load <dir>)")
    parser.add_argument("--superlink", default=os.environ.get("FLWR_CHAT_SUPERLINK", "supergrid"),
                        help="connection name from ~/.flwr/config.toml")
    parser.add_argument("--federation", default=os.environ.get("ROBOTSHOP_FEDERATION", DEFAULT_FEDERATION),
                        help="federation used when a /api/run body names none")
    parser.add_argument("--import-ndjson", type=Path, metavar="FILE",
                        help="cache a /api/run NDJSON recording (e.g. from curl) and exit; "
                             "needs --prompt-json")
    parser.add_argument("--prompt-json", type=Path, metavar="FILE",
                        help='the /api/run body of that recording: {"prompt": "<JSON string>"}')
    args = parser.parse_args()

    if args.import_ndjson or args.prompt_json:
        # Handled before BridgeServer() binds the port: importing never serves.
        if not (args.import_ndjson and args.prompt_json):
            parser.error("--import-ndjson and --prompt-json go together")
        try:
            key, path = import_ndjson(args.import_ndjson, args.prompt_json)
        except (OSError, ValueError) as exc:
            sys.exit(f"import failed: {exc}")
        print(f"cached {key} -> {path}")
        return

    token = os.environ.get("BRIDGE_TOKEN") or None
    if args.host not in LOOPBACK and not token:
        # Anyone who can reach this port could start runs in your federations as you.
        sys.exit("Refusing to listen on a non-loopback host without BRIDGE_TOKEN set.")

    server = BridgeServer((args.host, args.port), args.app_dir.resolve(), args.superlink, token,
                          args.federation or None)
    print(f"RobotShop bridge on http://{args.host}:{args.port}  app={args.app_dir.resolve()}  "
          f"superlink={args.superlink}  federation={args.federation}  "
          f"web={DIST}{'' if DIST.is_dir() else ' (not built)'}  token={'on' if token else 'off'}",
          flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
