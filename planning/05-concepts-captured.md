# Niva — Concepts Captured (supersedes the local design exploration)

_This file records every relevant concept from the (uncommitted) local exploration,
with its disposition, so the planning set is self-sufficient and the source material is
not needed in the repo. Clean-room: concepts are framed on QGIS/Python terms only._

## 1. Disposition of every concept

| Concept | Disposition | Where |
| :-- | :-- | :-- |
| Python wrapper over PyQGIS/QGIS Processing | **Core of v1** | 01, 02 |
| Alias registry (friendly verb → `native:*` id) | **v1** | 02 §4 |
| Op specs as one source of truth for lib + CLI | **v1** | 02 §4 |
| Concise grammar (verbs/nouns/modifiers) | **v1 — the spine** | 01 §2a |
| In-process PyQGIS backend | **v1** | 02 §3 |
| `qgis_process` headless backend | **v1** | 02 §3 |
| Auto backend selection + override | **v1** | 02 §3 |
| `run` universal escape hatch | **v1** | 03 §2 |
| Discovery (`find` / `describe` / inspect) | **v1** | 03 §2 |
| Consistent return type / `Layer` model | **v1 (key decision)** | 02 §2 |
| Interop with PyQGIS / GeoPandas / SQL | **v1 requirement** | 01 §2a, 02 §2a |
| `--json`, exit codes, stdout/stderr discipline | **v1** | 02 §5, 03 §4 |
| Fluent chaining (`chain(x).buffer()…`) | **v2 (designed-for in v1)** | 04 |
| Declarative YAML flows | **v2** | 04 |
| Flow-exec **string DSL** (`"buffer \| clip \| save"`) | **Dropped** | 03 §5, 04 |
| SQL / PostGIS live layers | **v2.x** | 04 |
| Raster operations | **v1.1 (v0.2)** | 04 |
| QGIS Processing-script / plugin packaging | **Later** | 04, §2 below |
| Rust/Go rewrite | **Rejected** (no speed gain) | §3 below |
| Naming = "niva" | **Decided** | §4 below |

## 2. QGIS integration patterns (how niva gets used in-context)

All four are supported by design; none require changes to the core grammar.

- **QGIS Python Console** — `import niva`; the in-process backend uses the live session
  and `Layer.as_qgs()` returns project layers. Primary interactive surface.
- **`startup.py` / `PYQGIS_STARTUP`** — preload niva so `import niva` is always ready in
  the console. Keep startup code light (paths + import only); defer GUI/`iface` work.
- **Standalone scripts on QGIS's Python** — `qgis_env` initializes a headless app (or
  niva auto-selects the `qgis_process` backend). Primary scripting/batch surface.
- **marimo-qgis notebooks** — niva is the geoprocessing layer inside a marimo cell; the
  notebook already runs on QGIS's Python (see the marimo-qgis project).
- **(Later) Processing-Toolbox script / plugin** — niva can be called inside a custom
  Processing script, or wrapped by a plugin where plugin = UI and niva = logic.

## 3. Performance guidance (informs design, not a v1 deliverable)

The bottleneck is QGIS/`qgis_process` startup + GDAL/GEOS/PROJ + I/O, **not** Python
glue, so:

- Implementation language stays **Python**; a Rust/Go rewrite buys packaging, not
  geoprocessing speed, and was rejected.
- Real wins to pursue later: minimize repeated QGIS startup (batch work per process),
  push set/filter/join work into **PostGIS SQL** where appropriate, prefer native
  provider algorithms over per-feature Python loops, and avoid needless temp I/O.
- `qgis_process --skip-loading-plugins` / `--no-python` are options for faster headless
  batch runs (consider exposing via CLI flags in v0.2).

## 4. Naming

- Project/package/command name: **`niva`** (decided).
- **To verify before publishing:** PyPI availability of `niva`. If taken, candidate
  fallbacks to evaluate (import name can differ from the distribution name): `pyniva`,
  `nivagis`, `niva-gis`. The CLI command stays `niva` regardless.

## 5. What was deliberately rejected or cut (and why)

- **Flow-exec string DSL** — quoting hell (`'\"CLASS\" = ''local'''`), a bespoke parser
  to maintain, and redundant with fluent chaining (interactive) + YAML (reproducible).
- **Single-backend-only v1** — considered, but the user wants both interactive and
  headless from the start; accepted the extra normalization cost (02 §3).
- **Rust/Go core** — no runtime benefit for this workload (§3).
- **Treating niva as a GeoPandas replacement** — it is a façade that *interoperates*
  with GeoPandas/PyQGIS, not a competitor to them.
