#!/usr/bin/env bash
# =============================================================================
# platform_selftest.sh — full niva platform validation (base utilities + flow)
# =============================================================================
# Runs niva's base CLI utilities AND the platform_selftest.niva flow, reporting
# PASS/FAIL per step so a FRESH install on ANY platform gets a complete capability
# report in one shot. Uses only data shipped under examples/demo/ — nothing to
# download. Failures don't cascade: every step runs, so you see exactly what works.
#
# USAGE:   bash platform_selftest.sh          # from examples/
#   Override the niva entrypoint if it isn't on PATH:
#          NIVA="python3 -m niva.cli.main" bash platform_selftest.sh
#
# WINDOWS: run the same five commands from the OSGeo4W shell / PowerShell, or run
# this script under Git Bash or WSL. The commands are identical on every OS:
#     niva pdal check
#     niva pdal test
#     niva validate platform_selftest.niva
#     niva run platform_selftest.niva --explain
#     niva run platform_selftest.niva
#
# The pdal steps need the point-cloud backend ($QGIS_WRENCH_EXECUTABLE) — if they
# FAIL, run `niva pdal setup` and see docs/guide/pdal-setup.md.
# =============================================================================
set -u
cd "$(dirname "$0")"            # run from examples/, where demo/ lives
NIVA="${NIVA:-niva}"           # entrypoint; override with NIVA="python3 -m niva.cli.main"
FLOW="platform_selftest.niva"

pass=0
fail=0
step() {
  local name="$1"
  shift
  printf '\n──────────── %s ────────────\n' "$name"
  if "$@"; then
    printf '  ✓ PASS — %s\n' "$name"
    pass=$((pass + 1))
  else
    printf '  ✗ FAIL — %s\n' "$name"
    fail=$((fail + 1))
  fi
}

echo "niva platform self-test — base utilities + processing flow"
echo "entrypoint: $NIVA"

# --- base CLI utilities ------------------------------------------------------
step "pdal check   — point-cloud backend present & wired"      $NIVA pdal check
step "pdal test    — wrench grids a cloud end-to-end"          $NIVA pdal test
step "validate     — offline lint of the flow"                 $NIVA validate "$FLOW"
step "explain      — offline plan (no QGIS)"                    $NIVA run "$FLOW" --explain

# --- the processing flow (needs QGIS) ---------------------------------------
step "run          — vector · raster · GRASS · LiDAR (both PDAL paths)" $NIVA run "$FLOW"

printf '\n════════════════════════════════════════\n'
printf '  %d passed, %d failed\n' "$pass" "$fail"
if [ "$fail" -eq 0 ]; then
  printf '  ✓ this platform is fully validated.\n'
else
  printf '  See the failing step(s) above; for pdal: `niva pdal setup`.\n'
fi
[ "$fail" -eq 0 ]
