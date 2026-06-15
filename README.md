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
with near-zero dependencies. **v0.2.0 runs real geoprocessing**, validated on real
data (122 unit + 19 integration checks on QGIS 4.0.3).

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

- **Friendly verbs → real QGIS algorithms** (`buffer`, `clip`, `dissolve`,
  `reproject`, `join`, `zonalstats`, …); `run <id>` reaches any of the ~769 with no
  alias, `describe` shows their parameters.
- **Databases** via named QGIS connections — `@conn` tables and `sql @conn "…"` —
  credentials never leave QGIS.
- **Provenance for free** — every `save` records lineage; `assess` writes data-quality
  reports.
- **Composable** — chain stages with `|`, compose files with `call`.

## Docs

- [About & goals](docs/about.md) · [Plugin](plugin/README.md) ·
  [Verb ↔ algorithm map](docs/planning/14-traceability-matrix.md)
- [Design & risk docs](docs/planning/) — PRD, architecture, grammar, security, the
  `Oscar` failure register
- [CHANGELOG](CHANGELOG.md)

## License

[GPLv3](LICENSE) — consistent with the QGIS ecosystem (niva builds on PyQGIS, a GPL
library). Not yet on PyPI; install from source or the plugin zip.
