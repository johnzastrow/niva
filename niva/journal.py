"""The run journal (planning/08-§2) — a timestamped record of every operation.

Writes **two files** from one base path, because humans don't read JSON:

- ``<base>.jsonl`` — machine-readable JSON Lines: one JSON object per line. Each run
  starts with a self-describing run-start object (`niva_journal` schema version,
  niva version, flow, started) and ends with a run-finished object; one object per
  operation in between.
- ``<base>.log``  — plain text, **one line per operation**:
  ``<ts>  <stage>  [algorithm]  → <full path>  (12 ms)`` (errors are appended inline,
  so a failure is still one line). A one-line ``# run:`` marker separates runs and a
  one-line ``# done:`` marker closes each.

With ``append=True`` the files are reused (a single log per QGIS session); otherwise
they are truncated (one log per CLI invocation). What is recorded is the niva stage
text + the resolved output path — never resolved parameter dicts or credentials.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

SCHEMA = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, base_path: str, *, append: bool = False):
        root, ext = os.path.splitext(base_path)
        self.base = root if ext in (".jsonl", ".log", ".json") else base_path
        self.jsonl_path = self.base + ".jsonl"
        self.log_path = self.base + ".log"
        self.append = append
        self._jsonl = None
        self._log = None
        self._n = 0
        self._failed = 0

    def open(self, *, flow: str, niva_version: str) -> "Journal":
        parent = os.path.dirname(self.base)
        if parent:
            os.makedirs(parent, exist_ok=True)
        mode = "a" if self.append else "w"
        existing = self.append and os.path.exists(self.log_path) and os.path.getsize(self.log_path) > 0
        self._jsonl = open(self.jsonl_path, mode, encoding="utf-8")
        self._log = open(self.log_path, mode, encoding="utf-8")
        started = _now()
        self._emit_json({
            "niva_journal": SCHEMA,
            "niva_version": niva_version,
            "run": flow,
            "started": started,
        })
        sep = "\n" if existing else ""  # blank line between runs in a session log
        self._log.write(f"{sep}# run: {flow}  ({started})\n")
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

        # exactly one line per operation (errors inlined, newlines flattened)
        parts = [ts, " ", text]
        if algorithm:
            parts.append(f"  [{algorithm}]")
        if summary:
            parts.append(f"  → {summary}")
        if duration_ms is not None:
            parts.append(f"  ({duration_ms} ms)")
        if not ok:
            flat = " ".join((error or "failed").split())
            parts.append(f"  ✗ FAILED: {flat[:200]}")
        self._log.write("".join(parts) + "\n")
        self._log.flush()

    def close(self) -> None:
        if self._log is not None:
            outcome = "ok" if self._failed == 0 else f"{self._failed} failed"
            self._log.write(f"# done: {self._n} operation(s), {outcome}  ({_now()})\n")
            self._log.close()
            self._log = None
        if self._jsonl is not None:
            self._emit_json({"run_finished": _now(), "operations": self._n, "failed": self._failed})
            self._jsonl.close()
            self._jsonl = None

    def _emit_json(self, obj: dict) -> None:
        self._jsonl.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self._jsonl.flush()
