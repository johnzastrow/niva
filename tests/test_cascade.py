"""Discovery cascade: `info` → `show` → run every Source and example `show` prints.

This dogfoods the *discovery* path a CLI user actually walks: run `info` to learn the
registered `@conn` references, `show` a location to get a copy-pasteable Source (and runnable
example flows) for each layer, then `load`/pipe that Source onward. Every Source and every
example `show` advertises must round-trip back into a working flow — otherwise discovery is a
dead end.

It specifically guards the **dotted-connection round-trip**: a GeoPackage/SpatiaLite
connection's name *is* a filename with a dot (e.g. `niva_cascade.sqlite`), so the Source
`show` prints is `@niva_cascade.sqlite.<table>`. Before the shared-resolver fix, `load`
split that on the first dot and looked for a phantom `niva_cascade` connection.

Needs a working QGIS (skips cleanly otherwise). Run under QGIS's Python, e.g.::

    LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libxml2.so.16 \
    PYTHONPATH=/usr/share/qgis/python:/usr/lib/python3/dist-packages \
    python3 -m unittest tests.test_cascade
"""

import os
import re
import tempfile
import unittest

# Projected CRS (UTM 18N, metres) so the `buffer 100m` example `show` emits actually runs —
# a metric buffer on a geographic layer is (correctly) refused by niva's degrees guard.
CRS = "EPSG:26918"


def setUpModule():
    os.environ["XDG_DATA_HOME"] = tempfile.mkdtemp(prefix="niva_xdg_cascade_")
    try:
        from niva.engine.pyqgis import ensure_qgis

        ensure_qgis()
    except Exception as exc:  # ImportError or QGIS init failure
        raise unittest.SkipTest(f"QGIS not available: {exc}")


def _points(layername, coords):
    """A tiny in-memory point layer named ``layername`` in the projected test CRS."""
    from qgis.core import QgsFeature, QgsGeometry, QgsPointXY, QgsVectorLayer

    vl = QgsVectorLayer(f"Point?crs={CRS}&field=id:integer&field=name:string",
                        layername, "memory")
    pr = vl.dataProvider()
    for i, (x, y) in enumerate(coords, start=1):
        f = QgsFeature()
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
        f.setAttributes([i, f"{layername}{i}"])
        pr.addFeature(f)
    vl.updateExtents()
    return vl


def _write(vl, path, driver, layername, first):
    from qgis.core import QgsProject, QgsVectorFileWriter

    action = QgsVectorFileWriter.ActionOnExistingFile
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = driver
    opts.layerName = layername
    opts.actionOnExistingFile = (action.CreateOrOverwriteFile if first
                                 else action.CreateOrOverwriteLayer)
    QgsVectorFileWriter.writeAsVectorFormatV3(
        vl, path, QgsProject.instance().transformContext(), opts)


def _aspatial(layername):
    """A NoGeometry (aspatial) table — `show` must list this as kind `table`."""
    from qgis.core import QgsFeature, QgsVectorLayer

    vl = QgsVectorLayer("None?field=id:integer&field=name:string", layername, "memory")
    pr = vl.dataProvider()
    for i, nm in [(1, "a"), (2, "b")]:
        f = QgsFeature()
        f.setAttributes([i, nm])
        pr.addFeature(f)
    return vl


def _write_dem(path):
    """A tiny gradient DEM in the projected test CRS — enough for `hillshade`/`warp` to run."""
    import numpy as np
    from osgeo import gdal, osr

    n = 32
    ds = gdal.GetDriverByName("GTiff").Create(path, n, n, 1, gdal.GDT_Float32)
    ds.SetGeoTransform((400000.0, 10.0, 0.0, 4500000.0, 0.0, -10.0))  # 10 m pixels
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(26918)
    ds.SetProjection(srs.ExportToWkt())
    yy, xx = np.mgrid[0:n, 0:n]
    band = ds.GetRasterBand(1)
    band.WriteArray((xx + yy).astype("float32") * 3.0)  # a sloped surface
    band.FlushCache()
    ds = None


# Coordinates well inside the UTM 18N valid area (eastern US), so writes/reprojects are clean.
_COORDS = [(400000, 4500000), (400100, 4500100), (400200, 4500200)]


class TestDiscoveryCascade(unittest.TestCase):
    CONN = "niva_cascade.sqlite"  # a *dotted* connection name — the round-trip under test

    def setUp(self):
        from qgis.core import QgsProviderRegistry

        self.tmp = tempfile.mkdtemp(prefix="niva_cascade_")

        # A multi-layer SpatiaLite database, registered as a dotted @conn.
        self.db = os.path.join(self.tmp, "niva_cascade.sqlite")
        _write(_points("homes", _COORDS), self.db, "SpatiaLite", "homes", first=True)
        _write(_points("parks", _COORDS), self.db, "SpatiaLite", "parks", first=False)
        self.md = QgsProviderRegistry.instance().providerMetadata("spatialite")
        self.md.saveConnection(self.md.createConnection(f"dbname='{self.db}'", {}), self.CONN)

        # A multi-layer GeoPackage file (the file-path `show` branch).
        self.gpkg = os.path.join(self.tmp, "places.gpkg")
        _write(_points("roads", _COORDS), self.gpkg, "GPKG", "roads", first=True)
        _write(_points("places", _COORDS), self.gpkg, "GPKG", "places", first=False)

        # A small DEM (pure raster) and an aspatial table — the other two example kinds.
        self.tif = os.path.join(self.tmp, "dem.tif")
        _write_dem(self.tif)
        self.aspatial = os.path.join(self.tmp, "stats.gpkg")
        _write(_aspatial("stats"), self.aspatial, "GPKG", "stats", first=True)

        self.scratch = os.path.join(self.tmp, "scratch")
        os.makedirs(self.scratch, exist_ok=True)

    def tearDown(self):
        try:
            self.md.deleteConnection(self.CONN)  # never pollute the user's real profile
        except Exception:
            pass

    # --- helpers -------------------------------------------------------------

    def _report(self, flow):
        """Run a terminal verb with `to=<file>` and return the Markdown it wrote."""
        import niva

        out = os.path.join(self.tmp, f"report_{abs(hash(flow))}.md")
        niva.flow(f"{flow} to={out}")
        with open(out, encoding="utf-8") as fh:
            return fh.read()

    # A `show` data row: 4 pipe-free leading cells then the backticked Source, which may
    # itself contain `|` (a file Source like `<path>|layername=<layer>`). So the Source cell
    # is captured non-greedily up to the row's trailing pipe, not by a naive `|` split.
    _ROW = re.compile(r"\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|"
                      r"\s*([^|]*?)\s*\|\s*(.*?)\s*\|\s*$")

    @classmethod
    def _sources(cls, report):
        """The `(kind, ref)` of each data row in a `show` table (ref minus its backticks)."""
        rows = []
        for line in report.splitlines():
            m = cls._ROW.match(line)
            if not m or m.group(1) == "Layer" or m.group(1).startswith("---"):
                continue
            rows.append((m.group(2), m.group(5).strip("`")))
        return rows

    @staticmethod
    def _examples(report):
        """Runnable flows from the first ``    niva '…'`` block in a `show` report.

        format_show() produces two indented blocks: the runnable "Examples" section
        and the "Write into an existing container" section. The write section uses a
        literal ``@conn`` placeholder (users fill in the real name) and ``mode=append``
        into a table that doesn't exist yet, so it must not be executed by the cascade.
        Stop extracting at the write-examples header so only the standalone examples run.
        """
        flows = []
        for line in report.splitlines():
            if line.startswith("Write into an"):
                break
            if line.startswith("    niva '") and line.endswith("'"):
                flows.append(line[10:-1])  # strip leading "    niva '" and trailing "'"
        return flows

    def _assert_loads(self, kind, source):
        """`load "<source>"` (verbatim, as the tip says to copy it) yields a valid layer.
        Save target follows the kind: a raster to `.tif`, a vector/table to `.gpkg`."""
        import niva
        from qgis.core import QgsRasterLayer, QgsVectorLayer

        ext = "tif" if kind == "raster" else "gpkg"
        out = os.path.join(self.scratch, f"loaded_{abs(hash(source))}.{ext}")
        niva.flow(f'load "{source}" | save {out}')
        if kind == "raster":
            layer = QgsRasterLayer(out, "o")
            self.assertTrue(layer.isValid(), f"`load \"{source}\"` produced no valid raster")
        else:
            layer = QgsVectorLayer(out, "o", "ogr")
            self.assertTrue(layer.isValid(), f"`load \"{source}\"` produced no valid layer")
            # An aspatial table legitimately may hold rows but no geometry; only require
            # features for a spatial vector layer.
            if kind == "vector":
                self.assertGreater(layer.featureCount(), 0, f"`{source}` loaded 0 features")

    def _run_example(self, flow):
        """Run an example flow verbatim in a scratch cwd; assert its `save` target lands and
        return that target's absolute path (so the cascade can continue *into* the output).

        Examples from format_show() use ``~/`` save targets so they work from the QGIS plugin
        dock (where relative paths would resolve against the app bundle). Redirect those into
        self.scratch so test output doesn't land in the user's home directory.
        """
        import niva

        # Redirect ~/file saves into scratch — keeps test output out of the user's home dir.
        # Use a function replacement so backslashes in a Windows scratch path (e.g. C:\Users\…)
        # aren't misread as regex escapes (\U, \g, …) in the replacement string.
        flow = re.sub(r"\bsave ~/", lambda _m: f"save {self.scratch}/", flow)
        m = re.search(r"\bsave\s+(\S+)", flow)
        target = m.group(1) if m else None
        cwd = os.getcwd()
        os.chdir(self.scratch)
        try:
            niva.flow(flow)
        finally:
            os.chdir(cwd)
        if not target:
            return None
        produced = target if os.path.isabs(target) else os.path.join(self.scratch, target)
        self.assertTrue(os.path.exists(produced),
                        f"example did not produce `{target}`: {flow}")
        return produced

    def _cascade_into(self, produced):
        """Keep going past the example: an example's *output* is itself a niva source, so
        `show` it and `load` every Source it advertises. This closes the discovery loop —
        what niva writes must be re-discoverable and re-loadable, recursively."""
        report = self._report(f'show "{produced}"')
        sources = self._sources(report)
        self.assertTrue(sources, f"show found nothing in produced output `{produced}`")
        for kind, ref in sources:
            if kind in ("vector", "raster", "table"):
                self._assert_loads(kind, ref)
        return report

    # --- the cascade ---------------------------------------------------------

    def test_info_reports_the_dotted_connection(self):
        # Step 1 of the cascade: `info` is where a user learns the valid @conn references.
        from niva.engine.pyqgis import PyqgisBackend

        self.assertIn(self.CONN, PyqgisBackend().connection_names())
        report = self._report("info")
        self.assertIn(self.CONN, report,
                      "info must list the registered connection a user would then `show`")

    def test_cascade_from_connection(self):
        # Step 2: `show @conn` → Sources + examples. Step 3: every one of them runs.
        report = self._report(f"show @{self.CONN}")
        sources = self._sources(report)
        refs = {ref for _kind, ref in sources}
        # The Source is the dotted form `show` advertises — the exact string the user copies.
        self.assertIn(f"@{self.CONN}.homes", refs)
        self.assertIn(f"@{self.CONN}.parks", refs)

        for kind, ref in sources:
            if kind == "vector":
                self._assert_loads(kind, ref)  # the round-trip the fix restores

        examples = self._examples(report)
        self.assertTrue(examples, "show printed no runnable examples for the connection")
        for flow in examples:
            produced = self._run_example(flow)
            # …and keep going past the example: re-`show` and re-`load` its output.
            if produced:
                self._cascade_into(produced)

    def test_cascade_from_file(self):
        # The file-path branch: Source is `<path>|layername=<layer>` from list_layers.
        report = self._report(f"show {self.gpkg}")
        sources = self._sources(report)
        self.assertTrue(any("layername=" in ref for _k, ref in sources),
                        "a multi-layer GeoPackage Source must name its layer")
        for kind, ref in sources:
            if kind == "vector":
                self._assert_loads(kind, ref)

        for flow in self._examples(report):
            produced = self._run_example(flow)
            if produced:
                self._cascade_into(produced)

    def test_cascade_from_raster(self):
        # A pure-raster source: `show` emits `hillshade` / `warp` examples. Run both and
        # carry their outputs onward — every raster example output must be a loadable raster.
        report = self._report(f'show "{self.tif}"')
        sources = self._sources(report)
        self.assertTrue(any(k == "raster" for k, _ in sources), "show found no raster layer")
        for kind, ref in sources:
            if kind == "raster":
                self._assert_loads(kind, ref)

        examples = self._examples(report)
        self.assertTrue(any("hillshade" in e or "warp" in e for e in examples),
                        "show did not emit raster examples for a raster source")
        for flow in examples:
            produced = self._run_example(flow)
            if produced:
                self._cascade_into(produced)

    def test_cascade_from_aspatial_table(self):
        # A NoGeometry table: `show` emits `assess` / `save extract.gpkg` examples. Both must
        # run; the `save` output must round-trip back through `show` + `load`.
        report = self._report(f'show "{self.aspatial}"')
        sources = self._sources(report)
        self.assertTrue(any(k == "table" for k, _ in sources),
                        "an aspatial layer must list as kind `table`")
        for kind, ref in sources:
            if kind == "table":
                self._assert_loads(kind, ref)

        for flow in self._examples(report):
            produced = self._run_example(flow)  # `assess` has no save → None, still runs
            if produced:
                self._cascade_into(produced)

    def test_cascade_two_hops_then_show(self):
        # The full chain, several hops deep: load a discovered Source → process → save →
        # show that output → load *its* Source → process again → save → show again. Every
        # niva output must remain a valid, self-describing niva input all the way down.
        import niva
        from qgis.core import QgsVectorLayer

        report = self._report(f"show @{self.CONN}")
        first = next(ref for kind, ref in self._sources(report) if kind == "vector")

        hop1 = os.path.join(self.scratch, "hop1.gpkg")
        niva.flow(f'load "{first}" | buffer 50m | save {hop1}')
        # show the hop-1 output, take its Source, and carry it onward.
        src1 = next(ref for kind, ref in self._sources(self._report(f'show "{hop1}"'))
                    if kind == "vector")

        hop2 = os.path.join(self.scratch, "hop2.gpkg")
        niva.flow(f'load "{src1}" | reproject EPSG:3857 | save {hop2}')
        src2 = next(ref for kind, ref in self._sources(self._report(f'show "{hop2}"'))
                    if kind == "vector")

        final = QgsVectorLayer(src2, "final", "ogr")
        self.assertTrue(final.isValid())
        self.assertGreater(final.featureCount(), 0)
        self.assertEqual(final.crs().authid(), "EPSG:3857")


if __name__ == "__main__":
    unittest.main()
