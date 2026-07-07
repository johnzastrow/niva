"""``niva find`` — discover spatial data across the filesystem (issue #43, CLI-epic Phase 1).

The scan is **offline**: globbing, extension, size and mtime come from the standard library, so
``find`` runs on any interpreter with no QGIS. When **GDAL/OGR is importable** (e.g. on QGIS's
own Python), each match is *enriched* with geometry type, CRS, layer/feature counts and field
names — and the richer filters (``--geom`` / ``--crs`` / ``--min-features`` / ``--has-field``)
become usable. Without GDAL those filters can't be satisfied, so ``find`` says so plainly rather
than silently returning nothing (the same graceful-degradation rule as the rest of niva).

The pure pieces here — :func:`walk`, :func:`base_record`, :func:`match_base`, :func:`match_meta`,
:func:`parse_size`, :func:`parse_age`, and the formatters — are QGIS-free and unit-tested; only
:func:`enrich` (and :func:`have_gdal`) touch GDAL, lazily and behind a guard.
"""

from __future__ import annotations

import fnmatch
import os
from functools import lru_cache

# Curated extension → human format label. This is the default corpus `find` scans (a bare
# `niva find` looks only for *data*, not every file); pass `--all-files` to widen it. Labels
# double as the `--format` filter's target. Grouped by kind for the enrichment `kind` hint.
_VECTOR = {
    "gpkg": "GeoPackage",
    "shp": "Shapefile",
    "geojson": "GeoJSON",
    "json": "GeoJSON",
    "gml": "GML",
    "kml": "KML",
    "kmz": "KMZ",
    "gpx": "GPX",
    "tab": "MapInfo TAB",
    "mif": "MapInfo MIF",
    "fgb": "FlatGeobuf",
    "parquet": "GeoParquet",
    "csv": "CSV",
    "sqlite": "SpatiaLite",
    "gdb": "File Geodatabase",
}
_RASTER = {
    "tif": "GeoTIFF",
    "tiff": "GeoTIFF",
    "img": "ERDAS IMG",
    "jp2": "JPEG2000",
    "vrt": "GDAL VRT",
    "asc": "Arc/Info ASCII Grid",
    "dem": "DEM",
    "nc": "NetCDF",
    "grd": "Surfer Grid",
}
_POINTCLOUD = {
    "las": "LAS point cloud",
    "laz": "LAZ point cloud",
    "copc": "COPC point cloud",
}
SPATIAL_EXTS: dict[str, str] = {**_VECTOR, **_RASTER, **_POINTCLOUD}


def _kind_for_ext(ext: str) -> str:
    if ext in _POINTCLOUD:
        return "pointcloud"
    if ext in _RASTER:
        return "raster"
    if ext in _VECTOR:
        return "vector"
    return "other"


# --------------------------------------------------------------------------- parsing helpers


def parse_size(text: str) -> int:
    """Bytes from a human string: ``512`` (bytes), ``10k``, ``2.5M``, ``1g`` (K/M/G = 1024ⁿ).
    Case-insensitive; a trailing ``b`` is ignored. Raises ``ValueError`` on garbage."""
    s = text.strip().lower().rstrip("b")
    if not s:
        raise ValueError("empty size")
    mult = 1
    if s[-1] in "kmgt":
        mult = {"k": 1024, "m": 1024**2, "g": 1024**3, "t": 1024**4}[s[-1]]
        s = s[:-1]
    return int(float(s) * mult)


def parse_age(text: str) -> float:
    """Seconds from a duration string: ``30s``, ``15m``, ``24h``, ``7d``, ``2w`` (bare number =
    days). Used by ``--newer-than`` as an *age cutoff*. Raises ``ValueError`` on garbage."""
    s = text.strip().lower()
    if not s:
        raise ValueError("empty duration")
    unit = s[-1]
    factors = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}
    if unit in factors:
        return float(s[:-1]) * factors[unit]
    return float(s) * 86400  # bare number → days


def human_size(n: int) -> str:
    """A compact human byte size: ``0 B`` … ``9.4 GB`` (1024-based, one decimal past KB)."""
    if n < 1024:
        return f"{n} B"
    val = float(n)
    for unit in ("KB", "MB", "GB", "TB"):
        val /= 1024
        if val < 1024 or unit == "TB":
            return f"{val:.1f} {unit}"
    return f"{n} B"  # unreachable, keeps the type-checker happy


def exts_for_pattern(pattern: str, *, all_files: bool) -> set[str] | None:
    """The extension allowlist implied by ``pattern``. If the glob pins an extension
    (``*.gpkg`` → ``{gpkg}``) use that; otherwise fall back to every spatial extension —
    unless ``all_files`` widens the scan to any extension (returns ``None`` = no restriction)."""
    _, dot, ext = pattern.rpartition(".")
    if dot and ext and not any(c in ext for c in "*?[]"):
        return {ext.lower()}
    return None if all_files else set(SPATIAL_EXTS)


# --------------------------------------------------------------------------- filesystem scan


def walk(roots, *, recursive: bool = True, max_depth: int | None = None):
    """Yield file paths under each of ``roots``. ``recursive`` walks subdirectories;
    ``max_depth`` (0 = the root itself) caps how deep. A root that is itself a file is
    yielded directly. Unreadable directories are skipped, never raised."""
    for root in roots:
        root = os.path.expanduser(root)
        if os.path.isfile(root):
            yield root
            continue
        base_depth = root.rstrip(os.sep).count(os.sep)
        for dirpath, dirnames, filenames in os.walk(root, onerror=lambda _e: None):
            depth = dirpath.rstrip(os.sep).count(os.sep) - base_depth
            for name in filenames:
                yield os.path.join(dirpath, name)
            if not recursive or (max_depth is not None and depth >= max_depth):
                dirnames[:] = []  # prune: stop descending


def base_record(path: str) -> dict:
    """The zero-dependency record for one file: absolute path, name, lower-case extension,
    format label (or ``""``), byte size, mtime, and inferred kind. No GDAL."""
    name = os.path.basename(path)
    ext = name.rpartition(".")[2].lower() if "." in name else ""
    try:
        st = os.stat(path)
        size, mtime = st.st_size, st.st_mtime
    except OSError:
        size, mtime = 0, 0.0
    return {
        "path": os.path.abspath(path),
        "name": name,
        "ext": ext,
        "format": SPATIAL_EXTS.get(ext, ""),
        "kind": _kind_for_ext(ext),
        "size": size,
        "mtime": mtime,
    }


def match_base(rec: dict, crit: dict) -> bool:
    """Whether ``rec`` passes the **offline** criteria (pattern, exts, size, age, format).
    ``crit`` keys (all optional): ``pattern``, ``exts`` (set|None), ``min_size``, ``max_size``,
    ``newer_than`` (epoch cutoff), ``format`` (case-insensitive substring)."""
    pattern = crit.get("pattern") or "*"
    if not fnmatch.fnmatch(rec["name"], pattern):
        return False
    exts = crit.get("exts")
    if exts is not None and rec["ext"] not in exts:
        return False
    if (mn := crit.get("min_size")) is not None and rec["size"] < mn:
        return False
    if (mx := crit.get("max_size")) is not None and rec["size"] > mx:
        return False
    if (cut := crit.get("newer_than")) is not None and rec["mtime"] < cut:
        return False
    fmt = crit.get("format")
    if fmt and fmt.lower() not in rec["format"].lower():
        return False
    return True


def match_meta(rec: dict, crit: dict) -> bool:
    """Whether an **enriched** ``rec`` passes the GDAL-derived criteria (geometry, CRS,
    feature-count range, has-field). A record that lacks a probed field fails the corresponding
    filter (we can't confirm it), so callers only apply this when enrichment ran."""
    if geom := crit.get("geom"):
        if geom.lower() not in str(rec.get("geometry", "")).lower():
            return False
    if crs := crit.get("crs"):
        if crs.lower() != str(rec.get("crs", "")).lower():
            return False
    feats = rec.get("features")
    if (mn := crit.get("min_features")) is not None and (feats is None or feats < mn):
        return False
    if (mx := crit.get("max_features")) is not None and (feats is None or feats > mx):
        return False
    if field := crit.get("has_field"):
        fields = [f.lower() for f in rec.get("fields", [])]
        if field.lower() not in fields:
            return False
    return True


# --------------------------------------------------------------------------- GDAL enrichment


@lru_cache(maxsize=1)
def have_gdal() -> bool:
    """Whether GDAL/OGR's Python bindings import here (they do on QGIS's Python; usually not
    in an isolated ``uv``/``pipx`` venv). Cached — the import probe runs once."""
    try:
        from osgeo import gdal, ogr  # noqa: F401

        return True
    except Exception:  # noqa: BLE001 — absence is the normal offline case, never fatal
        return False


def _crs_authority(srs) -> str:
    """``"EPSG:2262"`` from an OGR ``SpatialReference`` (best effort; ``""`` if unknown)."""
    if srs is None:
        return ""
    try:
        auth, code = srs.GetAuthorityName(None), srs.GetAuthorityCode(None)
        if auth and code:
            return f"{auth}:{code}"
    except Exception:  # noqa: BLE001
        pass
    return ""


def enrich(rec: dict) -> dict:
    """Populate ``rec`` in place with geometry/CRS/layers/features/fields (vector) or
    bands/CRS (raster) via a lazy GDAL/OGR probe. A no-op — and never raises — when GDAL is
    absent or the file won't open; a partly-probed record simply omits the missing keys."""
    if not have_gdal():
        return rec
    from osgeo import gdal, ogr

    gdal.UseExceptions()
    path = rec["path"]
    try:  # vector first (the common case)
        ds = ogr.Open(path)
    except Exception:  # noqa: BLE001 — not an OGR-readable source
        ds = None
    if ds is not None:
        try:
            rec["layers"] = [
                ds.GetLayer(i).GetName() for i in range(ds.GetLayerCount())
            ]
            layer = ds.GetLayer(0)
            if layer is not None:
                rec["kind"] = "vector"
                rec["geometry"] = ogr.GeometryTypeToName(layer.GetGeomType())
                rec["crs"] = _crs_authority(layer.GetSpatialRef())
                rec["features"] = layer.GetFeatureCount()
                defn = layer.GetLayerDefn()
                rec["fields"] = [
                    defn.GetFieldDefn(i).GetName() for i in range(defn.GetFieldCount())
                ]
                # The FID / primary-key column — this is the "unique identifier" that many
                # algorithms ask for (dissolve/join field, `native:*` unique-id params). Empty
                # for formats without an explicit FID column (e.g. plain Shapefile).
                rec["fid_column"] = layer.GetFIDColumn() or ""
        except Exception:  # noqa: BLE001 — a corrupt layer must not abort the scan
            pass
        finally:
            ds = None
        return rec
    try:  # else raster
        rds = gdal.Open(path)
    except Exception:  # noqa: BLE001
        rds = None
    if rds is not None:
        try:
            rec["kind"] = "raster"
            rec["bands"] = rds.RasterCount
            rec["geometry"] = f"{rds.RasterXSize}×{rds.RasterYSize} raster"
            srs = rds.GetSpatialRef() if hasattr(rds, "GetSpatialRef") else None
            rec["crs"] = _crs_authority(srs)
        except Exception:  # noqa: BLE001
            pass
        finally:
            rds = None
    return rec


# --------------------------------------------------------------------------- orchestration


def find(
    roots, crit: dict, *, recursive=True, max_depth=None, limit=None, do_enrich=True
):
    """Scan ``roots``, apply the offline criteria, enrich survivors (when GDAL is present and
    ``do_enrich``), apply the meta criteria, and return the matched records sorted by path.
    ``limit`` bounds the result. Enrichment happens only for files that already passed the
    cheap offline filters, so a probe is spent only on real candidates."""
    wants_meta = any(
        crit.get(k) is not None
        for k in ("geom", "crs", "min_features", "max_features", "has_field")
    )
    base = [
        r
        for r in (
            base_record(p)
            for p in walk(roots, recursive=recursive, max_depth=max_depth)
        )
        if match_base(r, crit)
    ]
    base.sort(key=lambda r: r["path"])
    enriched_ok = do_enrich and have_gdal()
    out: list[dict] = []
    for rec in base:
        if enriched_ok:
            enrich(rec)
        if wants_meta and not match_meta(rec, crit):
            continue
        out.append(rec)
        if limit is not None and len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------- rendering


def format_table(records, *, color: bool = False, meta: bool = False) -> str:
    """A padded, aligned table of ``records``. With ``meta`` (enrichment ran) it adds the
    KIND / GEOMETRY / CRS / FEATURES columns; otherwise just NAME / FORMAT / SIZE / PATH."""
    from . import color as _c

    def paint(text, *st):
        return _c.paint(text, *st) if color else text

    if not records:
        return "no matching data found"

    rows = []
    for r in records:
        row = {
            "NAME": r["name"],
            "FORMAT": r["format"] or r["ext"] or "?",
            "SIZE": human_size(r["size"]),
        }
        if meta:
            row["KIND"] = r.get("kind", "")
            geom = r.get("geometry", "")
            row["GEOMETRY"] = geom
            row["CRS"] = r.get("crs", "") or "—"
            feats = r.get("features")
            row["FEATURES"] = "" if feats is None else str(feats)
        row["PATH"] = r["path"]
        rows.append(row)

    cols = list(rows[0].keys())
    widths = {c: max(len(c), *(len(row[c]) for row in rows)) for c in cols}
    lines = [
        "  ".join(paint(f"{c:<{widths[c]}}", "bold", "cyan") for c in cols),
        "  ".join("─" * widths[c] for c in cols),
    ]
    for row in rows:
        cells = []
        for c in cols:
            text = f"{row[c]:<{widths[c]}}"
            if c == "NAME":
                text = paint(text, "green")
            elif c == "PATH":
                text = paint(text, "dim")
            cells.append(text)
        lines.append("  ".join(cells))
    lines.append(paint(f"# {len(records)} match(es)", "dim"))
    return "\n".join(lines)


def format_json(records) -> str:
    import json

    return json.dumps(records, indent=2, ensure_ascii=False, default=str)


def format_paths(records, *, nul: bool = False) -> str:
    """Just the absolute paths, one per line — the script-friendly output. Nothing else:
    no header, count, or colour, so it pipes cleanly into other tools
    (``… | xargs``, ``… | wc -l``, ``… > list.txt``). With ``nul=True`` the paths are
    NUL-separated (for ``xargs -0`` and paths containing spaces or newlines)."""
    paths = [r["path"] for r in records]
    return "\0".join(paths) if nul else "\n".join(paths)


def format_as_flow(records) -> str:
    """A runnable batch skeleton: one ``each "<path>" | <stages> | save …`` line per match, so
    *find becomes the source of a flow*. Fill in the middle stages and the output, then run."""
    if not records:
        return "# niva find: no matches — nothing to build a flow from"
    lines = [
        f"# niva find → batch skeleton ({len(records)} match(es)). "
        "Replace <stages>, set the output dir, then run each line (or paste into the repl):"
    ]
    for r in records:
        lines.append(f'each "{r["path"]}" | <stages> | save "out/{{name}}.gpkg"')
    return "\n".join(lines)
