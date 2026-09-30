# Classified robot parts database

**102 products from the existing eight-store catalog**, researched against official
product pages or manufacturer documentation on 2026-09-29. This is the current
project catalog, not a complete scrape of each retailer's inventory.

Start with [all_parts.csv](all_parts.csv), or give each supplier agent its own CSV:

| Store | File | Products |
| --- | --- | ---: |
| Adafruit | [adafruit.csv](by-store/adafruit.csv) | 12 |
| SparkFun | [sparkfun.csv](by-store/sparkfun.csv) | 12 |
| Pololu | [pololu.csv](by-store/pololu.csv) | 12 |
| ServoCity | [servocity.csv](by-store/servocity.csv) | 13 |
| Seeed Studio | [seeed.csv](by-store/seeed.csv) | 16 |
| DFRobot | [dfrobot.csv](by-store/dfrobot.csv) | 12 |
| ROBOTIS | [robotis.csv](by-store/robotis.csv) | 12 |
| Waveshare | [waveshare.csv](by-store/waveshare.csv) | 13 |

Every file has **the same 34 columns**. CSVs use UTF-8, comma delimiters, a header
row, and empty cells for unavailable values. List-valued cells use `|` between
entries. Standard CSV readers handle names and notes containing commas.

## Body roles

| `primary_role` | Meaning | Example |
| --- | --- | --- |
| `legs` | Complete locomotion bases | WAVE ROVER; Romi |
| `torso` | Structural frame or empty body shell | Bravo frame; Reachy shell |
| `arms` | Full manipulation assemblies | RoArm-M2-S; assembled SO-101 |
| `head` | Physical head housing | Reachy front shell |
| `actuators` | Bare motors, servos and motor-only kits | DYNAMIXEL; SO-101 servo kit |
| `sensors` | Perception and orientation components | Distance sensor; IMU |
| `wheels` | Individual wheels and casters | Romi wheel |
| `support` | Electronics, power and adapters | Controller; battery |
| `whole_robot` | Complete robot spanning multiple roles | TurtleBot3 |

Also see the [20-company body assembly research](../expansion/README.md).

`secondary_roles` records optional alternatives. For example, WAVE ROVER is
primarily `legs` because it drives the robot, with `torso` as a secondary role
because its chassis can carry other parts. These are builder suggestions inferred
from the researched product function, not vendor claims about anatomical roles.

`part_type` retains the actual component identity, and `assembly_level` separates
components, modules, kits, accessories, and complete robots. A servo is still a
joint component, not an entire arm. A distance-sensor board is a perception
component, not a complete head. Generic servos/steppers are actuator components, regardless of their eventual placement. High confidence means
the suggested main role is clear; it never means parts will physically fit.

There are four torso frame/shell choices; several mobile bases retain torso as
a secondary use, but are recommended as driving bases. Internal support parts remain available in the database
without being mislabeled as complete body sections. The browser demo's earlier
visual palette now reads this dataset for its recommended body roles. Its
Show all parts option still permits deliberate cross-role visual experiments.

## Included fields

- Identity: stable product/store IDs, SKU, original name, product URL and technical category.
- Classification: primary/secondary roles, component type, assembly level,
  function, reason, confidence, and package/assembly notes.
- Commercial snapshot: original price, currency, capture date and specifications.
  Prices were retained from `../stores.json`, not refreshed during classification.
- Evidence: official URLs, a short source finding, verification status and research date.
- Images: 100 of 102 entries have a product-image URL extracted from saved official
  product pages. Images were not downloaded or individually availability-tested;
  these URLs can expire. Source page/date and extraction hashes are retained.
- Models: CAD availability, formats, download URLs, local file paths and known
  caveats. Twenty entries link to browser GLBs and thumbnails: nineteen derived
  from collected CAD and one explicitly approximate Shadow Chassis frame preview.

See [schema.json](schema.json) for every column and [taxonomy.json](taxonomy.json)
for allowed values. Paths are relative to the repository root. Downloaded binary
models remain local and Git-ignored, as in the existing CAD collection.

## Evidence and caveats

All 102 classifications have `live_verified` evidence: an official product page or
manufacturer document was fetched and inspected during this research. Some store
fetches failed initially; manufacturer documentation or a successful retry was
used instead. `evidence_urls` identifies the successful supporting sources.

The build also supports `catalog_snapshot_only` and `inaccessible` for future
entries whose current product details cannot be verified. It never upgrades these
to verified based on a product name alone.

The CAD collection contains 57 products with downloaded 3D assets, 2 with related
models only, and 43 with no model found in the sources checked. `downloaded_3d`
does not guarantee a revision match or engineering compatibility. In particular:

- SO-ARM101's listed servo kit excludes the printed structure shown in its CAD.
- Romi's vendor assembly includes an additional caster beyond the kit's contents.
- Adafruit 1438's collected model is V2 while the catalog names v3.
- The D500 resource links to LD19-named CAD; it is marked `related_model_only`.
- TurtleBot CAD includes simplified visualization meshes; check its kit revision.

Per-product notes preserve these and other exclusions. Read `assembly_notes` and
`cad_notes` before using models or prices to describe a purchasable assembly.
Electrical, mounting, load, and dimensional compatibility are not verified.

[review_queue.csv](review_queue.csv) includes medium/low-confidence role suggestions,
non-live evidence (if any), and related-only CAD. It is a review shortlist, not a
list of errors. [store_summary.csv](store_summary.csv) gives counts by store and role.

## Maintain and regenerate

Reviewed source records live in `research/<store_id>.json`. The original commerce
catalog and CAD manifest remain the sources of truth for their own fields.
Update research records using official sources, then run:

```sh
python3 docs/robot-parts-stores/classified/build_database.py
```

The standard-library builder checks exact product coverage, unique IDs, shared
taxonomy values, source URLs, local asset paths, and the WAVE ROVER role before
writing the eight retailer files and combined exports. It performs no network
requests and does not fetch missing CAD files.

`image_sources.json` is a checked-in snapshot and requires no temporary files to
rebuild the CSVs. To refresh that snapshot from saved official HTML:

```sh
python3 docs/robot-parts-stores/classified/extract_images.py --html-dir /path/to/saved-pages --captured-at YYYY-MM-DD
```

Name each HTML file `<product_id>.html`; repeated `--html-dir` arguments let later
directories override earlier ones. This initial extraction uses same-day pages
from the CAD research and fresh classification research. When collecting images
on a later date, supply that date explicitly rather than assuming the price date.

Example: find locomotion options from every store, including secondary uses:

```python
import csv

with open("docs/robot-parts-stores/classified/all_parts.csv", encoding="utf-8", newline="") as f:
    parts = list(csv.DictReader(f))

legs = [p for p in parts if "legs" in [p["primary_role"], *p["secondary_roles"].split("|")]]
```
