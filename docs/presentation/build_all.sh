#!/usr/bin/env bash
# Rebuild the whole niva pitch deck from source. Safe to re-run after manual edits.
#
#   ./build_all.sh            # graphics + PPTX + Marp (HTML always; PDF if a browser is found)
#
# Outputs (all in presentation/):
#   graphics/png/*.png        rendered from graphics/*.svg
#   niva_pitch.pptx           the PowerPoint deck (python-pptx)
#   marp/niva_pitch.html      the Marp deck (web)
#   marp/niva_pitch.pdf       the Marp deck (PDF) — only if Chrome/Chromium is available
#
# Requires: rsvg-convert, uv (for python-pptx), npx/node (for Marp).
set -euo pipefail
cd "$(dirname "$0")"

echo "1/3 · graphics (SVG → PNG)"
./render_graphics.sh

echo "2/3 · PowerPoint (python-pptx)"
uv run --no-project --with python-pptx python build_deck.py

echo "3/3 · Marp deck"
MARP=(npx -y @marp-team/marp-cli@latest)
"${MARP[@]}" marp/niva_pitch.md --theme-set marp/niva-theme.css \
  --allow-local-files -o marp/niva_pitch.html
echo "  wrote marp/niva_pitch.html"
if "${MARP[@]}" marp/niva_pitch.md --theme-set marp/niva-theme.css \
     --allow-local-files --pdf -o marp/niva_pitch.pdf 2>/dev/null; then
  echo "  wrote marp/niva_pitch.pdf"
else
  echo "  (PDF skipped — no Chrome/Chromium found for Marp; HTML is ready)"
fi
echo "done."
