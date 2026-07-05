"""Pure deletion policy for the ``remove`` verb — **no QGIS, no filesystem access**.

This module decides *what kind of token* `remove` may act on and *which sidecar files* belong
to a primary output. It never touches the disk: the engine sequences these pure checks with the
filesystem-dependent ones (is-it-a-directory, does-it-exist) and does the actual ``os.remove``.

`remove` is the one destructive verb in niva, so the policy is deliberately strict — see
``docs/planning/18-remove-verb-design.md``. Scope this round: **files + their sidecars only**
(not ``@conn`` tables, not GeoPackage sub-layers).
"""

from __future__ import annotations

import os

# Recognised geodata outputs + the style/project/sidecar files niva itself writes. A `remove`
# of anything *not* here is refused unless the caller passes `force` (one path at a time).
ALLOWLIST = frozenset(
    {
        # vector
        ".gpkg",
        ".shp",
        ".geojson",
        ".gml",
        ".kml",
        ".kmz",
        ".fgb",
        ".sqlite",
        ".spatialite",
        ".db",
        ".tab",
        ".mif",
        ".dxf",
        # raster
        ".tif",
        ".tiff",
        ".jp2",
        ".img",
        ".vrt",
        ".asc",
        ".nc",
        ".grd",
        # niva-written styles / projects / layer defs
        ".qml",
        ".qmd",
        ".sld",
        ".qlr",
        ".qgs",
        ".qgz",
    }
)

# A short, human-readable rendering for error messages (grouped, not the raw set order).
ALLOWLIST_STR = (
    "vector: .gpkg .shp .geojson .gml .kml .kmz .fgb .sqlite .spatialite .tab .mif .dxf · "
    "raster: .tif .tiff .jp2 .img .vrt .asc .nc .grd · "
    "niva exports: .qml .qmd .sld .qlr .qgs .qgz"
)

_GLOB_CHARS = frozenset("*?[]")


def is_conn_ref(token: str) -> bool:
    """A ``@conn[.schema].table`` reference — out of scope for file deletion."""
    return token.lstrip().startswith("@")


def is_glob(token: str) -> bool:
    """A shell-glob pattern. `remove` refuses these; batch with ``each "<glob>" | remove``."""
    return any(ch in _GLOB_CHARS for ch in token)


def ext_of(path: str) -> str:
    """Lower-cased final extension (``.gpkg``), or ``""`` if none."""
    return os.path.splitext(path)[1].lower()


def on_allowlist(path: str) -> bool:
    """True if ``path``'s extension is a recognised geodata / niva-output type."""
    return ext_of(path) in ALLOWLIST


def family(primary: str) -> list[str]:
    """The ordered sidecar paths that belong to ``primary`` — the companions a single file
    output really has on disk (shapefile `.dbf`/`.prj`, GeoPackage `-wal`/`-shm`, a project's
    `_attachments.zip`, …). **Candidates only** (existence is the caller's job); the primary
    itself is never included, and duplicates are removed while preserving order.

    Detected by the primary's extension, plus a generic ``.aux.xml`` / ``.qml`` / ``.qmd`` sweep
    that applies to every output (those are written next to anything QGIS styles or georeferences).
    """
    stem, ext = os.path.splitext(primary)
    e = ext.lower()
    out: list[str] = []

    if e == ".shp":
        out += [
            stem + s for s in (".shx", ".dbf", ".prj", ".cpg", ".qpj", ".sbn", ".sbx")
        ]
        out.append(primary + ".xml")  # roads.shp.xml
    elif e == ".gpkg":
        out += [primary + s for s in ("-wal", "-shm", "-journal")]
        out.append(stem + "_attachments.zip")
    elif e in (".sqlite", ".spatialite", ".db"):
        out += [primary + s for s in ("-wal", "-shm", "-journal")]
    elif e in (".tif", ".tiff"):
        out += [stem + ".tfw", stem + ".wld", primary + ".ovr"]
    elif e == ".jp2":
        out += [stem + ".j2w", primary + ".ovr"]
    elif e in (".qgs", ".qgz"):
        out += [stem + "_attachments.zip", primary + "~"]

    # Generic sweep — written beside many outputs regardless of driver.
    out += [primary + ".aux.xml", stem + ".qml", stem + ".qmd"]

    seen, result = set(), []
    for p in out:
        if p != primary and p not in seen:
            seen.add(p)
            result.append(p)
    return result
