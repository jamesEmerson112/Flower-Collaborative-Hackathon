# RB1 — Mix-and-match robot concept builder

## RB2 — Correct researched roles and body placement

Source: user's request to correct misplaced parts, particularly a rover shown as torso.
Use the classified database for recommendations; mobile bases appear in legs only,
support electronics are excluded from anatomical suggestions, and starter slots use
matching roles. Supply the catalog's structural Shadow Chassis as an explicitly
labeled approximate preview because no supplier CAD was found. Render a selected
mobile base once beneath the torso, spanning both leg slots; count/export it once.
Migrate v1 saved builds per slot, retaining compatible choices. Preserve deliberate
cross-role choices made through Show all parts in new v2 builds.

Validation: real-catalog category/default checks; shared-base selection, replacement,
quantity and placement tests; legacy migration; browser recommendations and GLB
export of one horizontal base; desktop/mobile inspection. Physical fit stays out of scope.

Completed: four new regression tests reproduced incorrect roles, duplicate base
counting, and missing legacy migration before implementation. All nine unit tests
and four Chrome browser tests now pass; production build passes. WAVE ROVER,
Romi, desktop/mobile previews, and the v2 Blender render were inspected. Shared
placement logic now drives browser rendering, part quantities, and the Blender
scene plan. The structural-frame preview is explicitly approximate.

Source: the user's 2026-09-29 clarification: users should build a robot from
different companies' parts, with torso, arms, legs, and head; physical fit can
be approximate for the hackathon. This request is the milestone definition.

## Acceptance criteria

- R1: A browser displays a complete six-slot robot using actual downloaded CAD
  assets, initially from at least three suppliers.
- R2: A user can select a body slot and replace its part without altering other
  slots. Cross-supplier combinations are allowed without engineering fit checks.
- R3: The parts list aggregates repeated products and computes quantities and
  catalog-price totals correctly.
- R4: The build survives reload. Invalid or obsolete saved state recovers to a
  usable default; unknown product or slot IDs cannot corrupt a build.
- R5: Users can save their configuration and export the assembled robot as GLB.
- R6: Desktop and narrow mobile layouts support selecting slots and parts;
  keyboard controls, loading/error feedback, and visible focus are provided.

Out of scope: manufacturing fit, wiring, physics, live inventory, purchases,
and connecting or modifying the existing Flower master/worker interface.

## Flows

1. Open → see starter robot → choose body slot → select supplier part → robot
   and parts list update. A failed model load offers retry and keeps the build.
2. Choose slot → filter by supplier or search → choose part → selected state.
   An empty search offers clear filters.
3. Assemble → save configuration or GLB → downloadable local artifact.
4. Reload → restore choices; malformed saved state → default robot.

| Flow | Desktop | Mobile | Rationale |
| --- | --- | --- | --- |
| View robot | Large central orbit viewport | Viewport above controls | Keep the result visible |
| Select slot | Slot buttons beside viewport | Wrapping touch-sized buttons | Same model and labels |
| Find parts | Side catalog, search and supplier filter | Catalog below viewport | Avoid tiny side panels |
| Save/export | Header actions | Wrapping header actions | No gesture-only actions |

## Validation

`node --test`: cross-supplier swapping, independent slots, duplicate quantities,
price totals, and persistence/recovery. Browser checks: actual GLB loading,
part swap, reload, exports, viewport errors, keyboard, and mobile overflow.

Completed 2026-09-29: R1–R6 implemented. Five core tests were first run against
the missing implementation (red), then passed after implementation. Three
Chrome browser tests passed against real GLBs, including all 13 product models,
six-slot exports, and failed-load recovery. Production build passed. Desktop,
mobile, and Blender render previews were visually inspected. All 13 binary GLB
headers and lengths, and all 13 thumbnails, were checked.

## RB3 — Complete body assemblies and broader supplier research

Source: user wants arms and torsos that look like complete body sections, with
small motors/electronics separated; research 20 active companies using five agents
within a ten-minute research window, listing China-based companies last.

Acceptance: recommended arms are full assemblies, not bare servos; torso choices
include structural frames/body shells with purchased scope visible. Components
have a separate filter. Research records distinguish whole robots and inquiry-only
products from purchasable modules, and CAD availability from prepared previews.
Use uniform per-company CSVs and official evidence. Preserve intentional custom
placements in new builds and migrate old motor-as-arm defaults.

Validation: regression tests for body/component separation, arm and torso counts,
persistence migration, real GLB loading, and browser filters.

RB3 completed: five agents researched 20 companies and 29 products in 4m45s.
Uniform company CSVs and a linked source browser separate 20 arm listings, two
body shells and seven whole robots. The original catalog now has 102 products;
seven newly downloaded product sources supply 20 browser choices, including
three complete arms, four torso options and one head shell. Motors, sensors
and wheels have separate component roles. Version-3 migration removes obsolete
motor-as-arm suggestions while preserving new deliberate custom placements.

Two new regression tests failed before implementation and now pass. All 11 unit
checks and five browser scenarios passed; the starter/export scenario was rerun
after its frame asset finished generating. The production build passes, all 20
GLB headers and thumbnails were verified, and the mobile and Blender previews
were inspected. Updated scene: mixed-supplier-robot-v3.blend.

## RB4 — Body-model demo, ten-minute scope

User prioritizes only usable body-section 3D models for the demo, within ten
minutes. Remove component/price distractions from the visible builder. Add
available full-arm CAD and humanoid torso/head geometry; label extracted robot
sections as visual modules rather than separately sold products. Keep every
visible option backed by a prepared GLB and thumbnail; verify slot placement,
save/export and mobile layout. Preserve the wider research databases separately.

RB4 completed within the ten-minute window (23:10:39–23:20:05 UTC): the demo now
contains exactly 14 prepared body models (5 arms, 4 bodies, 2 heads, 3 bases).
Added Niryo Ned2, Elephant myCobot, and official Reachy 2 torso/head/base sections;
removed components, approximate frames and price displays from the active demo.
Kept broader research and old assets intact. Added a source/checksum CSV and JSON
index and an updated v4 Blender scene. The new starter uses a connected head and
torso with repositioned arm assemblies. Separate retail availability is not
implied for extracted whole-robot sections.

Validation: all 13 unit tests and all five Chrome browser scenarios pass; every
active GLB header/length and thumbnail was checked. Desktop/mobile screenshots
and the final Blender render were inspected. Production build passes. Active
GLBs total 25.42 MB; original/extracted CAD totals 1.305 GB, below 10 GB.

## RB5 — More torso models

User asks for more torso parts, within the body-only demo scope. Find official
humanoid body meshes, convert suitable examples into prepared GLBs/thumbnails,
and add them to Torso with source attribution. Preserve starter and other body
categories. Distinguish robot sections from separately purchasable products.
Validate new models, upright appearance, and browser swapping/export.

RB5 completed: added official OP3, Berkeley Humanoid Lite, G1, H1 and H2 torso
meshes with pinned source revisions, bringing the palette to nine torso options
and nineteen prepared body models. The H1 source includes a fixed head; its
preview omits triangles above source Z=0.52 m, with the untouched source and
filter metadata retained. All five torso thumbnails were visually inspected.
Anatomical body sections appear ahead of frames/shells, with China-based sources
kept after other suppliers. The existing starter remains unchanged.

Validation: the new torso regression failed before the additions and now passes.
All 14 unit tests and five browser scenarios pass, including loading all nineteen
models, swapping, save/export, and desktop/mobile layouts. Production build and
GLB binary checks pass. Original/extracted CAD is 1.320 GB, below 10 GB.

## RB6 — Two more head models

User requests two additional head parts while explicitly leaving store datasets
unmerged. Add two official head-section meshes, prepared GLBs/thumbnails and
source records. Preserve the starter, existing choices, and store catalogs.
Validate head-only recommendations, appearance/orientation, and browser loading.

RB6 completed: added ROBOTIS OP3 and Unitree G1 head sections from pinned
official repositories, with local GLBs, thumbnails and provenance. Four head
choices and twenty-one body models are available. Store datasets remain separate
and the starter is unchanged. Both head thumbnails were visually inspected.

Validation: the new regression failed before the additions and now passes. All
15 unit tests and five Chrome browser scenarios pass, including every active
model and both new head swaps. Production build and all 21 GLB integrity checks
pass. Original/extracted CAD totals 1.322 GB, below the 10 GB threshold.
