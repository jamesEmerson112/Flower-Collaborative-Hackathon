# Robot Workshop

A browser concept builder with **14 products across 7 suppliers**: 13 supplier-CAD
previews and one explicitly approximate structural-frame preview. The starter
uses a SparkFun frame, Pololu distance sensor, ROBOTIS and ServoCity arm actuators,
and one Waveshare rover base shared by both leg slots.

## Run

```sh
cd docs/robot-builder
npm ci
npm run dev
```

Open **http://127.0.0.1:5174**. Select a body slot, then choose a part. Use
**Show all parts** to put any product in any slot. Search and supplier filters
apply to the current palette. Orbit by dragging, or use the rotation/front
buttons; **Spread parts** separates the pieces for inspection.

Recommendations come from `../robot-parts-stores/classified/all_parts.csv`.
Rovers and wheeled bases belong to **legs**, structural frames to **torso**, and
distance sensors to **head**. Power, IMUs, and controller boards are support parts
and appear only through **Show all parts**. That option retains intentional
cross-role visual experimentation. Secondary research roles are retained in the
catalog but do not override the main recommended category.

Selecting a mobile base in either leg slot links both slots, positions one
horizontal base below the torso, and counts it once. Selecting an independent
leg component again separates the legs; the other slot receives a TT motor.
Version-1 saved builds migrate misplaced parts to the corrected defaults while
preserving compatible choices. Version-2 builds retain deliberate custom choices.

Choices persist in local browser storage. **Save build** downloads the versioned
slot/product configuration as JSON. **Export robot** downloads an assembled GLB
with product IDs, suppliers, and source URLs embedded in its nodes. The GLB can
be imported into Blender. The export omits the studio floor and display plinth.

The corrected editable starter scene is `blender/mixed-supplier-robot-v2.blend`,
with a rendered preview beside it. The previous scene is preserved. Generated
models, images, Blender files, dependencies, and
build output are kept locally and excluded from Git.

## Asset pipeline

The original downloads remain untouched under `../robot-parts-stores/cad/`.
`public/catalog.json` links the palette to the original store catalog and CAD
manifest. `public/model-provenance.json` records source hashes, conversion bounds,
mesh counts, and output sizes.

To rebuild locally, first collect the source assets described in
[`../robot-parts-stores/cad/README.md`](../robot-parts-stores/cad/README.md), then:

```sh
python3 scripts/select_assets.py
node scripts/convert_step.mjs
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --threads 4 --python scripts/prepare_blender.py
node scripts/write_scene_plan.mjs
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --threads 4 --python scripts/assemble_blender.py
```

Adjust the Blender executable path on other platforms. Asset preparation was
tested with Blender 5.2.2 and occt-import-js 0.0.23. STEP assemblies first pass through
[OpenCascade's WASM importer](https://github.com/kovacsv/occt-import-js); Blender normalizes the resulting meshes, reduces large
meshes, exports GLB, and renders thumbnails. STL models go directly to Blender.
Preparation skips existing completed outputs; remove the specific generated GLB
and thumbnail to regenerate after changing source geometry or conversion rules.

## Scope and model caveats

This is a visual composition tool. Each part is rotated and independently resized
to fit a conceptual body slot. Body roles are creative suggestions; a sensor can
act as a head and a motor as a leg. Displayed dimensions, mounting interfaces,
mechanical fit, wiring, strength, and physical behavior are **not validated**.
Use the original CAD for any subsequent engineering work.

Shadow Chassis has no downloaded supplier CAD. `scripts/frame_preview.py` creates
an illustrative plate-and-strut envelope using the vendor's published overall
dimensions; its holes and mounting details are approximate. It is labeled in the
catalog, parts list, provenance record and exported GLB metadata. See the
[official product description](https://www.sparkfun.com/shadow-chassis.html).

The SO-101 model includes printed structure absent from the listed servo kit.
The Romi vendor assembly includes a second caster, while the listed kit contains
one. These notes also appear in the parts list and exported metadata. Totals use
the existing catalog's USD prices, count each independent part (a shared base once), and exclude extras,
shipping, and tax. They are not live quotes or a complete manufacturing bill.

Original vendor/repository terms still apply to source and converted assets;
see the collection manifest and source links before redistribution. No blanket
license is implied by downloading or converting a model.

## Implementation and checks

Vite + vanilla JavaScript + Three.js render the browser preview; no backend or
Blender installation is required by the browser. Blender and OpenCascade prepare
assets offline. This demo is independent of the Flower master/worker UI.

```sh
npm test
npm run test:browser
npm run build
```

Browser checks use installed Chrome on macOS. Set `CHROME_PATH` to another local
Chrome/Chromium executable when needed. They check all 14 previews, researched
recommendations, shared-base placement/counting/export, legacy migration,
unrestricted custom swapping, persistence, JSON/GLB downloads, filters, keyboard
controls, and mobile overflow. Screenshots are written to `test-results/`.

The production output is `dist/`; serve that directory over HTTP. `base: './'`
supports hosting under a subdirectory. Keep its generated model and thumbnail
files alongside the HTML and JavaScript.
