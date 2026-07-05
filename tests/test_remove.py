"""Tests for the `remove` verb — the pure deletion policy and the engine's safety gate.

Pure Python (MockBackend + real temp files; no QGIS). See docs/planning/18-remove-verb-design.md.
"""

import os
import tempfile
import unittest

from niva import remove_policy as rp
from niva.engine import Engine, MockBackend
from niva.errors import FlowError
from niva.grammar import parse


def run(text):
    Engine(MockBackend()).execute(parse(text))


class TestRemovePolicy(unittest.TestCase):
    """The pure, filesystem-free policy module."""

    def test_conn_ref_and_glob_detection(self):
        self.assertTrue(rp.is_conn_ref("@pg.public.roads"))
        self.assertFalse(rp.is_conn_ref("roads.gpkg"))
        self.assertTrue(rp.is_glob("out/*.gpkg"))
        self.assertTrue(rp.is_glob("t[12].shp"))
        self.assertFalse(rp.is_glob("plain.gpkg"))

    def test_allowlist_is_by_extension_case_insensitive(self):
        self.assertTrue(rp.on_allowlist("/x/ROADS.GPKG"))
        self.assertTrue(rp.on_allowlist("a.tif"))
        self.assertFalse(rp.on_allowlist("notes.md"))
        self.assertFalse(rp.on_allowlist("script.py"))
        self.assertFalse(rp.on_allowlist("data.csv"))

    def test_shapefile_family(self):
        fam = rp.family("/d/roads.shp")
        for must in ("/d/roads.shx", "/d/roads.dbf", "/d/roads.prj", "/d/roads.cpg"):
            self.assertIn(must, fam)
        self.assertNotIn("/d/roads.shp", fam)  # never includes the primary

    def test_gpkg_and_qgs_families(self):
        gp = rp.family("/d/out.gpkg")
        self.assertIn("/d/out.gpkg-wal", gp)
        self.assertIn("/d/out.gpkg-shm", gp)
        self.assertIn("/d/out_attachments.zip", gp)
        qgs = rp.family("/d/map.qgs")
        self.assertIn("/d/map_attachments.zip", qgs)  # fixes the harness leak

    def test_generic_sweep_applies_to_any_primary(self):
        fam = rp.family("/d/dem.tif")
        self.assertIn("/d/dem.tif.aux.xml", fam)
        self.assertIn("/d/dem.qml", fam)
        self.assertEqual(len(fam), len(set(fam)))  # de-duplicated


class TestRemoveGate(unittest.TestCase):
    """The engine's ordered safety gate and deletion behaviour (real temp files)."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="niva_rm_")

    def _touch(self, name):
        p = os.path.join(self.tmp, name)
        with open(p, "w") as fh:
            fh.write("x")
        return p

    def test_deletes_primary_and_sidecar_family(self):
        for ext in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
            self._touch("roads" + ext)
        run(f'remove "{os.path.join(self.tmp, "roads.shp")}"')
        self.assertEqual(os.listdir(self.tmp), [], "shp + all sidecars should be gone")

    def test_dryrun_deletes_nothing(self):
        gpkg = self._touch("out.gpkg")
        self._touch("out.gpkg-wal")
        run(f'remove "{gpkg}" -dryrun')
        self.assertTrue(os.path.exists(gpkg))
        self.assertTrue(os.path.exists(gpkg + "-wal"))

    def test_force_deletes_non_allowlisted_exact_path_only(self):
        py = self._touch("keep.py")
        aux = self._touch(
            "keep.py.aux.xml"
        )  # would be a sidecar — but force is exact-only
        run(f'remove "{py}" force')
        self.assertFalse(os.path.exists(py))
        self.assertTrue(
            os.path.exists(aux), "force deletes only the named file, no family"
        )

    def test_refuse_non_allowlisted_without_force(self):
        md = self._touch("report.md")
        with self.assertRaises(FlowError) as cm:
            run(f'remove "{md}"')
        self.assertIn("force", str(cm.exception))  # the message tells you the way out
        self.assertTrue(os.path.exists(md))

    def test_refuse_conn_ref(self):
        with self.assertRaises(FlowError) as cm:
            run("remove @pg.public.roads")
        self.assertIn("DROP TABLE", str(cm.exception))

    def test_refuse_glob(self):
        with self.assertRaises(FlowError) as cm:
            run(f'remove "{self.tmp}/*.gpkg"')
        self.assertIn("each", str(cm.exception))

    def test_refuse_directory(self):
        with self.assertRaises(FlowError) as cm:
            run(f'remove "{self.tmp}"')
        self.assertIn("director", str(cm.exception).lower())

    def test_missing_path_is_idempotent(self):
        # No error: a cleanup verb must be safe to re-run.
        run(f'remove "{os.path.join(self.tmp, "never.gpkg")}"')

    def test_no_options_allowed(self):
        with self.assertRaises(FlowError):
            run(f'remove "{self._touch("a.gpkg")}" mode=force')

    def test_batch_each_remove_dedupes_and_clears(self):
        for n in ("a", "b", "c"):
            self._touch(n + ".gpkg")
            self._touch(n + ".gpkg-wal")
        run(f'each "{self.tmp}/*.gpkg" | remove')
        self.assertEqual(os.listdir(self.tmp), [])


if __name__ == "__main__":
    unittest.main()
