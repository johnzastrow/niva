# Heavier / real-world data for the niva tests

The suites run out-of-the-box on **generated** data ([`make_bigdata.py`](make_bigdata.py),
[`make_data.py`](make_data.py)) and **committed** data (`examples/*.geojson`, `*.kmz`) — no
network needed. To push harder on **real-world data** (irregular geometry, dense vertices, true
raster size, a wide mix of formats), fetch public datasets and point a flow at them.

## One command — a good mix of formats

[`fetch_testdata.sh`](fetch_testdata.sh) downloads a curated, no-auth set into `data/downloaded/`
(gitignored), covering **Shapefile · GeoJSON · GeoPackage · OSM PBF · GeoTIFF · FileGeodatabase ·
KML · CSV point data · JPEG2000** (plus the committed KMZ). The CSV gets a generated `.vrt` sidecar
so its lon/lat columns load as points (`load …/usgs_earthquakes.vrt`). All URLs are verified direct
downloads drawn from [`free_geospatial_data_report.md`](free_geospatial_data_report.md).

```bash
sh examples/fetch_testdata.sh          # SMALL (~35 MB): Natural Earth + geo-countries + TIGER Maine
sh examples/fetch_testdata.sh big      # + BIG  (~+800 MB): TIGER roads, GADM gpkg, OSM PBF, USGS DEM
```

Then, e.g.:

```bash
niva 'load "data/downloaded/ne_10m_admin_0_countries.shp" | reproject EPSG:3857 | buffer 50000m | save /tmp/ne.gpkg'
niva 'load "data/downloaded/gadm41_USA.gpkg|layername=ADM_ADM_2" | simplify 100 | save /tmp/us.gpkg'
niva 'load "data/downloaded/usgs_13_n44w072.tif" | warp EPSG:3857 | slope | save /tmp/slope.tif'
niva 'load "data/downloaded/vermont.osm.pbf|layername=lines" | fixgeom | save /tmp/vt.gpkg'
```

## The catalog

[`free_geospatial_data_report.md`](free_geospatial_data_report.md) is the full catalog of free,
`wget`-able sources (Natural Earth, TIGER/Line, Geofabrik OSM, GADM, NOAA GLOBE, USGS 3DEP,
OpenTopography, state portals, …) with format and size notes. The most automation-friendly
direct-download families — and what each is good for in a niva flow:

| Source | Format | Geometry | Good for stressing |
|---|---|---|---|
| Natural Earth 1:10m | Shapefile ZIP | polygon / line / point | reproject, buffer, dissolve (global, small) |
| TIGER/Line 2022 | Shapefile ZIP | polygon / line | real dense US admin + roads |
| `datasets/geo-countries` | GeoJSON | polygon | one large text-format file (parse cost) |
| GADM 4.1 | GeoPackage | polygon (multi-level) | multi-layer GPKG, deep admin hierarchy |
| Geofabrik OSM | OSM PBF / SHP ZIP | mixed | the heaviest realistic vector load |
| USGS 3DEP / Copernicus | GeoTIFF (COG) | raster | warp / slope / aspect / hillshade at scale |
| NOAA GLOBE | raster tile ZIP | raster | global elevation tiles |
| USFS EDW | FileGeodatabase (.gdb) | polygon | a raw `.gdb` → geoprocess → load into stores |
| Google KML samples | KML | mixed | raw KML parsing |
| USGS earthquakes feed | CSV (+ `.vrt`) | point | lon/lat CSV point data → points |
| GDAL sample / NAIP | JPEG2000 (.jp2) | raster | raw JP2 → warp / slope |

The [format-matrix suite](format_matrix_suite.niva) exercises the last four (FileGeodatabase, KML,
CSV point data, JPEG2000) end to end: load the raw file → geoprocess → write into GeoPackage /
SpatiaLite / Shapefile / PostGIS → geoprocess again in each store.

> Downloads are **optional** and **never committed** — `data/` is gitignored. The suites stay
> fully runnable from a bare clone using only generated + committed data.

## Rebuilding the heavy `data/` from a backup

If you have a `data.zip` backup of a full `data/` directory (the real heavy datasets — not
committed, ~1.6 GB), rebuild it with `unzip data.zip` at the repo root. This is a convenience for
machines that already have the backup; the canonical, portable path is the generators above.
