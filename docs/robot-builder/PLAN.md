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
