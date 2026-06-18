#!/usr/bin/env python3
"""Regenerate the bundled `example` template under ``niva/templates/``.

A niva *template* is just a saved QGIS project (its print layouts + styled layers); its
layers are the **slots** that ``project from-template=`` repoints to your same-named data
(matched by the layer's display name). See docs/templates.md for the full element reference.

This builds a deliberately **fully-populated** example so users can open it in QGIS and see
exactly what a good template contains — three distinctly-styled vector slots (``boundary``
polygon, ``roads`` line, ``places`` point), a print layout (title / map / legend / scale
bar), a spatial bookmark, and a project title + CRS. The slots point at sibling placeholder
GeoPackages via **relative** paths, so the committed template is self-contained and portable;
instantiating it repoints the slots to the user's ``boundary``/``roads``/``places`` data.

Run headless against a real QGIS (the project's python3.14 + PyQGIS recipe), from the repo
root:

    PYTHONPATH=$PWD:/usr/lib/python3/dist-packages:/usr/share/qgis/python \
        QT_QPA_PLATFORM=offscreen python3.14 templates/build_example.py

Re-run whenever the example design changes; commit the regenerated ``niva/templates/*``.
"""

import os

from niva.engine.pyqgis import ensure_qgis

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "niva", "templates")
CRS = "EPSG:4326"
# A small AOI near Niagara (matches the project's worked example), in lon/lat.
_BOUNDARY = [(-79.10, 43.06), (-79.02, 43.06), (-79.02, 43.12), (-79.10, 43.12)]
_ROADS = [[(-79.09, 43.07), (-79.04, 43.08), (-79.03, 43.11)]]
_PLACES = [(-79.08, 43.08), (-79.05, 43.10), (-79.06, 43.07)]


def _write(path, geom_type, name, features):
    """Write a one-layer GeoPackage ``name`` of ``geom_type`` with the given geometries."""
    from qgis.core import (QgsFeature, QgsField, QgsPointXY, QgsProject,
                           QgsVectorFileWriter, QgsVectorLayer)
    from qgis.PyQt.QtCore import QVariant

    vl = QgsVectorLayer(f"{geom_type}?crs={CRS}", name, "memory")
    dp = vl.dataProvider()
    dp.addAttributes([QgsField("id", QVariant.Int), QgsField("label", QVariant.String)])
    vl.updateFields()
    for i, g in enumerate(features):
        f = QgsFeature(vl.fields())
        f.setGeometry(g)
        f.setAttributes([i, f"{name}-{i}"])
        dp.addFeature(f)
    vl.updateExtents()
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = name
    if os.path.exists(path):
        os.remove(path)
    QgsVectorFileWriter.writeAsVectorFormatV3(
        vl, path, QgsProject.instance().transformContext(), opts)
    _ = QgsPointXY  # referenced by callers building geometries


def _placeholders():
    from qgis.core import QgsGeometry, QgsPointXY

    _write(os.path.join(OUT_DIR, "boundary.gpkg"), "Polygon", "boundary",
           [QgsGeometry.fromPolygonXY([[QgsPointXY(x, y) for x, y in _BOUNDARY]])])
    _write(os.path.join(OUT_DIR, "roads.gpkg"), "LineString", "roads",
           [QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in line]) for line in _ROADS])
    _write(os.path.join(OUT_DIR, "places.gpkg"), "Point", "places",
           [QgsGeometry.fromPointXY(QgsPointXY(x, y)) for x, y in _PLACES])


def _slot(proj, name, *, symbol):
    from qgis.core import QgsVectorLayer

    gpkg = os.path.join(OUT_DIR, f"{name}.gpkg")
    vl = QgsVectorLayer(f"{gpkg}|layername={name}", name, "ogr")
    if not vl.isValid():
        raise SystemExit(f"placeholder `{name}` failed to load")
    vl.renderer().setSymbol(symbol)
    proj.addMapLayer(vl)
    return vl


def build_example():
    from qgis.core import (Qgis, QgsBookmark, QgsCoordinateReferenceSystem, QgsFillSymbol,
                           QgsLayoutItemLabel, QgsLayoutItemLegend, QgsLayoutItemMap,
                           QgsLayoutItemScaleBar, QgsLayoutPoint, QgsLayoutSize,
                           QgsLineSymbol, QgsMarkerSymbol, QgsPrintLayout, QgsProject,
                           QgsRectangle, QgsReferencedRectangle, QgsUnitTypes)

    os.makedirs(OUT_DIR, exist_ok=True)
    _placeholders()

    proj = QgsProject()
    proj.setTitle("Example Map")
    crs = QgsCoordinateReferenceSystem(CRS)
    proj.setCrs(crs)

    boundary = _slot(proj, "boundary", symbol=QgsFillSymbol.createSimple(
        {"color": "0,0,0,0", "outline_color": "#33a02c", "outline_width": "0.8"}))
    _slot(proj, "roads", symbol=QgsLineSymbol.createSimple(
        {"color": "#e31a1c", "width": "0.6"}))
    _slot(proj, "places", symbol=QgsMarkerSymbol.createSimple(
        {"name": "circle", "color": "#1f78b4", "size": "3"}))

    # A print layout: title, map (framed to the AOI), legend, scale bar.
    lay = QgsPrintLayout(proj)
    lay.initializeDefaults()
    lay.setName("Map")
    title = QgsLayoutItemLabel(lay)
    title.setText("Example Map")
    title.adjustSizeToText()
    title.attemptMove(QgsLayoutPoint(10, 6, QgsUnitTypes.LayoutMillimeters))
    lay.addLayoutItem(title)
    mp = QgsLayoutItemMap(lay)
    mp.setRect(0, 0, 180, 130)
    mp.attemptMove(QgsLayoutPoint(10, 20, QgsUnitTypes.LayoutMillimeters))
    mp.attemptResize(QgsLayoutSize(180, 130, QgsUnitTypes.LayoutMillimeters))
    mp.setExtent(boundary.extent())
    lay.addLayoutItem(mp)
    legend = QgsLayoutItemLegend(lay)
    legend.setLinkedMap(mp)
    legend.attemptMove(QgsLayoutPoint(195, 20, QgsUnitTypes.LayoutMillimeters))
    lay.addLayoutItem(legend)
    bar = QgsLayoutItemScaleBar(lay)
    bar.setLinkedMap(mp)
    bar.applyDefaultSize()
    bar.attemptMove(QgsLayoutPoint(10, 155, QgsUnitTypes.LayoutMillimeters))
    lay.addLayoutItem(bar)
    proj.layoutManager().addLayout(lay)

    # A spatial bookmark covering the AOI (a jump-to for the compiled map).
    ext = boundary.extent()
    bm = QgsBookmark()
    bm.setName("Study Area")
    bm.setExtent(QgsReferencedRectangle(QgsRectangle(ext), crs))
    proj.bookmarkManager().addBookmark(bm)

    # Relative path storage → slots read `./boundary.gpkg` etc.: portable + self-contained.
    proj.setFilePathStorage(Qgis.FilePathType.Relative)
    out = os.path.join(OUT_DIR, "example.qgz")
    if not proj.write(out):
        raise SystemExit(f"could not write {out}")
    print(f"wrote {out} with slots boundary/roads/places + layout 'Map' + bookmark")


if __name__ == "__main__":
    ensure_qgis()
    build_example()
