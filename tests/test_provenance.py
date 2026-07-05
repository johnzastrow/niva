"""Provenance sidecar tests — the engine persists lineage for file outputs that bypass
`save`'s metadata path (point clouds). Pure Python via MockBackend.

Run: ``python -m unittest tests.test_provenance``.
"""

import os
import tempfile
import unittest

from niva.engine import Engine, MockBackend
from niva.engine.layer import SOURCE, Layer
from niva.grammar import parse


class _PointCloudBackend(MockBackend):
    """A MockBackend whose `run` escape hatch returns a file-backed *point cloud* — the
    shape a `run pdalcli:*` output has — so the engine's sidecar hook fires."""

    def __init__(self, out_path):
        super().__init__()
        self._out = out_path

    def run_raw(
        self, algorithm, params, *, input_layer=None, progress=None, cancel=None
    ):
        self.calls.append(("run", algorithm, params))
        return Layer(SOURCE, self._out, facet="pointcloud", name="cloud")


class TestProvenanceSidecar(unittest.TestCase):
    def test_pointcloud_output_triggers_sidecar_with_full_lineage(self):
        tmp = tempfile.mkdtemp(prefix="niva_prov_")
        out = os.path.join(tmp, "ground.laz")
        open(out, "wb").write(b"LASF")  # a real file so os.path.isfile passes
        be = _PointCloudBackend(out)
        Engine(be).execute(
            parse(f'load tile.las | run pdalcli:translate output="{out}"')
        )
        sidecars = [c for c in be.calls if c[0] == "sidecar"]
        self.assertEqual(len(sidecars), 1)
        _, dest, lineage = sidecars[0]
        self.assertEqual(dest, out)
        # lineage carries BOTH the load and the creating pdalcli op
        self.assertTrue(any("load tile.las" in e for e in lineage))
        self.assertTrue(any("pdalcli:translate" in e for e in lineage))

    def test_no_sidecar_for_ordinary_layer(self):
        # A normal vector result (MEMORY, not a file-backed point cloud) writes no sidecar.
        be = MockBackend()
        Engine(be).execute(parse("load a.gpkg | buffer 5m | save out.gpkg"))
        self.assertFalse(any(c[0] == "sidecar" for c in be.calls))

    def test_no_sidecar_when_pointcloud_path_absent(self):
        # A point-cloud handle whose file does not exist must not attempt a sidecar.
        be = _PointCloudBackend("/no/such/file.laz")
        Engine(be).execute(
            parse('load tile.las | run pdalcli:translate output="/no/such/file.laz"')
        )
        self.assertFalse(any(c[0] == "sidecar" for c in be.calls))


if __name__ == "__main__":
    unittest.main()
