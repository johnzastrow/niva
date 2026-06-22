#!/usr/bin/env python3
"""Generate LARGE synthetic data to push the niva benchmark hard — offline, deterministic.

The benchmark suite needs heavy layers (tens of thousands of features) and a big raster to trace
a real scaling curve. Rather than depend on any one machine's data, this script SYNTHESISES that
data with GDAL/OGR only (no QGIS, no network), so any clone of the repo can run the benchmark at
full weight. It is deterministic — same `--scale` ⇒ identical bytes — so results compare across
machines.

    python3 examples/make_bigdata.py [--out <dir>] [--scale <float>]

Default out dir is data/ (gitignored); default scale 1.0. Writes a single `bench.gpkg` with
size-tiered layers and a `bench_dem.tif` raster:

    bench.gpkg  polys_small (~1k) · polys_med (~10k) · polys_big (~60k·scale)
                points_big (~60k·scale) · lines_med (~5k)         (all EPSG:6346, metres)
    bench_dem.tif   (2000·√scale)² Float32 DEM

For an even harder run on REAL data, see examples/bigdata_urls.md — public datasets you can
wget/curl into data/ and point the benchmark at.
"""
from __future__ import annotations

import math
import os
import struct
import sys

from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "data")
SCALE = 1.0
if "--out" in sys.argv:
    OUT = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])
if "--scale" in sys.argv:
    SCALE = float(sys.argv[sys.argv.index("--scale") + 1])

# EPSG:6346 (NAD83(2011) UTM 17N, metres) — same family as the other test data.
OX, OY = 600000.0, 4800000.0
FIELDS = [("id", ogr.OFTInteger), ("name", ogr.OFTString),
          ("category", ogr.OFTString), ("value", ogr.OFTReal)]
_CATS = ("alpha", "beta", "gamma", "delta")


def _srs():
    s = osr.SpatialReference()
    s.ImportFromEPSG(6346)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return s


def _grid_polys(lyr, n, cell=40.0, gap=10.0):
    """`n` little square polygons laid out in a near-square grid (deterministic)."""
    cols = max(1, int(math.sqrt(n)))
    defn = lyr.GetLayerDefn()
    lyr.StartTransaction()
    for i in range(n):
        r, c = divmod(i, cols)
        x, y = OX + c * (cell + gap), OY + r * (cell + gap)
        ring = (f"{x} {y}, {x + cell} {y}, {x + cell} {y + cell}, "
                f"{x} {y + cell}, {x} {y}")
        f = ogr.Feature(defn)
        f["id"], f["name"] = i, f"f{i}"
        f["category"], f["value"] = _CATS[i % 4], i * 0.5
        f.SetGeometry(ogr.CreateGeometryFromWkt(f"POLYGON(({ring}))"))
        lyr.CreateFeature(f)
    lyr.CommitTransaction()


def _grid_points(lyr, n):
    cols = max(1, int(math.sqrt(n)))
    defn = lyr.GetLayerDefn()
    lyr.StartTransaction()
    for i in range(n):
        r, c = divmod(i, cols)
        x, y = OX + c * 25.0, OY + r * 25.0
        f = ogr.Feature(defn)
        f["id"], f["name"] = i, f"p{i}"
        f["category"], f["value"] = _CATS[i % 4], i * 1.5
        f.SetGeometry(ogr.CreateGeometryFromWkt(f"POINT({x} {y})"))
        lyr.CreateFeature(f)
    lyr.CommitTransaction()


def _lines(lyr, n, span=4000.0):
    defn = lyr.GetLayerDefn()
    lyr.StartTransaction()
    for i in range(n):
        y = OY + i * 12.0
        f = ogr.Feature(defn)
        f["id"], f["name"] = i, f"l{i}"
        f["category"], f["value"] = _CATS[i % 4], float(i)
        f.SetGeometry(ogr.CreateGeometryFromWkt(f"LINESTRING({OX} {y}, {OX + span} {y})"))
        lyr.CreateFeature(f)
    lyr.CommitTransaction()


def build_vectors(path):
    if os.path.exists(path):
        os.remove(path)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)

    def layer(name, geom):
        lyr = ds.CreateLayer(name, _srs(), geom, ["OVERWRITE=YES"])
        for fn, ft in FIELDS:
            lyr.CreateField(ogr.FieldDefn(fn, ft))
        return lyr

    small = 1_000
    med = 10_000
    big = int(60_000 * SCALE)
    _grid_polys(layer("polys_small", ogr.wkbPolygon), small)
    _grid_polys(layer("polys_med", ogr.wkbPolygon), med)
    _grid_polys(layer("polys_big", ogr.wkbPolygon), big)
    _grid_points(layer("points_big", ogr.wkbPoint), big)
    _lines(layer("lines_med", ogr.wkbLineString), 5_000)
    ds = None
    return path, {"polys_small": small, "polys_med": med, "polys_big": big,
                  "points_big": big, "lines_med": 5_000}


def build_dem(path):
    size = int(2000 * math.sqrt(SCALE))
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(path, size, size, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE", "TILED=YES"])
    ext = size * 5.0  # 5 m pixels
    ds.SetGeoTransform([OX, 5.0, 0, OY + ext, 0, -5.0])
    ds.SetProjection(_srs().ExportToWkt())
    band = ds.GetRasterBand(1)
    for row in range(size):
        vals = [100.0 + 40.0 * math.sin(c / 25.0) + 30.0 * math.cos(row / 30.0)
                for c in range(size)]
        band.WriteRaster(0, row, size, 1, struct.pack(f"<{size}f", *vals))
    band.FlushCache()
    ds = None
    return path, size


def main():
    os.makedirs(OUT, exist_ok=True)
    gpkg, counts = build_vectors(os.path.join(OUT, "bench.gpkg"))
    dem, size = build_dem(os.path.join(OUT, "bench_dem.tif"))
    print(f"wrote big benchmark data to {OUT}  (scale={SCALE})")
    print(f"  {os.path.basename(gpkg)}  ({os.path.getsize(gpkg):,} bytes)  layers: "
          + ", ".join(f"{k}={v}" for k, v in counts.items()))
    print(f"  {os.path.basename(dem)}  ({os.path.getsize(dem):,} bytes)  {size}×{size} Float32")


if __name__ == "__main__":
    main()
