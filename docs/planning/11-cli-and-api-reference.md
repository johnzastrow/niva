# Niva — CLI & Python API Reference (v1)

_The single contract for the command line, the Python API, exit codes, and
environment variables — gathered from `02`/`03`/`09`. Closes Oscar **G6**._

---

## 1. Command line

### Commands

| Command | Does |
|---------|------|
| `niva run <file.niva>` | run a flow file (procedural; `call`s resolved) |
| `niva "<flow>"` | run an inline flow string |
| `niva find <term>` | search niva verbs and QGIS algorithms |
| `niva describe <verb \| alg-id>` | show a verb's mapping + parameters (and defaults) |
| `niva doctor` | environment/capability report — QGIS & library versions, providers present, what's installable |

### Global flags

| Flag | Effect |
|------|--------|
| `--dry-run` | print the resolved algorithm call(s); execute **nothing** |
| `--json` | machine-readable result/data to **stdout** (logs go to stderr) |
| `--log <file.jsonl>` | write the operation journal (`08-§2`) |
| `-v`, `--verbose` | include the underlying QGIS/GDAL detail on errors |
| `--backend <name>` | **(v0.2)** choose the backend; v1 is PyQGIS-only (`00-§3.3`) |

### Exit codes (`02-§6`)

`0` ok · `1` runtime error · `2` usage/parse error (`FlowError`) · `3` missing
QGIS/dependency · `4` reserved for SQL/connection (v2).

### Streams

Data and `--json` → **stdout**; logs, timing, progress, and errors → **stderr**.
This keeps `niva … --json | jq …` clean.

## 2. Python API

The engine *is* the API; the CLI is a thin wrapper over it (`02-§5`). It is the
power-user escape hatch (`01-§2`, `02-§3.6`).

```python
import niva

r = niva.flow("load roads.gpkg | buffer 100m | save out.gpkg")   # -> Result
r = niva.run("native:slope", INPUT="dem.tif", OUTPUT="slope.tif")  # raw escape hatch
```

| Object | Surface |
|--------|---------|
| `niva.flow(s: str) -> Result` | run a flow string; returns the final `Result` |
| `niva.run(alg_id, **params) -> Result` | run any algorithm by id (raw) |
| `niva.find(term)` / `niva.describe(name)` | discovery, same as the CLI |
| `niva.use_backend(name)` | **(v0.2)** select backend |
| `Result` | `.ok`, `.output: Layer`, `.outputs: dict`, `.algorithm`, `.params`, `.elapsed`, `.backend`; `__fspath__()`, `.load(name)` (`02-§3`) |
| `Layer` | `.source()`, `.as_qgs()`, `.as_uri()`, `.db_ref()`, `.crs`, `.geometry_type`, `.fields`, `.feature_count`, `.materialize()`, `Layer.coerce(x)` (`02-§3.1`) |
| Errors | `niva.FlowError` (parse/grammar), `niva.OpError` (runtime) (`02-§6`) |

Interop (never a cage): `os.fspath(result)` → path · `layer.as_qgs()` →
`QgsVectorLayer` · `layer.source()` → `gpd.read_file(...)` (`02-§3.6`).

## 3. Environment variables

| Var | Effect |
|-----|--------|
| `NIVA_LOG` | default operation-journal path (`08-§2`) |
| `NIVA_CONFIG` | override the config-file location (`09-§Configuration`) |
| `NIVA_BACKEND` | **(v0.2)** default backend |

Precedence for any setting: **CLI flag > env var > project config > user config >
built-in default** (`09-§Configuration`).

## 4. Stability

The CLI commands, global flags, exit codes, and the `niva.*` / `Layer` / `Result`
surface are a **contract frozen at v1.0** under SemVer (`04`); the `--json` and
journal shapes are versioned schemas (`08-§2`). Additions are minor; removals or
renames are major.
