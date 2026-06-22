#!/usr/bin/env python3
"""Run a niva BENCHMARK suite and record CPU / memory / disk / network metrics per test.

Companion to run_validation_suite.py, but instead of asserting correctness it **instruments**
each pipeline and writes a timestamped, machine-readable record so runs can be compared later
(regressions, hardware changes, niva versions). Same block format as the validation suites; the
header's *category* names the dimension under stress (`cpu` / `memory` / `disk` / `network`).

Per test it captures:
  • wall_s            wall-clock seconds (time.monotonic)
  • cpu_user/sys_s    process CPU time consumed (resource.getrusage delta)
  • rss_peak_mb       peak resident memory during the test (sampled from /proc/self/statm)
  • rss_delta_mb      net resident-memory growth across the test
  • io_read/write_mb  bytes through read()/write() syscalls (delta of /proc/self/io)
  • disk_write_mb     actual block-device writes (delta of /proc/self/io write_bytes)
  • out_mb, features  size of the output(s) on disk and their feature count
plus an environment fingerprint (host, CPU count, RAM, niva/QGIS/Python versions).

Run under QGIS's Python:
    PYTHONPATH=<repo>:/usr/share/qgis/python:/usr/lib/python3/dist-packages \
      QT_QPA_PLATFORM=offscreen python3 examples/run_benchmark_suite.py \
        examples/benchmark_suite.niva [--out <dir>]

Writes <out>/benchmark_<host>_<UTCstamp>.json and .md (and refreshes benchmark_latest.json/.md).
Default <out> is ~/niva-test-results (cross-machine). JSON is the canonical comparison record.
"""
from __future__ import annotations

import contextlib
import glob
import io
import json
import os
import re
import resource
import sys
import threading
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # find the sibling report module
import _suite_report  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SUITE = os.path.abspath(_ARGS[0]) if _ARGS else os.path.join(REPO, "examples", "benchmark_suite.niva")
# Reports land in the user's home (~/niva-test-results) by default so they compare across
# machines; override with --out <dir>.
OUTDIR = str(_suite_report.results_dir())
if "--out" in sys.argv:
    OUTDIR = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
# {data}/{testdata}/{examples} path tokens (see _suite_report.data_tokens). The benchmark uses
# {data} (generate it with make_bigdata.py). Tokens let the suite run unchanged on any clone.
_TOKENS = _suite_report.data_tokens(REPO)


def _subst(text):
    return _suite_report.subst(text, _TOKENS)


_HDR = re.compile(r"#\s*=+\s*(PREAMBLE|TEST\s+\d+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*=+\s*$")
_PAGE = os.sysconf("SC_PAGE_SIZE")


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
        elif not s.startswith("#"):
            cur["flows"].append(line)
    return blocks


def niva_flow(text):
    import niva
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        niva.flow(text)


# --- metric probes -----------------------------------------------------------------------
def _rss_kb():
    try:
        with open("/proc/self/statm") as fh:
            return int(fh.read().split()[1]) * _PAGE // 1024
    except OSError:
        return 0


def _io_counters():
    out = {}
    try:
        with open("/proc/self/io") as fh:
            for ln in fh:
                k, _, v = ln.partition(":")
                out[k.strip()] = int(v.strip())
    except OSError:
        pass
    return out


class _RSSSampler(threading.Thread):
    """Polls resident memory in the background so we get a real per-test peak, not just the
    process-wide high-water mark."""
    def __init__(self, interval=0.05):
        super().__init__(daemon=True)
        self.interval, self.peak, self._stop = interval, _rss_kb(), threading.Event()

    def run(self):
        while not self._stop.is_set():
            cur = _rss_kb()
            if cur > self.peak:
                self.peak = cur
            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()
        self.join(timeout=1.0)
        return self.peak


def _mb(b):
    return round(b / (1024 * 1024), 2)


# --- output sizing -----------------------------------------------------------------------
def measure_output(spec):
    """`<path|@conn.table> :: <kind> [>=N]` → (bytes_on_disk, feature_count). For a file we
    sum the file + its sidecars; for a layer/raster we load it just to count. Best-effort:
    sizing must never crash a benchmark run."""
    target = spec.split("::")[0].strip()
    if target.startswith("@"):
        return 0, _safe_feature_count(target)
    base = os.path.splitext(target)[0]
    total = 0
    for p in [target, *glob.glob(base + ".*"), target + "-wal", target + "-shm"]:
        with contextlib.suppress(OSError):
            if os.path.isfile(p):
                total += os.path.getsize(p)
    return total, _safe_feature_count(target)


def _safe_feature_count(target):
    try:
        from qgis.core import QgsRasterLayer, QgsVectorLayer
        if target.lower().endswith((".tif", ".tiff", ".jp2", ".img", ".vrt", ".asc")):
            rl = QgsRasterLayer(target, "r")
            return rl.width() * rl.height() if rl.isValid() else 0
        vl = QgsVectorLayer(target, "v", "ogr")
        return vl.featureCount() if vl.isValid() else 0
    except Exception:  # noqa: BLE001
        return 0


def cleanup(directive):
    d = directive.strip()
    if d.startswith("rm "):
        d = "remove " + d[3:].strip()
    flow = d if d.startswith("remove ") else d[5:].strip() if d.startswith("flow ") else None
    if flow:
        with contextlib.suppress(Exception):
            niva_flow(flow)


# --- environment fingerprint (cross-platform, shared with the other runners) -------------
def environment():
    return _suite_report.environment()


def _stamp():
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def write_reports(env, results, outdir):
    os.makedirs(outdir, exist_ok=True)
    host = re.sub(r"\W+", "_", env.get("host") or "host")
    stamp = _stamp()
    payload = {"environment": env, "results": results}
    # host-in-name timestamped files are the durable, gather-from-many-machines record;
    # the latest.* are per-machine convenience.
    for name in (f"benchmark_{host}_{stamp}.json", "benchmark_latest.json"):
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
    md = _markdown(env, results)
    for name in (f"benchmark_{host}_{stamp}.md", "benchmark_latest.md"):
        with open(os.path.join(outdir, name), "w", encoding="utf-8") as fh:
            fh.write(md)
    return os.path.join(outdir, f"benchmark_{host}_{stamp}.json")


def _markdown(env, results):
    lines = ["# niva benchmark", "", "## Environment", ""]
    for k, v in env.items():
        lines.append(f"- **{k}**: {v}")
    lines += ["", "## Results", "",
              "_io-rd/io-wr = bytes through read()/write() syscalls (true throughput); the kernel "
              "buffers block-device writes in page cache, so they're a better disk signal than "
              "flushed `disk_write_mb` (kept in the JSON)._", "",
              "| ID | dim | description | ok | wall s | cpu s | peak RSS MB | ΔRSS MB | "
              "io-rd MB | io-wr MB | out MB | features |",
              "|----|-----|-------------|----|-------:|------:|------------:|--------:|"
              "--------:|--------:|-------:|---------:|"]
    by_dim = {}
    for r in results:
        by_dim.setdefault(r["cat"], []).append(r)
        lines.append(
            f"| {r['id']} | {r['cat']} | {r['desc'][:46]} | {'✓' if r['ok'] else '✗'} | "
            f"{r['wall_s']:.2f} | {r['cpu_total_s']:.2f} | {r['rss_peak_mb']:.0f} | "
            f"{r['rss_delta_mb']:+.0f} | {r['io_read_mb']:.1f} | {r['io_write_mb']:.1f} | "
            f"{r['out_mb']:.1f} | {r['features']} |")
    lines += ["", "## Totals by dimension", ""]
    for dim, rs in sorted(by_dim.items()):
        lines.append(f"- **{dim}**: {len(rs)} test(s), "
                     f"wall {sum(r['wall_s'] for r in rs):.1f}s, "
                     f"cpu {sum(r['cpu_total_s'] for r in rs):.1f}s, "
                     f"peak RSS {max(r['rss_peak_mb'] for r in rs):.0f}MB")
    return "\n".join(lines) + "\n"


def main():
    blocks = parse(SUITE)
    env = environment()
    print(f"niva benchmark — {len(blocks)} block(s)  |  {env.get('host')}  "
          f"niva {env.get('niva_version')}  {env.get('cpu_count')} CPU  "
          f"{env.get('ram_total_mb')}MB RAM\n" + "=" * 92)
    results = []
    for b in blocks:
        sampler = _RSSSampler()
        ru0 = resource.getrusage(resource.RUSAGE_SELF)
        io0 = _io_counters()
        rss0 = _rss_kb()
        sampler.start()
        err = None
        t0 = time.monotonic()
        try:
            for fl in b["flows"]:
                niva_flow(_subst(fl))
        except Exception as exc:  # noqa: BLE001 — record the failure, keep benchmarking
            err = f"{type(exc).__name__}: {str(exc).splitlines()[0][:120]}"
        wall = time.monotonic() - t0
        peak = sampler.stop()
        ru1 = resource.getrusage(resource.RUSAGE_SELF)
        io1 = _io_counters()
        out_bytes = feats = 0
        for o in b["outs"]:
            with contextlib.suppress(Exception):
                ob, fc = measure_output(_subst(o))
                out_bytes += ob
                feats += fc
        for c in b["cleanups"]:
            cleanup(_subst(c))
        rec = {
            "id": b["id"], "cat": b["cat"], "desc": b["desc"], "ok": err is None,
            "error": err,
            "wall_s": round(wall, 3),
            "cpu_user_s": round(ru1.ru_utime - ru0.ru_utime, 3),
            "cpu_sys_s": round(ru1.ru_stime - ru0.ru_stime, 3),
            "cpu_total_s": round((ru1.ru_utime - ru0.ru_utime) + (ru1.ru_stime - ru0.ru_stime), 3),
            "rss_peak_mb": round(peak / 1024, 1),
            "rss_delta_mb": round((_rss_kb() - rss0) / 1024, 1),
            "io_read_mb": _mb(io1.get("rchar", 0) - io0.get("rchar", 0)),
            "io_write_mb": _mb(io1.get("wchar", 0) - io0.get("wchar", 0)),
            "disk_write_mb": _mb(io1.get("write_bytes", 0) - io0.get("write_bytes", 0)),
            "out_mb": _mb(out_bytes), "features": feats,
        }
        results.append(rec)
        flag = "ok " if rec["ok"] else "ERR"
        print(f"[{flag}] {b['id']:8} [{b['cat']:7}] {b['desc'][:40]:40} "
              f"wall {rec['wall_s']:6.2f}s  cpu {rec['cpu_total_s']:6.2f}s  "
              f"peakRSS {rec['rss_peak_mb']:6.0f}MB  out {rec['out_mb']:6.1f}MB  n={rec['features']}")
        if err:
            print(f"         {err}")
    path = write_reports(env, results, OUTDIR)
    print("=" * 92)
    print(f"wrote {path}\n      {os.path.join(OUTDIR, 'benchmark_latest.json')} / .md")
    sys.stdout.flush()
    os._exit(0)  # skip the QGIS teardown segfault


if __name__ == "__main__":
    main()
