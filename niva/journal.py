"""The run journal (planning/08-§2) — a timestamped record of every operation.

Writes **two files** from one base path, because humans don't read JSON:

- ``<base>.jsonl`` — machine-readable JSON Lines: a header line carrying the schema
  version + niva version + flow source + start time, then one object per operation.
  A stable, versioned contract for tools (`niva_journal` = schema version).
- ``<base>.log``  — plain text a person can actually read: one timestamped line per
  operation, with a header and a final summary.

What is recorded is the **niva stage text** (what the user wrote) plus the resolved
algorithm id, timing, and ok/error — **never** resolved parameter dicts or
credentials (database logins live in QGIS's connection store and never reach here).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

SCHEMA = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    """Append-only run journal writing a JSONL + a human-readable log side by side."""

    def __init__(self, base_path: str):
        # `base_path` may be given with or without an extension; we always write
        # <base>.jsonl and <base>.log.
        root, ext = os.path.splitext(base_path)
        self.base = root if ext in (".jsonl", ".log", ".json") else base_path
        self.jsonl_path = self.base + ".jsonl"
        self.log_path = self.base + ".log"
        self._jsonl = None
        self._log = None
        self._n = 0
        self._failed = 0

    def open(self, *, flow: str, niva_version: str) -> "Journal":
        parent = os.path.dirname(self.base)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._jsonl = open(self.jsonl_path, "w", encoding="utf-8")
        self._log = open(self.log_path, "w", encoding="utf-8")
        started = _now()
        self._emit_json({
            "niva_journal": SCHEMA,
            "niva_version": niva_version,
            "flow": flow,
            "started": started,
        })
        self._log.write(f"niva run journal\n  flow:    {flow}\n  started: {started}\n\n")
        self._log.flush()
        return self

    def record(self, *, text: str, kind: str, algorithm: str | None = None,
               ok: bool = True, summary: str = "", error: str | None = None,
               duration_ms: int | None = None) -> None:
        self._n += 1
        if not ok:
            self._failed += 1
        ts = _now()
        rec = {"ts": ts, "n": self._n, "kind": kind, "text": text, "ok": ok}
        if algorithm:
            rec["algorithm"] = algorithm
        if summary:
            rec["summary"] = summary
        if error:
            rec["error"] = error
        if duration_ms is not None:
            rec["duration_ms"] = duration_ms
        self._emit_json(rec)

        # human line: "<ts>  <stage>  [algorithm]  → <full path>  (12 ms)" (+ error)
        parts = [ts, " ", text]
        if algorithm:
            parts.append(f"  [{algorithm}]")
        if summary:
            parts.append(f"  → {summary}")
        if duration_ms is not None:
            parts.append(f"  ({duration_ms} ms)")
        if not ok:
            parts.append("  ✗ FAILED")
        self._log.write("".join(parts) + "\n")
        if error:
            self._log.write(f"    {error}\n")
        self._log.flush()

    def close(self) -> None:
        if self._log is not None:
            outcome = "ok" if self._failed == 0 else f"{self._failed} failed"
            self._log.write(f"\ndone — {self._n} operation(s), {outcome} — {_now()}\n")
            self._log.close()
            self._log = None
        if self._jsonl is not None:
            self._emit_json({"finished": _now(), "operations": self._n, "failed": self._failed})
            self._jsonl.close()
            self._jsonl = None

    def _emit_json(self, obj: dict) -> None:
        self._jsonl.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._jsonl.flush()
