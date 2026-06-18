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

    def test_bad_missing_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" repoint="t.gpkg" missing=maybe'))

    def test_missing_to_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow('repoint="t.gpkg"'))

    def test_missing_repoint_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}"'))

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
