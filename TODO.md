# TODO

Parked work. See [`docs/planning/04-roadmap.md`](docs/planning/04-roadmap.md),
[`docs/planning/15-postgis-and-project-design.md`](docs/planning/15-postgis-and-project-design.md),
and [`docs/planning/16-anatomy-of-a-verb.md`](docs/planning/16-anatomy-of-a-verb.md) for context.

- [ ] **Test-hardening pass (agreed; the next thing).** The live-QGIS tier
  (`tests/test_pyqgis.py`) — which catches the real backend bugs — currently **skips in
  CI** (`.github/workflows/ci.yml` runs only the pure-Python suite + build). So that tier
  is a manual habit, not an enforced gate. Do:
  1. **Wire the live-QGIS tier into CI** — a job on the `qgis/qgis` Docker image running
     `test_pyqgis.py`. (Validating this needs a push-and-observe loop on GitHub Actions.)
  2. **Real-Postgres tier** — a Postgres service container in CI so the postgres-specific
     DB paths (`COMMENT ON TABLE`, schema-qualified writes, `public` default) are tested
     for real, not only via SpatiaLite.
  3. **Coverage fill + trivial-test audit** — verbs with thin tests; check for assertions
     that pass without exercising behaviour.

- [ ] **Raster-layer repointing in `project`.** The `project` verb (v0.18.0) repoints
  *vector* layers and leaves rasters unchanged. Extend it to repoint raster layers too —
  match a raster layer (DEM, orthophoto) to its clipped file (e.g. `dem_clip.tif`,
  `orthophoto_clip.jp2`) and `setDataSource(..., "gdal")`. Needs a target convention for
  rasters (they're separate files, not inside the one gpkg/DB used for vectors).
  Touchpoints: `niva/engine/pyqgis.py::repoint_project` / `_repoint_target`; tests in
  `tests/test_pyqgis.py::TestPyqgisProject`.

- [ ] **`style` verb — `.qml` / `.qmd` sidecars.** Read/write/apply QGIS layer style
  (`.qml`) and metadata (`.qmd`) sidecars, per the roadmap's "layer sidecars" item.
  New built-in verb alongside `project` (dispatch + `_style`; a backend method using
  `QgsMapLayer.loadNamedStyle`/`saveNamedStyle` and the `.qmd` metadata API).

- [ ] **Real end-to-end run of the analyst plan (now including Task 5).** Run
  `examples/analyst_plan.niva` against the real data headless (the python3.14 + QGIS
  recipe), through the new Task 5 `project` lines, and confirm: outputs valid, `/tmp`
  flat (scratch fix holds), the repointed `.qgs` projects open and resolve to the clips.
  This is a verification/ops task, not a feature.
