#!/usr/bin/env bash
# niva integration test — run the proven flows against real GIS data, on QGIS's
# own Python. Non-destructive (sources are only read; outputs go to a temp dir).
#
# Usage:   tests/integration/run.sh
# Config (env, all optional):
#   NIVA_PYTHON            python interpreter   (default: /usr/bin/python3)
#   NIVA_QGIS_PYTHONPATH   QGIS bindings dir    (default: /usr/share/qgis/python)
#   NIVA_TEST_GPKG         example GeoPackage   (default: marimo_qgis example)
#   NIVA_TEST_SHP          example shapefile    (default: marimo_qgis example)
#
# Exits 0 on success (or a clean SKIP when QGIS / data is absent), non-zero on a
# failed check.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PYBIN="${NIVA_PYTHON:-/usr/bin/python3}"
QGIS_PY="${NIVA_QGIS_PYTHONPATH:-/usr/share/qgis/python}"

# QGIS is required; skip cleanly (not a failure) if it is not importable.
if ! PYTHONPATH="$QGIS_PY" "$PYBIN" -c "import qgis.core" >/dev/null 2>&1; then
  echo "SKIP  integration: QGIS not importable with PYTHONPATH=$QGIS_PY"
  echo "      set NIVA_QGIS_PYTHONPATH to your QGIS bindings dir to run it."
  exit 0
fi

echo "niva integration test  (python=$PYBIN, qgis=$QGIS_PY)"
# Filter QGIS's benign teardown chatter; preserve the driver's exit code.
PYTHONPATH="$QGIS_PY:$REPO_ROOT" "$PYBIN" \
  "$REPO_ROOT/tests/integration/integration_flows.py" 2>&1 \
  | grep -vE "QThreadStorage|Qt bindings|^Warning:" || true

exit "${PIPESTATUS[0]}"
