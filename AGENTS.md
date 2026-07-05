# AGENTS.md — niva codebase guide

A concise, readable text-pipeline grammar for QGIS geoprocessing. niva provides ~45 friendly verbs that map to QGIS's ~769 Processing algorithms, plus built-in verbs for loading/saving/running SQL/exporting.

## Quick reference

```bash
# Run ALL tests (stdlib unittest)
python -m unittest discover -s tests -t .

# Try QGIS Python first, fall back to plain Python
scripts/run_tests.sh

# Run a specific test module
python -m unittest tests.test_grammar

# Validate aliases against the installed QGIS (must run under QGIS Python)
python scripts/lint_registry.py

# Regenerate test companion .niva files (required after adding/changing tests)
python scripts/gen_test_niva.py
python scripts/gen_run_niva.py

# Build wheel
python -m build

# Build PDF guide (needs pandoc + LaTeX)
python scripts/build_guide_pdf.py

# Run a flow
niva run myflow.niva
niva "load a.gpkg | buffer 100m | save b.gpkg"

# Validate without QGIS
niva "<flow>" --dry-run

# Show only the parse + bind plan
niva "<flow>" --explain

# Introspect a verb
niva describe buffer
```


## Authoring `.niva` flows — rules for agents

Follow these when writing or editing a flow; they prevent the most common (and *silent*) mistakes.
A one-page summary lives in [`docs/niva-cheatsheet.html`](docs/niva-cheatsheet.html).

1. **Verbs are a closed set — never invent one.** Built-in verbs are listed under "Built-in verbs
   vs aliases" below; the ~45 alias verbs are in [`docs/guide/reference.md` §5](docs/guide/reference.md).
   If a verb isn't in one of those, **it does not exist** — e.g. `stats`, `contour`, `index`,
   `dtm`, `flowaccum`, `transects` are *not* verbs. Do the operation with `run <provider:id>
   KEY=value` instead. **Learn any verb with `niva describe <verb>`** — it works **offline** and
   prints the verb→algorithm mapping, every option with its default and the QGIS param it sets,
   flags, and a worked example. (Running `describe` on an unknown token prints the full alias list.)
2. **Look up `run <id>` params offline** in [`docs/algorithms/<provider>.md`](docs/algorithms/)
   (gdal / native / qgis / grass / pdal / otb) — parameter names, types, defaults, and a worked
   example for all 878 algorithms. `describe <provider:id>` (an *algorithm*) needs a live QGIS —
   unlike `describe <verb>`, which is offline; the appendix covers the algorithms offline.
   `pdalcli:` / `saga:` harness params live in `docs/guide/pdal-lastools-qgis4.md`.
3. **Validate before claiming a flow works:** `niva run <flow> --explain` (or `niva "<inline>"
   --explain`) parses + binds every stage with **no QGIS required** — it catches bad verbs,
   options, and grammar. `--dry-run` also walks the MockBackend. Do this on every flow you author.
4. **One line per stage.** Continue a flow *between stages* by ending a line with a trailing `|`;
   a single stage's verb + options must stay on one line. `\` is **not** a continuation character.
5. **Provider preference:** native → gdal → QGIS → PDAL → GRASS (last). **Do not use SAGA or OTB**
   unless explicitly asked. Raw LiDAR: the `pdalcli:` harness (COPC-free).
6. **Aliases inject backend defaults that change the data** — e.g. `warp` → `RESAMPLING=nearest` +
   `CREATION_OPTIONS=COMPRESS=DEFLATE|TILED=YES`; `reproject` → `CONVERT_CURVED_GEOMETRIES=False`.
   See them with `--explain`; surface them when reproducibility matters.
7. **Micro-syntax:** report verbs take `to` without `=` (`assess to out.md`, `describe buffer
   to=out.md` — note `describe` uses `=`); `catalog <dir> to=<path>` uses `=`; `compute
   <field>="<QGIS expr>"` (string literals single-quoted); distances need a unit in a geographic
   CRS (`buffer 100m`, not `100`).


## Architecture

```
niva.grammar       (pure Python, no QGIS)
  lexer.py          — pipe-split, tokenize, strip comments, unquote
  parser.py         — text → Program (list[Flow | Call]), each Flow is list[Stage]

niva.registry      (pure Python, no QGIS)
  model.py          — Alias, Arg, Option, Flag dataclasses
  definitions.py    — CORE list: the ~45 verb → QGIS algorithm mappings
  binder.py         — Stage + Alias → BoundOp (resolved param dict for processing.run)
  registry.py       — verb → Alias lookup, duplicate detection

niva.engine        (pure Python except pyqgis.py — QGIS imports are lazy)
  engine.py         — Engine.execute(program): walks statements, pipes Layer handles
  backend.py        — Backend ABC (load, run, save, crs_of, …)
  pyqgis.py         — PyqgisBackend: the real processing.run adapter (QGIS required)
  layer.py          — Layer handle (kind=SOURCE|QGS|DB_TABLE|MEMORY, facet=vector|raster)
  connections.py    — @conn.table resolution
  units.py          — Distance resolution against CRS

niva/
  cli/main.py       — CLI entry point (niva run/describe/export/import)
  errors.py         — FlowError (parse, exit 2), OpError (runtime, exit 1)
  values.py         — Distance value type (value + unit)
  transpile.py      — .niva ↔ .py (PyQGIS script) conversion
  describe.py       — introspection for verbs + QGIS algorithms
  journal.py        — run journal (jsonl + human log)
  search.py         — fuzzy search across verbs + QGIS algorithm catalog
  __init__.py       — flow(), run_file() public API
```

### Control flow

1. Text (`.niva` file or inline string) → `parse()` → `list[Flow | Call]` — pure Python
2. Each `Stage` → `bind(stage, alias)` → `BoundOp{algorithm, params, input_param, output_param}` — pure Python
3. Engine executes statements procedurally: processes `call` includes (recursive), runs flow stages piping Layer handles through the Backend
4. Backend (`PyqgisBackend` or `MockBackend`) does all QGIS work via `processing.run()`

### Built-in verbs vs aliases

Built-in verbs are handled directly in `Engine.execute()` and are **not** in the registry:
`load`, `save`, `add`, `sql`, `filter`, `compute`, `run`, `find`, `describe`, `call`, `show`, `info`, `notify`, `email`, `catalog`, `project`, `style`, `docs`, `assess`, `metadata`, `each`

Aliases (~45 verbs like `buffer`, `clip`, `dissolve`, `intersect`, `reproject`, `warp`, `hillshade`) are in `niva/registry/definitions.py` and map to QGIS `native:*` algorithms. The `run <algorithm-id> KEY=value` escape hatch reaches any of the ~769 QGIS algorithms with no alias.

### Layer handle

`Layer` is a lightweight handle (not data). Four backing kinds:
- `SOURCE` — file path/URI on disk
- `QGS` — live QgsMapLayer in the current QGIS project
- `DB_TABLE` — table reachable via a QGIS connection
- `MEMORY` — in-process/temporary result of a previous op

The engine threads `Layer` handles through pipes; only the backend touches real QGIS objects.

## Critical gotchas

### 1. Must run under QGIS's own Python

niva executes QGIS algorithms. `import niva` works on any Python (all QGIS imports are lazy/in-function), but `niva.flow(...)` and `niva run ...` need QGIS's interpreter. The grammar, registry, binder, and MockBackend work on any Python — the PyQGIS smoke tests skip cleanly when `qgis` is unimportable.

### 2. QGIS segfault on teardown

A headless `QgsApplication` segfaults during interpreter shutdown **after printing its result**. The test runner and `lint_registry.py` gate on `unittest`'s `OK`/`FAILED` text output, not the exit code. Standalone QGIS initialization code must end with `os._exit(code)` not normal return.

### 3. Test companion files — must regenerate

Every `tests/test_*.py` has a generated companion at `tests/niva/<module>.niva` showing what each test exercises in niva form. **You must regenerate after adding or changing tests:**

```bash
python scripts/gen_test_niva.py        # regenerates tests/niva/*.niva
python scripts/gen_run_niva.py         # regenerates tests/suites/*.run.niva
```

This is enforced:
- **CI**: `test-companions` job regenerates and fails the build on drift
- **.claude hook**: `PostToolUse` on `Edit|Write|MultiEdit` of `tests/test_*.py` or `tests/suites/*.niva` auto-regenerates

### 4. Two kinds of test files

| Location | What | Companion? |
|---|---|---|
| `tests/test_*.py` | Python unittest modules | **generated** → `tests/niva/<module>.niva` |
| `tests/suites/*.niva` | Suites written directly in niva | already niva — no generation needed |

The validation suites also ship `.run.niva` companions (pure niva with directives stripped) that are generated by `gen_run_niva.py`.

### 5. Registry linter

`scripts/lint_registry.py` validates every alias against the **installed QGIS** — checks algorithm IDs exist and all referenced parameters are real. Must run under QGIS's Python. Catches silent drift when algorithms move between QGIS versions.

### 6. NIVA_TMPDIR for raster scratch

Raster operations write large intermediate files to the system temp dir (often a RAM-backed tmpfs). Set `NIVA_TMPDIR` to a disk-backed directory to avoid "disk quota exceeded" on long raster pipelines.

### 7. QT_QPA_PLATFORM=offscreen

All headless QGIS operations need `QT_QPA_PLATFORM=offscreen` in the environment.

### 8. NIVA_LOG env var

Set `NIVA_LOG=<base>` to write a run journal: `<base>.jsonl` (machine) + `<base>.log` (human).

### 9. Read-only mode

`--dry-run` validates a flow through `MockBackend` (no QGIS needed) and prints the operation sequence. `--explain` parses + binds only.

## Testing patterns

- Test framework: **stdlib unittest** (not pytest by default; pytest can run the same tests if installed)
- Pure Python tests (grammar, binder, search, engine over MockBackend): run with any Python
- PyQGIS tests (`test_pyqgis.py`): need QGIS interpreter, skip cleanly if unavailable
- PostGIS tests: need `NIVA_TEST_PG` env var or a running PostGIS service
- CI runs three jobs: `unit` (plain Python), `test-companions` (drift check), `qgis` (QGIS container + PostGIS), `build` (wheel + smoke)

## Naming conventions

- **Test files**: `tests/test_<module>.py` with `class Test<Module>(unittest.TestCase)`
- **Alias definitions**: verb name matches the `Alias.verb` lowercase string
- **QGIS parameter names**: UPPER_CASE (matching the `processing.run` parameter names)
- **Error types**: `FlowError` (grammar/parse problems, exit 2), `OpError` (algorithm runtime problems, exit 1)
- **Source files**: lowercase with underscores, mirror the module name
- **Layer/Stage/Flow vars**: short, descriptive names (e.g. `f` for a Flow, `s` for a Stage)

## QGIS plugin

The `plugin/` directory builds a QGIS plugin zip (`niva_qgis.zip`). Run `plugin/build_plugin.sh` to create it. The plugin bundles niva's Python source. Plugin-specific code lives in `plugin/plugin.py`, `plugin/dock.py`, `plugin/runner.py`, `plugin/flowtask.py`.

## Database connections (syntax)

- `load @conn.table` — read from a named QGIS connection
- `sql @conn "SELECT ..."` — server-side SQL query
- `save @conn.table mode=create|replace|append` — write to a database
- Non-SELECT `sql @conn "CREATE TABLE ... AS ..."` — DDL/DML (terminal step, no pipe output)

Connection name tokens are `@<name>`; dots in the name require quoting (e.g. `@"My PG Server"`).

## Key design constraints

- **Zero runtime dependencies** by design: niva runs inside QGIS's own Python and must never destabilize it. No YAML, no requests, no third-party libs. The registry uses Python data classes, not YAML files.
- **Lazy QGIS imports everywhere**: all `from qgis.core import ...` inside functions, never at module top level. This lets `import niva` succeed on any interpreter and tests run on plain Python.
- **Backend seam**: the engine never imports QGIS. Everything touching geodata goes through the `Backend` ABC. `MockBackend` enables `--dry-run` and pure-Python testing.
- **Layer handle abstraction**: `Layer` is a lightweight typed handle; the backend maps it to real QGIS objects. The engine never touches QGIS objects directly.