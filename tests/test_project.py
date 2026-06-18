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

    def test_bookmark_union(self):
        backend = _run(self._flow(f'to="{self.out}" bookmark="AOI"'))
        self.assertEqual(backend.calls[-1][7], {"name": "AOI", "at": None, "width": None})

    def test_bookmark_at_width(self):
        backend = _run(self._flow(f'to="{self.out}" bookmark="AOI" at="10,20" width=400'))
        self.assertEqual(backend.calls[-1][7], {"name": "AOI", "at": (10.0, 20.0), "width": 400.0})

    def test_bookmark_at_scale_converts_to_width(self):
        backend = _run(self._flow(f'to="{self.out}" bookmark="AOI" at="10,20" scale=1000'))
        self.assertEqual(backend.calls[-1][7]["width"], 500.0)  # scale * 0.5 m ref

    def test_bookmark_at_needs_scale_or_width(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" bookmark="AOI" at="10,20"'))

    def test_bookmark_scale_needs_at(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" bookmark="AOI" scale=1000'))

    def test_at_without_bookmark_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" at="1,2" width=5'))

    def test_bookmark_bad_at_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'to="{self.out}" bookmark="AOI" at="nope" width=5'))

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


class TestProjectFromTemplate(unittest.TestCase):
    """`project from-template=<name|path> to= data=` — parsing/dispatch (Mock-backed).
    The real template instantiation runs in test_pyqgis.py::TestPyqgisProject."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="niva_tmpl_")
        self.template = os.path.join(self.tmp, "report.qgz")
        open(self.template, "w").close()
        self.out = os.path.join(self.tmp, "out.qgz")
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data, exist_ok=True)
        for n in ("roads.gpkg", "parcels.gpkg"):
            open(os.path.join(self.data, n), "w").close()

    def _run(self, tail):
        backend = MockBackend()
        Engine(backend).execute(parse(f"project {tail}"))
        return backend

    def test_path_template_builds_slot_map(self):
        backend = self._run(f'from-template="{self.template}" to="{self.out}" data="{self.data}"')
        call = backend.calls[-1]
        self.assertEqual(call[0], "repoint_project")
        self.assertEqual(call[1], self.template)  # src is the template
        self.assertEqual(call[2], self.out)
        target = call[3]
        self.assertIsInstance(target, dict)  # the {name: uri} slot map
        self.assertEqual(set(target), {"roads", "parcels"})
        self.assertTrue(target["roads"].endswith("roads.gpkg"))

    def test_default_missing_is_keep(self):
        # Templates default to keep so unmatched slots preserve layout structure.
        backend = self._run(f'from-template="{self.template}" to="{self.out}" data="{self.data}"')
        self.assertEqual(backend.calls[-1][4], "keep")

    def test_missing_override(self):
        backend = self._run(
            f'from-template="{self.template}" to="{self.out}" data="{self.data}" missing=drop')
        self.assertEqual(backend.calls[-1][4], "drop")

    def test_glob_data_source(self):
        backend = self._run(
            f'from-template="{self.template}" to="{self.out}" data="{self.data}/*.gpkg"')
        self.assertEqual(set(backend.calls[-1][3]), {"roads", "parcels"})

    def test_named_template_resolves_from_env(self):
        lib = os.path.join(self.tmp, "lib")
        os.makedirs(lib, exist_ok=True)
        open(os.path.join(lib, "atlas.qgz"), "w").close()
        os.environ["NIVA_TEMPLATES"] = lib
        try:
            backend = self._run(f'from-template=atlas to="{self.out}" data="{self.data}"')
        finally:
            del os.environ["NIVA_TEMPLATES"]
        self.assertTrue(backend.calls[-1][1].endswith("atlas.qgz"))

    def test_unknown_named_template_is_error(self):
        os.environ["NIVA_TEMPLATES"] = self.tmp  # no .qgz named "ghost" here
        try:
            with self.assertRaises(FlowError):
                self._run(f'from-template=ghost to="{self.out}" data="{self.data}"')
        finally:
            del os.environ["NIVA_TEMPLATES"]

    def test_missing_data_is_error(self):
        with self.assertRaises(FlowError):
            self._run(f'from-template="{self.template}" to="{self.out}"')

    def test_empty_data_is_error(self):
        empty = os.path.join(self.tmp, "empty")
        os.makedirs(empty, exist_ok=True)
        with self.assertRaises(FlowError):
            self._run(f'from-template="{self.template}" to="{self.out}" data="{empty}"')

    def test_to_must_be_a_project(self):
        with self.assertRaises(FlowError):
            self._run(
                f'from-template="{self.template}" to="{self.tmp}/o.gpkg" data="{self.data}"')

    def test_template_path_must_be_a_project(self):
        notproj = os.path.join(self.tmp, "x.gpkg")
        open(notproj, "w").close()
        with self.assertRaises(FlowError):
            self._run(f'from-template="{notproj}" to="{self.out}" data="{self.data}"')

    def test_unexpected_option_is_error(self):
        with self.assertRaises(FlowError):
            self._run(
                f'from-template="{self.template}" to="{self.out}" data="{self.data}" repoint=x')


if __name__ == "__main__":
    unittest.main()
