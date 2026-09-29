"""Extract product-image links from saved official pages; do not download images."""
import argparse
import hashlib
import json
import re
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent


class Metadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.image = None
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta" and attrs.get("property", attrs.get("name")) == "og:image":
            self.image = attrs.get("content")
        if tag == "img" and attrs.get("src"):
            self.images.append(attrs["src"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--html-dir", action="append", required=True,
                        help="Saved official HTML directory; later directories take priority")
    parser.add_argument("--captured-at", type=date.fromisoformat, required=True,
                        help="Date the supplied HTML pages were captured, YYYY-MM-DD")
    args = parser.parse_args()
    catalog = json.loads((ROOT.parent / "stores.json").read_text())
    result = []
    for store in catalog["stores"]:
        for product in store["items"]:
            candidates = [Path(folder) / (product["id"] + ".html") for folder in args.html_dir]
            source = next((p for p in reversed(candidates) if p.exists()), None)
            row = dict(product_id=product["id"], image_url="", image_source_url=product["url"],
                       image_captured_at=args.captured_at.isoformat(), image_source_kind="not_found", source_html_sha256="")
            if source:
                raw = source.read_bytes()
                html = raw.decode("utf-8", errors="replace")
                metadata = Metadata()
                metadata.feed(html)
                image = metadata.image
                kind = "product_page_og_image"
                if not image:
                    section = re.search(r'<div\s+class=[\"\']product-image[\"\'][^>]*>([\s\S]{0,4000})', html)
                    if section:
                        main_image = Metadata()
                        main_image.feed(section.group(1))
                        image = next(iter(main_image.images), None)
                        kind = "product_page_main_image"
                if image:
                    row.update(image_url=urljoin(product["url"], image), image_source_kind=kind)
                row["source_html_sha256"] = hashlib.sha256(raw).hexdigest()
            result.append(row)
    (ROOT / "image_sources.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Extracted {sum(bool(p['image_url']) for p in result)}/{len(result)} product-image URLs")


if __name__ == "__main__":
    main()
