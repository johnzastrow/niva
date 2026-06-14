"""niva integration test — proven flows against real GIS data.

These are the flows that were validated by hand against the marimo_qgis example
dataset (a 24-layer Youngstown, NY GeoPackage + a wandering-cat shapefile). They
exercise the *whole* stack on real geodata: load (incl. GeoPackage sublayers),
assess, the degrees-mismatch safety guard, reproject/buffer/dissolve/clip,
metadata + auto-lineage, and the `run` escape hatch.

**Non-destructive:** sources are only read; every output is written under a fresh
temp directory.

Requires QGIS — run via ``tests/integration/run.sh`` (which sets PYTHONPATH to
QGIS's bindings) or::

    PYTHONPATH=/usr/share/qgis/python:. /usr/bin/python3 tests/integration/integration_flows.py

Data locations default to the marimo_qgis example and can be overridden::

    NIVA_TEST_GPKG=/path/example.gpkg  NIVA_TEST_SHP=/path/cat.shp

If the data is absent the script SKIPs (exit 0); a real failure exits non-zero.
"""

import os
import sys
import tempfile

GPKG = os.environ.get(
    "NIVA_TEST_GPKG", "/home/jcz/Github/marimo_qgis/example/example.gpkg"
)
SHP = os.environ.get(
    "NIVA_TEST_SHP", "/home/jcz/Github/marimo_qgis/example/wandering_cat.shp"
)

_results = []


def check(name, ok, detail=""):
    _results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def main():
    if not (os.path.exists(GPKG) and os.path.exists(SHP)):
        print(f"SKIP  integration: test data not found\n"
              f"      gpkg={GPKG} (exists={os.path.exists(GPKG)})\n"
              f"      shp ={SHP} (exists={os.path.exists(SHP)})")
        return 0

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import niva
    from niva.engine.pyqgis import ensure_qgis, owned_app
    from niva.errors import FlowError
    from qgis.core import QgsVectorLayer, QgsWkbTypes

    ensure_qgis()

    def feats(path, layername=None):
        uri = f"{path}|layername={layername}" if layername else path
        layer = QgsVectorLayer(uri, "x", "ogr")
        return layer.featureCount() if layer.isValid() else None

    def geom(path, layername):
        layer = QgsVectorLayer(f"{path}|layername={layername}", "x", "ogr")
        return QgsWkbTypes.displayString(layer.wkbType())

    out = tempfile.mkdtemp(prefix="niva_integration_")

    # 1. assess deep on real parcels (a few thousand polygons)
    niva.flow(f'load "{GPKG}|layername=parcels" | assess deep to {out}/parcels.md')
    report = read(f"{out}/parcels.md")
    check("assess deep parcels",
          "## Quality checks" in report and "**Features:**" in report,
          "quality report written")

    # 2. SAFETY: a linear distance on a geographic (EPSG:4326) layer must fail loud
    try:
        niva.flow(f'load "{GPKG}|layername=ny_ytown_buildings" | buffer 10m | save {out}/x.gpkg')
        check("degrees guard", False, "no error raised!")
    except FlowError as exc:
        check("degrees guard",
              "degrees" in str(exc) and "reproject" in str(exc).lower(),
              "linear buffer on 4326 rejected")

    # 3. reproject (4326 -> 26918) then buffer + dissolve
    niva.flow(f'load "{GPKG}|layername=ny_ytown_buildings" | reproject EPSG:26918 '
              f'| buffer 10m dissolve | save {out}/buildings_buf.gpkg')
    check("reproject + buffer + dissolve",
          feats(f"{out}/buildings_buf.gpkg", "buildings_buf") == 1,
          "dissolved to 1 feature")

    # 4. buffer directly on a projected (metre) layer
    niva.flow(f'load "{GPKG}|layername=ny_youngstown" | buffer 100m | save {out}/town_buf.gpkg')
    check("buffer on projected layer", feats(f"{out}/town_buf.gpkg", "town_buf") == 1)

    # 5. clip buildings by the town boundary (count drops, stays > 0)
    total = feats(f"{GPKG}", "ny_ytown_buildings")
    niva.flow(f'load "{GPKG}|layername=ny_ytown_buildings" | reproject EPSG:26918 '
              f'| clip "{GPKG}|layername=ny_youngstown" | save {out}/clipped.gpkg')
    clipped = feats(f"{out}/clipped.gpkg", "clipped")
    check("clip by overlay", clipped is not None and 0 < clipped <= total,
          f"{clipped} of {total} buildings inside town")

    # 6. metadata + auto-lineage round-trip
    niva.flow(f'load "{GPKG}|layername=gnis" | metadata set title="GNIS names" '
              f'keywords=names,gnis | save {out}/gnis.gpkg')
    md = QgsVectorLayer(f"{out}/gnis.gpkg|layername=gnis", "g", "ogr").metadata()
    check("metadata set persists", md.title() == "GNIS names", md.title())
    check("auto-lineage to history",
          any("metadata set" in h for h in md.history()),
          f"{len(md.history())} history items")

    # 7. `run` escape hatch on a real, un-aliased algorithm
    gnis_n = feats(f"{GPKG}", "gnis")
    niva.flow(f'load "{GPKG}|layername=gnis" | run native:centroids | save {out}/centroids.gpkg')
    check("run native:centroids",
          feats(f"{out}/centroids.gpkg", "centroids") == gnis_n, f"{gnis_n} points")

    # 8. the wandering cat: 4326 line path -> reproject -> buffered "territory"
    niva.flow(f"load {SHP} | assess deep to {out}/cat.md")
    cat_report = read(f"{out}/cat.md")
    check("assess shapefile", "**Features:**" in cat_report)
    niva.flow(f'load {SHP} | reproject EPSG:26918 | buffer 50m dissolve '
              f'| metadata set title="Wandering cat territory" | save {out}/cat_territory.gpkg')
    check("cat territory (line -> polygon)",
          geom(f"{out}/cat_territory.gpkg", "cat_territory").endswith("Polygon")
          and feats(f"{out}/cat_territory.gpkg", "cat_territory") == 1,
          "buffered path dissolved to one polygon")

    passed = sum(1 for r in _results if r)
    print(f"\n{passed}/{len(_results)} checks passed   (outputs in {out})")
    code = 0 if passed == len(_results) else 1

    # Tear QGIS down cleanly and hard-exit so the interpreter-shutdown segfault does
    # not clobber our exit code (see niva/engine/pyqgis.ensure_qgis).
    app = owned_app()
    if app is not None:
        sys.stdout.flush()
        sys.stderr.flush()
        app.exitQgis()
        os._exit(code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
