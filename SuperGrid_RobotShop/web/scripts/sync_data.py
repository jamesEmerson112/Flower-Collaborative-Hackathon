#!/usr/bin/env python3
"""Refresh the Robot Shop's static data from the repo's source datasets.

Re-runnable, stdlib only; every path resolves from this file, so any cwd works.

- public/catalog.json     <- docs/robot-builder/public/catalog.json, minus "price"/"currency"
- public/components.json  <- docs/robot-parts-stores/classified/all_parts.csv, rows not in the
                             catalog, as {id, name, store_id, store_name, part_type,
                             primary_role, summary} (no price: stores quote it at run time)
- public/models/, public/thumbnails/  <- copied from docs/robot-builder/public (replaced)
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

WEB = Path(__file__).resolve().parents[1]
ROOT = WEB.parents[1]
BUILDER_PUBLIC = ROOT / "docs" / "robot-builder" / "public"
ALL_PARTS = ROOT / "docs" / "robot-parts-stores" / "classified" / "all_parts.csv"
PUBLIC = WEB / "public"

DROP_KEYS = ("price", "currency")


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def sync_catalog() -> list[dict]:
    catalog = json.loads((BUILDER_PUBLIC / "catalog.json").read_text(encoding="utf-8"))
    cleaned = [{k: v for k, v in part.items() if k not in DROP_KEYS} for part in catalog]
    write_json(PUBLIC / "catalog.json", cleaned)
    return cleaned


def sync_components(catalog_ids: set[str]) -> list[dict]:
    with ALL_PARTS.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    components = [
        {
            "id": row["product_id"],
            "name": row["product_name"],
            "store_id": row["store_id"],
            "store_name": row["store_name"],
            "part_type": row["part_type"],
            "primary_role": row["primary_role"],
            "summary": row["function_summary"],
        }
        for row in rows
        if row["product_id"] and row["product_id"] not in catalog_ids
    ]
    write_json(PUBLIC / "components.json", components)
    return components


def sync_assets() -> dict[str, int]:
    counts = {}
    for name in ("models", "thumbnails"):
        src, dst = BUILDER_PUBLIC / name, PUBLIC / name
        if not src.is_dir():
            raise SystemExit(f"missing {src} (the builder's git-ignored assets)")
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        counts[name] = sum(1 for p in dst.iterdir() if p.is_file())
    return counts


def main() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    catalog = sync_catalog()
    components = sync_components({part["id"] for part in catalog})
    assets = sync_assets()
    print(f"catalog.json: {len(catalog)} body parts (price/currency removed)")
    print(f"components.json: {len(components)} components from "
          f"{len({c['store_id'] for c in components})} stores")
    print(f"assets: {assets['models']} models, {assets['thumbnails']} thumbnails")


if __name__ == "__main__":
    main()
