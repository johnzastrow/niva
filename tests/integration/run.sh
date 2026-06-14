#!/usr/bin/env bash
# niva integration test — the tests ARE niva scripts (tests/integration/flows/*.niva),
# run through the real `niva run` CLI against real GIS data, and verified by grepping
# the `assess` reports that niva itself produces. Dogfoods the whole language.
#
# Non-destructive: sources are only read; every output goes to a temp dir.
#
# Usage:   tests/integration/run.sh
# Config (env, all optional):
#   NIVA_PYTHON            python interpreter   (default: /usr/bin/python3)
#   NIVA_QGIS_PYTHONPATH   QGIS bindings dir    (default: /usr/share/qgis/python)
#   NIVA_TEST_GPKG         example GeoPackage   (default: marimo_qgis example)
#   NIVA_TEST_SHP          example shapefile    (default: marimo_qgis example)
#
# Exits 0 on success (or a clean SKIP when QGIS / data is absent), 1 on a failed check.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYBIN="${NIVA_PYTHON:-/usr/bin/python3}"
QGIS_PY="${NIVA_QGIS_PYTHONPATH:-/usr/share/qgis/python}"
GPKG="${NIVA_TEST_GPKG:-/home/jcz/Github/marimo_qgis/example/example.gpkg}"
SHP="${NIVA_TEST_SHP:-/home/jcz/Github/marimo_qgis/example/wandering_cat.shp}"

if ! PYTHONPATH="$QGIS_PY" "$PYBIN" -c "import qgis.core" >/dev/null 2>&1; then
  echo "SKIP  integration: QGIS not importable (set NIVA_QGIS_PYTHONPATH)"; exit 0
fi
if [ ! -f "$GPKG" ] || [ ! -f "$SHP" ]; then
  echo "SKIP  integration: test data not found ($GPKG / $SHP)"; exit 0
fi

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FLOWDIR="$TMP/flows"; OUT="$TMP/out"; mkdir -p "$FLOWDIR" "$OUT"
# Substitute data/output paths into every flow (so call targets resolve in FLOWDIR).
for f in "$REPO_ROOT"/tests/integration/flows/*.niva; do
  sed -e "s|@@GPKG@@|$GPKG|g" -e "s|@@SHP@@|$SHP|g" -e "s|@@OUT@@|$OUT|g" \
      "$f" > "$FLOWDIR/$(basename "$f")"
done

PASS=0; FAIL=0
ok()  { echo "PASS  $1"; PASS=$((PASS+1)); }
bad() { echo "FAIL  $1${2:+  — $2}"; FAIL=$((FAIL+1)); }
niva() { PYTHONPATH="$QGIS_PY:$REPO_ROOT" "$PYBIN" -m niva.cli.main "$@"; }

run_flow() {  # <flow.niva> <expected-exit>
  niva run "$FLOWDIR/$1" >"$TMP/$1.out" 2>"$TMP/$1.err" && rc=0 || rc=$?
  if [ "$rc" = "$2" ]; then ok "run $1 (exit $rc)"
  else bad "run $1 (exit $rc, expected $2)" "$(tail -1 "$TMP/$1.err")"; fi
}
in_report() {  # <report.md> <substring> <label>
  if grep -qF -- "$2" "$OUT/$1"; then ok "$3"; else bad "$3" "missing '$2' in $1"; fi
}
in_stderr() {  # <flow.niva> <substring> <label>
  if grep -qiF -- "$2" "$TMP/$1.err"; then ok "$3"; else bad "$3" "no '$2' on stderr"; fi
}

echo "niva integration  (python=$PYBIN, qgis=$QGIS_PY)"; echo

run_flow 01_assess_parcels.niva 0
in_report 01_parcels.md "## Quality checks"          "01 assess deep: quality checks"
in_report 01_parcels.md "**Duplicate geometries:**"  "01 assess deep: topology (duplicates)"

run_flow 02_degrees_guard.niva 2                      # must fail loud
in_stderr 02_degrees_guard.niva "degrees"            "02 degrees guard: rejected metric buffer on 4326"

run_flow 03_reproject_buffer.niva 0
in_report 03_buf.md "**Features:** 1"                 "03 reproject+buffer+dissolve -> 1 feature"
in_report 03_buf.md "Polygon"                         "03 buffer output is polygonal"

run_flow 04_clip.niva 0
in_report 04_clip.md "**Features:** 497"              "04 clip by overlay -> 497 features"

run_flow 05_metadata_lineage.niva 0
in_report 05_gnis.md "**Title:** GNIS names"          "05 metadata title round-trips (via assess)"
in_report 05_gnis.md "metadata set title"            "05 auto-lineage recorded (via assess)"

run_flow 06_run_centroids.niva 0
in_report 06_cent.md "**Features:** 37"               "06 run native:centroids -> 37 points"
in_report 06_cent.md "Point"                          "06 centroids are points"

run_flow 07_cat_territory.niva 0                       # uses `call` composition
in_report 07_territory.md "**Features:** 1"           "07 call-composed cat territory -> 1 polygon"
in_report 07_territory.md "**Title:** Wandering cat territory"  "07 territory carries metadata"

echo; echo "$PASS/$((PASS+FAIL)) checks passed"
[ "$FAIL" -eq 0 ]
