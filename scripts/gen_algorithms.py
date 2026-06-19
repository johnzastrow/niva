#!/usr/bin/env python3
"""Regenerate the full QGIS algorithm appendix under ``docs/algorithms/``.

Introspects every algorithm in the live QGIS Processing registry and writes one Markdown
file per provider (plus an index), listing for each algorithm: its id, display name, group,
**which niva verb (if any) aliases it**, a description (what it does and how), every parameter
(name, type, required/optional, default, enum options), and outputs. This makes the entire
`run <algorithm-id> KEY=value` surface discoverable.

Run headless against the same QGIS niva targets (the python3.14 + PyQGIS recipe), from the
repo root:

    PYTHONPATH=$PWD:/usr/lib/python3/dist-packages:/usr/share/qgis/python \
        QT_QPA_PLATFORM=offscreen python3.14 scripts/gen_algorithms.py

Re-run after a QGIS upgrade; commit the regenerated ``docs/algorithms/*``.
"""

import os
import re

from niva.engine.pyqgis import ensure_qgis
from niva.registry.definitions import CORE

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "docs", "algorithms")
QGIS_VERSION = "4.0.3"

PROVIDER_TITLES = {
    "native": "native — QGIS native (C++) algorithms",
    "gdal": "gdal — GDAL/OGR algorithms",
    "qgis": "qgis — QGIS (Python) algorithms",
    "grass": "grass — GRASS GIS algorithms",
    "pdal": "pdal — PDAL point-cloud algorithms",
    "3d": "3d — 3D algorithms",
}

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"[ \t]*\n[ \t]*")


def clean(text):
    """Strip HTML tags and collapse whitespace from a QGIS help string."""
    if not text:
        return ""
    text = _TAG.sub("", text)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = _WS.sub("\n", text).strip()
    # collapse 3+ newlines to a paragraph break
    return re.sub(r"\n{3,}", "\n\n", text)


def esc(text):
    """Escape Markdown table-breaking characters in a cell."""
    return (text or "").replace("|", "\\|").replace("\n", " ").strip()


def fmt_default(value):
    if value is None or value == "":
        return "—"
    s = str(value)
    return esc(s[:60] + ("…" if len(s) > 60 else ""))


# --- example usage -----------------------------------------------------------

# Destination ("output") parameter types — passed as `OUTPUT=…` in a run command.
DEST_TYPES = {"sink", "vectorDestination", "rasterDestination", "fileDestination",
              "folderDestination", "pointCloudDestination", "vectorTileDestination"}
DEST_EXT = {"sink": ".gpkg", "vectorDestination": ".gpkg", "rasterDestination": ".tif",
            "pointCloudDestination": ".laz", "fileDestination": ".txt",
            "folderDestination": "/", "vectorTileDestination": ".mbtiles"}


def _num(v):
    f = float(v)
    return str(int(f)) if f == int(f) else f"{f:g}"


def _runval(value):
    s = str(value)
    return f'"{s}"' if (" " in s or ";" in s) else s


def example_value(p):
    """A plausible illustrative value for a parameter, by its type / default."""
    t = p.type()
    dv = p.defaultValue()
    fixed = {
        "raster": "dem.tif", "mesh": "mesh.nc", "band": "1", "crs": "EPSG:6346",
        "extent": "0,1000,0,1000", "point": "100,100", "expression": '"value > 0"',
        "file": "input.dat", "folder": "inputs/", "color": '"#1f78b4"',
        "datetime": "2024-06-01", "multilayer": '"a.gpkg;b.gpkg"',
    }
    if t in ("source", "vector", "layer", "maplayer", "annotationlayer"):
        return "input.gpkg"
    if t == "pointcloud":
        return "cloud.copc.laz"
    if t in ("field", "attribute", "pointcloudattribute"):
        return _runval(dv) if isinstance(dv, str) and dv else "field1"
    if t == "enum":
        return str(dv if isinstance(dv, int) and not isinstance(dv, bool) else 0)
    if t == "boolean":
        return "true" if dv in (True, "true", 1) else "false"
    if t in ("number", "distance", "duration", "scale"):
        return _num(dv) if isinstance(dv, (int, float)) and not isinstance(dv, bool) else "10"
    if t in ("string", "execute_sql"):
        return _runval(dv) if isinstance(dv, str) and dv else "value"
    if t in fixed:
        return fixed[t]
    if isinstance(dv, bool):
        return "true" if dv else "false"
    if isinstance(dv, (int, float)):
        return _num(dv)
    if isinstance(dv, str) and dv:
        return _runval(dv)
    return "…"


def _short(desc, n=80):
    d = clean(desc).split("\n")[0].strip()
    return (d[:n].rsplit(" ", 1)[0] + "…") if len(d) > n else d


def _enum_label(p, value):
    opts = getattr(p, "options", None)
    if not callable(opts):
        return None
    try:
        return opts()[int(value)]
    except Exception:
        return None


def example_section(alg, params, optional_flag, advanced_flag):
    """A worked `run` command (required params + a few notable optional ones) plus a
    narrative explaining each parameter passed."""
    # Skip GRASS-style dash flags (e.g. `-a`): a `run` KEY must start with a letter/underscore.
    def runnable(p):
        n = p.name()
        return bool(n) and (n[0].isalpha() or n[0] == "_")
    inputs = [p for p in params if p.type() not in DEST_TYPES and runnable(p)]
    dests = [p for p in params if p.type() in DEST_TYPES and runnable(p)]
    required = [p for p in inputs
                if not (p.flags() & optional_flag)
                and (p.defaultValue() is None or p.defaultValue() == "")]
    extra = [p for p in inputs if p not in required and not (p.flags() & advanced_flag)]
    selected = (required + extra)[:7]  # complex but readable

    args, notes = [], []
    for p in selected:
        v = example_value(p)
        if v == "…" and p not in required:
            continue
        args.append(f"{p.name()}={v}")
        label = _enum_label(p, v) if p.type() == "enum" else None
        if label is not None:
            notes.append(f"`{p.name()}={v}` selects *{esc(str(label))}*")
        else:
            d = _short(p.description())
            notes.append(f"`{p.name()}={v}`" + (f" — {d}" if d else ""))
    if dests:
        o = dests[0]
        ext = DEST_EXT.get(o.type(), ".gpkg")
        fname = o.name().lower() + ("/" if ext == "/" else ext)
        args.append(f"{o.name()}={fname}")
        notes.append(f"`{o.name()}={fname}` is where the result is written")

    cmd = "run " + alg.id() + ((" " + " ".join(args)) if args else "")
    if notes:
        body = (f"This calls **{esc(alg.displayName())}**: " + "; ".join(notes)
                + ". Enum values are integer indices; the paths and values here are "
                "illustrative — substitute your own.")
    else:
        body = f"This calls **{esc(alg.displayName())}** (no required parameters)."
    return ["**Example usage**", "", "```", cmd, "```", "", body, ""]


def main():
    from qgis.core import QgsApplication, QgsProcessingParameterDefinition

    ensure_qgis()
    reg = QgsApplication.processingRegistry()
    optional_flag = QgsProcessingParameterDefinition.Flag.FlagOptional
    advanced_flag = QgsProcessingParameterDefinition.Flag.FlagAdvanced

    # algorithm id -> niva verb
    alias_of = {a.algorithm: a.verb for a in CORE}

    # group algorithms by provider
    by_provider = {}
    for alg in reg.algorithms():
        by_provider.setdefault(alg.provider().id(), []).append(alg)

    os.makedirs(OUT_DIR, exist_ok=True)
    counts = {}
    alias_counts = {}

    for provider in sorted(by_provider):
        algs = sorted(by_provider[provider], key=lambda a: a.id())
        counts[provider] = len(algs)
        alias_counts[provider] = sum(1 for a in algs if a.id() in alias_of)
        lines = [
            f"# `{provider}:` algorithms",
            "",
            f"{PROVIDER_TITLES.get(provider, provider)} — {len(algs)} algorithms "
            f"(QGIS {QGIS_VERSION}). Auto-generated by `scripts/gen_algorithms.py`; "
            "see [the index](README.md).",
            "",
            "Call any of these with `run <id> KEY=value …` (the **Name** column is the "
            "`KEY`); each entry includes a worked **Example usage**. A ⭐ marks an algorithm "
            "with a friendly niva alias verb.",
            "",
        ]
        for alg in algs:
            aid = alg.id()
            verb = alias_of.get(aid)
            star = " ⭐" if verb else ""
            title = f"### `{aid}` — {alg.displayName()}{star}"
            lines.append(title)
            meta = [f"**group:** {alg.group() or '—'}"]
            if verb:
                meta.append(f"**niva verb:** `{verb}`")
            lines.append("  ·  ".join(meta))
            lines.append("")
            desc = clean(alg.shortHelpString()) or clean(alg.shortDescription())
            if desc:
                lines.append(desc)
                lines.append("")
            params = alg.parameterDefinitions()
            if params:
                lines.append("| Parameter | Type | Required | Default | Description |")
                lines.append("|---|---|---|---|---|")
                for p in params:
                    dv = p.defaultValue()
                    has_default = dv is not None and dv != ""
                    # "Required" = you must pass it via `run KEY=…`: not optional AND no
                    # default to fall back on.
                    req = "no" if (p.flags() & optional_flag or has_default) else "yes"
                    name = p.name()
                    if p.flags() & advanced_flag:
                        name += " *(adv)*"
                    desc_p = esc(p.description())
                    opts = getattr(p, "options", None)
                    if callable(opts):
                        try:
                            ov = opts()
                        except Exception:
                            ov = None
                        if ov:
                            enumerated = ", ".join(f"{i}={esc(str(o))}"
                                                   for i, o in enumerate(ov))
                            desc_p = (desc_p + " — " if desc_p else "") + f"options: {enumerated}"
                    lines.append(
                        f"| `{esc(name)}` | {esc(p.type())} | {req} "
                        f"| {fmt_default(p.defaultValue())} | {desc_p} |")
                lines.append("")
            outs = alg.outputDefinitions()
            if outs:
                outtxt = ", ".join(f"`{esc(o.name())}` ({esc(o.type())})" for o in outs)
                lines.append(f"**Outputs:** {outtxt}")
                lines.append("")
            lines.extend(example_section(alg, params, optional_flag, advanced_flag))
            lines.append("")
        path = os.path.join(OUT_DIR, f"{provider}.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines).rstrip() + "\n")
        print(f"wrote {path} ({len(algs)} algorithms)")

    # index
    total = sum(counts.values())
    total_alias = sum(alias_counts.values())
    idx = [
        "# QGIS algorithm appendix",
        "",
        f"Every QGIS Processing algorithm reachable from niva via `run <id> KEY=value …` — "
        f"**{total} algorithms** across {len(counts)} providers (QGIS {QGIS_VERSION}). For "
        "each: its parameters (with types, defaults, and enum options), description, outputs, "
        "a worked **Example usage**, and which niva **alias verb** (if any) wraps it (⭐).",
        "",
        "This is auto-generated — regenerate with `scripts/gen_algorithms.py` after a QGIS "
        "upgrade. Most users only need the 45 [alias verbs](../reference.md#5-alias-verbs-the-registry); "
        "this appendix is for reaching everything else through `run`. Discover one live with "
        "`niva describe <id>`.",
        "",
        "| Provider | Algorithms | niva alias verbs | Reference |",
        "|---|---|---|---|",
    ]
    for provider in sorted(counts):
        idx.append(f"| `{provider}:` | {counts[provider]} | {alias_counts[provider]} "
                   f"| [{provider}.md]({provider}.md) |")
    idx.append(f"| **Total** | **{total}** | **{total_alias}** | |")
    idx.append("")
    with open(os.path.join(OUT_DIR, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(idx) + "\n")
    print(f"wrote {os.path.join(OUT_DIR, 'README.md')}")
    # emit the summary table for pasting elsewhere
    print("\n--- SUMMARY TABLE ---")
    print("| Provider | Algorithms | niva alias verbs |")
    print("|---|---|---|")
    for provider in sorted(counts):
        print(f"| `{provider}:` | {counts[provider]} | {alias_counts[provider]} |")
    print(f"| **Total** | **{total}** | **{total_alias}** |")


if __name__ == "__main__":
    main()
