#!/usr/bin/env python3
"""Regenerate the pure-runnable `.run.niva` companions for the tests/suites/ validation suites.

The validation suites (tests/suites/) (`validation_suite*.niva`) carry test directives
(`#@out`, `#@cleanup`) and ship a **pure, `niva run`-able companion** — `<suite>.run.niva`
with the directives stripped — emitted by `run_validation_suite.py --emit`. This keeps every
such companion in sync with its source: the tests/suites/ analogue of `scripts/gen_test_niva.py`
for `tests/`. CI fails on drift; a Claude Code hook regenerates on edit.

(The assert suites — portable/numerical/round_trip/security/error_path/format_matrix — and the
benchmark suite use ordinary niva comments, so they are *already* directly runnable and have no
generated companion.)

Pure Python (no QGIS): it shells out to the runner's `--emit` path. Run with:
    python scripts/gen_run_niva.py
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUITES = os.path.join(REPO, "tests", "suites")
RUNNER = os.path.join(SUITES, "run_validation_suite.py")


def main() -> int:
    companions = sorted(glob.glob(os.path.join(SUITES, "*.run.niva")))
    if not companions:
        print("no .run.niva companions found under tests/suites/")
        return 0
    env = dict(os.environ)
    env["PYTHONPATH"] = REPO + os.pathsep + env.get("PYTHONPATH", "")
    n = 0
    for companion in companions:
        source = companion[: -len(".run.niva")] + ".niva"
        if not os.path.exists(source):
            print(
                f"warning: source missing for {os.path.basename(companion)} — leaving as is"
            )
            continue
        # `--emit <source>` writes <source-without-.niva>.run.niva (pure, no QGIS needed).
        subprocess.run(
            [sys.executable, RUNNER, "--emit", source],
            check=True,
            env=env,
            stdout=subprocess.DEVNULL,
        )
        n += 1
    print(f"regenerated {n} .run.niva companion(s) under tests/suites/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
