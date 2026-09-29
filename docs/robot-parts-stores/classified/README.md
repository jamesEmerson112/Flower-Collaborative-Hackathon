# Classified robot parts database

**95 products from the existing eight-store catalog**, researched against official
product pages or manufacturer documentation on 2026-09-29. This is the current
project catalog, not a complete scrape of each retailer's inventory.

Start with [all_parts.csv](all_parts.csv), or give each supplier agent its own CSV:

| Store | File | Products |
| --- | --- | ---: |
| Adafruit | [adafruit.csv](by-store/adafruit.csv) | 12 |
| SparkFun | [sparkfun.csv](by-store/sparkfun.csv) | 12 |
| Pololu | [pololu.csv](by-store/pololu.csv) | 12 |
| ServoCity | [servocity.csv](by-store/servocity.csv) | 12 |
| Seeed Studio | [seeed.csv](by-store/seeed.csv) | 12 |
| DFRobot | [dfrobot.csv](by-store/dfrobot.csv) | 12 |
| ROBOTIS | [robotis.csv](by-store/robotis.csv) | 12 |
| Waveshare | [waveshare.csv](by-store/waveshare.csv) | 11 |

Every file has **the same 34 columns**. CSVs use UTF-8, comma delimiters, a header
row, and empty cells for unavailable values. List-valued cells use `|` between
entries. Standard CSV readers handle names and notes containing commas.

## Body roles

| `primary_role` | Meaning | Example |
| --- | --- | --- |
| `legs` | Locomotion, including wheeled/tracked bases, wheels, casters and drive motors | **WAVE ROVER**; Romi; Devastator |
| `torso` | Structural body/frame | SparkFun Shadow Chassis |
| `arms` | Manipulation assemblies or suggested arm-joint components | SO-ARM101 servo kit; DYNAMIXEL actuator |
| `head` | Perception components | Distance sensor; lidar |
| `support` | Electronics, power, orientation sensing and adapters | Controller; battery; IMU |
| `whole_robot` | A complete robot kit covering multiple body roles | TurtleBot3 Burger kit |

`secondary_roles` records optional alternatives. For example, WAVE ROVER is
primarily `legs` because it drives the robot, with `torso` as a secondary role
because its chassis can carry other parts. These are builder suggestions inferred
from the researched product function, not vendor claims about anatomical roles.

`part_type` retains the actual component identity, and `assembly_level` separates
components, modules, kits, accessories, and complete robots. A servo is still a
joint component, not an entire arm. A distance-sensor board is a perception
component, not a complete head. Generic servos/steppers receive medium confidence
because their preferred body role depends on the design. High confidence means
the suggested main role is clear; it never means parts will physically fit.

There is only one primary torso entry in this sample; several mobile bases have
torso as a secondary use. Internal support parts remain available in the database
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
- Images: all 95 entries have a product-image URL extracted from saved official
  product pages. Images were not downloaded or individually availability-tested;
  these URLs can expire. Source page/date and extraction hashes are retained.
- Models: CAD availability, formats, download URLs, local file paths and known
  caveats. Fourteen entries link to browser GLBs and thumbnails: thirteen derived
  from collected CAD and one explicitly approximate Shadow Chassis frame preview.

See [schema.json](schema.json) for every column and [taxonomy.json](taxonomy.json)
for allowed values. Paths are relative to the repository root. Downloaded binary
models remain local and Git-ignored, as in the existing CAD collection.

## Evidence and caveats

All 95 classifications have `live_verified` evidence: an official product page or
manufacturer document was fetched and inspected during this research. Some store
fetches failed initially; manufacturer documentation or a successful retry was
used instead. `evidence_urls` identifies the successful supporting sources.

The build also supports `catalog_snapshot_only` and `inaccessible` for future
entries whose current product details cannot be verified. It never upgrades these
to verified based on a product name alone.

The CAD collection contains 50 products with downloaded 3D assets, 2 with related
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
