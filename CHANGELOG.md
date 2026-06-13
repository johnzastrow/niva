# Changelog

All notable changes to **niva** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it has releases.

> **Status: pre-release.** niva is an early-stage design exploration — no
> versioned release or installable package exists yet. Everything below sits
> under *Unreleased*; the grammar and API are still goals, not shipped features.

## [Unreleased]

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
- **Worked verb reference** (`planning/13-verb-reference.md`): the verb model
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
- **Failure register** (`planning/Oscar_the_Grouch.md`): a comprehensive,
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
- **Deployment & operation doc** (`planning/09-deployment-and-operation.md`),
  analyst-friendly: niva installs into QGIS's own Python (pip now; QGIS plugin
  later); connects to QGIS tools, files, and databases via QGIS's saved
  connections (`@name`, no stored credentials); the human-interface options
  (`.niva` files, CLI, QGIS console, marimo, later a plugin GUI and service mode);
  where it runs (workstation/headless/CI/service); and a phased maturity table.
- **PRD reworked** (`planning/01-prd.md`) as the capstone summary of everything
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

- **Planning materials** (`planning/`): critique & open questions, product
  requirements for the non-programmer text-pipeline grammar, architecture, MVP
  scope, roadmap, and captured concepts.
- **QGIS capability surface reference** (`planning/06-qgis-surface-reference.md`
  + `planning/reference/*.tsv`): a snapshot, enumerated live from QGIS 4.0.3, of
  everything niva could reach — 769 Processing algorithms (8 providers), 406
  expression functions, SpatiaLite/PostGIS spatial SQL (cross-checked against the
  official SpatiaLite 5.1.0 and PostGIS function references — ~300+ documented
  spatial functions each, under OGC `ST_` plus legacy/extension names), the
  SQL-capable data providers and OGR/GDAL drivers, and the full version stack —
  with current signatures/access and before/after niva examples. Cross-checked
  against the QGIS Processing manual (framework model, Modeler/batch) and the
  SpatiaLite topics cookbook (Virtual Tables for SQL across heterogeneous
  sources).
- **Alias registry design** (`planning/07-alias-registry-design.md`): how niva
  maps friendly verbs onto QGIS algorithms — the declarative entry schema,
  grammar→parameter binding, type coercion, enum vocabularies, the raw `run`
  escape hatch for full coverage, generation/validation against the live
  registry, and worked examples.
- **Layer handle contract** in `planning/02-architecture.md`: the value threaded
  through the `|` pipeline — one `Layer` type with four backing kinds (source /
  live QgsVectorLayer / db_table / memory), its invariants, and the rules for
  **crossing surfaces** (Processing ↔ SQL ↔ expressions) with materialization
  only at boundaries that need it; connections by `@name`; eager-now/lazy-later.
- **Concepts captured** reworked (`planning/05-concepts-captured.md`): the
  disposition table now spans the original exploration plus the surface (06),
  engine/registry (02/07), and provenance (08) concepts — including the
  five-surface model, the three-way name collision and its resolution, the layer
  handle, and provenance-as-byproduct; backends flagged as the one unsettled call.
- **Roadmap** reworked (`planning/04-roadmap.md`): v0.1 MVP → v2.x sequenced
  across three parallel tracks (grammar/engine, coverage via the registry,
  provenance), reconciled with the ~40-verb set, SQL read-in-v1/writes-in-v2, the
  layer handle contract, and the logging/assess/auto-lineage plan.
- **Metadata, data quality & lineage surface** in `planning/06-§2.5`: the
  "Metadata tools" algorithms (with signatures) + `QgsLayerMetadata` model, the
  21-algorithm Check-geometry group and profiling stats for quality assessment,
  and proposed niva verbs.
- **Data quality, provenance & lineage design** (`planning/08-data-quality-
  provenance.md`): the operation log / run journal, the `assess` verb for
  profiling incoming data (CRS/schema/validity/duplicates/nulls), and
  auto-recording data-altering steps as formal metadata lineage
  (`native:addhistorymetadata` → `QgsLayerMetadata.history`) on save — making
  provenance a byproduct of the work.
- **Initial verb set** in `planning/03-mvp-scope.md`: a curated ~40-verb v1 set
  (9 built-ins incl. `sql` read passthrough; Tier 1 + Tier 2 registry aliases),
  every alias mapped to a real, verified QGIS 4.0.3 algorithm id, tied to the
  `use_cases.md` analyst workflow; verb-naming reconciled across docs and the
  out-of-scope/definition-of-done updated (SQL reads in v1; writes/routing v2+).
- **Brand assets** (`logos/`): the niva mark (`logo.svg` / `logo.png`) and
  wordmark (`logo_text.svg` / `logo_text.png`); earlier logo explorations
  archived under `logos/OLD/`.
- **QGIS plugin stub** (`plugin/`): a minimal plugin that previews the niva logo
  on the toolbar and Plugins menu (no geoprocessing yet), Qt5/Qt6-compatible,
  with a `make package` build for the install zip.
- **README** describing the project goals and current (early, exploratory)
  status.
- This changelog.

[Unreleased]: https://github.com/johnzastrow/niva/commits/main
