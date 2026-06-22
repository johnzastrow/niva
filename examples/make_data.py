#!/usr/bin/env python3
"""Generate niva's test data directory (data/) for this machine.

Creates data/ from the portable testdata (examples/testdata/) and example.gpkg,
registers the needed QGIS connections (@localpg, @actual_spatialite.sqlite), and
populates PostGIS with the fixture tables used by the security and round-trip suites.

Run under QGIS's Python:

    PYTHONHOME=/Applications/QGIS-final-4_0_3.app/Contents/Frameworks \\
    PYTHONPATH=/path/to/niva:/Applications/.../Resources/qgis/python:... \\
    /Applications/QGIS-final-4_0_3.app/Contents/MacOS/python3.12 examples/make_data.py
"""
from __future__ import annotations

import csv
import os
import shutil
from pathlib import Path

REPO     = Path(__file__).parent.parent
TESTDATA = REPO / "examples" / "testdata"
EX_GPKG  = REPO / "examples" / "example.gpkg"
DATA     = REPO / "data"

PG_HOST = "localhost"
PG_PORT = "5432"
PG_DB   = "niva_test"
PG_USER = os.environ.get("USER", os.environ.get("USERNAME", "jcz"))


def main() -> None:
    from niva.engine.pyqgis import ensure_qgis
    ensure_qgis()

    import niva
    from qgis.core import (
        QgsFeature,
        QgsField,
        QgsProject,
        QgsProviderRegistry,
        QgsSettings,
        QgsVectorFileWriter,
        QgsVectorLayer,
    )
    from qgis.PyQt.QtCore import QVariant

    DATA.mkdir(exist_ok=True)

    gpkg = str(TESTDATA / "niva_testdata.gpkg")
    dem  = str(TESTDATA / "niva_testdata_dem.tif")
    sl   = str(TESTDATA / "niva_testdata.sqlite")
    ex   = str(EX_GPKG)

    poly_src  = f"{gpkg}|layername=polygons"
    multi_src = f"{gpkg}|layername=multipolys"
    pt_src    = f"{gpkg}|layername=points"
    line_src  = f"{gpkg}|layername=lines"
    aoi_src   = f"{gpkg}|layername=aoi"

    # ── basemap.gpkg ──────────────────────────────────────────────────────────
    # boundary-polygon needs NAME / NAME_EN / ADMIN_LVL fields for the round-trip
    # suite's field-preservation tests (rt02, rt03, rt05, rt07).
    # The testdata polygons layer stores the name field as lowercase 'name';
    # we rename it to uppercase 'NAME' during the copy and add NAME_EN / ADMIN_LVL.
    # Some NAME_EN values are NULL (every 4th row) so rt05's null-propagation test works.
    basemap = str(DATA / "basemap.gpkg")
    if os.path.exists(basemap):
        os.remove(basemap)

    poly_lyr = QgsVectorLayer(poly_src, "src", "ogr")
    assert poly_lyr.isValid(), f"could not open {poly_src}"

    # Build a memory layer with the renamed / added fields.
    src_fields = poly_lyr.fields()
    crs_id     = poly_lyr.crs().authid()
    mem_lyr = QgsVectorLayer(f"MultiPolygon?crs={crs_id}", "boundary-polygon", "memory")
    pr = mem_lyr.dataProvider()
    new_fields = []
    for f in src_fields:
        if f.name().lower() == "name":
            new_fields.append(QgsField("NAME", QVariant.String))
        else:
            new_fields.append(QgsField(f.name(), f.type()))
    new_fields.append(QgsField("NAME_EN",   QVariant.String))
    new_fields.append(QgsField("ADMIN_LVL", QVariant.Int))
    pr.addAttributes(new_fields)
    mem_lyr.updateFields()

    n_base = poly_lyr.featureCount()
    mem_feats = []
    for i, feat in enumerate(poly_lyr.getFeatures()):
        out = QgsFeature(mem_lyr.fields())
        out.setGeometry(feat.geometry())
        for j, f in enumerate(src_fields):
            field_name = "NAME" if f.name().lower() == "name" else f.name()
            idx = mem_lyr.fields().indexOf(field_name)
            if idx >= 0:
                out.setAttribute(idx, feat.attribute(j))
        out.setAttribute(mem_lyr.fields().indexOf("NAME_EN"),
                         None if i % 4 == 0 else f"Name_EN_{i:03d}")
        out.setAttribute(mem_lyr.fields().indexOf("ADMIN_LVL"), (i % 4) + 2)
        mem_feats.append(out)
    pr.addFeatures(mem_feats)

    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName  = "boundary-polygon"
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteFile
    err, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        mem_lyr, basemap, QgsProject.instance().transformContext(), opts)
    assert err == QgsVectorFileWriter.NoError, msg

    # Remaining basemap layers added to the existing file via niva.
    # railway-line and poi-point are used by suite_2/3 (pointsalong, sample, spatialjoin, etc.)
    for src, lname in [
        (multi_src, "boundary-polygon-lvl2"),
        (poly_src,  "landuse-polygon"),
        (poly_src,  "nature_reserve-polygon"),  # poly_src ≠ multi_src so symdifference(nature_reserve, park_polygons[multi]) is non-empty
        (pt_src,    "settlement-point"),
        (poly_src,  "water-polygon"),
        (line_src,  "railway-line"),
        (pt_src,    "poi-point"),
    ]:
        niva.flow(f'load "{src}" | save "{basemap}" as {lname}')
    print(f"  basemap.gpkg  ({n_base} boundary-polygon features + railway-line + poi-point)")

    # ── study_area_bbox.gpkg ──────────────────────────────────────────────────
    study = str(DATA / "study_area_bbox.gpkg")
    niva.flow(f'load "{aoi_src}" | save "{study}"')
    print("  study_area_bbox.gpkg")

    # ── DEM (dem_clip.tif + dem.tif) ─────────────────────────────────────────
    for dest in ("dem_clip.tif", "dem.tif"):
        shutil.copy(dem, str(DATA / dest))
    print("  dem_clip.tif, dem.tif")

    # ── collected.gpkg ────────────────────────────────────────────────────────
    # park_lines + park_polygons + park_points.
    # park_polygons uses the polygon layer (same CRS, same area as basemap layers).
    # park_points uses the point layer for join/countpoints/spatialjoin tests.
    collected = str(DATA / "collected.gpkg")
    niva.flow(f'load "{line_src}"  | save "{collected}" as park_lines')
    niva.flow(f'load "{poly_src}"  | save "{collected}" as park_polygons')
    niva.flow(f'load "{pt_src}"    | save "{collected}" as park_points')
    print("  collected.gpkg  (park_lines + park_polygons + park_points)")

    # ── actual_spatialite.sqlite ──────────────────────────────────────────────
    # park_points + park_polygons + park_lines.
    # park_polygons uses multipolys (4 features) rather than the 16-feature polygon
    # layer, so that difference/union operations against water-polygon (16 polygons)
    # return non-empty results instead of cancelling out entirely.
    actual_sl = str(DATA / "actual_spatialite.sqlite")
    if os.path.exists(actual_sl):
        os.remove(actual_sl)
    niva.flow(f'load "{sl}|layername=points"   | save "{actual_sl}" as park_points')
    niva.flow(f'load "{multi_src}"             | save "{actual_sl}" as park_polygons')
    niva.flow(f'load "{sl}|layername=lines"    | save "{actual_sl}" as park_lines')
    print("  actual_spatialite.sqlite  (park_points + park_polygons[multipolys] + park_lines)")

    # ── aoism.shp + aoism.gpkg (was ~/Downloads/NiagaraBasemap/aoism.shp) ─────
    # Use the AOISM (area-of-interest) layer from example.gpkg reprojected to
    # EPSG:6346 — same Youngstown study-area polygon the Linux machine used.
    aoism_src = f"{ex}|layername=AOISM"
    niva.flow(f'load "{aoism_src}" | reproject EPSG:6346 | save "{str(DATA / "aoism.gpkg")}"')
    niva.flow(f'load "{aoism_src}" | reproject EPSG:6346 | save "{str(DATA / "aoism.shp")}"')
    print("  aoism.shp, aoism.gpkg")

    # ── order_boundary.geojson (was ~/Downloads/NiagaraOverture/…) ────────────
    niva.flow(f'load "{aoi_src}" | reproject EPSG:4326 | save "{str(DATA / "order_boundary.geojson")}"')
    print("  order_boundary.geojson")

    # ── performance.csv (was ~/Downloads/OLD/…PerformanceResults….csv) ────────
    # Synthetic aspatial table that exercises the CSV load path (t09).
    csv_path = DATA / "performance.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["Run", "Test", "Duration_ms", "Status"])
        for i in range(10):
            w.writerow([i + 1, f"test_{i:03d}", (i + 1) * 37, "PASS"])
    print("  performance.csv")

    # ── QGIS connections ──────────────────────────────────────────────────────
    s = QgsSettings()
    for k, v in [("host", PG_HOST), ("port", PG_PORT), ("database", PG_DB),
                  ("username", PG_USER), ("password", ""),
                  ("saveUsername", "true"), ("savePassword", "true"),
                  ("allowGeometrylessTables", "true")]:
        s.setValue(f"PostgreSQL/connections/localpg/{k}", v)
    s.sync()
    print(f"  registered @localpg → {PG_HOST}:{PG_PORT}/{PG_DB} as {PG_USER}")

    sl_md   = QgsProviderRegistry.instance().providerMetadata("spatialite")
    sl_conn = sl_md.createConnection(f"dbname='{actual_sl}'", {})
    sl_md.saveConnection(sl_conn, "actual_spatialite.sqlite")
    print(f"  registered @actual_spatialite.sqlite → {actual_sl}")

    # ── PostGIS fixture tables (awkward identifiers, for security + round-trip) ─
    # Save via a simple temp name first, then rename with SQL — niva's flow
    # grammar can't parse table names that contain spaces or SQL keywords.
    def _pg_load_rename(src: str, tmp: str, final: str) -> None:
        niva.flow(f'load "{src}" | save @localpg.public.{tmp} mode=replace')
        niva.flow(f'sql @localpg "DROP TABLE IF EXISTS public.\\"{final}\\""')
        niva.flow(f'sql @localpg "ALTER TABLE public.{tmp} RENAME TO \\"{final}\\""')
        print(f'  @localpg.public."{final}"')

    _pg_load_rename(line_src, "niva_tmp_roads", "My Roads")
    _pg_load_rename(pt_src,   "niva_tmp_cafe",  "café points")
    _pg_load_rename(poly_src, "niva_tmp_mixed", "Mixed.Case.Dots")
    _pg_load_rename(pt_src,   "niva_tmp_sel",   "select")
    _pg_load_rename(pt_src,   "niva_tmp_123",   "123_leading")
    _pg_load_rename(pt_src,   "niva_tmp_hash",  "name-with-dash#hash")

    # name-with-dash#hash: rename the geom column so niva must detect it by type
    niva.flow('sql @localpg "ALTER TABLE public.\\"name-with-dash#hash\\" '
              'RENAME COLUMN geom TO wkt_geometry"')

    # two_geoms: a table with two geometry columns (niva must pick the right one)
    niva.flow(f'load "{pt_src}" | save @localpg.public.two_geoms mode=replace')
    niva.flow('sql @localpg "ALTER TABLE public.two_geoms '
              'ADD COLUMN IF NOT EXISTS extra_geom geometry(Point,6346)"')
    niva.flow('sql @localpg "UPDATE public.two_geoms SET extra_geom = geom"')
    print( '  @localpg.public.two_geoms (two geometry columns)')

    print(f"\ndata/ ready at {DATA}")
    print(f"Boundary-polygon has {n_base} features.")
    print("round_trip_suite.niva PREAMBLE should check: "
          f"count(src.gpkg) == {n_base}")


if __name__ == "__main__":
    main()
