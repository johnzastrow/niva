#!/usr/bin/env python3
"""Verify the cookbook recipes run against the demo dataset (examples/demo/).

Runs a representative recipe from each cookbook section against the data built by
build_demo_data.niva, reporting pass / fail / skip. Database recipes (§G SpatiaLite,
§H PostGIS) register/locate a connection if one is available, else skip with a reason.

Run headless from the repo root:

    NIVA_TMPDIR=$HOME/niva_scratch \
    PYTHONPATH=$PWD:/usr/lib/python3/dist-packages:/usr/share/qgis/python \
    QT_QPA_PLATFORM=offscreen python3.14 examples/verify_cookbook.py
"""

import os
import tempfile

import niva
from niva.engine.pyqgis import ensure_qgis

ROOT = os.path.expanduser("~/Github/niva")
DEMO = f"{ROOT}/examples/demo"
V = f"{DEMO}/vectors"
EX = f"{ROOT}/examples/example.gpkg"
OUT = tempfile.mkdtemp(prefix="niva_verify_")

# (id, section, flow) — {OUT} is filled per recipe; paths point at the demo data.
RECIPES = [
    ("buffer", "A", f'load "{V}/roads.gpkg" | buffer 100m | save "{{OUT}}/o.gpkg"'),
    ("reproject", "A", f'load "{V}/parcels.gpkg" | reproject EPSG:4326 | save "{{OUT}}/o.gpkg"'),
    ("clip", "A", f'load "{V}/buildings.gpkg" | clip "{V}/aoi.gpkg" | save "{{OUT}}/o.gpkg"'),
    ("filter (synthetic zoning)", "A", f'load "{V}/parcels.gpkg" | filter "zoning = \'R1\'" | save "{{OUT}}/o.gpkg"'),
    ("centroid", "A", f'load "{V}/parcels.gpkg" | centroid | save "{{OUT}}/o.gpkg"'),
    ("filter→reproject→buffer", "B", f'load "{V}/roads.gpkg" | filter "class = \'primary\'" | reproject EPSG:6346 | buffer 100m dissolve | save "{{OUT}}/o.gpkg"'),
    ("clip→fix→dissolve", "B", f'load "{V}/parcels.gpkg" | clip "{V}/aoi.gpkg" | fix | dissolve zoning | save "{{OUT}}/o.gpkg"'),
    ("simplify→explode", "B", f'load "{V}/roads.gpkg" | simplify 5m method=area | explode | save "{{OUT}}/o.gpkg"'),
    ("keepfields", "C", f'load "{V}/parcels.gpkg" | keepfields OwnrName,zoning,ACRES | save "{{OUT}}/o.gpkg"'),
    ("join (census.csv)", "C", f'load "{V}/watersheds.gpkg" | join with="{DEMO}/census.csv" field=NHDPlusID field2=NHDPlusID fields=pop,income prefix=cen_ | save "{{OUT}}/o.gpkg"'),
    ("countpoints", "C", f'run native:countpointsinpolygon POLYGONS="{V}/parcels.gpkg" POINTS="{V}/points.gpkg" FIELD=n | save "{{OUT}}/o.gpkg"'),
    ("intersect", "D", f'load "{V}/parcels.gpkg" | intersect "{V}/floodzone.gpkg" | save "{{OUT}}/o.gpkg"'),
    ("difference", "D", f'load "{V}/parcels.gpkg" | fix | difference "{V}/buildings.gpkg" | save "{{OUT}}/o.gpkg"'),
    ("selectloc", "D", f'load "{V}/buildings.gpkg" | selectloc "{V}/floodzone.gpkg" predicate=intersect | save "{{OUT}}/o.gpkg"'),
    ("spatialjoin", "D", f'load "{V}/points.gpkg" | spatialjoin with="{V}/watersheds.gpkg" predicate=within method=first fields=NHDPlusID | save "{{OUT}}/o.gpkg"'),
    ("zonalstats (dem.tif)", "D", f'load "{V}/watersheds.gpkg" | zonalstats raster="{DEMO}/dem.tif" stats=mean,min,max prefix=elev_ | save "{{OUT}}/o.gpkg"'),
    ("each glob (layers/*.gpkg)", "E", f'each "{DEMO}/layers/*.gpkg" | reproject EPSG:6346 | save "{{OUT}}/each.gpkg"'),
    ("each container (example.gpkg)", "E", f'each "{EX}" | save "{{OUT}}/cont.gpkg"'),
    ("warp", "F", f'load "{DEMO}/dem.tif" | warp EPSG:4326 | save "{{OUT}}/o.tif"'),
    ("clipraster", "F", f'load "{DEMO}/dem.tif" | clipraster "{V}/aoi.gpkg" | save "{{OUT}}/o.tif"'),
    ("hillshade", "F", f'load "{DEMO}/dem.tif" | hillshade | save "{{OUT}}/o.tif"'),
    ("slope percent", "F", f'load "{DEMO}/dem.tif" | slope percent | save "{{OUT}}/o.tif"'),
    ("polygonize (landcover.tif)", "F", f'load "{DEMO}/landcover.tif" | polygonize field=DN | save "{{OUT}}/o.gpkg"'),
    ("gdal:contour", "K", f'load "{DEMO}/dem.tif" | run gdal:contour INTERVAL=10 FIELD_NAME=ELEV | save "{{OUT}}/o.gpkg"'),
    ("gdal:rasterize", "K", f'load "{V}/parcels.gpkg" | run gdal:rasterize FIELD=ACRES UNITS=1 WIDTH=20 HEIGHT=20 | save "{{OUT}}/o.tif"'),
    ("gdal:proximity (targets.tif)", "K", f'load "{DEMO}/targets.tif" | run gdal:proximity UNITS=0 MAX_DISTANCE=500 | save "{{OUT}}/o.tif"'),
    ("gdal:fillnodata (gappy.tif)", "K", f'load "{DEMO}/gappy.tif" | run gdal:fillnodata DISTANCE=20 | save "{{OUT}}/o.tif"'),
    ("qgis:executesql (input1)", "K", f'run qgis:executesql INPUT_DATASOURCES="{V}/roads.gpkg" INPUT_QUERY="SELECT * FROM input1 WHERE class = \'primary\'" | save "{{OUT}}/o.gpkg"'),
    ("native:dbscanclustering", "K", f'load "{V}/points.gpkg" | run native:dbscanclustering MIN_SIZE=3 EPS=500 | save "{{OUT}}/o.gpkg"'),
    ("native:joinbynearest", "K", f'load "{V}/points.gpkg" | run native:joinbynearest INPUT_2="{V}/parcels.gpkg" NEIGHBORS=1 | save "{{OUT}}/o.gpkg"'),
    ("grass:r.slope.aspect", "K", f'run grass:r.slope.aspect elevation="{DEMO}/dem.tif" format=0 slope="{{OUT}}/slope.tif"'),
    ("project info", "I", f'project info "{DEMO}/youngstown.qgs" to="{{OUT}}/info.md"'),
    ("project new", "I", f'project new from="{DEMO}/layers" to="{{OUT}}/p.qgz" crs=EPSG:6346'),
    ("from-template=example", "I", f'project from-template=example to="{{OUT}}/t.qgz" data="{V}"'),
    ("style save", "J", f'load "{V}/roads.gpkg" | style save "{{OUT}}/s.qml"'),
    ("style apply (house.qml)", "J", f'load "{V}/roads.gpkg" | save "{{OUT}}/r.gpkg" | style apply "{DEMO}/house.qml"'),
]


def register_spatialite():
    """Register youngstown.sqlite as a SpatiaLite connection `sl`; return True if it
    then exposes tables (ST_ functions usable)."""
    from qgis.core import QgsProviderRegistry

    path = f"{DEMO}/youngstown.sqlite"
    if not os.path.isfile(path):
        return False, "youngstown.sqlite not found"
    try:
        md = QgsProviderRegistry.instance().providerMetadata("spatialite")
        conn = md.createConnection(f"dbname='{path}'", {})
        md.saveConnection(conn, "sl")
        tables = [t.tableName() for t in conn.tables("")]
        return (bool(tables), f"tables: {tables}" if tables else "no tables exposed")
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:120]


def find_postgres():
    """Return a usable saved PostGIS connection name, or None."""
    from qgis.core import QgsProviderRegistry

    try:
        md = QgsProviderRegistry.instance().providerMetadata("postgres")
        names = list(md.connections().keys())
        for name in names:
            try:
                md.connections()[name].tables("public")  # probe reachability
                return name
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    return None


def run_recipe(flow):
    out = tempfile.mkdtemp(dir=OUT)
    try:
        niva.flow(flow.replace("{OUT}", out))
        return True, ""
    except Exception as exc:  # noqa: BLE001
        return False, type(exc).__name__ + ": " + str(exc).splitlines()[0][:140]


def main():
    ensure_qgis()
    results = []
    for rid, section, flow in RECIPES:
        ok, err = run_recipe(flow)
        results.append((section, rid, ok, err))

    # §G SpatiaLite
    sl_ok, sl_note = register_spatialite()
    sl_recipes = [
        ("sql @sl subset", f'sql @sl "SELECT * FROM parcels WHERE zoning = \'R1\'" | save "{{OUT}}/o.gpkg"'),
        ("sql @sl GROUP BY", f'sql @sl "SELECT zoning, COUNT(*) AS n FROM parcels GROUP BY zoning" | save "{{OUT}}/o.gpkg"'),
        ("sql @sl ST_Buffer", f'sql @sl "SELECT ST_Buffer(geometry, 50) AS geometry FROM points" | save "{{OUT}}/o.gpkg"'),
    ]
    for rid, flow in sl_recipes:
        if sl_ok:
            ok, err = run_recipe(flow)
        else:
            ok, err = None, f"@sl unavailable ({sl_note})"
        results.append(("G", rid, ok, err))

    # §H PostGIS — use any reachable saved connection
    pg = find_postgres()
    if pg:
        load_ok, load_err = run_recipe(
            f'load "{V}/roads.gpkg" | save @{pg}.public.niva_demo_roads mode=replace')
        results.append(("H", f"save @{pg}.public (load demo)", load_ok, load_err))
        pg_recipes = [
            ("sql @pg SELECT→pipe", f'sql @{pg} "SELECT * FROM niva_demo_roads WHERE class = \'primary\'" | buffer 50m | save "{{OUT}}/o.gpkg"'),
            ("sql @pg CREATE (analyse)", f'sql @{pg} "CREATE TABLE niva_demo_buf AS SELECT ST_Buffer(geom, 50) AS geom FROM niva_demo_roads"'),
            ("load @pg.table", f'load @{pg}.public.niva_demo_roads | save "{{OUT}}/o.gpkg"'),
        ]
        for rid, flow in pg_recipes:
            ok, err = run_recipe(flow)
            results.append(("H", rid, ok, err))
    else:
        results.append(("H", "PostGIS recipes", None, "no reachable saved connection"))

    # report
    print("\n# Cookbook verification against examples/demo/\n")
    print(f"{'§':<3} {'recipe':<34} result")
    print("-" * 70)
    npass = nfail = nskip = 0
    for section, rid, ok, err in results:
        if ok is True:
            mark, npass = "PASS", npass + 1
        elif ok is False:
            mark, nfail = "FAIL", nfail + 1
        else:
            mark, nskip = "SKIP", nskip + 1
        line = f"{section:<3} {rid:<34} {mark}"
        if err:
            line += f"  — {err}"
        print(line)
    print("-" * 70)
    print(f"{npass} passed, {nfail} failed, {nskip} skipped, of {len(results)} recipes")
    print(f"\nSpatiaLite @sl: {'available' if sl_ok else 'skipped'} ({sl_note})")
    print(f"PostGIS: {'using @'+pg if pg else 'skipped (no connection)'}")


if __name__ == "__main__":
    main()
