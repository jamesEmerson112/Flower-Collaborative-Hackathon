#!/usr/bin/env python3
"""Regenerate everything in this folder from stores.json (the source of truth).

    python3 build.py

Writes:
  index.html                  - embeds a copy of the store/item data inline (works from file://)
  data/stores.csv             - one row per store
  data/items.csv              - one row per item
  data/by-store/<id>.json     - one supplier catalogue per store (drop-in for a supplier SuperNode)
  data/sources.csv            - every URL fetched during research, with HTTP status and time

Then syntax-checks the page's inline app script with `node --check` when Node is available.
Standard library only.
"""
import csv
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "stores.json"
PAGE = HERE / "index.html"
DATA = HERE / "data"

STORE_KEYS = ["id", "name", "url", "country", "specialty", "ships_international", "fetch_status", "notes"]
ITEM_KEYS = ["id", "name", "category", "price", "currency", "sku", "url", "spec"]


def validate(d):
    cats = {c["id"] for c in d["categories"]}
    seen = set()
    for s in d["stores"]:
        missing = [k for k in STORE_KEYS + ["items"] if k not in s]
        assert not missing, f"store {s.get('id')}: missing {missing}"
        for it in s["items"]:
            missing = [k for k in ITEM_KEYS if k not in it]
            assert not missing, f"item {it.get('id')}: missing {missing}"
            assert it["category"] in cats, f"item {it['id']}: unknown category {it['category']}"
            assert it["id"] not in seen, f"duplicate item id {it['id']}"
            assert it["price"] is None or isinstance(it["price"], (int, float)), f"item {it['id']}: price not numeric"
            assert it["url"].startswith("http"), f"item {it['id']}: bad url"
            seen.add(it["id"])


def cell(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, float):
        return f"{v:.2f}"
    return v


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            w.writerow([cell(v) for v in r])


def write_data(d):
    write_csv(
        DATA / "stores.csv",
        ["id", "name", "url", "country", "specialty", "ships_international", "fetch_status", "item_count"],
        [[s["id"], s["name"], s["url"], s["country"], s["specialty"], s["ships_international"], s["fetch_status"], len(s["items"])]
         for s in d["stores"]],
    )
    write_csv(
        DATA / "items.csv",
        ["store_id", "store_name", "item_id", "name", "category", "price", "currency", "sku", "spec", "url", "captured_at"],
        [[s["id"], s["name"], it["id"], it["name"], it["category"], it["price"], it["currency"], it["sku"], it["spec"], it["url"], d["captured_at"]]
         for s in d["stores"] for it in s["items"]],
    )
    write_csv(
        DATA / "sources.csv",
        ["url", "store_id", "http_status", "fetched_at", "role"],
        [[r["url"], r["store_id"], r["http_status"], r["fetched_at"], r.get("role")] for r in d.get("sources", [])],
    )
    by_store = DATA / "by-store"
    by_store.mkdir(parents=True, exist_ok=True)
    wanted = set()
    for s in d["stores"]:
        used = {it["category"] for it in s["items"]}
        doc = {
            "captured_at": d["captured_at"],
            "currency_note": d["currency_note"],
            "categories": [c for c in d["categories"] if c["id"] in used],
            "store": {k: s[k] for k in STORE_KEYS},
            "items": s["items"],
        }
        p = by_store / f"{s['id']}.json"
        wanted.add(p.name)
        p.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for old in by_store.glob("*.json"):  # drop catalogues for stores no longer in stores.json
        if old.name not in wanted:
            old.unlink()


def embed(d):
    page_data = {k: v for k, v in d.items() if k != "sources"}
    blob = json.dumps(page_data, ensure_ascii=False, separators=(",", ":"))
    # Safe inside <script>: no "</script>", no HTML-significant characters, no JS line separators.
    blob = (blob.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
                .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))
    html = PAGE.read_text(encoding="utf-8")
    pat = re.compile(r'(<script id="store-data" type="application/json">)(.*?)(</script>)', re.S)
    html, n = pat.subn(lambda m: m.group(1) + blob + m.group(3), html, count=1)
    if n != 1:
        sys.exit("index.html: store-data script block not found")
    PAGE.write_text(html, encoding="utf-8")
    return html


def node_check(html):
    node = shutil.which("node")
    if not node:
        print("node not found; skipped syntax check")
        return True
    m = re.search(r'<script id="app">(.*?)</script>', html, re.S)
    if not m:
        sys.exit("index.html: app script block not found")
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as f:
        f.write(m.group(1))
        tmp = f.name
    r = subprocess.run([node, "--check", tmp], capture_output=True, text=True)
    Path(tmp).unlink(missing_ok=True)
    if r.returncode != 0:
        print(r.stderr)
        return False
    # the embedded JSON must parse too
    blob = re.search(r'<script id="store-data" type="application/json">(.*?)</script>', html, re.S).group(1)
    json.loads(blob)
    print("node --check: inline app script OK; embedded JSON parses")
    return True


def main():
    d = json.loads(SRC.read_text(encoding="utf-8"))
    validate(d)
    write_data(d)
    html = embed(d)
    n_items = sum(len(s["items"]) for s in d["stores"])
    print(f"built index.html + data/: {len(d['stores'])} stores, {n_items} items, {len(d.get('sources', []))} sources")
    if not node_check(html):
        sys.exit(1)


if __name__ == "__main__":
    main()
