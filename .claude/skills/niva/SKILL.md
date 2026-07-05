---
name: niva
description: >-
  Author, edit, validate, and run niva flows — the text-pipeline grammar for QGIS
  geoprocessing (.niva files). Use when writing or debugging a niva pipeline, choosing
  verbs, reaching QGIS/GDAL/GRASS/PDAL algorithms via `run`, building a multi-stage
  geospatial study, or working anywhere in the johnzastrow/niva repo. Triggers on
  ".niva", "niva flow/run", "niva verb/alias", or geoprocessing-pipeline authoring.
---

# Authoring niva flows

niva is a readable text-pipeline grammar over QGIS Processing: **~23 built-in verbs +
~45 alias verbs**, plus `run <provider:id> KEY=value` to reach any of **878** QGIS
Processing algorithms. Flows are `.niva` files (or inline strings); stages chain with `|`.
Quick visual reference: [`docs/niva-cheatsheet.html`](../../../docs/niva-cheatsheet.html).

## Golden rules — apply on EVERY flow

1. **Never invent a verb.** Verbs are a **closed set**. Built-ins are in `AGENTS.md`
   ("Built-in verbs vs aliases"); alias verbs are in `docs/guide/reference.md §5`. If a verb
   isn't in one of those, it does not exist — `stats`, `contour`, `index`, `dtm`, `flowaccum`,
   `transects` are **not** verbs. Do the operation with `run <provider:id> KEY=value`.
   **Learn any verb with `niva describe <verb>`** — it works **offline** and prints the
   verb→algorithm mapping, each option with its default and the QGIS param it sets, and an example.
2. **Validate offline before you claim it works:** run
   `niva run <flow> --explain` (no QGIS needed) — it parses and binds every stage and flags
   bad verbs/options/grammar. Use `--dry-run` to also walk the MockBackend. **Do not present a
   flow you have not `--explain`-ed.**
3. **Look up params offline.** For a **verb**: `niva describe <verb>` (offline). For a **`run`
   algorithm id**: `docs/algorithms/<provider>.md` (gdal/native/qgis/grass/pdal/otb) — names,
   types, defaults, worked example for all 878 ids (`describe <provider:id>` itself needs QGIS).
   `pdalcli:`/`saga:` harness params are in `docs/guide/pdal-lastools-qgis4.md`.
4. **One line per stage.** Continue a flow *between stages* with a trailing `|`; a single
   stage's verb + options stay on one line. `\` is **not** continuation.
5. **Provider preference:** native → gdal → QGIS → PDAL → GRASS (last). **No SAGA/OTB** unless
   asked. Raw LiDAR → the `pdalcli:` harness (COPC-free).

## Procedure

1. **Understand the goal**, then sketch the stage sequence (load → transform → save).
2. **Pick verbs from the closed set.** For each operation, confirm the verb in
   `docs/guide/reference.md §5`; if none fits, choose a `run <id>` and confirm its parameters in
   `docs/algorithms/<provider>.md` (copy exact KEY names — do not guess).
3. **Write it**, one stage per line, `#` comments for narration (match the style of
   `examples/analyst_plan.niva`).
4. **Validate:** `niva run <flow> --explain`. Fix every reported error. Only then present it.
5. **Note the caveats you couldn't verify offline** (e.g. a `run` step whose exact params need
   a live QGIS check, or data that must exist to run) — honestly, as the examples do.

## Syntax quick facts

- Report verbs: `assess to out.md`, `describe buffer to=out.md` (`describe` uses `=`),
  `catalog <dir> to=<path>`.
- `compute <field>="<QGIS expression>"` — string literals single-quoted: `compute src="'ndwi'"`.
- `zonalstats raster=<r> stats=count,sum,mean,median,stdev,min,max prefix=<p>`.
- `figure out.png` — quick image (pass-through, chains after `save`);
  `map out.pdf title="…" layers="a;b" dpi=200` — composed layout (legend/scale/N-arrow → PDF/PNG).
- Distances need a unit in a geographic CRS: `buffer 100m`, not `buffer 100` (= 100 degrees).
- Multi-layer GeoPackage: `load "data.gpkg|layername=parcels"`.

## Reproducibility note

Alias verbs **inject backend defaults that change the data** — e.g. `warp` → `RESAMPLING=nearest`
+ `COMPRESS=DEFLATE|TILED=YES`; `reproject` → `CONVERT_CURVED_GEOMETRIES=False`. Reveal them with
`--explain`, and record them when the work must be reproducible (they are part of the method).

## Tests

If you add or change a `tests/test_*.py` or `tests/suites/*.niva`, regenerate the companions:
`python scripts/gen_test_niva.py && python scripts/gen_run_niva.py` (a PostToolUse hook and the CI
`test-companions` job both enforce this — a drift fails the build).

## Common gotchas

| symptom | fix |
|---|---|
| `a stage must start with a verb` | one stage per line; continue between stages with a trailing `\|`; `\` is not continuation |
| `unknown verb` / invented verb | verbs are a closed set — check `reference.md §5`; use `run <id>` otherwise |
| `unknown option` | `describe <verb>` (or `reference.md`) for the real options |
| `notify needs a topic` | set `NIVA_NTFY_TOPIC` or add `to=<topic>` |
| `could not import QGIS` | `niva.flow(...)`/`run` need QGIS's Python; grammar/`--explain` work on any Python |
| raster scratch fills up | `export NIVA_TMPDIR=<disk-backed dir>` |
| headless run | `export QT_QPA_PLATFORM=offscreen` |
