#!/usr/bin/env bash
# Re-render the brand SVGs in graphics/ to high-res PNGs in graphics/png/
# (the PNGs are what the PPTX embeds). Run after editing any .svg.
set -euo pipefail
cd "$(dirname "$0")/graphics"
mkdir -p png
for svg in *.svg; do
  name="${svg%.svg}"
  rsvg-convert -w 2000 "$svg" -o "png/$name.png"
  echo "rendered png/$name.png"
done
