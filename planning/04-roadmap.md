# Niva — Roadmap

_Status: draft for review. Sequencing from MVP to the chaining/flows destination._

## Guiding sequence

Build the **grammar and the dual-backend engine** first (v1), prove it's correct and
interoperable, then add the **chaining/flows** the grammar was designed for (v2), then
the **SQL/PostGIS** and packaging surfaces (v2+). Each milestone is shippable.

## v0.1 — Core engine + grammar (MVP)

The foundation. Everything later builds on these contracts, so get them right.

- `core/`: `Layer`, `Result`, `OpError`, `engine.run()`, `registry` (aliases + specs),
  `qgis_env` (interpreter/app detection, locate `qgis_process`).
- `backends/`: `Backend` ABC, `PyqgisBackend`, `QgisProcessBackend`, auto-`select`.
- Op specs + generated functions for the **13 v1 verbs** + `run`/`find`/`describe`.
- Thin **CLI** generated from the specs; `--json`, exit codes, `--dry-run`, `--timing`.
- `pyproject.toml`; `pip install` into QGIS's Python; `niva` console-script entry point.
- **Tests/CI**: registry/spec units (no QGIS), backend-parity tests, CLI tests; headless
  GitHub Actions on a QGIS Linux container with fixture GeoPackages.
- **Exit criteria**: `03-mvp-scope.md` "definition of done" met.

## v0.2 — Breadth + polish

- Raster operations (first set: `warp`/reproject, `clip` by mask/extent, `hillshade`).
- More vector verbs (symmetric difference, centroids, convex hull, simplify, …).
- Minimal `config` (default backend/profile); richer `--json` contracts.
- Docs site + worked examples in all four usage contexts.

## v1.0 — Stable release

- API freeze for the v1 grammar; semantic-versioning commitment.
- PyPI publish (verify `niva` name first; fallback list in `05-concepts-captured.md`).
- A worked **marimo-qgis integration** example (niva as the geoprocessing layer in a
  notebook), and a QGIS `startup.py` snippet for console preloading.

## v2.0 — Chaining + flows (the destination)

The grammar was designed for this from day one; v2 adds it **without changing the v1
surface**.

- **Fluent chaining**: `niva.chain(x).buffer(...).clip(...).dissolve(...).save(...)`,
  built on the v1 `Layer`/`Result` contract (each step feeds its output forward).
- **Declarative flows (YAML)** for reproducible, version-controlled pipelines:
  `niva flow run pipeline.yaml`, plus `flow validate`. (The bespoke pipe **string DSL**
  is intentionally **not** built — fluent chain + YAML cover its use cases without the
  quoting/parsing cost.)
- Temp-output lifecycle management across a chain (materialize on `save`/`load`,
  auto-clean intermediates).

## v2.x — SQL / PostGIS + packaging

- **SQL/PostGIS live layers**: `sql add` (query → live layer), `sql exec`, `sql test`,
  service/profile config. Adds exit code `4` (connection/SQL).
- Optional **QGIS Processing-Toolbox provider** and/or a thin **plugin** wrapper so niva
  ops appear in the QGIS GUI.
- Optional compiled outer CLI only if packaging/startup friction warrants it (no
  geoprocessing-speed reason to — see performance notes in `05`).

## Cross-cutting, all milestones

- Keep the **clean-room** discipline: API derived from QGIS Processing + idiomatic
  Python only.
- Keep **interop first-class**: every release preserves the escape hatches in
  `02-architecture.md §2a`.
- Keep **library and CLI generated from one spec** so they never diverge.
