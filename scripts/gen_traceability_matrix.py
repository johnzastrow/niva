#!/usr/bin/env python3
"""Generate planning/14-traceability-matrix.md from the registry + live QGIS.

Run on QGIS's Python so the original signatures can be introspected:

    PYTHONPATH=/usr/share/qgis/python:. /usr/bin/python3 scripts/gen_traceability_matrix.py

Built-in verbs are described by hand (they map to mechanisms, not single algorithms);
alias rows are generated from niva/registry/definitions.py paired with the QGIS
Processing registry. Re-run after changing the registry.
"""

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "planning", "14-traceability-matrix.md")

BUILTINS = [
    ("load", "`load <path>` or `load @conn[.schema].table`",
     "QgsVectorLayer / QgsRasterLayer; provider-connection `tableUri` for `@conn`"),
    ("save", "`save <path>`",
     "QgsVectorFileWriter (driver by extension) + metadata/lineage persistence"),
    ("sql", '`sql @conn "<query>"`',
     "QgsAbstractDatabaseProviderConnection.createSqlVectorLayer"),
    ("run", "`run <algorithm-id> KEY=value …`",
     "processing.run (raw escape hatch; scalar-coerced params)"),
    ("call", "`call <file.niva>`",
     "engine file composition (relative resolve, cycle-checked)"),
    ("metadata", "`metadata set key=value …`",
     "QgsLayerMetadata setters (title/abstract/keywords/identifier/license), persisted on save"),
    ("assess", "`assess [deep] to <report.md>`",
     "QgsVectorLayer/QgsRasterLayer introspection → markdown; `deep` adds validity/empty/duplicate/null"),
    ("describe", "`describe <verb-or-algorithm-id>` (CLI/API, not a flow stage)",
     "registry + Processing registry introspection"),
]


def niva_sig(alias):
    parts = [alias.verb]
    for arg in alias.args:
        parts.append(f"<{arg.name}>" if arg.required else f"[{arg.name}]")
    for name in alias.flags:
        parts.append(f"[{name}]")
    for key, opt in alias.options.items():
        val = "/".join(opt.values) if opt.values else opt.type
        tok = f"{key}={val}"
        parts.append(tok if opt.required else f"[{tok}]")
    return "`" + " ".join(parts) + "`"


def orig_sig(info):
    if info is None:
        return "_(not installed)_"
    ps = []
    for p in info["params"]:
        d = "" if p["default"] is None else f"={p['default']}"
        opt = "?" if p["optional"] else ""
        ps.append(f"{p['name']}({p['type']}){d}{opt}")
    outs = ", ".join(f"{o['name']}({o['type']})" for o in info["outputs"])
    s = ", ".join(ps) + (f" → {outs}" if outs else "")
    return s.replace("|", "\\|")


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from qgis.core import Qgis, QgsApplication

    from niva.engine.pyqgis import algorithm_info, ensure_qgis, owned_app
    from niva.registry import core_registry

    ensure_qgis()
    reg = core_registry()
    qv = Qgis.QGIS_VERSION
    nalg = len(QgsApplication.processingRegistry().algorithms())

    L = [
        "# 14 · Traceability matrix",
        "",
        "Maps every niva verb to the QGIS algorithm/function it drives, its original",
        "QGIS signature, the niva signature, and implementation status. **Status legend:**",
        "✅ implemented + tested · 🟡 partial · ⬜ planned.",
        "",
        f"> Grounded in live QGIS introspection — **QGIS {qv}**. Alias signatures are read",
        "> from `niva/registry/definitions.py`; original signatures from the QGIS Processing",
        "> registry. Regenerate with `scripts/gen_traceability_matrix.py`. Param notation:",
        "> `NAME(type)[=default]`, a trailing `?` marks an optional QGIS parameter; niva",
        "> notation: `<required>`, `[optional]`, `key=a/b/c` (enum choices).",
        "",
        "## Built-in verbs (engine-handled, not registry aliases)",
        "",
        "| niva verb | niva signature | backed by | status |",
        "|-----------|----------------|-----------|--------|",
    ]
    for verb, sig, by in BUILTINS:
        L.append(f"| `{verb}` | {sig} | {by} | ✅ |")
    L += [
        "",
        "Auto-lineage: every `save` records the flow's stages into the output's",
        "`QgsLayerMetadata.history` (prefixed `niva: `) — no verb required.",
        "",
        "## Verb aliases (registry → `native:*`)",
        "",
        "| niva verb | algorithm | original QGIS signature | niva signature | status |",
        "|-----------|-----------|-------------------------|----------------|--------|",
    ]
    for verb in reg.verbs():
        alias = reg.get(verb)
        info = algorithm_info(alias.algorithm)
        L.append(f"| `{verb}` | `{alias.algorithm}` | {orig_sig(info)} | {niva_sig(alias)} | ✅ |")
    L += [
        "",
        "## The long tail (reachable, no alias needed)",
        "",
        f"All **{nalg}** algorithms in the installed QGIS Processing registry (native, gdal,",
        "grass, pdal, qgis, 3d, …) are reachable today via the `run <id> KEY=value` escape",
        "hatch (status: ✅), with `describe <id>` to surface each one's signature. Curated",
        "aliases are added to the table above as they are promoted from the long tail.",
        'Database geoprocessing (SpatiaLite/PostGIS) is reachable via `sql @conn "…"`.',
        "",
    ]
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"wrote {OUT} — QGIS {qv}, {len(reg.verbs())} aliases, {nalg} algorithms")

    app = owned_app()
    if app is not None:
        sys.stdout.flush()
        app.exitQgis()
        os._exit(0)


if __name__ == "__main__":
    main()
