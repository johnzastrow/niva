# Changelog

All notable changes to **niva** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it has releases.

> **Status: pre-release.** niva is an early-stage design exploration — no
> versioned release or installable package exists yet. Everything below sits
> under *Unreleased*; the grammar and API are still goals, not shipped features.

## [Unreleased]

### Added
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
