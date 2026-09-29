# Robot product CAD collection

Collected 2026-09-29 for the 95 products in `../stores.json`.

- **50 products have downloaded 3D assets** from supplier, manufacturer, or original designer sources.
- **2 products have related models only**; these are not verified exact matches.
- **0 products have only downloaded 2D drawings.**
- **43 products have no downloaded model in the sources checked.** This is a research result, not proof that a model does not exist.
- **0.946 GB** of original and extracted assets (358.4 MB original downloads). Below the requested **10 GB** notification threshold. GB means 1,000,000,000 bytes. The archive originals and extracted copies are both counted.

## Files

- `originals/<product-id>/`: supplier downloads, including ZIP/RAR archives and native CAD files.
- `extracted/<product-id>/`: extracted CAD, drawings, and associated documentation. No software installers or demo programs were collected.
- [manifest.json](manifest.json): source/download URLs, repository commit IDs where applicable, file sizes, SHA-256 hashes, formats, validation results, and mappings to catalog products.
- [coverage.csv](coverage.csv): all 95 products, including gaps and revision notes.
- [SHA256SUMS](SHA256SUMS): checksums for the 250 original and extracted files.

`originals/` and `extracted/` are ignored by Git to keep vendor binaries out of ordinary source commits. They are present locally. The catalog and its generated files are unchanged.

## Coverage

| Store | 3D assets | Related only | 2D only | No download found |
| --- | ---: | ---: | ---: | ---: |
| adafruit | 6 | 1 | 0 | 5 |
| sparkfun | 2 | 0 | 0 | 10 |
| pololu | 10 | 0 | 0 | 2 |
| servocity | 10 | 0 | 0 | 2 |
| seeed | 3 | 0 | 0 | 9 |
| dfrobot | 3 | 0 | 0 | 9 |
| robotis | 8 | 0 | 0 | 4 |
| waveshare | 8 | 1 | 0 | 2 |

## Useful starting models

- [ServoCity Strafer chassis STEP](extracted/servocity-3209-0001-0007/3209-0001-0007/3209-0001-0007.step)
- [WAVE ROVER STL](<extracted/waveshare-wave-rover/WAVE_ROVER_MODEL_STL/WAVE ROVER_MODEL_STL.stl>)
- [SO-101 assembly STEP](<originals/seeed-114993667/SO101 Assembly.step>) and [STL](<originals/seeed-114993667/SO101 Assembly.stl>)
- [Romi chassis STEP](originals/pololu-3500/romi-chassis-kit.step)
- [TurtleBot3 Burger URDF](originals/robotis-901-0118-301/turtlebot3_description/urdf/turtlebot3_burger.urdf)
- [SparkFun stepper Blender file](originals/sparkfun-rob-09238/9238.blend)

## Important model differences

- **Adafruit 1438:** the official CAD repository names MotorShield V2; the catalog currently names v3. Treat it as a related revision.
- **Romi chassis:** the supplied assembly includes an additional front ball caster sold separately from the kit.
- **Pololu families:** only `No Encoder/mmgm-cb.step` (HPCB, standard gearbox body) and `qtr-md-08x.step` (medium-density, eight-channel array) were retrieved from the two large archives, using HTTP ranges and ZIP member CRC checks. Full family archives were not retained. Some sensor/regulator models are explicitly shared across product families.
- **SO-101:** structural parts and the assembly come from TheRobotStudio. The catalog entry is a servo motor kit; its printed structural parts are not included. Check the Pro kit's servo/electronics revision against the assembly.
- **TurtleBot3:** the ROS package contains simplified visualization meshes and a URDF, not the full manufacturing assembly. Check the RPi4 kit revision and sensor against the visualization.
- **Waveshare D500:** the supplier wiki links to LD19-named models. These are retained as related models, with exact D500 fit unverified.
- Board revisions, units, attachment points, and electrical compatibility still need checking before these become robot-builder assets.

## Opening and verification

STEP/STP files preserve CAD geometry. Convert them with a CAD tool such as CadQuery or FreeCAD before importing meshes into Blender or exporting browser GLB files. STL and the included SparkFun `.blend` files can be opened/imported in Blender. Native Fusion and SolidWorks files are retained where supplied.

Downloads were checked for HTML error pages; ZIP archives passed CRC checks; RAR members were read successfully; STEP envelopes and STL triangle counts/ASCII endings were checked. Native proprietary files were retained but not fully parsed. These checks confirm file integrity, **not** manufacturability, physical fit, or successful opening in a CAD application.

To verify the local copies from this directory:

```sh
shasum -a 256 -c SHA256SUMS
```

## Provenance and reuse

These are third-party assets, not newly authored project models. Available source licenses and documentation are retained alongside the files (including Adafruit, SparkFun, TheRobotStudio, ROBOTIS ROS, and Raspberry Pi notices). A public download does not establish a common redistribution license; source-specific terms still apply. No account login or paid download was used.
