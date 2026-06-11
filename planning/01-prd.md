# Niva — Product Requirements (v1)

_A concise, high-level Python grammar over PyQGIS / QGIS Processing._
_Status: draft for review. Decisions tracked in `00-…`._

> **Clean-room design.** niva's API is derived from QGIS Processing's own model and
> idiomatic Python — not from any proprietary GIS scripting API. No external API is
> referenced, reproduced, or used as a template. The goal is a coherent grammar that
> stands on QGIS's own terms.

## 1. Problem

PyQGIS Processing is powerful but verbose for everyday geoprocessing. To buffer a
layer you must initialize a `QgsApplication`, know the exact algorithm ID
(`native:buffer`), build an `ALL_CAPS` parameter dict, manage `TEMPORARY_OUTPUT`,
and dig the result out of an output dictionary. For interactive and scripting work
this boilerplate dominates the actual intent. niva's job is to provide a **concise
grammar** for the common cases while staying fully interoperable with raw PyQGIS for
everything else.

**Before (raw PyQGIS):**
```python
from qgis.core import QgsApplication
import processing
from processing.core.Processing import Processing
QgsApplication.setPrefixPath("/usr", True)
qgs = QgsApplication([], False); qgs.initQgis(); Processing.initialize()
res = processing.run("native:buffer", {
    "INPUT": "roads.gpkg", "DISTANCE": 100, "DISSOLVE": True,
    "SEGMENTS": 5, "END_CAP_STYLE": 0, "JOIN_STYLE": 0, "MITER_LIMIT": 2,
    "OUTPUT": "roads_buf.gpkg",
})
out = res["OUTPUT"]
```

**After (niva):**
```python
import niva
out = niva.buffer("roads.gpkg", distance=100, dissolve=True, output="roads_buf.gpkg")
```

## 2. Value proposition / the wedge

niva removes five specific PyQGIS pains, in order of impact:

1. **Environment boilerplate** — one import; niva initializes QGIS/Processing lazily
   and correctly whether run inside QGIS or standalone on QGIS's Python.
2. **Algorithm-ID knowledge** — friendly verbs (`buffer`) resolve to `native:*` IDs
   via an alias registry, with `niva.find("buffer")` discovery.
3. **Parameter ergonomics** — Pythonic lowercase kwargs with sane defaults instead
   of full `ALL_CAPS` dicts; you only pass what you mean.
4. **Result handling** — operations return a consistent, useful result object (the
   output, plus feature count / CRS / elapsed), not a raw dict you must unpack.
5. **One mental model across contexts** — the same call works in a notebook, the
   QGIS console, a standalone script, and (via a thin CLI) the terminal.

**Not the wedge (explicitly):** niva is not a new geometry engine, not a GeoPandas
replacement, and not a faster runtime — the heavy lifting stays in GDAL/GEOS/PROJ via
QGIS. niva is an *ergonomics and orchestration* layer.

## 2a. Design principles (the spine of the project)

1. **Grammar first.** The product is a small, consistent *grammar* — verbs
   (`buffer`, `clip`, `dissolve`), nouns (layers), and modifiers (kwargs) — that reads
   the same everywhere. Consistency and predictability beat breadth or cleverness.
2. **Chaining is the destination, designed-in from day one.** v1 ships only direct
   one-shot calls, but every v1 decision (return types, the `Layer` model, how output
   defaults work) is made so that fluent chaining (`x.buffer().clip().dissolve()`) and
   declarative flows drop in for v2 **without changing the v1 surface**. We are not
   building chaining yet; we are refusing to paint ourselves out of it.
3. **Interoperable, never a walled garden.** niva is a façade, not a cage. Every niva
   value exposes the underlying standard objects — a `QgsVectorLayer` and/or a file
   path/URI — so a user can drop into raw PyQGIS, GeoPandas, Shapely, or SQL the moment
   they need more flexibility or granularity, then hand the result back to niva. niva
   covers the common 90%; the other 10% must remain one attribute access away.
4. **Thin and honest.** niva adds ergonomics and orchestration, not a new engine. It
   never hides what QGIS algorithm ran or what parameters were sent (`--dry-run`,
   `result.algorithm`, `result.params`).

## 3. Who it's for

- **Primary:** the author — a PostGIS/QGIS power user who wants concise, high-level
  scripting in marimo notebooks, the QGIS console, and standalone scripts.
- **Secondary:** QGIS Python users who want a friendlier Processing façade and a
  small CLI for batch/automation.

## 4. Goals (v1)

- A **library** (`import niva`) exposing ~10–12 common vector operations as concise
  functions with good defaults (see `03-mvp-scope.md`).
- A universal **`niva.run(alg_id, **params)`** escape hatch so full Processing
  coverage is never blocked.
- **Two backends** behind one API: in-process PyQGIS (interactive) and `qgis_process`
  (headless), with automatic selection and an explicit override.
- A consistent **result/`Layer` model** (see `02-architecture.md`).
- A **thin CLI** (`niva ...`) generated from the same operation specs, for terminal
  and batch use.
- **Discovery**: `niva.find()` / `niva inspect` to list and describe algorithms.
- **Runs on QGIS's own Python** (the marimo-qgis model), installable via pip into
  that interpreter; tested headlessly in CI.

## 5. Non-goals (v1 — deferred, see roadmap)

- **Chaining / pipelines** (`niva.chain(...)`, `flow exec`, YAML flows) → v2.
- **SQL / PostGIS live layers** (`niva sql ...`) → v2.
- **Raster operations** beyond maybe a token few → v1.1.
- **QGIS plugin / Processing-Toolbox packaging** of niva itself → later.
- **A bespoke flow string DSL** → likely dropped entirely in favor of v2 YAML + chain.

## 6. Success criteria for v1

- A user can do the top ~12 vector ops in one readable line each, in all four usage
  contexts, against GeoPackage/PostGIS/shapefile inputs.
- `niva.run(...)` reaches any Processing algorithm not yet aliased.
- The same script runs in-process (console/notebook) and headless (`qgis_process`)
  by changing only the backend selector (or nothing, via auto-detect).
- Green headless CI on QGIS's Python with a small fixture dataset.

## 7. Key risks (carried from the critique)

- **Output/layer lifecycle** is the core design risk even without chaining — nailing
  the return-type contract (`02`) is the make-or-break ergonomics decision.
- **Dual-backend drift** — param/result handling must be normalized so behavior is
  identical across backends; this is the main engineering cost of the "both" decision.
- **Testing in a QGIS env** — must be solved early or it blocks confidence.
- **PyPI name `niva`** — availability to be verified before publishing.
