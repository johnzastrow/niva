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
# 3DEP publishes Entwine Point Tiles (EPT) on AWS; PDAL reads EPT directly and
# clips to the AOI — no per-tile download list needed. Discover the resource(s)
# covering Youngstown at the 3DEP LidarExplorer, then record each as raw LAZ:
#   portal: https://apps.nationalmap.gov/lidar-explorer/    <CONFIRM resource id(s)>
#   EPT root (example): https://s3-us-west-2.amazonaws.com/usgs-lidar-public/<PROJECT>/ept.json
# Pull an AOI-clipped LAZ per project via PDAL (records ALL points in-AOI):
#   pdal translate ept://<EPT_URL> "$IN/lidar/<PROJECT>.laz" \
#     --readers.ept.bounds="([656891,661956],[4788563,4793208])"   # AOI in EPT CRS
# (Repeat for every project/vintage that intersects the AOI — "fetch all".)
echo "  -> list 3DEP projects over the AOI, then PDAL-clip each EPT to inputs/lidar/*.laz (see comments)"

echo "== 3/5  NLCD % Developed Imperviousness — 2001 & 2021 (MRLC) =="
# MRLC/USGS national COGs; subset to the AOI bbox on download (raw = AOI subset).
#   portal: https://www.mrlc.gov/data   product: 'NLCD <yr> Developed Imperviousness (CONUS)'
for YR in 2001 2021; do
  URL="<CONFIRM: MRLC NLCD ${YR} impervious COG URL>"
  OUT="$IN/nlcd/nlcd_impervious_${YR}.tif"
  echo "  NLCD ${YR}: gdal_translate -projwin (AOI in the COG CRS) '$URL' '$OUT'"
  # gdal_translate -projwin <ulx uly lrx lry in EPSG:5070> "/vsicurl/$URL" "$OUT"
  # log_prov "nlcd_impervious_${YR}" "MRLC NLCD" "$URL" "$OUT"
done

echo "== 4/5  WBD HUC12 — USGS Watershed Boundary Dataset =="
# HUC12 polygons for the AOI. Pull via the WBD service / TNM, subset to AOI.
#   portal: https://www.usgs.gov/national-hydrography/watershed-boundary-dataset
URL_WBD="<CONFIRM: WBD HUC12 service or TNM download for HU 04130001 (Niagara)>"
echo "  WBD HUC12: ogr2ogr -spat (AOI bbox in WBD CRS) '$IN/huc12/huc12.gpkg' '$URL_WBD'"
# log_prov "huc12" "USGS WBD" "$URL_WBD" "$IN/huc12/huc12.gpkg"

echo "== 5/5  Historical ortho — 'past' epoch (~2001) for change =="
# NAIP (4-band from 2007+) or an older NYS ortho; NAIP is on AWS/EarthExplorer.
#   portal: https://earthexplorer.usgs.gov  (dataset: NAIP)  <CONFIRM year/tile>
URL_HIST="<CONFIRM: historical ortho tile(s) covering the AOI, ~2001>"
echo "  historical ortho: curl -o '$IN/ortho_hist/<tile>.tif' '$URL_HIST'"
# log_prov "ortho_hist" "USGS/USDA NAIP or NYS ortho" "$URL_HIST" "$IN/ortho_hist/<tile>.tif"

echo
echo "Done. Raw inputs under: $IN  (treat as READ-ONLY)"
echo "Provenance recorded in:  $PROV"
echo "Next: run  niva run 01_acquire.niva  to document (catalog/assess) the inputs."
