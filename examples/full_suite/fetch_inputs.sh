#!/usr/bin/env bash
# =============================================================================
# full_suite / fetch_inputs.sh  —  ACQUIRE raw primary-source data (OUTSIDE niva)
# -----------------------------------------------------------------------------
# Part of the Youngstown hydrologic assessment (see use_case.md). This is the
# "outside niva" half of Stage 1: it downloads RAW data from primary sources into
# a READ-ONLY inputs/ tree and records provenance (URL, date, sha256). niva's
# 01_acquire.niva then documents (catalog/assess) what landed — the "inside niva"
# half. niva has no `fetch` verb yet (candidate in ../../TODO.md), so downloads
# live here.
#
# DESIGN RULES
#   * Raw is never modified. Files land in inputs/ exactly as the source returns
#     them for the AOI query; all reprojection/clipping for analysis happens later
#     in 02_prepare.niva and writes to derived/ — never back into inputs/.
#   * Every fetch appends a provenance line (source, url, utc date, sha256) to
#     outputs/notes/provenance_inputs.md.
#   * Endpoints marked <CONFIRM> are primary-source portals whose exact per-AOI
#     product URL the analyst pastes in (product URLs rotate); the portal and the
#     query are documented so the fetch is reproducible.
#
# USAGE:   bash fetch_inputs.sh              # from examples/full_suite/
# NEEDS:   curl, gdal (gdalinfo/gdal_translate/ogr2ogr), sha256sum. Network.
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
IN="$ROOT/inputs"
NOTES="$ROOT/outputs/notes"
PROV="$NOTES/provenance_inputs.md"
# AOI bbox in EPSG:6346 (from examples/demo aoi) — used to subset national data.
# xmin ymin xmax ymax (meters). Refine from derived/aoi_6346.gpkg once built.
AOI_BBOX_6346="656891 4788563 661956 4793208"
# AOI bbox in EPSG:4326 (lon/lat, WGS84) for REST queries — xmin,ymin,xmax,ymax.
AOI_BBOX_4326="-79.067,43.233,-79.005,43.275"

mkdir -p "$IN"/{lidar,ortho_2024,ortho_hist,nlcd,huc12} "$NOTES"
[ -f "$PROV" ] || printf '# Input provenance — raw primary sources\n\n| dataset | source | url | fetched (UTC) | sha256 |\n|---|---|---|---|---|\n' > "$PROV"

log_prov() { # dataset source url file
  local sha; sha="$( [ -f "$4" ] && sha256sum "$4" | cut -d' ' -f1 || echo n/a )"
  # NOTE: pass a fixed timestamp in CI; `date -u` is fine for an interactive run.
  printf '| %s | %s | %s | %s | `%s` |\n' "$1" "$2" "$3" "$(date -u +%FT%TZ)" "$sha" >> "$PROV"
}

echo "== 1/5  Present imagery — 2024 4-band (R,G,B,NIR) ortho (already local) =="
# Copy the local 2024 ortho verbatim into inputs/ (raw, read-only afterward).
SRC_ORTHO="$HOME/Downloads/twn_Porter_sp24"
if [ -d "$SRC_ORTHO" ]; then
  cp -n "$SRC_ORTHO/porter_ortho.jp2" "$IN/ortho_2024/" 2>/dev/null || true
  # (Optionally copy the 202 tiles; the merged mosaic is enough for the study.)
  log_prov "ortho_2024 (RGB+NIR, 1ft)" "NYS GIS 2024 / local" "file://$SRC_ORTHO/porter_ortho.jp2" "$IN/ortho_2024/porter_ortho.jp2"
else
  echo "  !! $SRC_ORTHO not found — set SRC_ORTHO or place the 2024 ortho manually."
fi

echo "== 2/5  LiDAR — USGS 3DEP (fetch ALL coverage for the AOI) =="
# Two real, reproducible routes (needs PDAL for the EPT route). Discover the NY
# project(s) covering Youngstown from the entwine index (resolves): usgs.entwine.io
# ROUTE A — Entwine Point Tiles (AWS), AOI-clipped by PDAL (records ALL in-AOI points):
#   for P in <NY_PROJECT_1> <NY_PROJECT_2>; do
#     pdal translate "ept://https://s3-us-west-2.amazonaws.com/usgs-lidar-public/$P/ept.json" \
#       "$IN/lidar/$P.laz" --readers.ept.bounds="([656891,661956],[4788563,4793208])"
#     done                                   # AOI bbox in the EPT CRS (EPSG:6346 here)
# ROUTE B — Staged LPC LAZ tiles direct from rockyweb (resolves; no PDAL needed to fetch):
#   base: https://rockyweb.usgs.gov/vdelivery/Datasets/Staged/Elevation/LPC/Projects/<PROJECT>/<...>/LAZ/
#   curl -sO --output-dir "$IN/lidar" "<TILE_URL>.laz"   # per tile intersecting the AOI
echo "  -> pick the NY 3DEP project(s) over the AOI (usgs.entwine.io), then Route A or B above"

echo "== 3/5  NLCD % Developed Imperviousness — 2001 & 2021 (MRLC WCS) =="
# MRLC GeoServer WCS (live service) — clip the national coverage to the AOI on download.
# NOTE: confirm the exact coverageId + axis labels once via GetCapabilities:
#   curl "https://www.mrlc.gov/geoserver/mrlc_download/wcs?service=WCS&version=2.0.1&request=GetCapabilities"
NLCD_WCS="https://www.mrlc.gov/geoserver/mrlc_download/wcs"
# Coverage is EPSG:5070 with axis labels X/Y → subset in 5070 metres (not lon/lat).
# coverageId form: mrlc_download__NLCD_<YR>_Impervious_L48. VERIFIED (valid GeoTIFF).
read -r NX0 NY0 _z0 < <(printf '%s\n' "-79.067 43.233" | gdaltransform -s_srs EPSG:4326 -t_srs EPSG:5070 2>/dev/null)
read -r NX1 NY1 _z1 < <(printf '%s\n' "-79.005 43.275" | gdaltransform -s_srs EPSG:4326 -t_srs EPSG:5070 2>/dev/null)
for YR in 2001 2021; do
  COV="mrlc_download__NLCD_${YR}_Impervious_L48"
  URL="${NLCD_WCS}?service=WCS&version=2.0.1&request=GetCoverage&coverageId=${COV}&subset=X(${NX0},${NX1})&subset=Y(${NY0},${NY1})&format=image/geotiff"
  curl -s --max-time 180 "$URL" -o "$IN/nlcd/nlcd_impervious_${YR}.tif"
  gdalinfo "$IN/nlcd/nlcd_impervious_${YR}.tif" >/dev/null 2>&1 && echo "  NLCD ${YR}: OK" || echo "  !! NLCD ${YR}: invalid raster — inspect the WCS response"
  log_prov "nlcd_impervious_${YR}" "MRLC NLCD (WCS)" "$URL" "$IN/nlcd/nlcd_impervious_${YR}.tif"
done

echo "== 4/5  WBD HUC12 — USGS Watershed Boundary Dataset (live REST) =="
# HUC12 polygons intersecting the AOI, from the USGS National Map WBD MapServer
# (layer 6 = WBDHU12). Returns GeoJSON in EPSG:4326; 02_prepare reprojects + clips it.
# VERIFIED WORKING for this AOI (returns the Niagara-River-outlet / Fourmile-Creek units).
WBD_URL="https://hydro.nationalmap.gov/arcgis/rest/services/wbd/MapServer/6/query?geometry=${AOI_BBOX_4326}&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=huc12,name,areasqkm&returnGeometry=true&f=geojson"
curl -s --max-time 120 "$WBD_URL" -o "$IN/huc12/wbd_huc12.geojson"
ogr2ogr -f GPKG "$IN/huc12/huc12.gpkg" "$IN/huc12/wbd_huc12.geojson" 2>/dev/null || echo "  !! ogr2ogr failed — check $IN/huc12/wbd_huc12.geojson"
log_prov "huc12" "USGS WBD (National Map REST)" "$WBD_URL" "$IN/huc12/huc12.gpkg"

echo "== 5/5  Historical ortho — oldest NAIP over the AOI (Planetary Computer, public) =="
# NAIP is 4-band (RGB+NIR). Microsoft Planetary Computer serves it publicly (STAC +
# free SAS signing — no account). Fetch the OLDEST tile over the AOI for the 'past'
# epoch (NY NAIP starts ~2011, not 2001 — note this in the report). VERIFIED WORKING.
NAIP_ITEM=$(curl -s --max-time 60 "https://planetarycomputer.microsoft.com/api/stac/v1/search" -H "Content-Type: application/json" -d "{\"collections\":[\"naip\"],\"bbox\":[${AOI_BBOX_4326}],\"limit\":1,\"sortby\":[{\"field\":\"properties.datetime\",\"direction\":\"asc\"}]}")
NAIP_HREF=$(printf '%s' "$NAIP_ITEM" | python3 -c "import json,sys;print(json.load(sys.stdin)['features'][0]['assets']['image']['href'])")
NAIP_DATE=$(printf '%s' "$NAIP_ITEM" | python3 -c "import json,sys;print(json.load(sys.stdin)['features'][0]['properties']['datetime'][:10])")
NAIP_SIGNED=$(curl -s --max-time 40 "https://planetarycomputer.microsoft.com/api/sas/v1/sign?href=${NAIP_HREF}" | python3 -c "import json,sys;print(json.load(sys.stdin)['href'])")
gdal_translate -projwin -79.067 43.275 -79.005 43.233 -projwin_srs EPSG:4326 "/vsicurl/${NAIP_SIGNED}" "$IN/ortho_hist/porter_hist.tif" >/dev/null 2>&1
gdalinfo "$IN/ortho_hist/porter_hist.tif" >/dev/null 2>&1 && echo "  NAIP ${NAIP_DATE}: OK (4-band RGB+NIR)" || echo "  !! NAIP fetch failed"
log_prov "ortho_hist (NAIP ${NAIP_DATE})" "USDA NAIP via Planetary Computer" "$NAIP_HREF" "$IN/ortho_hist/porter_hist.tif"

echo
echo "Done. Raw inputs under: $IN  (treat as READ-ONLY)"
echo "Provenance recorded in:  $PROV"
echo "Next: run  niva run 01_acquire.niva  to document (catalog/assess) the inputs."
