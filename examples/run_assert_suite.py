#!/usr/bin/env python3
"""Run an ASSERTION suite — property checks beyond "the output has geometry".

Companion to run_validation_suite.py. Where that harness asserts *success* (non-empty geometry),
this one tests **what the prior suites pass through**: error paths (a bad flow must fail with a
useful message and leave no partial output), numerical correctness (a 100 m buffer really is
~100 m), round-trip fidelity (load→save→reload preserves data), and security (injection is
quoted not executed; credentials never reach the journal).

Block format (ordinary niva comments, so the file is still `niva run`-able):

    # ===== TEST NN | category | description =====
    <flow line(s)>                                run in order (sharing one journal)
    #@fails <substring>                           the flow MUST raise; message contains <substring>
    #@check <python expr>                         must be truthy — see HELPERS below
    #@cleanup remove <path> [force] | flow <niva> tidy up

A block with `#@fails` is a NEGATIVE test (expects an error); otherwise flows must succeed. Both
kinds may add `#@check` (e.g. `#@check not exists(out)` to prove fail-closed).

HELPERS available inside `#@check` / referenced paths use {tmp} for the per-suite scratch dir:
    exists(p) count(p) gtype(p) crs(p) fields(p) values(p,f) area(p) length(p) bbox(p)
    nonempty(p) within_all(pts,polys) approx(a,b,tol) err() journal()
plus safe builtins (abs min max round len all any sum sorted set str int float bool).

Run under QGIS's Python:
    PYTHONPATH=<repo>:/usr/share/qgis/python:/usr/lib/python3/dist-packages \
      QT_QPA_PLATFORM=offscreen python3 examples/run_assert_suite.py examples/<suite>.niva
"""
from __future__ import annotations

import contextlib
import glob
import io
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SUITE = os.path.abspath(_ARGS[0]) if _ARGS else ""
TMP = "/tmp/niva_assert"
JDIR = os.path.join(TMP, "journal")

_HDR = re.compile(r"#\s*=+\s*(PREAMBLE|TEST\s+\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*=+\s*$")


def parse(path):
    blocks, cur = [], None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        m = _HDR.match(line)
        if m:
            cur = {"id": m.group(1).strip(), "cat": m.group(2), "desc": m.group(3),
                   "flows": [], "fails": [], "checks": [], "cleanups": []}
            blocks.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if not s:
            continue
        if s.startswith("#@fails "):
            cur["fails"].append(s[len("#@fails "):].strip())
        elif s.startswith("#@check "):
            cur["checks"].append(s[len("#@check "):].strip())
        elif s.startswith("#@cleanup "):
            cur["cleanups"].append(s[len("#@cleanup "):].strip())
        elif not s.startswith("#"):
            cur["flows"].append(line)
    return blocks


# --- layer helpers (file paths; @conn is round-tripped through niva's own load) ----------
def _vl(path):
    from qgis.core import QgsVectorLayer
    p = path.format(tmp=TMP)
    if p.startswith("@"):
        t = os.path.join(TMP, "_assess.gpkg")
        for f in glob.glob(t + "*"):
            os.remove(f)
        _flow(f'load "{p}" | save "{t}"', None)
        return QgsVectorLayer(t, "a", "ogr")
    return QgsVectorLayer(p, "a", "ogr")


def _geoms(path):
    return [f.geometry() for f in _vl(path).getFeatures()]


def _helpers():
    from qgis.core import QgsWkbTypes

    def exists(p):
        p = p.format(tmp=TMP)
        return os.path.exists(p) or bool(glob.glob(os.path.splitext(p)[0] + ".*"))

    def count(p):
        return _vl(p).featureCount()

    def gtype(p):
        return QgsWkbTypes.displayString(_vl(p).wkbType())

    def crs(p):
        return _vl(p).crs().authid()

    def fields(p):
        return [f.name() for f in _vl(p).fields()]

    def values(p, f):
        return [ft[f] for ft in _vl(p).getFeatures()]

    def area(p):
        return sum(g.area() for g in _geoms(p) if not g.isEmpty())

    def length(p):
        return sum(g.length() for g in _geoms(p) if not g.isEmpty())

    def bbox(p):
        e = _vl(p).extent()
        return (e.xMinimum(), e.yMinimum(), e.xMaximum(), e.yMaximum())

    def nonempty(p):
        gs = _geoms(p)
        return bool(gs) and all(not g.isEmpty() for g in gs[:50]) and gtype(p) != "NoGeometry"

    def within_all(pts, polys):
        from qgis.core import QgsGeometry
        poly = QgsGeometry.unaryUnion(_geoms(polys))
        return all(poly.contains(g) for g in _geoms(pts) if not g.isEmpty())

    def approx(a, b, tol):
        return abs(a - b) <= tol

    def filetext(p):
        p = p.format(tmp=TMP)
        try:
            with open(p, "rb") as fh:
                return fh.read().decode("latin-1")
        except OSError:
            return ""

    def leaks(text):
        # credential / DB-URI markers that must NEVER appear in a journal or output file —
        # niva keeps connection details in QGIS; only the @conn *name* crosses into a flow.
        toks = ("dbname=", " host=", "password", "user=", "port=", "service=", "pg: ")
        low = text.lower()
        return any(tok in low for tok in toks)

    return {
        "exists": exists, "count": count, "gtype": gtype, "crs": crs, "fields": fields,
        "values": values, "area": area, "length": length, "bbox": bbox, "nonempty": nonempty,
        "within_all": within_all, "approx": approx, "filetext": filetext, "leaks": leaks,
        "abs": abs, "min": min, "max": max, "round": round, "len": len, "all": all,
        "any": any, "sum": sum, "sorted": sorted, "set": set, "str": str, "int": int,
        "float": float, "bool": bool,
    }


def _flow(text, log):
    import niva
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        niva.flow(text, log=log, log_append=log is not None)


def cleanup(directive):
    d = directive.strip().format(tmp=TMP)
    if d.startswith("rm "):
        d = "remove " + d[3:].strip()
    flow = d if d.startswith("remove ") else d[5:].strip() if d.startswith("flow ") else None
    if flow:
        with contextlib.suppress(Exception):
            _flow(flow, None)


def main():
    os.makedirs(JDIR, exist_ok=True)
    blocks = parse(SUITE)
    npass = 0
    print(f"niva assertion suite: {os.path.basename(SUITE)} — {len(blocks)} block(s)\n" + "=" * 80)
    helpers = _helpers()
    for b in blocks:
        logbase = os.path.join(JDIR, re.sub(r"\W+", "_", b["id"]))
        for ext in (".log", ".jsonl"):
            with contextlib.suppress(OSError):
                os.remove(logbase + ext)
        err = None
        for fl in b["flows"]:
            try:
                _flow(fl.format(tmp=TMP), logbase)
            except Exception as exc:  # noqa: BLE001 — capture; negative tests expect this
                err = exc
                break

        def journal(_lb=logbase):
            txt = ""
            for ext in (".log", ".jsonl"):
                with contextlib.suppress(OSError), open(_lb + ext, encoding="utf-8") as fh:
                    txt += fh.read()
            return txt

        ns = dict(helpers)
        ns["err"] = lambda _e=err: ("" if _e is None else str(_e))
        ns["journal"] = journal

        problems = []
        if b["fails"]:
            if err is None:
                problems.append("expected an error, but the flow succeeded")
            else:
                et = str(err).lower()
                for sub in b["fails"]:
                    if sub.lower() not in et:
                        problems.append(f"error missing {sub!r}: {str(err).splitlines()[0][:80]}")
        elif err is not None:
            problems.append(f"unexpected error: {type(err).__name__}: {str(err).splitlines()[0][:90]}")

        if not (b["fails"] and err is None):
            # Helpers go in GLOBALS (not locals) so names resolve inside generator/comprehension
            # scopes too (a genexpr can't see eval's locals). __builtins__ stays empty.
            gns = {**ns, "__builtins__": {}}
            for expr in b["checks"]:
                try:
                    if not eval(expr, gns):  # noqa: S307 — trusted, repo-authored suite text
                        problems.append(f"check failed: {expr}")
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"check errored: {expr} -> {exc}")

        for c in b["cleanups"]:
            cleanup(c)

        ok = not problems
        npass += ok
        print(f"[{'PASS' if ok else 'FAIL'}] {b['id']:8} [{b['cat']}] {b['desc'][:48]}")
        for p in problems:
            print(f"         ✗ {p}")
    print("=" * 80 + f"\n{npass}/{len(blocks)} blocks passed")
    sys.stdout.flush()
    os._exit(0 if npass == len(blocks) else 1)


if __name__ == "__main__":
    main()
