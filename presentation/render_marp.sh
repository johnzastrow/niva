#!/usr/bin/env bash
# Render the Marp deck (marp/niva_pitch.md) to PDF and HTML.
# Requires node/npx; the PDF step needs a Chrome/Chromium (Marp uses it headless).
#
#   ./render_marp.sh           # -> marp/niva_pitch.pdf and marp/niva_pitch.html
#
# If PDF fails with "could not find Chrome", set CHROME_PATH to your browser, e.g.:
#   CHROME_PATH=/usr/bin/google-chrome ./render_marp.sh
set -euo pipefail
cd "$(dirname "$0")"

MARP=(npx -y @marp-team/marp-cli@latest)
COMMON=(marp/niva_pitch.md --theme-set marp/niva-theme.css --allow-local-files)

"${MARP[@]}" "${COMMON[@]}" -o marp/niva_pitch.html
echo "wrote marp/niva_pitch.html"

"${MARP[@]}" "${COMMON[@]}" --pdf -o marp/niva_pitch.pdf
echo "wrote marp/niva_pitch.pdf"
