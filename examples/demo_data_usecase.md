# Use case — build niva's demonstration dataset, with niva

**Analyst objective.** Assemble a tidy, self-contained body of geospatial data under
`examples/demo/` that exercises every section of the [Cookbook](../docs/guide/cookbook.md) —
vectors, rasters, point clouds, tables, two database flavours, a project, and a style — and
produce it **using niva itself**. The build is recursive: a `.niva` flow file is the tool that
manufactures niva's own demo data, so the dataset doubles as a worked example of niva at scale.

## Study area & sources

- **Study area:** the **AOISM** polygon (Youngstown, NY) — a ~5 × 4.6 km area in **EPSG:6346**
  (NAD83(2011) / UTM 17N), the project's working CRS.
- **Vector source:** [`examples/example.gpkg`](example.gpkg) — a 25-layer Youngstown
  GeoPackage (parcels, buildings, streets, hydrography, points of interest, the AOISM/AOI
  boundaries, …).
- **Raster source:** `~/Downloads/ytown_dem.tif` — a 1 m DEM covering the area.
- **Point-cloud source:** `~/Downloads/17TPH*.las` — USGS LiDAR tiles; seven overlap AOISM.
- **Database target:** a PostGIS instance reachable as user `jcz`, schema `testing`.

## Data-role → asset map

Most **vector roles the cookbook needs are already in `example.gpkg`**; the build's job is to
shape them into clean, study-area, single-CRS demo assets and to manufacture the **rasters,
tables, point cloud, and databases** that aren't there. Each asset below notes the cookbook
sections it feeds.

**All demo vectors live in one GeoPackage — `demo.gpkg`** — as named layers. Every source
layer (reprojected to EPSG:6346); `parcels` enhanced with a synthetic `zoning`; `ny_ytown_streets`
with a synthetic `class`; friendly aliases `roads`/`buildings`/`aoi`/`points`/`watersheds`; and a
derived `floodzone`. Address a layer as `demo.gpkg|layername=<name>`.

| Asset (under `examples/demo/`) | Built from | Feeds cookbook |
|---|---|---|
| `demo.gpkg \| aoi` | `AOISM` | clip masks (§A, B, raster clips) |
| `demo.gpkg \| roads` (synthetic `class`) | `ny_ytown_streets` | filter, network, SQL `class='primary'` |
| `demo.gpkg \| parcels` (synthetic `zoning`) | `parcels` | filter, dissolve, SQL `GROUP BY zoning` |
| `demo.gpkg \| buildings` | `ny_ytown_buildings` | difference, footprints |
| `demo.gpkg \| points` | `gnis` | clustering, count-in-polygon, hub lines |
| `demo.gpkg \| watersheds` | `nhdplus_catchment` | zonalstats zones |
| `demo.gpkg \| floodzone` | buffered `nhd_flowlines` | intersect / selectloc / ST_Intersects |
| `demo.gpkg` (31 layers) | `each example.gpkg` + enhancements | `each <container>` batch (§E) |
| `dem.tif` (10 m, AOISM) | `ytown_dem.tif` | warp, clipraster, hillshade, slope, aspect, zonalstats, contour, GRASS terrain |
| `hillshade.tif` / `slope.tif` / `aspect.tif` | `dem.tif` | raster derivatives (§F) |
| `cost_surface.tif` | `dem.tif` (slope) | `grass:r.cost` |
| `landcover.tif` (categorical) | rasterised `nhdplus_catchment` | `polygonize` |
| `gappy.tif` (NoData hole) | donut-clipped `dem.tif` | `gdal:fillnodata` |
| `targets.tif` (burned streams) | rasterised `nhd_flowlines` | `gdal:proximity` |
| `census.csv` (synthetic pop/income) | `nhdplus_catchment` | attribute `join` (§C) |
| `owners.csv` | `parcels` | attribute `join` |
| `youngstown.sqlite` (parcels/roads/points/zones) | demo vectors | **SpatiaLite SQL §G** (`@sl`) |
| `youngstown.qgs` + `house.qml` | demo layers / roads | `project`/`style` (§I) |
| `lidar.laz` + `lidar_dem.tif` | `17TPH*.las` | **PDAL §K** |
| PostGIS `testing.{roads,parcels,flood,points}` | demo vectors | **PostGIS SQL §H** (`@pg`) |

## Build plan

Three flow files, by input/credential domain:

1. **[`build_demo_data.niva`](build_demo_data.niva)** — the file-based core (Tasks 1–7):
   themed vectors with synthetic columns, per-layer explosion (`each`), a 10 m DEM clipped to
   AOISM plus its derivatives, the categorical/NoData/target rasters, the join CSVs, the
   SpatiaLite database, the project + style, and a `catalog` inventory of the result. Runs
   anywhere QGIS is available; the rasters are downsampled to 10 m so the committed products
   stay small (each < 0.5 MB).
2. **[`build_demo_lidar.niva`](build_demo_lidar.niva)** — merges the seven AOISM-overlapping
   LiDAR tiles, clips to AOISM, and exports a DEM, via `run pdal:*`. **Run where QGIS has
   working PDAL point-cloud support** (and confirm the tiles' CRS first).
3. **[`build_demo_postgis.niva`](build_demo_postgis.niva)** — loads the demo vectors into the
   `testing` schema. **Set the `@conn` name to your saved PostGIS connection first** (the
   account needs CREATE on `testing`).

### Notes on method (what this build taught)

- **Synthetic columns** are added with `run native:fieldcalculator` — a CASE expression for
  `roads.class`/`parcels.zoning`, `rand()` for `census.pop`/`income`. (In `run`, `FIELD_TYPE`
  takes its integer index: `2` = Text, `1` = Integer.)
- **A NoData raster** (`gappy.tif`) is made the pure-niva way: build a donut (AOISM minus a
  buffered centroid) and `clipraster` the DEM with it.
- The build surfaced and fixed a real niva bug: **`save` now creates its parent directory**
  (previously only `catalog`/`project`/`assess` did), so a fresh output tree just works.

## Running it

```bash
NIVA_TMPDIR=$HOME/niva_scratch \
PYTHONPATH=$PWD:/usr/lib/python3/dist-packages:/usr/share/qgis/python \
QT_QPA_PLATFORM=offscreen python3.14 -c \
  "import niva; niva.run_file('examples/build_demo_data.niva')"
```

The result is inventoried in `examples/demo/catalog.md`. With `examples/demo/` populated, the
cookbook recipes run against it directly (point `@sl`/`@pg` at the SpatiaLite file and your
PostGIS connection). Verifying that mapping end to end is the next step.
