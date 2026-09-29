"""Validate reviewed product classifications and export consistent retailer CSVs."""
import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
STORES = ROOT.parent
REPO = STORES.parents[1]

# Column order is the same in the combined catalog and every per-store export.
COLUMNS = {
    "product_id": "Stable product ID, matching stores.json and CAD manifest",
    "store_id": "Stable retailer ID",
    "store_name": "Retailer name from the original catalog",
    "product_name": "Original catalog product name",
    "sku": "Retailer SKU, empty when not supplied",
    "product_url": "Original official product page",
    "store_category": "Original normalized technical category",
    "primary_role": "Main builder role; enum in taxonomy.json",
    "secondary_roles": "Optional alternative roles; pipe-separated, excludes primary",
    "part_type": "Specific component type; enum in taxonomy.json",
    "assembly_level": "complete_robot, module, component, kit, or accessory",
    "function_summary": "Researched physical function, paraphrased from the source",
    "classification_reason": "Reason for the inferred body role, not a vendor anatomical claim",
    "classification_confidence": "high, medium, or low; confidence in the suggested classification, not compatibility",
    "assembly_notes": "Purchased scope, exclusions, or extra parts needed",
    "price": "Original single-unit catalog price; not refreshed by classification research",
    "currency": "Original currency code; no conversion",
    "price_captured_at": "Date of the original price snapshot, YYYY-MM-DD",
    "spec_snapshot": "Technical specification summary retained from the original catalog",
    "evidence_status": "live_verified, catalog_snapshot_only, or inaccessible",
    "evidence_urls": "Pipe-separated official source URLs consulted; snapshot URLs are marked by evidence_status",
    "evidence_note": "Brief source finding; body-role mapping remains an inference",
    "researched_at": "Classification research date, YYYY-MM-DD",
    "image_url": "Vendor product-image URL extracted from official page metadata/main image; not locally downloaded",
    "image_source_url": "Product page from which the image URL was extracted",
    "image_captured_at": "Date of the saved page used for the image URL",
    "cad_status": "Original collection status; downloaded_3d, related_model_only, or not_found_in_checked_sources",
    "cad_formats": "Pipe-separated formats from the collection manifest",
    "cad_source_urls": "Pipe-separated original CAD download/source URLs",
    "cad_local_paths": "Pipe-separated original/extracted asset paths relative to repository root",
    "cad_notes": "Revision, product-family, or included-parts caveats from the CAD manifest",
    "browser_model_path": "Prepared GLB path relative to repository root, empty if not yet prepared",
    "browser_thumbnail_path": "Prepared PNG thumbnail path relative to repository root, empty if not yet prepared",
    "review_flags": "Pipe-separated flags for uncertain classifications, non-live evidence, or related-only CAD",
}
REQUIRED = ["product_id", "primary_role", "secondary_roles", "part_type", "assembly_level",
            "function_summary", "classification_reason", "classification_confidence", "assembly_notes",
            "evidence_status", "evidence_urls", "evidence_note", "researched_at"]
LIST_COLUMNS = ["secondary_roles", "evidence_urls", "cad_formats", "cad_source_urls", "cad_local_paths", "review_flags"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def joined(values):
    values = list(dict.fromkeys(values))
    require(all("|" not in value for value in values), "Pipe is reserved as the list separator")
    return "|".join(values)


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n", extrasaction="raise")
        writer.writeheader()
        writer.writerows(rows)


def main():
    catalog = json.loads((STORES / "stores.json").read_text())
    taxonomy = json.loads((ROOT / "taxonomy.json").read_text())
    manifest = json.loads((STORES / "cad/manifest.json").read_text())
    cad_products = {p["id"]: p for p in manifest["products"]}
    prepared = {p["id"]: p for p in json.loads((REPO / "docs/robot-builder/public/catalog.json").read_text())}
    images = {p["product_id"]: p for p in json.loads((ROOT / "image_sources.json").read_text())}
    all_rows, store_summaries = [], []
    seen = set()
    role_names = list(taxonomy["roles"])
    for store in catalog["stores"]:
        records = json.loads((ROOT / "research" / (store["id"] + ".json")).read_text())
        classifications = {r["product_id"]: r for r in records}
        require(len(classifications) == len(records), f"Duplicate classification in {store['id']}")
        require(set(classifications) == {p["id"] for p in store["items"]}, f"Incomplete or extra records in {store['id']}")
        rows = []
        for product in store["items"]:
            ident = product["id"]
            require(ident not in seen, f"Duplicate product {ident}")
            seen.add(ident)
            record = classifications[ident]
            require(all(k in record for k in REQUIRED), f"Missing fields in {ident}")
            for field, allowed in [("primary_role", role_names), ("part_type", taxonomy["part_types"]),
                                   ("assembly_level", taxonomy["assembly_levels"]),
                                   ("classification_confidence", taxonomy["confidence_levels"]),
                                   ("evidence_status", taxonomy["evidence_statuses"])]:
                require(record[field] in allowed, f"Invalid {field} in {ident}: {record[field]}")
            secondary = record["secondary_roles"]
            require(isinstance(secondary, list) and set(secondary) <= set(role_names), f"Invalid secondary roles in {ident}")
            require(record["primary_role"] not in secondary and len(set(secondary)) == len(secondary), f"Repeated role in {ident}")
            require(isinstance(record["evidence_urls"], list) and record["evidence_urls"], f"No evidence URLs for {ident}")
            require(all(urlparse(u).scheme in {"http", "https"} for u in record["evidence_urls"]), f"Invalid URL in {ident}")
            require(record["function_summary"] and record["classification_reason"] and record["evidence_note"], f"Missing explanation for {ident}")
            cad = cad_products[ident]
            assets = [a for a in manifest["assets"] if a["product_id"] == ident]
            paths = [path for a in assets for path in [a["path"], *[f["path"] for f in a["extracted_files"]]]]
            for path in paths:
                require((STORES / "cad" / path).is_file(), f"Missing local CAD asset {path}")
            preview = prepared.get(ident, {})
            model_path = f"docs/robot-builder/public/{preview['model']}" if preview else ""
            thumb_path = f"docs/robot-builder/public/{preview['thumbnail']}" if preview else ""
            for path in [model_path, thumb_path]:
                require(not path or (REPO / path).is_file(), f"Missing prepared asset {path}")
            image = images.get(ident, {})
            flags = []
            if record["classification_confidence"] != "high": flags.append("role_" + record["classification_confidence"] + "_confidence")
            if record["evidence_status"] != "live_verified": flags.append(record["evidence_status"])
            if cad["status"] == "related_model_only": flags.append("cad_related_model_only")
            row = dict(product_id=ident, store_id=store["id"], store_name=store["name"], product_name=product["name"],
                       sku=product.get("sku") or "", product_url=product["url"], store_category=product["category"],
                       **{key: record[key] for key in ["primary_role", "part_type", "assembly_level", "function_summary",
                           "classification_reason", "classification_confidence", "assembly_notes", "evidence_status", "evidence_note", "researched_at"]},
                       secondary_roles=joined(secondary), evidence_urls=joined(record["evidence_urls"]),
                       price=format(Decimal(str(product["price"])), ".2f") if product["price"] is not None else "",
                       currency=product["currency"], price_captured_at=catalog["captured_at"], spec_snapshot=product.get("spec") or "",
                       image_url=image.get("image_url", "") or record.get("image_url", ""),
                       image_source_url=image.get("image_source_url", ""), image_captured_at=image.get("image_captured_at", ""),
                       cad_status=cad["status"], cad_formats=joined(sorted({f for a in assets for f in a["formats"]})),
                       cad_source_urls=joined([a["source_url"] for a in assets]),
                       cad_local_paths=joined([f"docs/robot-parts-stores/cad/{p}" for p in paths]),
                       cad_notes=" ".join(filter(None,[cad.get("notes", ""), preview.get("note", "") if preview.get("modelKind") == "approximate_preview" else ""])),
                       browser_model_path=model_path, browser_thumbnail_path=thumb_path, review_flags=joined(flags))
            rows.append(row)
        # Assemble everything before publishing outputs, so missing research never creates partial CSVs.
        all_rows.extend(rows)
        counts = Counter(r["primary_role"] for r in rows)
        store_summaries.append(dict(store_id=store["id"], store_name=store["name"], product_count=len(rows),
            **{role: counts[role] for role in role_names},
            live_verified=sum(r["evidence_status"] == "live_verified" for r in rows),
            downloaded_3d=sum(r["cad_status"] == "downloaded_3d" for r in rows),
            related_model_only=sum(r["cad_status"] == "related_model_only" for r in rows),
            browser_ready=sum(bool(r["browser_model_path"]) for r in rows)))
    require(next(r for r in all_rows if r["product_id"] == "waveshare-wave-rover")["primary_role"] == "legs", "WAVE ROVER must be legs per user instruction")
    for store in catalog["stores"]:
        write_csv(ROOT / "by-store" / (store["id"] + ".csv"), [r for r in all_rows if r["store_id"] == store["id"]], COLUMNS)
    write_csv(ROOT / "all_parts.csv", all_rows, COLUMNS)
    write_csv(ROOT / "store_summary.csv", store_summaries, store_summaries[0].keys())
    write_csv(ROOT / "review_queue.csv", [r for r in all_rows if r["review_flags"]], COLUMNS)
    schema = dict(version=1, encoding="UTF-8", delimiter=",", list_separator="|", null_value="", path_base="repository root",
                  columns=[dict(name=k, description=v, type="pipe-separated list" if k in LIST_COLUMNS else "decimal" if k == "price" else "string") for k, v in COLUMNS.items()])
    (ROOT / "schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    print(json.dumps(dict(products=len(all_rows), stores=len(store_summaries), primary_roles=dict(Counter(r["primary_role"] for r in all_rows)),
        evidence=dict(Counter(r["evidence_status"] for r in all_rows)), with_images=sum(bool(r["image_url"]) for r in all_rows),
        review_items=sum(bool(r["review_flags"]) for r in all_rows)), indent=2))


if __name__ == "__main__":
    main()
