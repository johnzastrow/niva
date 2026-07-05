#!/usr/bin/env bash
# =============================================================================
# build_selftest_data.sh — (re)generate the platform_selftest.niva fixtures
# =============================================================================
# AUTHOR-LOCAL. The committed fixtures in examples/selftest_data/ are tiny and
# derived from ONE public-domain USGS 3DEP tile; this script rebuilds them. You
# only need it if you want to change the fixtures — normal users just run
# platform_selftest.niva against the committed copies.
#
# Produces (all EPSG:6346 / NAD83(2011) UTM 17N, ~320 KB total):
#   selftest_data/points.copc.laz  — a 120×120 m LiDAR clip (classes incl. 2=ground)
#   selftest_data/dem.tif          — a 2 m gap-filled DSM from that clip
#   selftest_data/area.gpkg        — a polygon over the clip extent
#
# NEEDS: pdal + gdal on PATH (e.g. the conda env from docs/guide/pdal-setup.md),
#        and a source LiDAR tile. Override SRC_TILE for your own data.
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"
OUT="selftest_data"
SRC_TILE="${SRC_TILE:-$HOME/Downloads/17TPH585925.las}"   # public-domain USGS 3DEP
mkdir -p "$OUT"

echo "1/3 · clip + decimate the point cloud → $OUT/points.copc.laz"
pdal pipeline /dev/stdin <<JSON
[ {"type":"readers.las","filename":"$SRC_TILE"},
  {"type":"filters.crop","bounds":"([659560,659680],[4792560,4792680])"},
  {"type":"filters.decimation","step":4},
  {"type":"writers.copc","filename":"$OUT/points.copc.laz","forward":"all"} ]
JSON

echo "2/3 · 2 m gap-filled DEM (DSM) → $OUT/dem.tif"
pdal translate "$OUT/points.copc.laz" /tmp/_dsm.tif \
  --writers.gdal.resolution=2 --writers.gdal.output_type=idw --writers.gdal.dimension=Z
if command -v gdal_fillnodata.py >/dev/null 2>&1; then
  gdal_fillnodata.py /tmp/_dsm.tif "$OUT/dem.tif"
else
  gdal_fillnodata /tmp/_dsm.tif "$OUT/dem.tif"
fi

echo "3/3 · polygon over the extent → $OUT/area.gpkg"
ogr2ogr -f GPKG -a_srs EPSG:6346 "$OUT/area.gpkg" /dev/stdin <<'JSON'
{"type":"FeatureCollection","name":"area",
 "crs":{"type":"name","properties":{"name":"urn:ogc:def:crs:EPSG::6346"}},
 "features":[{"type":"Feature","properties":{"name":"selftest_area"},
   "geometry":{"type":"Polygon","coordinates":[[[659560,4792560],[659680,4792560],
     [659680,4792680],[659560,4792680],[659560,4792560]]]}}]}
JSON

echo "done → $OUT/  (points.copc.laz · dem.tif · area.gpkg)"
