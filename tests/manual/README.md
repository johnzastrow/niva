# Manual tests

Human-in-the-loop checks that can't be automated headless — chiefly the **QGIS
plugin dock** (it needs a live QGIS GUI + `iface`). Screenshots of verified runs are
kept here as a record.

The automated suites cover everything else:
- `scripts/run_tests.sh` — unit tests (incl. PyQGIS smoke tests under QGIS's Python).
- `tests/integration/run.sh` — niva-script integration flows against real data.

| File | What it shows |
|------|---------------|
| `plugin1.png` | the niva dock running in QGIS 4: loads a raster, `assess`, adds the layer to the map, and reports a missing-file error cleanly. |
