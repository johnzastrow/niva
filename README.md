# niva

**A concise, readable text-pipeline grammar for QGIS geoprocessing — for people who
don't want to write PyQGIS.** *Easy wins every time.*

<img src="docs/logos/logo_text.png" width="320" alt="niva">

Write a whole pipeline on one line — friendly verbs running on QGIS's own Processing
algorithms underneath:

```
load roads.gpkg | buffer 100m dissolve | clip city.gpkg | save roads_local.gpkg
```

niva turns QGIS automation from a PyQGIS programming task into a line of text a
GUI-first analyst can write *and* read. It runs in QGIS's own Python, reaches **any**
of its ~769 algorithms, talks to your databases, and records provenance as it goes —
with near-zero dependencies. **v0.7.1 runs real geoprocessing**, validated on real
data (156 tests on QGIS 4.0.3). The QGIS plugin runs flows in the **background** with
a **Stop** button, logs provenance per session, and can **export a flow to a
standalone PyQGIS script** (and import niva-shaped scripts back).

## Quick start

### In QGIS — no install needed (easiest)

1. Get `niva_qgis.zip` — download it from the
   [latest release](https://github.com/johnzastrow/niva/releases/latest), or build it
   with `plugin/build_plugin.sh`.
2. In QGIS: **Plugins ▸ Manage and Install Plugins ▸ Install from ZIP** → pick the
   zip. (Enable *"Show also experimental plugins"* if it doesn't appear.)
3. Click the **niva** toolbar button, type a flow, hit **Run** — results land on the
   map. The plugin bundles niva, so there's no pip step on Windows, macOS, or Linux.

### As a package — CLI + Python

Install into **QGIS's own Python** (niva runs on QGIS's Processing):

```bash
<qgis-python> -m pip install git+https://github.com/johnzastrow/niva.git
```

Then run flows from the shell or Python:

```bash
niva run myflow.niva                              # execute a .niva file
niva "load a.gpkg | buffer 100m | save b.gpkg"    # a one-liner
niva describe buffer                              # how a verb maps to a QGIS algorithm
niva "load a.gpkg | buffer 100m | save b.gpkg" --dry-run   # validate — no QGIS needed
```

```python
import niva
niva.flow('load "data.gpkg|layername=roads" | buffer 100m dissolve | save out.gpkg')
```

> A GeoPackage holds many layers — name one with `|layername=…`. Databases:
> `load @conn.table` and `sql @conn "SELECT …"` (credentials stay in QGIS).

## What it does

- **~45 friendly verbs → real QGIS algorithms**, across vector geometry (`buffer`,
  `simplify`, `smooth`, `convexhull`, `centroid`, `densify`, `offset`, …), overlay
  (`clip`, `intersect`, `union`, `difference`, `dissolve`, `spatialjoin`,
  `selectloc`, …), attributes (`renamefield`, `dropfields`, `keepfields`,
  `countpoints`, …), and **raster** (`warp`, `clipraster`, `hillshade`, `slope`,
  `aspect`, `polygonize`, …). `run <id>` reaches any of the ~769 with no alias;
  `describe` shows their parameters. Every alias is validated against the installed
  QGIS by `scripts/lint_registry.py`.
- **Raster and vector output** — `save` writes either (rasters via `gdal:translate`,
  vectors via `QgsVectorFileWriter`, driver chosen by extension).
- **Databases** via named QGIS connections — `@conn` tables and `sql @conn "…"` —
  credentials never leave QGIS.
- **Provenance for free** — every `save` records lineage; `assess` writes data-quality
  reports; the run journal echoes the exact `processing.run(…)` for each step.
- **Composable** — chain stages with `|`, compose files with `call`, and **export a
  flow to a standalone PyQGIS script** (`niva export`) or import one back.

## Docs

- [About & goals](docs/about.md) · [Plugin](plugin/README.md) ·
  [Verb ↔ algorithm map](docs/planning/14-traceability-matrix.md)
- [Design & risk docs](docs/planning/) — PRD, architecture, grammar, security, the
  `Oscar` failure register
- [CHANGELOG](CHANGELOG.md)

## License

[GPLv3](LICENSE) — consistent with the QGIS ecosystem (niva builds on PyQGIS, a GPL
library). Not yet on PyPI; install from source or the plugin zip.
