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

1. **Never invent a verb — ground the verb set in the code.** Verbs are a **closed set**: the 22
   built-ins (`Engine._BUILTIN_VERBS` in `niva/engine/engine.py`, + `each`/`call`) and the 45
   aliases (`core_registry().verbs()` / `docs/guide/reference.md §5`). Regenerate either with
   `python -c "from niva.registry.registry import core_registry; print(sorted(core_registry().verbs()))"`.
   If a verb isn't in one of those it does not exist — `stats`, `contour`, `index`, `dtm`,
   `flowaccum`, `transects`, `compute`, `add`, `find` are **not** verbs. Do the operation with
   `run <provider:id> KEY=value`. (Same rule for parameters and defaults: verify against
   `describe <id>` / `docs/algorithms/`, never memory.)
   **Learn any verb with `niva describe <verb>`** — it works **offline** and prints the
   verb→algorithm mapping, each option with its default and the QGIS param it sets, and an example.
2. **Validate offline before you claim it works:** run **`niva validate <flow.niva>`** (no QGIS
   needed) — the linter runs grammar + closed-set verb check (did-you-mean on a typo) + alias
   arg/option/enum binding + `run <id>` param check against the catalog, **then** a MockBackend
   dry-run, so a clean pass means the flow actually runs, not just parses. It also flags style
   smells (a distance with no unit, a `run <id>` with a friendly verb, SAGA/OTB, a missing `save`).
   Exit `0` clean, `1` on any error. **Do not present a flow that does not pass `niva validate`.**
   (`--explain` / `--dry-run` stay as lighter one-off checks on inline `"<flow>"` strings.)
3. **Look up params offline** — `niva describe <verb-or-id>` works **without QGIS** for both verbs
   and the 878 algorithm ids (it reads the packaged catalog), as does `docs/algorithms/<provider>.md`
   (gdal/native/qgis/grass/pdal/otb) — names, types, defaults, worked example. `pdalcli:`/`saga:`
   harness params are in `docs/guide/pdal-lastools-qgis4.md`.
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
4. **Validate:** `niva validate <flow.niva>`. Fix every reported error. Only then present it.
5. **Note the caveats you couldn't verify offline** (e.g. a `run` step whose exact params need
   a live QGIS check, or data that must exist to run) — honestly, as the examples do.

## Syntax quick facts

- Report verbs: `assess to out.md`, `describe buffer to=out.md` (`describe` uses `=`),
  `catalog <dir> to=<path>`.
- String literals inside a QGIS expression are single-quoted: `filter "landuse = 'R'"`.
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
