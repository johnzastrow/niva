# Changelog

All notable changes to **niva** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.6.0] - 2026-06-15

### Changed
- **The plugin runs flows in a background thread — the QGIS UI no longer freezes.** A
  real run now executes in a `QgsTask` off the GUI thread: progress streams in live
  (via a queued signal), **Cancel responds immediately** (no longer only between
  progress ticks), and you can keep using QGIS while a long mosaic builds. The result
  is added to the map on the main thread when the task finishes. Dry-run stays
  synchronous (it's fast and mock-only). Flows remain **serial — one at a time** (the
  dock disables Run while one is in flight), honouring the single-QgsApplication rule
  (Oscar A9).
- **`save` no longer touches `QgsProject`** (uses a standalone
  `QgsCoordinateTransformContext`), so it's safe to call off the main thread. Plugin
  unload cancels any in-flight task. (Engine/grammar unchanged; CLI still synchronous.)

## [0.5.0] - 2026-06-15

### Added
- **Live progress, elapsed time, and cancel.** niva now emits status as a flow runs:
  - **Progress** — a `▶ <stage>` line as each stage starts, throttled **algorithm
    progress %** during long operations (via QGIS's processing feedback), and a
    per-stage `✓ <elapsed>`. Shown live in the plugin dock (it repaints mid-run, so a
    minutes-long mosaic streams `5% 10% …` instead of freezing silently) and on the
    CLI (stderr). API: `niva.flow(progress=callable)`.
  - **Elapsed time** — per stage in the progress, a **total when the job's done** (dock
    + CLI `# done in …`), and in the run-journal footer (`# done: … in 2.3 s`).
  - **Cancel** — a **Cancel** button in the dock aborts the running operation
    (`niva.flow(cancel=callable)`; the dock disables Run while a flow is in flight).
    In-process native algorithms abort promptly; gdal subprocess ops are best-effort
    (a fast one may finish first). A canceled run is reported as `… canceled`.
  - **+5 tests** (141 total); verified live progress %, elapsed, and real cancellation.

## [0.4.0] - 2026-06-15

### Added
- **Wildcards and `~` in paths — no more listing every file.** A `run` option value
  that contains a path glob (`*`, `?`, `[…]`) is expanded to the **sorted matching
  files**, so `run gdal:buildvirtualraster INPUT="tiles/*.jp2" …` reaches every tile
  without naming them. Relative globs resolve against the flow's directory; `;`-lists
  still work and combine with globs; a glob that matches nothing is a clear error; and
  a value that just happens to contain `*` (e.g. an expression `area * 2`) is left
  alone. `~` (home) is expanded in `run` values and in `load`/`save`/`assess` paths.
  **+4 tests** (136 total). Note: a glob in the *output's own folder* can match the
  output — use a specific pattern (e.g. `w_*.jp2`, not `*.jp2`).

## [0.3.1] - 2026-06-15

### Added
- **Friendlier error for `load @file.ext`.** `@` is for *saved database connections*,
  but `load @example.gpkg` is a common slip (it searched for a connection named
  `example`). niva now detects a `@`-ref that ends in a known file extension and points
  at the path form: ``load "example.gpkg|layername=<layer>"``. +1 test (132 total).

## [0.3.0] - 2026-06-15

### Changed
- **One run log per QGIS session (not per run), one line per operation.** The plugin
  now appends every run to a single session journal (`niva-session-<stamp>.{log,jsonl}`)
  until you hit a new **Reset (new file)** button in the Setup tab — and the Setup tab
  shows the current session-log path. The human `.log` is now strictly **one line per
  operation** (`<ts>  <stage>  [algorithm]  → <full path>  (ms)`, errors inlined), with
  a one-line `# run:` marker separating runs and a one-line `# done:` per run (was a
  3-line header + footer). `niva.flow(..., log_append=True)` enables session append;
  the CLI's `--log` still truncates per invocation. **+3 journal tests** (131 total).

## [0.2.1] - 2026-06-15

### Fixed
- **Plugin: `flow() got an unexpected keyword argument 'log'` after reinstalling
  without restarting QGIS.** Python caches modules in `sys.modules` across plugin
  reloads, so a reinstalled plugin kept running the *old* vendored niva. The entry
  point now **purges cached `niva` modules and loads the bundled copy first**, so a
  reinstall + reload picks up the new code with no QGIS restart. The plugin now always
  uses its own vendored niva (matching its runner) rather than preferring an external
  one — no version skew.

## [0.2.0] - 2026-06-15

Plugin maturity + observability: a Setup tab, a timestamped run journal (human +
machine), configurable logging, and QGIS-4/Qt6 fixes. (Engine/grammar unchanged from
0.1.0.)

### Added
- **Plugin: configurable run logging (Setup tab).** A "Write a log for each run"
  toggle + a log-folder field (with Browse), persisted in QGIS settings
  (`niva/log_enabled`, `niva/log_dir`). The dock passes the folder to the runner; the
  environment report shows the effective setting. (Of niva's three env vars, only
  `NIVA_LOG` is meaningful in-plugin — now exposed as a setting; `QGIS_PREFIX_PATH`
  and `QT_QPA_PLATFORM` only affect the standalone CLI bootstrap, so they're not in
  the UI.)
- **Plugin: a Setup tab** showing the environment a niva user cares about — niva
  version + where it's imported from (bundled vs pip), built-in + aliased verbs, the
  number of algorithms `run` can reach + the Processing providers, the available
  database connections (the `@conn` names), QGIS/Qt/GDAL/PROJ/GEOS versions,
  Python/platform, and where run journals land. Rendered as markdown with Refresh +
  Copy buttons (`plugin/environment.py`; the dock is now a Flow + Setup tab widget).
- **Run journal — a timestamped log of every operation** (planning 08-§2), written as
  **two files** because humans don't read JSON:
  - `<base>.jsonl` — machine-readable JSON Lines: a versioned header
    (`niva_journal`/version/flow/started) then one record per op (ts, kind, stage
    text, algorithm, ok, duration, full output path), plus a footer.
  - `<base>.log` — plain text a person reads: a header, one timestamped line per op
    (`<ts>  <stage>  [algorithm]  → <full path>  (12 ms)`), and a `done — N ops` footer.
  - **Full paths everywhere** — outputs are logged as **absolute** paths (resolved
    against the run's cwd), so you can always find what a flow wrote (the fix for the
    relative-path confusion).
  - **The plugin auto-logs every run** to the OS temp dir (`…/niva_logs/niva-<ts>.log`)
    and shows the path in the dock. CLI: `niva run flow.niva --log <base>`; both honor
    the `NIVA_LOG` env var; `niva.flow(text, log=<base>)` in Python.
  - Kept alongside the existing per-`save` lineage in `QgsLayerMetadata.history`
    (**now timestamped too**) — you get *both* the layer's embedded history and the
    run log. Only stage text + resolved paths are logged; never params or credentials.
  - **6 new journal tests** (128 total, all green).

### Fixed
- **Plugin: QGIS 4 / Qt6 compatibility metadata.** QGIS 4 flagged the plugin as
  "designed for QGIS 3.0–3.99" because `metadata.txt` had no maximum version (it
  defaults to `<min-major>.99`) and no Qt6 marker. Set `supportsQt6=True`,
  `qgisMaximumVersion=4.99`, `qgisMinimumVersion=3.22`. Rebuild/reinstall the zip.
- **Plugin: only the input stands out; read-only panels recede.** Instead of forcing
  white everywhere (which made the dock all-white), the dock now lets the theme style
  the editable flow editor as a field and paints the read-only output + Setup report
  with the dialog's window colour (theme-adaptive via the palette — works on light and
  dark themes). The area you type into is visually distinct from the rest.
- **Plugin: Qt6 scoped-enum crash opening the dock.** `Qt.RightDockWidgetArea`
  (Qt5) is `Qt.DockWidgetArea.RightDockWidgetArea` in Qt6 (QGIS 4), so the toolbar
  button raised `AttributeError`. Resolved both ways; the `QFont.StyleHint` hint is
  guarded too. Rebuild/reinstall `niva_qgis.zip`.

### Added
- **QGIS plugin on-ramp** (`plugin/`). A dock to write or open a `.niva` flow and
  **Run** it in the current QGIS session — a saved output lands on the map; a
  **Dry-run** button validates the flow over the mock backend (no geoprocessing) and
  prints the operation sequence. **Cross-platform with no install step:** niva
  (zero-dependency, pure Python) is **vendored** into the plugin and runs
  **in-process** — no `pip`, no subprocess, no interpreter detection — so it behaves
  identically on Windows (OSGeo4W), macOS, and Linux, sidestepping the install
  friction Oscar flags as the top adoption risk (E2/E3). The plugin prefers a
  `pip`-installed `niva` if present, else the vendored `libs/niva`.
  `plugin/build_plugin.sh` vendors niva and builds `niva_qgis.zip` (top-level folder
  `niva_qgis`, so it never shadows the vendored `niva` package). `plugin.py` /
  `dock.py` / `runner.py` go through `qgis.PyQt` (Qt5 + Qt6). Verified on the
  installed layout (repo off `sys.path`): the vendored import resolves with no
  collision and a real flow runs through the dock's runner.

## [0.1.0] - 2026-06-15

First working release — niva runs real geoprocessing. The pipeline is complete end
to end (grammar → registry/binder → engine → PyQGIS backend), validated against real
GIS data (a 24-layer Youngstown GeoPackage + DEM rasters) on QGIS 4.0.3: **122 unit
tests + 19 niva-script integration checks**, all green. Highlights:
verbs `load` (files + `@conn` tables + multi-layer-safe), `save` (with metadata +
auto-lineage), `sql @conn`, `run` (any algorithm, incl. multilayer params), `call`
file composition, `metadata set`, `assess` (quality + topology + lineage),
`describe`; 12 curated `native:*` aliases; a parse/`--dry-run`/`--explain`/`describe`
CLI and a `niva.flow()` Python API; near-zero runtime dependencies.

### Changed
- **`run` reaches multilayer params; fixed a GeoPackage save bug** (both surfaced by
  real raster/vector data):
  - A `run` option value containing `;` is now split into a **list** — QGIS's own
    layer-list separator — so multilayer params work, e.g.
    `run gdal:merge INPUT="a.tif;b.tif;c.tif" …`. (Enabled merging 13 DEM tiles +
    clipping to an AOI entirely via `run`; see `build_ytown_dem.niva`.)
  - **`save` to GeoPackage no longer fails when the layer carries an `fid` field**
    (`UNIQUE constraint failed: fid` — common in `pointsalonglines`, `intersection`,
    joins). niva tells GDAL to mint a fresh primary key and keeps the source `fid`
    as an ordinary attribute (no data loss). +2 tests (122 total).
- **Traceability matrix: ten verified `run`-only pipelines.** Added a "Proof" section
  with **10 multi-stage, alias-free pipelines (built-ins + `run` only)**, each
  **executed against the real Youngstown dataset** with recorded feature counts — the
  concrete evidence behind the Oscar verdict (answers "I don't see the concrete
  tests"). Plus the cross-provider raster build (`gdal:merge` → `gdal:clip…`).
- **Multi-layer sources handled explicitly.** A GeoPackage/SpatiaLite holds many
  layers, tables, and views — niva no longer silently loads the first. `load` of a
  multi-layer source **without** a layer name is now a clear error listing the
  available layers; pick one with `load "file.gpkg|layername=<name>"` (selects a
  layer, attribute table, or view), or a DB table with `load @conn[.schema].table`.
  Single-layer files load unchanged. +2 PyQGIS smoke tests (120 total). The
  traceability matrix gains a "Multi-layer sources" section (and a save caveat:
  one layer per file today; multi-layer write is planned, 03-§2.5).
- **Widened `reproject` and `join` aliases** to expose previously-hidden QGIS params
  (surfaced by the traceability matrix): `reproject` gains `convert_curved` and
  `transform_z` flags (moving `CONVERT_CURVED_GEOMETRIES` out of `forced` so it is
  overridable; both still default off); `join` gains `unmatched=<path>` for the
  `NON_MATCHING` sink (write the input rows that found no match). +2 tests (118 total).
- **Traceability matrix (`docs/planning/14`) reworked:** the alias table now lists the
  verbose original QGIS signature **last**, so the niva-signature and status columns
  stay visible; added a section explaining the `run` escape hatch (how to reach any
  of the installed algorithms — `describe` to find params, auto-filled `INPUT`/
  `OUTPUT`, `KEY=value` for the rest) with **8 worked native examples** verified
  against the live registry; and a section **proving `run` meets Oscar's success
  bar** (defuses Top-7 #6 registry-rot and #7 scope/bus-factor, softens #5 the cliff;
  zero deps, no injection surface). Regenerate with `scripts/gen_traceability_matrix.py`.

### Added
- **`assess` now reports existing metadata/lineage and checks duplicate geometries.**
  The report gains a **Metadata** section (title, abstract, keywords, and the
  lineage/history — 08-§4's "any existing lineage"), and `deep` adds a
  **duplicate-geometry** count (a topology check via WKB hashing) alongside the
  invalid/empty/null checks. This also lets niva verify its own metadata round-trip
  in pure niva (set → save → load → assess shows it).
- **Integration tests are now niva scripts** (`tests/integration/flows/*.niva`),
  run through the real `niva run` CLI against real GIS data and **self-verified by
  grepping the `assess` reports niva produces** — the language tests itself.
  `tests/integration/run.sh` substitutes the data/output paths, runs each flow
  (asserting exit codes — incl. the degrees guard's exit 2), and checks the reports:
  assess+topology, reproject/buffer/dissolve, clip-by-overlay (497 features),
  metadata+lineage round-trip, the `run` escape hatch, and a `call`-composed cat
  territory. **19/19 checks pass** on QGIS 4.0.3. Non-destructive, env-overridable
  data paths, SKIPs cleanly when QGIS/data absent. (Replaces the earlier Python
  integration driver.)
- **`scripts/run_tests.sh`** — runs the unit suite on QGIS's Python (falls back to
  plain Python, where the PyQGIS smoke tests skip). Reads unittest's own `OK`/`FAILED`
  line so the QGIS interpreter-shutdown segfault can't clobber the exit code.
- **v0.1 increment 11 — `describe`: introspection** (planning 11). Makes the `run`
  escape hatch discoverable. `niva describe <verb>` / `niva.describe("buffer")` shows
  how an alias maps to its QGIS algorithm (positionals, options with defaults/enums,
  flags) — pure, no QGIS. `niva describe <algorithm-id>` (anything with `:`)
  introspects the live algorithm: parameters (name, type, optional, default) and
  outputs — describe an algorithm, then `run` it. CLI `describe` subcommand +
  `niva.describe()` API; the algorithm path tears QGIS down cleanly (no shutdown
  segfault). **4 new tests** (103 bare / 116 under QGIS) incl. a real
  `describe native:buffer`.
- **v0.1 increment 10 — auto-lineage to metadata history** (planning 08-§3). Every
  `save` now records the niva stages that built the layer into the output's
  `QgsLayerMetadata.history` (prefixed `niva: `), so a saved layer carries its own
  reproducible recipe — provenance as a byproduct, with no extra verbs. The engine
  accumulates each flow's stage text and passes it to `save`; the PyQGIS backend
  appends history items (alongside any descriptive `metadata set` fields) and writes
  them with `saveDefaultMetadata` (`.qmd` sidecar fallback). **4 new tests** (100
  bare / 112 under QGIS) incl. a real round-trip reading the recipe back out of the
  saved GeoPackage. The Youngstown example header updated: **RUNS (v0.1)**.
- **v0.1 increment 9 — `assess`: data-quality reports** (planning 08-§4). A
  signature niva feature — provenance/quality as a byproduct.
  `assess [deep] to <report.md>` profiles the current layer and writes a markdown
  report (overview: type/feature-count/CRS-set?/extent; full field schema). `deep`
  adds quality checks: invalid + empty geometry counts and per-field null counts.
  A pass-through stage (profile, then keep piping). Backend returns a structured
  profile dict (so markdown formatting is unit-tested with a mock); PyQGIS inspects
  the real layer (vector full, raster basic). **11 new tests** (97 bare / 108 under
  QGIS) incl. a real `assess deep` that catches a null value and reports it.
- **v0.1 increment 8 — `metadata set`** (planning 08-§3). Attach descriptive
  metadata to the current layer and persist it on the next `save`:
  `metadata set title="…" abstract="…" keywords=a,b,c` (also `identifier`, `license`).
  A pass-through stage — sets `QgsLayerMetadata` in memory; `save` writes it to the
  file (GPKG/SpatiaLite via an explicit layer name + `saveDefaultMetadata`, falling
  back to a `.qmd` sidecar). Unknown fields are a FlowError. `save` now sets a layer
  name on multilayer outputs so metadata can be persisted and reloaded. **6 new
  tests** (92 bare / 102 under QGIS) incl. a real round-trip (write title/abstract/
  keywords → reopen → verify).
- **v0.1 increment 7 — database connections: `@conn` loading + `sql`** (planning 02,
  `niva/engine/connections.py`). niva reaches databases through **named QGIS
  connections** the user already configured:
  - `load @conn.table` / `load @conn.schema.table` — load a DB table as a layer.
  - `sql @conn "SELECT …"` — run a query and get a result (query) layer back, pipeable.
  - **Security boundary:** niva passes only the connection *name* to the backend,
    which resolves host/credentials from QGIS's own connection store. niva never
    sees, stores, logs, or transmits credentials (global CLAUDE.md §1/§14); the SQL
    text is not logged either (it stays in the provider). `_find_connection` searches
    all DB providers by name; `load_table` uses `tableUri`, `run_sql` uses
    `createSqlVectorLayer` (the provider parameterises — no string-built creds).
  - **13 new tests** (87 bare / 96 under QGIS) incl. real SpatiaLite smoke tests
    (`load @conn.homes`, `sql @conn "…WHERE id=1"`) that register a temp connection
    and clean it up, plus an unknown-connection → OpError check.
- **v0.1 increment 6 — the `run` escape hatch + `explode` alias** (planning 07-§8).
  `run <algorithm> KEY=value …` reaches **any** QGIS algorithm with no curated alias
  — the long tail the example needs (gdal, grass, pdal, native). Implemented as an
  engine built-in routing to a new `Backend.run_raw`: the backend injects `INPUT`
  from the upstream layer (piped use) and a temporary `OUTPUT` when absent, and
  returns the output as a handle (or `None` for terminal exports like a PDF/folder).
  Option values are best-effort scalar-coerced (`RES=1.5`→float, `FLAG=true`→bool,
  `RESAMPLING=1`→int; paths/CRS/field names stay strings). Added the `explode` alias
  (`native:multiparttosingleparts`). CLI `--explain`/`--dry-run` render `run` stages
  specially. **6 new tests** (74 bare / 80 under QGIS), incl. a real
  `run native:centroids` smoke test.
- **v0.1 increment 5 — `call` execution** (`niva/engine/engine.py`, planning 02/10).
  The file-composition mechanism the design centres on now runs: a `call <file>`
  statement resolves the target **relative to the calling file's directory**, parses
  it, and executes its flows inline (depth-first). `niva.flow`/`run_file` and the CLI
  thread the `base_dir` through so paths resolve correctly; the engine carries a
  call-stack for **cycle detection** (`a → b → a` is a clear FlowError, not a hang),
  and a missing/un-readable target is a FlowError with the offending name. Calling
  the same file twice in sequence is allowed (not a cycle).
- `tests/test_call.py` — **9 new unittest cases** (68 on bare Python, 73 under QGIS):
  composition, relative-path resolution, nesting, result propagation, self/indirect
  cycles, missing file, and error-propagation from a called file.

### Changed
- **Consistency pass over the planning set.** Unified verb names to canonical
  `filter`/`compute` (was `where`/`calc` in 02/06/07); fixed the version scheme so
  `v1.1` → `v0.2` (the roadmap's post-MVP release; `v1.1` contradicted
  `v1.0`=stable) and clarified that the MVP = `v0.1`; flagged doc 00 as historical
  with its superseded decisions (library-first, pipelines-deferred) and answered
  open questions struck through; removed remaining stale "both backends /
  auto-select in v1" wording.
- **Backend decision pinned: PyQGIS-only for v1** (ratifies `00-§3.3`). The
  in-process backend runs both interactively and headless (a headless
  `QgsApplication`), so one backend covers every context with no
  normalization/parity cost. The `Backend` ABC stays as the extension seam;
  `qgis_process` + auto-selection move to v0.2. Updated across docs 00–05.

### Added
- **v0.1 increment 4 — the PyQGIS backend: niva now runs real geoprocessing.**
  (`niva/engine/pyqgis.py`, `niva/__init__.py`, `niva/cli/main.py`, planning 02-§4.)
  - `PyqgisBackend` implements the four `Backend` methods against QGIS:
    `load` → `QgsVectorLayer`/`QgsRasterLayer`; `run` → `processing.run` with the
    upstream layer fed into the input param + `TEMPORARY_OUTPUT`, errors wrapped as
    `OpError`; `save` → `QgsVectorFileWriter` (driver by extension); `crs_of` →
    `CrsInfo` from the layer CRS (`isGeographic()` + metres-per-unit factor) so the
    engine's distance resolution runs against the real CRS. All `qgis` imports are
    lazy, so the package stays importable on any interpreter.
  - `ensure_qgis()` reuses a running QGIS or bootstraps a headless one, working
    around three standalone-PyQGIS traps (all in planning 02-§4.1): the Processing
    registry is empty without an explicit `QgsNativeAlgorithms` provider, and both
    that provider **and** the `QgsApplication` must be retained or GC tears the
    registry down. The CLI's owned-app path hard-exits cleanly to dodge the
    shutdown segfault.
  - **Python API:** `niva.flow("…")` and `niva.run_file(path)` (default real
    backend; pass `backend=MockBackend()` to dry-run without QGIS).
  - **CLI now executes for real** by default; `--dry-run` (mock) and `--explain`
    (plan only) remain QGIS-free.
  - `tests/test_pyqgis.py` — **5 smoke tests** that run actual geoprocessing
    (load→buffer→save produces a real polygon layer; 1km-buffer dissolve; filter;
    the degrees-mismatch FlowError; bad-load OpError). They **skip cleanly** when
    QGIS is absent, so the suite is 59-pass on bare `python3` and **64-pass under
    QGIS's Python** (verified on QGIS 4.0.3 / Python 3.14, PyQGIS at
    `/usr/share/qgis/python`).
- **v0.1 increment 3 — the engine core** (`niva/engine/`, planning 05/06),
  QGIS-free and mock-backed so it is fully unit-testable with plain `python3`:
  - `layer.py` — the `Layer` handle (backing `kind`: source/qgs/db_table/memory +
    vector/raster `facet`) and `CrsInfo`. The engine moves *handles*; only a backend
    ever touches real QGIS objects.
  - `backend.py` — the `Backend` seam (load / run / save / crs_of) and `MockBackend`,
    a no-QGIS double that records calls and returns fake handles (powers `--dry-run`).
  - `units.py` — `resolve_distance`: a unit-bearing distance (`100m`) is converted
    into the layer's CRS units; a linear distance on a **geographic CRS is a hard
    error**, never a silent degrees buffer (03-§1.1); a bare number is trusted as
    CRS units.
  - `engine.py` — `Engine.execute`: walks the program, threads one `Layer` down each
    flow's pipe, routes built-in `load`/`save` vs registry aliases, feeds the
    upstream layer into each op's input param, resolves distances against its CRS,
    and delegates to the backend. Unknown verb / op-before-load / save-with-nothing
    are `FlowError`s with line + stage; `call` is parsed but not yet executed.
  - `tests/test_engine.py` — **18 new unittest cases** (59 total, all passing):
    pipeline threading, filter-as-alias, multi-flow, the full distance/CRS matrix
    (m/ft/km, bare number, deg, and both degrees-mismatch errors), and the error paths.
  - CLI gains **`--dry-run`**: runs the whole flow through the engine over
    `MockBackend` and prints the validated backend operation sequence.
  - `requires-python` bumped to **>=3.12** (QGIS 4.x ships Python 3.12).
- **v0.1 increment 2 — the registry + binder** (`niva/registry/`, planning 07):
  - `model.py` — the declarative `Alias` / `Arg` / `Option` / `Flag` schema.
  - `definitions.py` — `CORE`: the curated verb set (buffer, clip, intersect,
    difference, dissolve, reproject, fix, centroid, join, zonalstats) as Python
    data, every `native:*` id and param name grounded in QGIS 4.0.3.
  - `registry.py` — `Registry` lookup with duplicate detection; `core_registry()`.
  - `binder.py` — `bind(stage, alias) → BoundOp`: splits flags from positionals,
    coerces by type (`distance` → `Distance(value, unit)`, enum word → QGIS int,
    `enumlist`, comma-lists), fills defaults, forces fixed values, validates
    arity / required options / unknown options — all `FlowError`s with line + stage.
  - `values.py` — the `Distance` value type (unit resolved against the layer CRS at
    run time, never silently reprojected).
  - `tests/test_registry.py` — **20 new unittest cases** (41 total, all passing).
  - **Registry format decision:** Python data, **not** YAML — a YAML parser would be
    a runtime dependency and break the zero-dep rule (Oscar E1). Doc 07 §11 revised.
  - CLI upgraded to **parse + bind**: alias verbs now print their resolved QGIS
    algorithm and `processing.run` params (built-ins marked pending the engine).
- **v0.1 MVP — build started (the package).** First code increment, grounded in
  the design docs:
  - `pyproject.toml` (hatchling; **zero runtime deps** per Oscar E1; `niva` console
    script; `dev` extra = pytest).
  - `niva/grammar/` — the **lexer + parser** (`10-grammar-spec.md`): comment
    stripping, quote-aware pipe splitting and stage tokenization (`key="…"`,
    `"expr"`, `@conn`, distances), `|` line-continuation, blank-line flow
    separation, and `call` statements → a `Program` of `Flow`/`Stage`/`Call`.
  - `niva/errors.py` — `FlowError` (exit 2; names file+line+stage) / `OpError`.
  - `niva/cli/` — a **parse-only CLI** (`niva "<flow>"`, `niva run <file>`) that
    prints the parsed structure (the engine/backend aren't built yet).
  - `tests/test_grammar.py` — **21 stdlib-`unittest` tests, all passing**; runs in
    QGIS's own Python with no install (where CI will run them).
- **Worked verb reference** (`docs/planning/13-verb-reference.md`): the verb model
  fully explained (positional/flag/option, defaults, enum-by-word, units,
  input/output threading), three signatures from simple to complex (`reproject` →
  `buffer` → `join`) each with the resulting `processing.run` call, and a composite
  flow that uses all three. Writing it **exercised the design and surfaced issues**:
  fixed back into the specs — list-valued options (`10-§2.1`), `save` creates
  parent dirs (`03-§2.5`); and logged as open — stage line-wrapping and
  text-flow secondary outputs (`00`), plus a new silent join-key-type-mismatch
  risk (Oscar D8). Also confirmed the simplified `filter` (`03-§3`) is essential,
  not optional.
  - **Round 2 — `zonalstats` (raster × vector)** stressed the enumlist + raster
    input: **verified** the `stats` enum vocab matches live QGIS; and surfaced —
    the **layer handle is vector-centric** (needs a vector/raster facet + piped
    type-checking, noted in `02-§3.1`, Oscar A10), a **raster-secondary CRS
    caveat** (don't silently warp, `03-§1.2`), and **field-name truncation** on
    Shapefiles (Oscar D9). Fixed a consistency bug: doc `06`'s `zonalstats`
    example used the space form → corrected to `key=value`.
  - **Round 3 — the SQL path** (`13-§8`) stressed cross-surface bridging and the
    connection model. **Spec'd the `sql` verb** (`03-§2.6`): three forms (`@conn`
    query-layer / `from file` `gdal:executesql` / bare `qgis:executesql` virtual),
    `input1` table naming, `key=`/`geom=`/`crs=` for non-self-describing SELECTs,
    result-CRS from the SRID, and a v1 **read-only rule** (top-level SELECT, run in
    a read-only transaction). **Corrected** the conflation of `SELECT` reads with
    the write-only `*executesql` algorithms, and reconciled the drifted `sql`
    syntax (`06-§4.4` used `use @conn`/`| load`). New risks: Oscar C15 (read-only
    detection), C16 (SELECT not self-describing).
  - **Round 4 — the `call` path** (`13-§9`) stressed multi-file composition.
    Spec'd in `03-§4.1`: `call` is a **statement, not a pipeable stage** (no shared
    `current` layer — handoff is via saved files / the live project); **path
    resolution split** (call-target = caller-relative, data paths = run `work_dir`);
    cycles/nesting with a max-depth backstop; provenance across calls — the journal
    tags each op by **source file** and lineage records the **call chain** (`08`);
    errors name the **file + line** across calls (`02-§6`). New limitation Oscar
    U11 (`call` doesn't transform the current layer; parameterized `call` is v2).
  - **Round 5 — the `assess` / lineage round-trip** (`13-§10`) stressed provenance
    across non-algorithm steps and runs. Spec'd in `08`: `sql`/`load` lineage
    entries (no `native:*` id — record the SQL+engine / source); **multi-input
    lineage merge** (flatten each input's history, role-tagged); sharpened
    "data-altering" to **include `filter`/`extract`** (they define the output, so
    they're recorded, not omitted); DB sources carry no lineage store (v1 records
    on the file output); the `assess` report is self-documenting (version/source
    stamp). New risk Oscar D10 (merge can mislead/bloat); open question on
    structured-provenance representation.
  - **Round 6 — the `add`-to-live-project path** (`13-§11`) stressed the
    interactive backend. Spec'd `add` (`03-§2.7`): **live-session only** (headless
    `add` warns/skips; an add-only flow errors headless); **sinks pass through** so
    `save … | add` chains (`02-§2a` corrected); `add` registers a *temporary*
    project layer (lost on close unless saved); default name + QGIS default
    styling (no styling verb in v1); **main-thread only** (can't background an
    `add`-flow). New limitation Oscar U12; raster `add` ties to A10.
  - **Synthesis (`13-§0`)** rolls up the six exercise rounds into a box score: 34
    issues surfaced, ~26 folded into specs, 1 verified-positive, ~5 still open,
    8 logged as Oscar risks — grouped by theme (grammar/verbs, sinks, the layer
    handle, SQL, `call`, provenance) so the conclusions aren't buried in the rounds.
  - **Verified all of `13`'s signatures against live QGIS 4.0.3** — param names,
    defaults, and enum-by-word mappings (`buffer` cap/join, `join` method,
    `zonalstats` stats) all confirmed; noted in the doc header.
- **Closed the two v1 blockers** flagged by Oscar (G1/G2), now specified in
  `03-mvp-scope.md`:
  - **Distances & units** (§1.1): a bare number = the layer's CRS units; unit
    suffixes (`100m`/`2km`/`ft`/…) convert; a linear distance on a **degrees CRS
    is a hard error** with a reproject fix — niva never silently buffers in
    degrees; auto-reproject convenience deferred to v0.2.
  - **`save` semantics** (§2.5): GeoPackage default + extension-inferred format;
    `as <layer>` naming in a container; replaces the target by default **but
    refuses to overwrite a source read earlier in the same flow**; `append`
    option; never reprojects; lock-aware errors; `--dry-run` preview.
  Marked resolved in `00` and Oscar (G1/G2/C8 closed; MVP-odds gate cleared).
- **Closed the remaining design holes (G3–G9)** — nothing now blocks *building* v1:
  - **CRS handling policy** (`03-§1.2`): work in each layer's CRS, never silently
    reproject; reproject secondary→primary on multi-input ops (logged); no-CRS =
    hard error.
  - **Error UX** (`02-§6`): every error names the failing stage + offending token
    in plain language with a suggested fix; friendly by default, `-v` for detail;
    common-error mapping.
  - **Formal grammar** (`10-grammar-spec.md`): EBNF + lexical rules.
  - **CLI & Python-API reference** (`11-cli-and-api-reference.md`).
  - **Config spec** (`09-§6a`): TOML, locations, precedence, v1 keys.
  - **Journal schema** (`08-§2`): versioned JSONL, secrets redacted.
  - **Security & threat model** (`12-security-model.md`).
  Oscar's gap verdict updated: only process/coverage docs (G10–G17) remain, and
  they can wait for code.
- **Failure register** (`docs/planning/Oscar_the_Grouch.md`): a comprehensive,
  adversarial catalogue of how niva could fail — premise/market, architecture,
  engineering, packaging/environment (incl. breaking QGIS's own Python), data
  correctness (silent wrong results), users, and sustainability — each with a
  severity and a mitigation, plus an existential-risk shortlist. Also includes a
  **performance & computational-limits deep dive** (§9: OOM/memory, scaling
  envelope, materialization I/O, large SQL results, caching, interactivity);
  **Oscar's review of the planning docs for gaps** (§10: undecided fundamentals
  that block v1 — distance units, `save` semantics, CRS policy, error UX — and
  missing specs/process docs); and a **conclusion estimating the probability of
  success of each development phase** (§12: ~60% MVP → ~3% full maturity,
  cumulative, gated by non-technical factors).
- **Deployment & operation doc** (`docs/planning/09-deployment-and-operation.md`),
  analyst-friendly: niva installs into QGIS's own Python (pip now; QGIS plugin
  later); connects to QGIS tools, files, and databases via QGIS's saved
  connections (`@name`, no stored credentials); the human-interface options
  (`.niva` files, CLI, QGIS console, marimo, later a plugin GUI and service mode);
  where it runs (workstation/headless/CI/service); and a phased maturity table.
- **PRD reworked** (`docs/planning/01-prd.md`) as the capstone summary of everything
  decided: the procedural grammar + `call`, the one-grammar-every-surface value
  prop (Processing native-first, expressions, `sql` passthrough), **provenance for
  free** (assess + op-log + lineage), the ~40-verb alias registry, the layer
  handle, and updated v1 goals/non-goals/success-criteria/risks (SQL reads in v1,
  writes v2; backends flagged as the one unsettled call).
- **File composition (`call`)**: a `.niva` file executes procedurally, and a
  `call <file.niva>` may appear anywhere to run another file's flows inline —
  procedural reuse / macros. Documented in `03-§4.1`, placed on the roadmap
  (v0.2 parameterless; v2.0 parameterized), and captured in concepts.
- **Worked example** (`examples/youngstown_cat_canvassing.niva`): the full
  `use_cases.md` workflow expressed in the proposed niva grammar (illustrative,
  not runnable) — multi-source/CRS/format load, assess, reproject, clip, geocode,
  PostGIS select, lidar→DEM→slope, GRASS routing/TSP, atlas handouts, and
  metadata/lineage on save.
- **Provider preference order (decided)**: native > gdal > qgis > pdal > … >
  **GRASS/SAGA last** — documented in `07-§12.1` and applied across the use-case
  walkthrough (`03-§2.4`), roadmap, and concepts. The canonical use case is shown
  to be almost entirely native, with GRASS reached (via `run`) only for
  cost-surface routing / TSP, which native lacks.

- **Planning materials** (`docs/planning/`): critique & open questions, product
  requirements for the non-programmer text-pipeline grammar, architecture, MVP
  scope, roadmap, and captured concepts.
- **QGIS capability surface reference** (`docs/planning/06-qgis-surface-reference.md`
  + `docs/planning/reference/*.tsv`): a snapshot, enumerated live from QGIS 4.0.3, of
  everything niva could reach — 769 Processing algorithms (8 providers), 406
  expression functions, SpatiaLite/PostGIS spatial SQL (cross-checked against the
  official SpatiaLite 5.1.0 and PostGIS function references — ~300+ documented
  spatial functions each, under OGC `ST_` plus legacy/extension names), the
  SQL-capable data providers and OGR/GDAL drivers, and the full version stack —
  with current signatures/access and before/after niva examples. Cross-checked
  against the QGIS Processing manual (framework model, Modeler/batch) and the
  SpatiaLite topics cookbook (Virtual Tables for SQL across heterogeneous
  sources).
- **Alias registry design** (`docs/planning/07-alias-registry-design.md`): how niva
  maps friendly verbs onto QGIS algorithms — the declarative entry schema,
  grammar→parameter binding, type coercion, enum vocabularies, the raw `run`
  escape hatch for full coverage, generation/validation against the live
  registry, and worked examples.
- **Layer handle contract** in `docs/planning/02-architecture.md`: the value threaded
  through the `|` pipeline — one `Layer` type with four backing kinds (source /
  live QgsVectorLayer / db_table / memory), its invariants, and the rules for
  **crossing surfaces** (Processing ↔ SQL ↔ expressions) with materialization
  only at boundaries that need it; connections by `@name`; eager-now/lazy-later.
- **Concepts captured** reworked (`docs/planning/05-concepts-captured.md`): the
  disposition table now spans the original exploration plus the surface (06),
  engine/registry (02/07), and provenance (08) concepts — including the
  five-surface model, the three-way name collision and its resolution, the layer
  handle, and provenance-as-byproduct; backends flagged as the one unsettled call.
- **Roadmap** reworked (`docs/planning/04-roadmap.md`): v0.1 MVP → v2.x sequenced
  across three parallel tracks (grammar/engine, coverage via the registry,
  provenance), reconciled with the ~40-verb set, SQL read-in-v1/writes-in-v2, the
  layer handle contract, and the logging/assess/auto-lineage plan.
- **Metadata, data quality & lineage surface** in `docs/planning/06-§2.5`: the
  "Metadata tools" algorithms (with signatures) + `QgsLayerMetadata` model, the
  21-algorithm Check-geometry group and profiling stats for quality assessment,
  and proposed niva verbs.
- **Data quality, provenance & lineage design** (`docs/planning/08-data-quality-
  provenance.md`): the operation log / run journal, the `assess` verb for
  profiling incoming data (CRS/schema/validity/duplicates/nulls), and
  auto-recording data-altering steps as formal metadata lineage
  (`native:addhistorymetadata` → `QgsLayerMetadata.history`) on save — making
  provenance a byproduct of the work.
- **Initial verb set** in `docs/planning/03-mvp-scope.md`: a curated ~40-verb v1 set
  (9 built-ins incl. `sql` read passthrough; Tier 1 + Tier 2 registry aliases),
  every alias mapped to a real, verified QGIS 4.0.3 algorithm id, tied to the
  `use_cases.md` analyst workflow; verb-naming reconciled across docs and the
  out-of-scope/definition-of-done updated (SQL reads in v1; writes/routing v2+).
- **Brand assets** (`docs/logos/`): the niva mark (`logo.svg` / `logo.png`) and
  wordmark (`logo_text.svg` / `logo_text.png`); earlier logo explorations
  archived under `docs/logos/OLD/`.
- **QGIS plugin stub** (`plugin/`): a minimal plugin that previews the niva logo
  on the toolbar and Plugins menu (no geoprocessing yet), Qt5/Qt6-compatible,
  with a `make package` build for the install zip.
- **README** describing the project goals and current (early, exploratory)
  status.
- This changelog.

[Unreleased]: https://github.com/johnzastrow/niva/commits/main
