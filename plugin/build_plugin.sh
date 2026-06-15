#!/usr/bin/env bash
# Build the niva QGIS plugin zip.
#
# Vendors the zero-dependency niva package into the plugin (libs/niva) so the plugin
# installs and runs on Windows / macOS / Linux with NO pip step. The zip's top-level
# folder is `niva_qgis` (NOT `niva`, which would shadow the vendored package).
#
# Usage: plugin/build_plugin.sh   →   plugin/niva_qgis.zip
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # plugin/
ROOT="$(cd "$HERE/.." && pwd)"                          # repo root
NAME="niva_qgis"
WORK="$(mktemp -d)"
STAGE="$WORK/$NAME"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$STAGE/libs"
for f in __init__.py plugin.py dock.py runner.py flowtask.py environment.py metadata.txt icon.svg README.md; do
  [ -f "$HERE/$f" ] && cp "$HERE/$f" "$STAGE/$f"
done

# Vendor the niva package (pure Python, zero deps).
cp -r "$ROOT/niva" "$STAGE/libs/niva"
find "$STAGE" -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -name '*.pyc' -delete 2>/dev/null || true

OUT="$HERE/$NAME.zip"
rm -f "$OUT"
( cd "$WORK" && zip -qr "$OUT" "$NAME" )
echo "built $OUT"
unzip -l "$OUT" | awk 'NR==1||/niva_qgis\/(metadata|__init__|plugin|dock|runner)|libs\/niva\/(__init__|engine\/pyqgis)/'
