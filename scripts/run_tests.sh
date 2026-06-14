#!/usr/bin/env bash
# Run the niva unit suite. Tries QGIS's Python first (so the PyQGIS smoke tests run
# too); the suite is designed to skip those cleanly on a plain interpreter.
#
# Usage:   scripts/run_tests.sh
# Config (env, optional):
#   NIVA_PYTHON            python interpreter   (default: /usr/bin/python3)
#   NIVA_QGIS_PYTHONPATH   QGIS bindings dir    (default: /usr/share/qgis/python)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYBIN="${NIVA_PYTHON:-/usr/bin/python3}"
QGIS_PY="${NIVA_QGIS_PYTHONPATH:-/usr/share/qgis/python}"

cd "$REPO_ROOT"

if PYTHONPATH="$QGIS_PY" "$PYBIN" -c "import qgis.core" >/dev/null 2>&1; then
  echo "== unit tests on QGIS's Python (incl. PyQGIS smoke tests) =="
  # The unittest process owns a QgsApplication and segfaults during interpreter
  # shutdown AFTER printing its result — which would clobber the exit code. So we
  # determine pass/fail from unittest's own "OK"/"FAILED" line, not the exit code.
  out="$(PYTHONPATH="$QGIS_PY" "$PYBIN" -m unittest discover -s tests -t . 2>&1 || true)"
  echo "$out" | grep -vE "QThreadStorage|Qt bindings|^Warning:" || true
  if echo "$out" | grep -qE "^OK"; then
    exit 0
  elif echo "$out" | grep -qE "^FAILED"; then
    exit 1
  else
    echo "run_tests: could not determine result (crash before unittest finished?)" >&2
    exit 2
  fi
else
  echo "== unit tests on plain Python (PyQGIS smoke tests will skip) =="
  exec "$PYBIN" -m unittest discover -s tests -t .
fi
