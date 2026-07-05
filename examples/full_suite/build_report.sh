#!/usr/bin/env bash
# =============================================================================
# full_suite / build_report.sh — render the scientific report to PDF (with figures)
# -----------------------------------------------------------------------------
# The "outside niva" render step (niva has no `report` verb). Turns the authored
# Markdown report + the figures produced by stages 01–08 into a paginated PDF.
#
# INPUT : outputs/report/youngstown_hydrologic_assessment.md  (fill report_template.md
#         with results first; if that file is absent, the template itself is rendered).
# FIGS  : outputs/figures/*.png  (referenced by relative path in the Markdown).
# OUTPUT: outputs/report/youngstown_hydrologic_assessment.pdf
#
# NEEDS : pandoc + a PDF engine (xelatex / tectonic / wkhtmltopdf). Same toolchain
#         as scripts/build_guide_pdf.py.
# USAGE : bash build_report.sh            # from examples/full_suite/
# =============================================================================
set -euo pipefail
cd "$(dirname "$0")"

SRC="outputs/report/youngstown_hydrologic_assessment.md"
[ -f "$SRC" ] || SRC="report_template.md"   # fall back to the template
OUT="outputs/report/youngstown_hydrologic_assessment.pdf"
mkdir -p outputs/report

command -v pandoc >/dev/null || { echo "ERROR: pandoc not found (install pandoc + a LaTeX engine)"; exit 1; }

# Pick an available PDF engine.
ENGINE=""
for e in xelatex tectonic pdflatex wkhtmltopdf; do command -v "$e" >/dev/null && { ENGINE="$e"; break; }; done
[ -n "$ENGINE" ] || { echo "ERROR: no PDF engine (install one of: tectonic, xelatex, wkhtmltopdf)"; exit 1; }

echo "Rendering $SRC → $OUT  (engine: $ENGINE)"
# --resource-path lets the relative outputs/figures/*.png references resolve.
pandoc "$SRC" \
  --from=gfm \
  --pdf-engine="$ENGINE" \
  --resource-path=".:outputs:outputs/figures" \
  --toc --number-sections \
  -V geometry:margin=1in \
  -o "$OUT"

echo "Done → $OUT"
