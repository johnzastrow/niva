#!/usr/bin/env sh
# Fetch a MIX of free, no-auth, real-world geospatial data to push niva's tests harder.
#
# Sources are drawn from examples/free_geospatial_data_report.md (direct-download URLs verified
# 2026-06-22). Nothing here is committed to the repo — files land in data/downloaded/ (gitignored)
# so a clone stays small; the suites still run fully on generated + committed data without this.
#
#   sh examples/fetch_testdata.sh            # SMALL tier (~35 MB): quick, automation-friendly
#   sh examples/fetch_testdata.sh big        # + BIG tier (~+800 MB): heavy real data, slow
#   sh examples/fetch_testdata.sh all        # everything
#
# Idempotent: an already-present, non-empty file is skipped. Uses wget (resume with -c) or curl.
# After fetching, point a flow at a file, e.g.:
#   niva 'load "data/downloaded/ne_10m_admin_0_countries.shp" | reproject EPSG:3857 \
#         | buffer 50000m | save /tmp/ne_buf.gpkg'
set -eu

DEST="$(cd "$(dirname "$0")/.." && pwd)/data/downloaded"
mkdir -p "$DEST"
TIER="${1:-small}"

# dl <url> <outfile> — download into $DEST/<outfile> unless it already exists non-empty.
dl() {
  url="$1"; out="$DEST/$2"
  if [ -s "$out" ]; then echo "  ✓ have $2"; return 0; fi
  echo "  ↓ $2"
  if command -v wget >/dev/null 2>&1; then
    wget -q -c -O "$out.part" "$url" && mv "$out.part" "$out"
  else
    curl -fL -C - -o "$out.part" "$url" && mv "$out.part" "$out"
  fi
}

# unzip_into <zipfile> — extract a shapefile/gpkg ZIP in place (then keep the zip for caching).
unzip_into() {
  z="$DEST/$1"
  [ -s "$z" ] || return 0
  if command -v unzip >/dev/null 2>&1; then unzip -o -q -d "$DEST" "$z"; fi
}

fetch_small() {
  echo "SMALL tier → $DEST"
  # Natural Earth 1:10m (Shapefile ZIP) — global polygons / lines / points
  dl "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_admin_0_countries.zip" ne_admin0.zip
  dl "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_roads.zip"             ne_roads.zip
  dl "https://naciscdn.org/naturalearth/10m/cultural/ne_10m_populated_places.zip"  ne_places.zip
  unzip_into ne_admin0.zip; unzip_into ne_roads.zip; unzip_into ne_places.zip
  # GeoJSON — world country polygons (one big file, dense rings)
  dl "https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson" countries.geojson
  # TIGER/Line 2022 (Shapefile ZIP) — real US admin vectors (Maine)
  dl "https://www2.census.gov/geo/tiger/TIGER2022/PLACE/tl_2022_23_place.zip" tl_2022_23_place.zip
  dl "https://www2.census.gov/geo/tiger/TIGER2022/TRACT/tl_2022_23_tract.zip" tl_2022_23_tract.zip
  unzip_into tl_2022_23_place.zip; unzip_into tl_2022_23_tract.zip
  fetch_formats
}

# The extra formats the format-matrix suite exercises on real data: FileGeodatabase, KML,
# CSV point data (+ a generated .vrt so lon/lat columns load as points), and JPEG2000.
fetch_formats() {
  # FileGeodatabase (zipped .gdb) — USFS Administrative Forest boundaries (~20 MB)
  dl "https://data.fs.usda.gov/geodata/edw/edw_resources/fc/S_USA.AdministrativeForest.gdb.zip" usfs_admin_forest.gdb.zip
  unzip_into usfs_admin_forest.gdb.zip
  # KML — Google's KML sample document (points, lines, polygons)
  dl "https://developers.google.com/kml/documentation/KML_Samples.kml" kml_samples.kml
  # CSV point data — USGS earthquakes, past 30 days (longitude/latitude columns)
  dl "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_month.csv" usgs_earthquakes.csv
  # …with an OGR .vrt sidecar so niva loads it as POINTS (load the .vrt, not the .csv):
  if [ -s "$DEST/usgs_earthquakes.csv" ] && [ ! -s "$DEST/usgs_earthquakes.vrt" ]; then
    cat > "$DEST/usgs_earthquakes.vrt" <<'VRT'
<OGRVRTDataSource>
  <OGRVRTLayer name="usgs_earthquakes">
    <SrcDataSource relativeToVRT="1">usgs_earthquakes.csv</SrcDataSource>
    <GeometryType>wkbPoint</GeometryType>
    <LayerSRS>EPSG:4326</LayerSRS>
    <GeometryField encoding="PointFromColumns" x="longitude" y="latitude"/>
  </OGRVRTLayer>
</OGRVRTDataSource>
VRT
    echo "  + wrote usgs_earthquakes.vrt (loads the CSV as points)"
  fi
  # JPEG2000 — a small georeferenced JP2 (GDAL sample). For a heavier JP2, see bigdata_urls.md.
  dl "https://github.com/OSGeo/gdal/raw/master/autotest/gdrivers/data/jpeg2000/byte.jp2" sample.jp2
}

fetch_big() {
  echo "BIG tier → $DEST  (hundreds of MB — slow)"
  # TIGER national primary roads (Shapefile ZIP) — dense lines (~38 MB)
  dl "https://www2.census.gov/geo/tiger/TIGER2022/PRIMARYROADS/tl_2022_us_primaryroads.zip" tl_2022_us_primaryroads.zip
  unzip_into tl_2022_us_primaryroads.zip
  # GADM 4.1 (GeoPackage, multi-level admin) — real GPKG (~112 MB)
  dl "https://geodata.ucdavis.edu/gadm/gadm4.1/gpkg/gadm41_USA.gpkg" gadm41_USA.gpkg
  # Geofabrik OSM (PBF, mixed geometry) — a whole small state (~45 MB)
  dl "https://download.geofabrik.de/north-america/us/vermont-latest.osm.pbf" vermont.osm.pbf
  # Geofabrik OSM themed Shapefiles (ZIP) — heavy real vectors (~168 MB)
  dl "https://download.geofabrik.de/north-america/us/maine-latest-free.shp.zip" maine-free.shp.zip
  # USGS 3DEP 1/3 arc-second DEM (GeoTIFF, COG) — heavy real raster (~471 MB)
  dl "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/n44w072/USGS_13_n44w072.tif" usgs_13_n44w072.tif
}

case "$TIER" in
  small) fetch_small ;;
  big)   fetch_small; fetch_big ;;
  all)   fetch_small; fetch_big ;;
  *) echo "usage: $0 [small|big|all]"; exit 2 ;;
esac

echo "done. files in $DEST:"
ls -1 "$DEST" | sed 's/^/  /'
echo
echo "Types fetched: Shapefile · GeoJSON · GeoPackage · OSM PBF · GeoTIFF (+ the committed KMZ in examples/)."
echo "Point niva at any of them via data/downloaded/<file>. See examples/bigdata_urls.md for ideas."
