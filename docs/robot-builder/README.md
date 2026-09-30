# Robot Workshop — body-only demo

Twenty-one prepared 3D body sections: **five arms, nine bodies, four heads and three
mobile bases**. The demo excludes small components, shopping prices and broad
company research. Every visible option has a local GLB and thumbnail.

## Run

```sh
cd docs/robot-builder
npm ci
npm run dev
```

Open **http://127.0.0.1:5174/**. Choose a body slot and select a part. **All body
parts** allows free composition; supplier/search filters narrow the palette.
Drag to orbit, inspect with Spread parts, and use Start over for the starter.
Save build downloads JSON; Export robot downloads GLB for Blender. Choices survive
reload. The browser requires WebGL, with no Blender or backend dependency.

The starter combines the Reachy 2 torso/head, a Niryo arm, a Seeed SO-101 arm and
one Waveshare rover base shared by both leg slots. Body sections are positioned
for a visual concept; mechanical fit, wiring and manufacturing dimensions are
not validated. Reachy sections come from the official whole-robot visualization
and do not imply separate retail availability. Empty shells are labeled.

## Ready assets

- [body-parts.csv](public/body-parts.csv): exact selectable palette, categories,
  model/thumbnail paths, source URLs and checksums.
- [body-models.json](public/body-models.json): the same asset index as JSON.
- [catalog.json](public/catalog.json): placement metadata and source notes.
- `public/models/`: 21 active GLBs; older component models are preserved locally.
- `public/thumbnails/`: prepared PNG previews.
- `blender/mixed-supplier-robot-v4.blend`: editable starter, with a PNG preview.

Models, thumbnails and Blender binaries are local and Git-ignored. The broader
store catalog and research remain under `../robot-parts-stores/`.

## Rebuild models

Original source files must be present under `../robot-parts-stores/cad/`.

```sh
python3 scripts/select_assets.py
node scripts/convert_step.mjs
python3 scripts/convert_dae.py
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --threads 4 --python scripts/prepare_blender.py
python3 scripts/export_body_catalog.py
node scripts/write_scene_plan.mjs
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --threads 4 --python scripts/assemble_blender.py
```

Adjust the Blender executable path as needed. STEP uses OpenCascade; COLLADA
conversion preserves triangle meshes, node transforms and material colors while
omitting source cameras and lights. Blender normalizes meshes, exports GLB, and
renders previews. The original sources remain untouched. Source licenses still
apply; model availability does not establish redistribution permission.

The palette combines classified retail products with `scripts/demo_parts.json`
for additional official arm models and extracted robot sections. Unknown prices
remain unknown in data; the demo does not display shopping totals.

## Validate and build

```sh
npm test
npm run test:browser
npm run build
```

Browser tests use installed Chrome on macOS; set CHROME_PATH for another binary.
They cover every active model, body-only filters, legacy recovery, persistence,
JSON/GLB export, failed-load retry, and mobile layout. Serve `dist/` over HTTP to
run the production build. This demo is independent of the Flower master/worker UI.

Additional torso choices use official ROBOTIS OP3, Berkeley Humanoid Lite and
Unitree G1/H1/H2 meshes. Source revisions are pinned in the catalog URLs. The H1
preview omits triangles above source Z=0.52 m to remove the integrated head; the
original STL is unchanged, and the filter is recorded in model provenance.

Additional head choices use the official ROBOTIS OP3 and Unitree G1 head meshes.
These are robot visualization sections; separate retail availability is not established.
