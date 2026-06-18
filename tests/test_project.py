"""`project` verb — copy a QGIS project and repoint layer datasources. Mock-backed
parsing/dispatch tests (no QGIS); the real repoint logic is exercised in
test_pyqgis.py::TestPyqgisProject."""

import os
import tempfile
import unittest

from niva.engine import Engine, MockBackend
from niva.errors import FlowError
from niva.grammar import parse


def _run(text):
    backend = MockBackend()
    Engine(backend).execute(parse(text))
    return backend


class TestProjectVerb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="niva_proj_")
        self.src = os.path.join(self.tmp, "in.qgs")
        open(self.src, "w").close()  # the engine only checks it exists + extension
        self.out = os.path.join(self.tmp, "out.qgs")

    def _flow(self, tail):
        return f'project "{self.src}" {tail}'

    def test_dispatch_records_repoint(self):
        backend = _run(self._flow(f'to="{self.out}" repoint="data/basemap_clip.gpkg"'))
        call = backend.calls[-1]
        self.assertEqual(call[0], "repoint_project")
        self.assertEqual(call[1], self.src)
        self.assertEqual(call[2], self.out)
        self.assertTrue(call[3].endswith("data/basemap_clip.gpkg"))
        self.assertEqual(call[4], "fail")  # default missing policy

    def test_missing_policies_parse(self):
        for pol in ("fail", "keep", "drop"):
            backend = _run(self._flow(f'to="{self.out}" repoint="t.gpkg" missing={pol}'))
            self.assertEqual(backend.calls[-1][4], pol)

    def test_connection_target_passes_through(self):
        # An @conn target is not path-expanded; the backend resolves it.
        backend = _run(self._flow(f'to="{self.out}" repoint=@pg.niagara'))
        self.assertEqual(backend.calls[-1][3], "@pg.niagara")

    def test_rasters_option_recorded(self):
        backend = _run(self._flow(f'to="{self.out}" repoint="t.gpkg" rasters="{self.tmp}"'))
        self.assertEqual(backend.calls[-1][5], self.tmp)  # rasters dir is the 6th element

    def test_rasters_defaults_to_none(self):
        backend = _run(self._flow(f'to="{self.out}" repoint="t.gpkg"'))
        self.assertIsNone(backend.calls[-1][5])

    def test_rasters_must_be_a_directory(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" repoint="t.gpkg" rasters="{self.tmp}/nope"'))

    def _outputs_dir(self, *names):
        d = os.path.join(self.tmp, "outs")
        os.makedirs(d, exist_ok=True)
        for n in names:
            open(os.path.join(d, n), "w").close()
        return d

    def test_new_records_create_project(self):
        d = self._outputs_dir("a.gpkg", "b.gpkg")
        out = os.path.join(self.tmp, "new.qgs")
        backend = _run(f'project new from="{d}" to="{out}" crs=EPSG:4326 title="Region"')
        call = backend.calls[-1]
        self.assertEqual(call[0], "create_project")
        self.assertEqual(sorted(os.path.basename(u) for u in call[1]), ["a.gpkg", "b.gpkg"])
        self.assertEqual(call[2], out)
        self.assertEqual(call[3], "EPSG:4326")  # crs
        self.assertEqual(call[4], "Region")     # title

    def test_new_needs_from(self):
        with self.assertRaises(FlowError):
            _run(f'project new to="{self.tmp}/x.qgs"')

    def test_new_needs_to(self):
        d = self._outputs_dir("a.gpkg")
        with self.assertRaises(FlowError):
            _run(f'project new from="{d}"')

    def test_new_to_must_be_a_project(self):
        d = self._outputs_dir("a.gpkg")
        with self.assertRaises(FlowError):
            _run(f'project new from="{d}" to="{self.tmp}/x.gpkg"')

    def test_new_empty_source_is_error(self):
        d = os.path.join(self.tmp, "empty")
        os.makedirs(d)
        with self.assertRaises(FlowError):
            _run(f'project new from="{d}" to="{self.tmp}/x.qgs"')

    def test_info_records_and_writes_report(self):
        src = os.path.join(self.tmp, "p.qgs")
        open(src, "w").close()
        out = os.path.join(self.tmp, "report.md")
        backend = _run(f'project info "{src}" to="{out}"')
        self.assertIn(("read_project", src), backend.calls)
        self.assertTrue(os.path.isfile(out))
        self.assertIn("# Project", open(out).read())

    def test_info_default_output_path(self):
        src = os.path.join(self.tmp, "p.qgs")
        open(src, "w").close()
        _run(f'project info "{src}"')
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "p_info.md")))

    def test_info_bad_src_is_error(self):
        with self.assertRaises(FlowError):
            _run(f'project info "{self.tmp}/nope.qgs"')

    def test_info_unknown_option_is_error(self):
        src = os.path.join(self.tmp, "p.qgs")
        open(src, "w").close()
        with self.assertRaises(FlowError):
            _run(f'project info "{src}" repoint=x.gpkg')

    def test_bad_missing_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" repoint="t.gpkg" missing=maybe'))

    def test_missing_to_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow('repoint="t.gpkg"'))

    def test_no_repoint_is_a_copy(self):
        # repoint= is optional — `project src to=out` copies/converts without repointing.
        backend = _run(self._flow(f'to="{self.out}"'))
        call = backend.calls[-1]
        self.assertEqual(call[0], "repoint_project")
        self.assertIsNone(call[3])  # target

    def test_paths_option_recorded(self):
        backend = _run(self._flow(f'to="{self.out}" paths=relative'))
        self.assertEqual(backend.calls[-1][6], "relative")  # paths is the 7th element

    def test_bad_paths_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" paths=sideways'))

    def test_unknown_option_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" repoint="t.gpkg" mode=replace'))

    def test_src_must_exist(self):
        with self.assertRaises(FlowError):
            _run(f'project "{self.tmp}/nope.qgs" to="{self.out}" repoint="t.gpkg"')

    def test_src_must_be_a_project(self):
        notproj = os.path.join(self.tmp, "x.gpkg")
        open(notproj, "w").close()
        with self.assertRaises(FlowError):
            _run(f'project "{notproj}" to="{self.out}" repoint="t.gpkg"')

    def test_out_must_be_a_project(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.tmp}/out.gpkg" repoint="t.gpkg"'))

    def test_qgz_extension_accepted(self):
        src = os.path.join(self.tmp, "in.qgz")
        open(src, "w").close()
        backend = MockBackend()
        Engine(backend).execute(
            parse(f'project "{src}" to="{self.tmp}/o.qgz" repoint="t.gpkg"'))
        self.assertEqual(backend.calls[-1][0], "repoint_project")


if __name__ == "__main__":
    unittest.main()
