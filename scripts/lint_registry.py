#!/usr/bin/env python3
"""Validate every niva alias against the QGIS actually installed (planning 07-§9).

For each ``Alias`` in ``niva.registry.definitions.CORE`` this checks that the
algorithm id exists and that every parameter niva references (positional args,
options, flags, forced values, primary input/output) is a real parameter of that
algorithm. It fails loud — exit code 1 with a list — when an algorithm or parameter
has moved, so the registry can never drift silently from the host's QGIS.

Run with **QGIS's own Python** (the interpreter niva runs on), e.g.:

    <qgis_python> scripts/lint_registry.py

On a typical Linux QGIS install the bindings/plugins dirs may need to be on the
path; set QGIS_PYTHON_PATH to point at them (colon-separated) if `import qgis`
or `import processing` fails.
"""

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Let the caller add bindings/plugins dirs (e.g. /usr/share/qgis/python[:.../plugins]).
for _p in os.environ.get("QGIS_PYTHON_PATH", "").split(os.pathsep):
    if _p:
        sys.path.insert(0, _p)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def main() -> int:
    try:
        from qgis.core import QgsApplication
    except ImportError:
        print("lint_registry: run me with QGIS's own Python (import qgis failed). "
              "Set QGIS_PYTHON_PATH to the bindings dir if needed.", file=sys.stderr)
        return 3

    QgsApplication.setPrefixPath(sys.prefix, True)
    app = QgsApplication([], False)
    app.initQgis()
    from qgis.analysis import QgsNativeAlgorithms
    from processing.core.Processing import Processing

    Processing.initialize()
    reg = QgsApplication.processingRegistry()
    reg.addProvider(QgsNativeAlgorithms(reg))

    from niva.registry.definitions import CORE

    problems = []
    for a in CORE:
        alg = reg.algorithmById(a.algorithm)
        if alg is None:
            problems.append(f"{a.verb}: algorithm {a.algorithm} NOT FOUND")
            continue
        params = {p.name() for p in alg.parameterDefinitions()}
        refs = {a.primary_input, a.primary_output}
        refs.update(arg.param for arg in a.args)
        refs.update(o.param for o in a.options.values())
        refs.update(f.param for f in a.flags.values())
        refs.update(a.forced.keys())
        missing = sorted(r for r in refs if r not in params)
        if missing:
            problems.append(f"{a.verb} ({a.algorithm}): unknown params {missing}")

    print(f"checked {len(CORE)} aliases")
    for p in problems:
        print("  ✗", p)
    print("OK" if not problems else f"FAILED: {len(problems)} alias(es) drifted")

    sys.stdout.flush()
    app.exitQgis()
    # Hard exit: avoids the standalone-QgsApplication teardown segfault.
    os._exit(1 if problems else 0)


if __name__ == "__main__":
    main()
