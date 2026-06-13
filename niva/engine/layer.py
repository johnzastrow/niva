"""The layer handle and CRS info (planning/05-architecture.md, 06-§ layer contract).

``Layer`` is a *handle*, not the data: one type with a backing ``kind`` (where the
bytes live) and a ``facet`` (vector vs raster). The engine passes handles between
stages and only the backend ever touches real QGIS objects, so the engine core
stays QGIS-free and unit-testable. ``CrsInfo`` is the minimum the engine needs to
resolve a ``Distance`` against a layer's CRS without importing QGIS.
"""

from __future__ import annotations

from dataclasses import dataclass

# Backing kinds (05): where a layer's data actually lives.
SOURCE = "source"      # a file path or URI on disk
QGS = "qgs"            # a live QgsMapLayer in the current project
DB_TABLE = "db_table"  # a table reachable via a QGIS connection
MEMORY = "memory"      # an in-process/temporary result of a previous op


@dataclass(frozen=True)
class Layer:
    kind: str            # one of SOURCE / QGS / DB_TABLE / MEMORY
    ref: object          # backend-specific: path, uri, layer id, or QGIS object
    facet: str = "vector"  # "vector" | "raster"
    name: str = ""


@dataclass(frozen=True)
class CrsInfo:
    authid: str               # e.g. "EPSG:2262"
    is_geographic: bool       # True => coordinates are in degrees
    units_to_meters: float = 1.0  # length of one CRS linear unit in metres (ignored if geographic)
    map_units: str = "meters"     # human label for messages ("meters" / "feet" / "degrees")
