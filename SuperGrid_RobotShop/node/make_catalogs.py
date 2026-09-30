"""Build the per-store catalogues that the store SuperNodes read (node-local data, never in the FAB).

Reads docs/robot-parts-stores/classified/by-store/<store>.csv (34 columns) and writes
node/catalogs/<store>.csv with only the columns a store worker needs to quote a part.

Stdlib only; paths resolve from this file, so any cwd works:
    python3 SuperGrid_RobotShop/node/make_catalogs.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
SOURCE_DIR = REPO / "docs" / "robot-parts-stores" / "classified" / "by-store"
OUT_DIR = HERE / "catalogs"

STORES = ["adafruit", "sparkfun", "pololu", "servocity", "seeed", "dfrobot", "robotis", "waveshare"]
COLUMNS = [
    "product_id", "store_id", "store_name", "product_name", "sku",
    "product_url", "price", "currency", "part_type", "primary_role",
]


def build(store: str) -> tuple[int, int]:
    """Write one store's catalogue. Returns (source rows, written rows)."""
    src = SOURCE_DIR / f"{store}.csv"
    with src.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{src}: missing columns {missing}")
        rows = list(reader)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{store}.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)  # source order kept
    with out.open(encoding="utf-8", newline="") as fh:  # count what actually landed on disk
        written = sum(1 for _ in csv.DictReader(fh))
    return len(rows), written


def main() -> None:
    total_src = total_out = 0
    print(f"{'store':<10} {'source':>6} {'written':>7}")
    for store in STORES:
        n_src, n_out = build(store)
        total_src, total_out = total_src + n_src, total_out + n_out
        print(f"{store:<10} {n_src:>6} {n_out:>7}")
    print(f"{'total':<10} {total_src:>6} {total_out:>7}   -> {OUT_DIR}")
    if total_src != total_out:
        sys.exit("row counts differ")


if __name__ == "__main__":
    main()
