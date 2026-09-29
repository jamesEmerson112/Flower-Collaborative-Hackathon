"""Build robot-build-relay.html: inject the real store catalogues into the page template.

    python3 docs/artifacts/robot-build-relay/build.py

Reads docs/robot-parts-stores/stores.json, keeps only the fields the demo needs, and writes
robot-build-relay.html next to this script. Then syntax-checks the page script with node if available.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STORES = HERE.parents[1] / "robot-parts-stores" / "stores.json"
SHORT = {
    "adafruit": "Adafruit", "sparkfun": "SparkFun", "pololu": "Pololu", "servocity": "ServoCity",
    "seeed": "Seeed Studio", "dfrobot": "DFRobot", "robotis": "ROBOTIS", "waveshare": "Waveshare",
}


def main() -> None:
    src = json.loads(STORES.read_text(encoding="utf-8"))
    data = {
        "captured_at": src["captured_at"],
        "stores": [
            {
                "id": s["id"],
                "name": SHORT.get(s["id"], s["name"]),
                "items": [
                    {k: i[k] for k in ("name", "category", "price", "sku", "spec", "url")}
                    for i in s["items"]
                ],
            }
            for s in src["stores"]
        ],
    }
    page = (HERE / "page.template.html").read_text(encoding="utf-8")
    assert "__DATA__" in page
    out = page.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    dest = HERE / "robot-build-relay.html"
    dest.write_text(out, encoding="utf-8")
    items = sum(len(s["items"]) for s in data["stores"])
    print(f"wrote {dest.name}: {len(data['stores'])} stores, {items} items, {len(out) // 1024} KB")

    if shutil.which("node"):
        script = re.search(r"<script>(.*?)</script>", out, re.S).group(1)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(script)
        subprocess.run(["node", "--check", fh.name], check=True)
        Path(fh.name).unlink()
        print("page script: node --check OK")


if __name__ == "__main__":
    main()
