# Robot parts stores

Eight online retailers that sell robotics parts to the public, each with 11–12 real items (95 in total). The data was captured from each store's own product pages on **2026-09-29**, for the hackathon demo where a "shop" agent sources parts from "supplier" agents.

> **Prices change.** Every price is the single-unit price as it appeared on the product page on 2026-09-29, in that page's currency (all USD in this capture). No currency conversion, tax, shipping, quantity discounts or stock levels are included. Check the product page before relying on a price.

## Files

The [classified parts database](classified/README.md) adds researched robot body
roles, component types, product images, evidence, and CAD links for all 95 items.
It includes one identically formatted CSV per store and a combined catalog.

| File | What it is |
| --- | --- |
| `stores.json` | **Source of truth.** `{captured_at, currency_note, scope_note, categories[], stores[{id, name, url, country, specialty, ships_international, fetch_status, notes, items[{id, name, category, price, currency, sku, url, spec}]}], sources[]}` |
| `index.html` | Self-contained browser page with the same data embedded inline. Open it straight from disk (`file://`). It needs no network, apart from optional Google Fonts that fall back to system fonts. |
| `data/stores.csv` | One row per store: `id, name, url, country, specialty, ships_international, fetch_status, item_count` |
| `data/items.csv` | One row per item: `store_id, store_name, item_id, name, category, price, currency, sku, spec, url, captured_at` |
| `data/by-store/<store_id>.json` | One catalogue per store (`captured_at`, `currency_note`, the categories it uses, `store`, `items`). Drop one of these onto a supplier SuperNode as that supplier's local catalogue. |
| `data/sources.csv` | Every URL fetched during research: `url, store_id, http_status, fetched_at, role`. `role` is `item` (the item's product page), `listing / discovery` (category or search pages used to find items) or `probe` (reachability checks for stores that were skipped). Raw HTML is not stored in the repo. |
| `build.py` | Regenerates `index.html` and everything in `data/` from `stores.json`, then syntax-checks the page script with `node --check`. |

CSV files are UTF-8 with a header row. A null value is an empty cell. `ships_international` is `true`, `false` or empty.

## Regenerate

```sh
python3 build.py
```

Edit `stores.json`, then run the build. It uses only the Python standard library. The build validates the data (known category, unique ids, numeric prices), rewrites `data/`, re-embeds the data in `index.html`, and runs `node --check` on the inline script if Node is installed.

## Data rules

- Every item comes from a product page that was fetched on the capture date, and `url` is that page. Where a site redirected (for example SparkFun's legacy `/products/NNNNN` links), `url` is the final address.
- `name`, `price`, `currency` and `sku` come from the page's schema.org Product data, or from the visible page where a page had none (three Waveshare items). A field the page did not show is `null`. The three Waveshare items have no SKU for this reason.
- `spec` is a short summary written from the page's own description or specification table.
- `ships_international` is set only where a fetched page said so: Seeed Studio, Waveshare, and ROBOTIS America (which ships to the Americas only). The other stores are `null`, and `notes` records what the pages did say.
- `country` means HQ country. It was confirmed from the site footer for SparkFun (Niwot, CO) and ROBOTIS America (Corona, CA). For the other six it comes from general knowledge, and `notes` says so.
- Categories: `motors`, `servos`, `motor-drivers`, `microcontrollers-sbc`, `sensors`, `chassis-kits`, `wheels-mechanical`, `power-batteries`.

## Scope

- **Included:** Adafruit, SparkFun, Pololu, ServoCity, Seeed Studio, DFRobot, ROBOTIS America (robotis.us) and Waveshare.
- **Skipped:** RobotShop and DigiKey returned HTTP 403 to automated fetching. Mouser returned a bot-check page. Pimoroni and The Pi Hut were reachable but were left out to keep the scope at 8 stores.
- **Excluded:** general marketplaces (Amazon, eBay, AliExpress).

## Complete arms and body sections

The [20-company research database](expansion/README.md) has uniform per-company CSVs,
official product/CAD sources and recent activity evidence. China-based companies
appear last. The [classified catalog](classified/README.md) now separates complete
body sections from actuator, sensor, wheel and electronics components.
