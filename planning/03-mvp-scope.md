# Niva — v1 MVP Scope

_Status: draft for review. The concrete v1 boundary: operations, grammar, CLI._

## 1. Grammar conventions (apply to every operation)

- **Verb = function/subcommand name**, lowercase, natural (`buffer`, `clip`, `where`).
- **Inputs/outputs/modifiers = kwargs / flags**, lowercase, consistent names:
  `input`, `inputs`, `output`, `overlay`, `field`, `fields`, `expr`, `predicate`,
  `target_crs`, `distance`. Same concept → same name everywhere.
- **Inputs are coerced** via `Layer.coerce` (path str, URI, PostGIS, `QgsMapLayer`,
  `Result`, `Layer`).
- **`output` is optional.** Omitted → managed temporary output, returned as
  `result.output`. Given → materialized to that path.
- **Sane defaults**; you pass only what you mean. Full parameter access is always
  available via `niva.run(alg_id, **PARAMS)`.
- Library and CLI are generated from the same op specs, so they never drift.

## 2. v1 operation set (vector-first, ~13 verbs)

| niva verb | QGIS algorithm | Key params |
| :-- | :-- | :-- |
| `buffer` | `native:buffer` | input, distance, dissolve, segments, output |
| `clip` | `native:clip` | input, overlay, output |
| `intersection` | `native:intersection` | input, overlay, output |
| `union` | `native:union` | input, overlay, output |
| `difference` | `native:difference` | input, overlay, output |
| `dissolve` | `native:dissolve` | input, field, output |
| `reproject` | `native:reprojectlayer` | input, target_crs, output |
| `fix` | `native:fixgeometries` | input, output |
| `explode` | `native:multiparttosingleparts` | input, output |
| `calc` | `native:fieldcalculator` | input, field, expr, output |
| `where` | `native:extractbyexpression` | input, expr, output |
| `select` | `native:extractbylocation` | input, overlay, predicate, output |
| `merge` | `native:mergevectorlayers` | inputs, target_crs, output |

Plus three non-op verbs:

| verb | purpose |
| :-- | :-- |
| `run` | universal escape hatch: run any algorithm by id with raw params |
| `find` | search/list algorithms and niva aliases (discovery) |
| `describe` | show an algorithm's parameters and the niva alias mapping |

## 3. Public Python API (v1)

```python
import niva

# direct ops — each returns a Result whose .output is a Layer
niva.buffer("roads.gpkg", distance=100, dissolve=True, output="roads_buf.gpkg")
niva.clip("parcels.gpkg", overlay="city.gpkg")            # temp output
niva.where("parcels.gpkg", expr='"ZONE" = \'R1\'')
niva.reproject("parcels.gpkg", target_crs="EPSG:2264")

# escape hatch + discovery
niva.run("native:slope", INPUT="dem.tif", OUTPUT="slope.tif")
niva.find("dissolve")
niva.describe("native:buffer")

# backend control (default = auto)
niva.use_backend("qgis_process")                          # or per-call backend=
```

## 4. CLI surface (v1 — thin wrapper, flat verbs mirroring the library)

```text
niva buffer  --input roads.gpkg --distance 100 --dissolve [--output out.gpkg]
niva clip    --input parcels.gpkg --overlay city.gpkg
niva where   --input parcels.gpkg --expr "\"ZONE\" = 'R1'"
niva select  --input parcels.gpkg --overlay schools.gpkg --predicate intersects
niva run     native:buffer --param INPUT=roads.gpkg --param DISTANCE=50 --param OUTPUT=out.gpkg
niva find    dissolve
niva describe native:buffer
niva version
```

Global flags: `--backend {auto,pyqgis,qgis_process}`, `--json`, `--dry-run`,
`--verbose`, `--quiet`, `--timing`, `--project PATH`.
Exit codes: `0` ok · `1` runtime · `2` usage · `3` missing QGIS/dep · (`4` reserved
for SQL/connection in v2).

Flat verbs (not `niva vector buffer`) keep the CLI symmetric with the library
(`niva.buffer`). When raster lands (v1.1) it can either stay flat (`niva hillshade`)
or introduce a `raster` group — decided then, not now.

## 5. Explicitly OUT of v1 (see roadmap)

- Chaining / fluent API and declarative flows (YAML) → **v2** (designed-for, not built).
- The flow-exec **string DSL** → **dropped** (redundant with chain + YAML; quoting cost).
- SQL / PostGIS live layers → **v2**.
- Raster operations → **v1.1**.
- `config` profiles beyond a minimal default-backend setting → **v1.1**.
- Packaging niva as a QGIS plugin / Processing-Toolbox provider → **later**.

## 6. Definition of done (v1)

- All 13 verbs work via **both** backends with equivalent results, verified by
  backend-parity tests on fixture GeoPackages.
- `run` reaches any algorithm; `find`/`describe` aid discovery.
- Library works in: a marimo cell, the QGIS Python Console, a standalone script on
  QGIS's Python; the CLI works in a terminal.
- Interop verified: `result.output.as_qgs()`, `.source`, `os.fspath(result)`, and
  round-tripping a GeoPandas frame back into a niva op.
- `pip install`able into QGIS's Python; headless CI green.
