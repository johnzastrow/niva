#!/usr/bin/env python3
"""Generate TRANSPORTABLE niva test data — a single self-contained GeoPackage (plus a DEM GeoTIFF
and a SpatiaLite copy) that can be copied between machines and QGIS instances unchanged.

The data is synthetic and fully reproducible (no dependence on any one computer's `data/` dir or
`@conn`), so the portable test suite produces comparable results everywhere. It uses only GDAL/OGR
— it does NOT require QGIS — so you can regenerate it on any machine with GDAL installed:

    python3 tests/datagen/make_testdata.py [--out <dir>]

Default output dir is tests/datagen/testdata/ (the portable suite finds it there, or via $NIVA_TESTDATA).
Layers (EPSG:6346 unless noted): points, lines, polygons, multipolys, aoi, points_wgs84 (EPSG:4326),
plus two awkward names — "weird name" (space) and "select" (reserved word). Files written:
    niva_testdata.gpkg   niva_testdata_dem.tif   niva_testdata.sqlite
"""

from __future__ import annotations

import math
import os
import struct
import sys

from osgeo import gdal, ogr, osr

gdal.UseExceptions()
ogr.UseExceptions()

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(REPO, "tests", "datagen", "testdata")
if "--out" in sys.argv:
    OUT = os.path.abspath(sys.argv[sys.argv.index("--out") + 1])

# A plausible NAD83(2011) UTM 17N (EPSG:6346, metres) origin and a 7 km square extent.
OX, OY, EXT = 600000.0, 4800000.0, 7000.0


def _srs(epsg):
    s = osr.SpatialReference()
    s.ImportFromEPSG(epsg)
    s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)  # x/y (lon/lat) order
    return s


def _layer(ds, name, geom_type, epsg, fields):
    lyr = ds.CreateLayer(name, _srs(epsg), geom_type, ["OVERWRITE=YES"])
    for fname, ftype in fields:
        lyr.CreateField(ogr.FieldDefn(fname, ftype))
    return lyr


def _add(lyr, wkt, attrs):
    f = ogr.Feature(lyr.GetLayerDefn())
    for k, v in attrs.items():
        f[k] = v
    f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
    lyr.CreateFeature(f)


_FIELDS = [
    ("id", ogr.OFTInteger),
    ("name", ogr.OFTString),
    ("category", ogr.OFTString),
    ("value", ogr.OFTReal),
]
_CATS = ("alpha", "beta", "gamma")


def build_vectors(gpkg_path):
    if os.path.exists(gpkg_path):
        os.remove(gpkg_path)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(gpkg_path)

    # points — 8×8 grid (64), some attributes null to exercise null handling
    pts = _layer(ds, "points", ogr.wkbPoint, 6346, _FIELDS)
    fid = 0
    for r in range(8):
        for c in range(8):
            x, y = OX + c * (EXT / 7), OY + r * (EXT / 7)
            name = None if (r + c) % 7 == 0 else f"pt_{r}_{c}"  # some nulls
            _add(
                pts,
                f"POINT({x} {y})",
                {
                    "id": fid,
                    "name": name,
                    "category": _CATS[fid % 3],
                    "value": fid * 1.5,
                },
            )
            fid += 1

    # lines — 8 horizontal lines spanning the extent
    lines = _layer(ds, "lines", ogr.wkbLineString, 6346, _FIELDS)
    for i in range(8):
        y = OY + i * (EXT / 7)
        _add(
            lines,
            f"LINESTRING({OX} {y}, {OX + EXT} {y})",
            {"id": i, "name": f"line_{i}", "category": _CATS[i % 3], "value": float(i)},
        )

    # polygons — 4×4 grid of 1200 m squares (16)
    polys = _layer(ds, "polygons", ogr.wkbPolygon, 6346, _FIELDS)
    fid = 0
    side = 1200.0
    for r in range(4):
        for c in range(4):
            x, y = OX + c * 1600, OY + r * 1600
            ring = (
                f"{x} {y}, {x + side} {y}, {x + side} {y + side}, "
                f"{x} {y + side}, {x} {y}"
            )
            _add(
                polys,
                f"POLYGON(({ring}))",
                {
                    "id": fid,
                    "name": f"poly_{r}_{c}",
                    "category": _CATS[fid % 3],
                    "value": side * side,
                },
            )
            fid += 1

    # multipolys — 4 multipolygons, each two disjoint squares (exercises explode/promote/collect)
    multi = _layer(ds, "multipolys", ogr.wkbMultiPolygon, 6346, _FIELDS)
    for i in range(4):
        x, y = OX + i * 1500, OY + 4000
        s = 500.0
        sq1 = f"(({x} {y}, {x + s} {y}, {x + s} {y + s}, {x} {y + s}, {x} {y}))"
        x2 = x + 700
        sq2 = f"(({x2} {y}, {x2 + s} {y}, {x2 + s} {y + s}, {x2} {y + s}, {x2} {y}))"
        _add(
            multi,
            f"MULTIPOLYGON({sq1}, {sq2})",
            {
                "id": i,
                "name": f"multi_{i}",
                "category": _CATS[i % 3],
                "value": 2 * s * s,
            },
        )

    # aoi — one rectangle covering most of the extent (a clip/centroid fixture)
    aoi = _layer(
        ds,
        "aoi",
        ogr.wkbPolygon,
        6346,
        [("id", ogr.OFTInteger), ("name", ogr.OFTString)],
    )
    m = 500
    ring = (
        f"{OX + m} {OY + m}, {OX + EXT - m} {OY + m}, {OX + EXT - m} {OY + EXT - m}, "
        f"{OX + m} {OY + EXT - m}, {OX + m} {OY + m}"
    )
    _add(aoi, f"POLYGON(({ring}))", {"id": 1, "name": "aoi"})

    # points_wgs84 — a few points in EPSG:4326 (for geographic-CRS / units error tests)
    geo = _layer(
        ds,
        "points_wgs84",
        ogr.wkbPoint,
        4326,
        [("id", ogr.OFTInteger), ("name", ogr.OFTString)],
    )
    for i, (lon, lat) in enumerate([(-79.0, 43.0), (-79.01, 43.01), (-78.99, 43.02)]):
        _add(geo, f"POINT({lon} {lat})", {"id": i, "name": f"geo_{i}"})

    # awkward identifiers — a space and a SQL reserved word as LAYER names
    for nm in ("weird name", "select"):
        wl = _layer(
            ds,
            nm,
            ogr.wkbPoint,
            6346,
            [("id", ogr.OFTInteger), ("name", ogr.OFTString)],
        )
        for i in range(3):
            _add(
                wl,
                f"POINT({OX + i * 100} {OY + i * 100})",
                {"id": i, "name": f"{nm}_{i}"},
            )

    ds = None
    return gpkg_path


def build_dem(tif_path, size=200):
    """A smooth synthetic elevation surface, EPSG:6346, Float32 — for warp/slope/aspect tests."""
    drv = gdal.GetDriverByName("GTiff")
    ds = drv.Create(
        tif_path, size, size, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE", "TILED=YES"]
    )
    pixel = EXT / size
    ds.SetGeoTransform([OX, pixel, 0, OY + EXT, 0, -pixel])  # north-up
    ds.SetProjection(_srs(6346).ExportToWkt())
    band = ds.GetRasterBand(1)
    for row in range(size):
        vals = []
        for col in range(size):
            z = (
                100.0
                + 40.0 * math.sin(col / 18.0)
                + 30.0 * math.cos(row / 22.0)
                + 0.01 * (col + row)
            )
            vals.append(z)
        band.WriteRaster(0, row, size, 1, struct.pack(f"<{size}f", *vals))
    band.FlushCache()
    ds = None
    return tif_path


def build_spatialite(sl_path, gpkg_path):
    """A SpatiaLite copy of points & polygons (a transportable file-DB for spatialite tests)."""
    if os.path.exists(sl_path):
        os.remove(sl_path)
    src = ogr.Open(gpkg_path)
    dst = ogr.GetDriverByName("SQLite").CreateDataSource(sl_path, ["SPATIALITE=YES"])
    for name in ("points", "polygons", "lines"):
        dst.CopyLayer(src.GetLayerByName(name), name, ["OVERWRITE=YES"])
    src = dst = None
    return sl_path


def build_kml(kml_path, gpkg_path):
    """A KML copy of the points layer (a raw KML input for the format-matrix suite)."""
    if os.path.exists(kml_path):
        os.remove(kml_path)
    src = ogr.Open(gpkg_path)
    drv = ogr.GetDriverByName("LIBKML") or ogr.GetDriverByName("KML")
    dst = drv.CreateDataSource(kml_path)
    dst.CopyLayer(src.GetLayerByName("points"), "points")
    src = dst = None
    return kml_path


def build_filegdb(gdb_path, gpkg_path):
    """A FileGeodatabase (OpenFileGDB) with the points & polygons layers — a raw .gdb input."""
    import shutil

    if os.path.isdir(gdb_path):
        shutil.rmtree(gdb_path)
    src = ogr.Open(gpkg_path)
    dst = ogr.GetDriverByName("OpenFileGDB").CreateDataSource(gdb_path)
    for name in ("points", "polygons"):
        dst.CopyLayer(src.GetLayerByName(name), name)
    src = dst = None
    return gdb_path


def build_csv_points(csv_path):
    """A CSV of point data (lon/lat columns) plus an OGR .vrt sidecar that turns it into points,
    so niva can geoprocess it as geometry — the way real lon/lat CSVs (e.g. the USGS earthquake
    feed) are consumed. The .vrt is named `<stem>.vrt` and is what the suite loads."""
    with open(csv_path, "w", encoding="utf-8") as fh:
        fh.write("id,name,category,longitude,latitude\n")
        for i in range(50):
            lon, lat = -79.0 + (i % 10) * 0.02, 43.0 + (i // 10) * 0.02
            fh.write(f"{i},pt_{i},cat{i % 3},{lon:.5f},{lat:.5f}\n")
    vrt_path = os.path.splitext(csv_path)[0] + ".vrt"
    base = os.path.basename(csv_path)
    layer = os.path.splitext(base)[0]
    with open(vrt_path, "w", encoding="utf-8") as fh:
        fh.write(
            f"<OGRVRTDataSource>\n"
            f'  <OGRVRTLayer name="{layer}">\n'
            f'    <SrcDataSource relativeToVRT="1">{base}</SrcDataSource>\n'
            f"    <GeometryType>wkbPoint</GeometryType>\n"
            f"    <LayerSRS>EPSG:4326</LayerSRS>\n"
            f'    <GeometryField encoding="PointFromColumns" x="longitude" y="latitude"/>\n'
            f"  </OGRVRTLayer>\n"
            f"</OGRVRTDataSource>\n"
        )
    return csv_path, vrt_path


def build_jp2(jp2_path, dem_path):
    """A small 3-band JP2 image (CreateCopy from a synthetic RGB GeoTIFF) — a raw .jp2 input."""
    drv = gdal.GetDriverByName("JP2OpenJPEG")
    if drv is None:
        return None
    size = 256
    tmp = jp2_path + ".tmp.tif"
    src = gdal.GetDriverByName("GTiff").Create(tmp, size, size, 3, gdal.GDT_Byte)
    pixel = EXT / size
    src.SetGeoTransform([OX, pixel, 0, OY + EXT, 0, -pixel])
    src.SetProjection(_srs(6346).ExportToWkt())
    for b in range(1, 4):
        row_vals = []
        for r in range(size):
            row_vals.append(bytes((int((c + r * b) % 256) for c in range(size))))
        src.GetRasterBand(b).WriteRaster(0, 0, size, size, b"".join(row_vals))
    src.FlushCache()
    src = None
    if os.path.exists(jp2_path):
        os.remove(jp2_path)
    drv.CreateCopy(jp2_path, gdal.Open(tmp))
    os.remove(tmp)
    return jp2_path


def main():
    os.makedirs(OUT, exist_ok=True)
    gpkg = build_vectors(os.path.join(OUT, "niva_testdata.gpkg"))
    dem = build_dem(os.path.join(OUT, "niva_testdata_dem.tif"))
    extra = []
    for label, fn in (
        (
            "niva_testdata.sqlite",
            lambda: build_spatialite(os.path.join(OUT, "niva_testdata.sqlite"), gpkg),
        ),
        (
            "niva_testdata.kml",
            lambda: build_kml(os.path.join(OUT, "niva_testdata.kml"), gpkg),
        ),
        (
            "niva_testdata.gdb",
            lambda: build_filegdb(os.path.join(OUT, "niva_testdata.gdb"), gpkg),
        ),
        (
            "niva_testdata_points.csv",
            lambda: build_csv_points(os.path.join(OUT, "niva_testdata_points.csv"))[0],
        ),
        (
            "niva_testdata.jp2",
            lambda: build_jp2(os.path.join(OUT, "niva_testdata.jp2"), dem),
        ),
    ):
        try:
            extra.append(fn() or f"(skipped: {label})")
        except Exception as exc:  # noqa: BLE001 — a missing optional driver shouldn't abort
            extra.append(f"(skipped {label}: {str(exc).splitlines()[0][:60]})")
    print("wrote transportable test data to", OUT)
    for p in (gpkg, dem, *extra):
        if isinstance(p, str) and os.path.exists(p):
            size = f"{os.path.getsize(p):,} bytes" if os.path.isfile(p) else "(dir)"
            print(f"  {os.path.basename(p)}  {size}")
        else:
            print(f"  {p}")
    # quick self-check: report layer feature counts
    ds = ogr.Open(gpkg)
    print(
        "layers:",
        ", ".join(
            f"{ds.GetLayer(i).GetName()}={ds.GetLayer(i).GetFeatureCount()}"
            for i in range(ds.GetLayerCount())
        ),
    )


if __name__ == "__main__":
    main()
