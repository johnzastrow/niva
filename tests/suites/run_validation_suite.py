#!/usr/bin/env python3
"""Execute tests/suites/validation_suite.niva test-by-test, ASSESS each output, then CLEAN UP.

This is the runner for the niva validation suite — it dogfoods niva across data sources,
targets, processing options, and data types, and (crucially) checks that each output has
*real, non-empty geometry* — the exact assertion that would have caught the load_table
"aspatial layer / empty geometry" bug.

Run under QGIS's Python (it reads the user's real QGIS profile, so `@conn` names resolve):

    PYTHONPATH=<repo>:/usr/share/qgis/python:/usr/lib/python3/dist-packages \
      QT_QPA_PLATFORM=offscreen python3 tests/suites/run_validation_suite.py

Block format in the .niva file (see validation_suite.niva):

    # ===== TEST 07 | raster gpkg->tif | description =====
    <pipeline flow line(s)>                       run in order via niva.flow
    #@out <path|@conn.table> :: <vector|raster|table|file> [>=N]   one or more assertions
    #@cleanup remove <path> [force]               delete a file output via niva's own `remove`
    #@cleanup flow <niva flow>                    run a cleanup flow (e.g. sql … DROP TABLE)

A `# ===== PREAMBLE | … =====` block runs first (environment/data validation).
"""
from __future__ import annotations

import contextlib
import glob
import io
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find the sibling report module
import _suite_report  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Optional positional arg picks the suite (default = suite 1); --emit writes the pure .niva.
_ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SUITE = os.path.abspath(_ARGS[0]) if _ARGS else os.path.join(REPO, "examples", "validation_suite.niva")
# Keep the exact POSIX path (`/tmp/niva_validation`) on Linux/macOS; on Windows (no /tmp) fall
# back to the OS temp dir. The suites embed the literal `/tmp/niva_validation`, so `_subst`
# redirects that prefix to SCRATCH (a no-op on POSIX, where they're identical).
SCRATCH = os.path.join("/tmp" if os.name != "nt" else tempfile.gettempdir(), "niva_validation")
OUT = os.path.join(SCRATCH, "out")
# {data}/{testdata}/{examples} path tokens (see _suite_report.data_tokens), so suites run
# unchanged on any clone. {data} prefers data/ (make_data.py / make_bigdata.py write there).
_TOKENS = _suite_report.data_tokens(REPO)


def _subst(text: str) -> str:
    return _suite_report.subst(text.replace("/tmp/niva_validation", SCRATCH), _TOKENS)

_HDR = re.compile(r"#\s*=+\s*(PREAMBLE|TEST\s+\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*=+\s*$")


def parse(path):
    blocks, cur = [], None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        m = _HDR.match(line)
        if m:
            cur = {"id": m.group(1).strip(), "cat": m.group(2), "desc": m.group(3),
                   "flows": [], "outs": [], "cleanups": []}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if not s:
            continue
        if s.startswith("#@out "):
            cur["outs"].append(s[len("#@out "):].strip())
        elif s.startswith("#@cleanup "):
            cur["cleanups"].append(s[len("#@cleanup "):].strip())
        elif s.startswith("#"):
            continue
        else:
            cur["flows"].append(line)
    return blocks


def niva_flow(text):
    import niva

    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        niva.flow(text)


_assess_seq = 0


def _vector(target):
    """A QgsVectorLayer for a file path or an @conn.table (via niva's own load)."""
    global _assess_seq
    from qgis.core import QgsVectorLayer
    if target.startswith("@"):
        # Use a fresh scratch file per @-assessment. Reusing one name fails on Windows, where the
        # previous assessment's still-open QgsVectorLayer locks the .gpkg and os.remove raises
        # WinError 32 (POSIX allows unlinking an open file, so this only bit on Windows).
        _assess_seq += 1
        tmp = os.path.join(OUT, f"_assess_{_assess_seq}.gpkg")
        for p in glob.glob(tmp + "*"):
            with contextlib.suppress(OSError):
                os.remove(p)
        niva_flow(f'load "{target}" | save "{tmp}"')
        return QgsVectorLayer(tmp, "a", "ogr")
    return QgsVectorLayer(target, "a", "ogr")


def assess(spec):
    from qgis.core import QgsRasterLayer, QgsWkbTypes
    target, _, rest = spec.partition("::")
    target, rest = target.strip(), rest.strip()
    toks = rest.split()
    kind = toks[0] if toks else "file"
    minn = next((int(t[2:]) for t in toks[1:] if t.startswith(">=")), 1)

    if kind == "file":
        ok = os.path.exists(target) and os.path.getsize(target) > 0
        return ok, (f"{os.path.getsize(target)} bytes" if ok else "missing/empty")
    if kind == "raster":
        rl = QgsRasterLayer(target, "r")
        return ((rl.isValid() and rl.bandCount() > 0),
                f"{rl.width()}x{rl.height()} {rl.bandCount()}-band" if rl.isValid() else "invalid")
    vl = _vector(target)
    if not vl.isValid():
        return False, "layer invalid"
    n = vl.featureCount()
    if n < minn:
        return False, f"{n} features (< {minn})"
    if kind == "table":
        return True, f"{n} rows (aspatial)"
    gt = QgsWkbTypes.displayString(vl.wkbType())
    if gt == "NoGeometry":
        return False, "loaded as NoGeometry — geometry LOST"
    nonempty = sum(1 for i, f in enumerate(vl.getFeatures()) if i < 5 and not f.geometry().isEmpty())
    if nonempty == 0:
        return False, f"{n} features but ALL-EMPTY geometry ({gt})"
    return True, f"{n} {gt}, geometry OK"


def cleanup(directive):
    # Cleanups are run as real niva flows — the suite dogfoods its own verbs. `remove <path>`
    # deletes a file output (and its sidecar family) via niva's `remove`; `flow <…>` runs an
    # arbitrary cleanup flow (e.g. `sql @conn "DROP TABLE …"`). Best-effort: a failing cleanup
    # never fails the test (the assertion already ran), and `remove` is idempotent anyway.
    if directive.startswith("remove "):
        flow = directive
    elif directive.startswith("flow "):
        flow = directive[len("flow "):].strip()
    elif directive.startswith("rm "):  # back-compat shorthand → niva `remove`
        flow = "remove " + directive[len("rm "):].strip()
    else:
        return
    with contextlib.suppress(Exception):
        niva_flow(flow)


def emit_pure(blocks, path):
    """Write a PURE, `niva run`-able .niva from the suite: per-test header comments, the
    pipeline flows, and each test's DB cleanup as a real inline flow (`sql … DROP TABLE`).
    File outputs aren't deleted (niva has no file-delete verb) — they're noted as comments."""
    out = [
        "# Pure runnable niva — generated from validation_suite.niva by",
        "#   python tests/suites/run_validation_suite.py --emit",
        "# Run it and watch every pipeline:  niva run <this file>",
        "# Fully self-cleaning: file outputs are deleted with `remove` and DB tables with",
        "# inline `sql … DROP`. Outputs land in /tmp/niva_validation/out during the run.",
        "",
    ]
    for b in blocks:
        out.append(f"# ── {b['id']} | {b['cat']} | {b['desc']}")
        out.extend(b["flows"])
        for c in b["cleanups"]:
            if c.startswith("remove "):  # already a niva flow — emit verbatim
                out.append(c + "    # cleanup")
            elif c.startswith("flow "):
                out.append(c[len("flow "):].strip() + "    # cleanup")
            elif c.startswith("rm "):  # back-compat shorthand → niva `remove`
                from niva import remove_policy as _rp
                p = c[len("rm "):].strip()
                force = "" if _rp.on_allowlist(p.strip('"')) else " force"
                out.append(f"remove {p}{force}    # cleanup")
        out.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print(f"wrote pure runnable script: {path}")


def main():
    if "--emit" in sys.argv:
        target = SUITE.replace(".niva", ".run.niva")
        emit_pure(parse(SUITE), target)
        return
    os.makedirs(OUT, exist_ok=True)
    blocks = parse(SUITE)
    npass = 0
    rows = []
    env = _suite_report.environment()
    run_t0 = time.monotonic()
    print(f"niva validation suite — {len(blocks)} blocks\n" + "=" * 78)
    for b in blocks:
        label = f"{b['id']:8} [{b['cat']}] {b['desc']}"
        err = None
        t0 = time.monotonic()
        try:
            for fl in b["flows"]:
                niva_flow(_subst(fl))
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {str(exc).splitlines()[0][:100]}"
        results = []
        if err is None:
            for o in b["outs"]:
                o_s = _subst(o)
                try:
                    results.append((*assess(o_s), o_s.split("::")[0].strip()))
                except Exception as exc:  # noqa: BLE001
                    results.append((False, f"assess error: {exc}", o_s.split('::')[0].strip()))
        for c in b["cleanups"]:
            cleanup(_subst(c))
        dt = time.monotonic() - t0
        ok = err is None and all(r[0] for r in results)
        npass += ok
        note = err or "; ".join(m for good, m, _ in results if not good) or "ok"
        rows.append([b["id"], b["cat"], b["desc"][:48], "PASS" if ok else "FAIL",
                     f"{dt:.2f}", note[:80]])
        print(f"[{'PASS' if ok else 'FAIL'}] {label}  ({dt:.1f}s)")
        if err:
            print(f"         flow error: {err}")
        for good, msg, tgt in results:
            print(f"         {'✓' if good else '✗'} {tgt} — {msg}")
    elapsed = time.monotonic() - run_t0
    print("=" * 78 + f"\n{npass}/{len(blocks)} blocks passed")
    _write_report(env, rows, npass, len(blocks), elapsed)
    sys.stdout.flush()
    os._exit(0 if npass == len(blocks) else 1)  # skip QGIS teardown segfault


def _write_report(env, rows, npass, total, elapsed):
    try:
        suite = os.path.splitext(os.path.basename(SUITE))[0]
        path = _suite_report.write_summary(
            suite, env, ["ID", "category", "description", "status", "time (s)", "notes"], rows,
            [f"{npass}/{total} blocks passed", f"total elapsed {elapsed:.1f}s"],
            env["timestamp_utc"], elapsed)
        print(f"summary report → {path}")
    except Exception as exc:  # noqa: BLE001 — reporting must never fail the run
        print(f"(could not write summary report: {exc})")


if __name__ == "__main__":
    main()
