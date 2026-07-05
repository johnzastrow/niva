# niva examples

Runnable, real-world niva flows you can read to learn the grammar. For the full recipe
collection see the [Cookbook](../docs/guide/cookbook.md); for the **test** suites and fixtures
(which used to live here) see [`tests/suites/`](../tests/suites/) and
[`tests/datagen/`](../tests/datagen/).

## Flows

| File | What it shows |
|---|---|
| [`platform_selftest.niva`](platform_selftest.niva) | **Validate a niva install on any platform.** Exercises every provider — vector (native), raster (gdal), terrain (GRASS), and LiDAR point clouds via **both** `pdalcli:` and `pdal:` — using only shipped `demo/` data (nothing to download). Run the whole check, base CLI utilities included, with [`platform_selftest.sh`](platform_selftest.sh) (`niva pdal check` → `pdal test` → `validate` → `--explain` → `run`). |
| [`analyst_plan.niva`](analyst_plan.niva) | An end-to-end analyst workflow — load → reproject → clip/overlay → assess → save deliverables. Narrated in [`analyst_plan.md`](analyst_plan.md). |
| [`youngstown_cat_canvassing.niva`](youngstown_cat_canvassing.niva) | A worked municipal use case (canvassing) chaining many verbs over real local data. |
| [`build_demo_data.niva`](build_demo_data.niva) | Author-local build script: assembles the consolidated demo GeoPackage under `demo/` from `data/example.gpkg`. |
| [`build_demo_lidar.niva`](build_demo_lidar.niva) | Author-local: builds the demo LiDAR (`.laz` + DEM) via the `pdal:` algorithms. |
| [`build_demo_postgis.niva`](build_demo_postgis.niva) | Author-local: pushes the demo layers into a PostGIS connection (`@pg`). |

> The `build_demo_*` flows are **author-local** (absolute `~/Github/niva/...` paths) — they
> regenerate the demo dataset, not something you run as a tutorial. The first two flows are the
> ones to read.

## Data

- [`data/example.gpkg`](data/) — the multi-layer Youngstown GeoPackage the example flows load
  (also the seed `tests/datagen/make_data.py` builds the machine-local `data/` test dir from).
- [`data/layout_template.qpt`](data/) — a QGIS print-layout template (the default for the planned
  `figure` verb; see [`TODO.md`](../TODO.md)).
- `demo/`, `demo.zip` — the generated demo dataset (gitignored; produced by `build_demo_data.niva`,
  shipped as a release asset). See [`demo_data_usecase.md`](demo_data_usecase.md).

## Running a flow

Under QGIS's Python (see the [User Guide](../docs/guide/user-guide.md) for the exact env):

```bash
niva run examples/analyst_plan.niva           # run a file
niva "load examples/data/example.gpkg | show" # or an inline flow
```
