"""`call` execution tests (docs/planning/02, 10). Pure Python via MockBackend.

Run: ``python -m unittest discover -s tests`` (or ``pytest``).
"""

import os
import tempfile
import unittest

from niva.engine import Engine, MockBackend
from niva.errors import FlowError
from niva.grammar import parse


class TestCall(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="niva_call_")

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return path

    def run_file(self, name):
        backend = MockBackend()
        path = os.path.join(self.dir, name)
        with open(path, encoding="utf-8") as fh:
            program = parse(fh.read(), file=path)
        result = Engine(backend).execute(program, base_dir=self.dir)
        return backend, result

    def test_call_runs_the_other_files_flow(self):
        self.write("acquire.niva", "load source.gpkg | save work.gpkg")
        self.write("main.niva", "call acquire.niva\nload work.gpkg | buffer 10m | save out.gpkg")
        backend, _ = self.run_file("main.niva")
        kinds = [c[0] for c in backend.calls]
        # acquire's load+save, then main's load+run+save
        self.assertEqual(kinds, ["load", "save", "load", "run", "save"])

    def test_relative_path_resolves_from_calling_file(self):
        os.mkdir(os.path.join(self.dir, "sub"))
        self.write("sub/child.niva", "load a.gpkg | save b.gpkg")
        self.write("parent.niva", "call sub/child.niva")
        backend, _ = self.run_file("parent.niva")
        self.assertEqual([c[0] for c in backend.calls], ["load", "save"])

    def test_nested_calls(self):
        self.write("c.niva", "load c.gpkg | save c_out.gpkg")
        self.write("b.niva", "call c.niva\nload b.gpkg | save b_out.gpkg")
        self.write("a.niva", "call b.niva\nload a.gpkg | save a_out.gpkg")
        backend, _ = self.run_file("a.niva")
        # depth-first: c, then b's own flow, then a's own flow
        saved = [c[1] for c in backend.calls if c[0] == "save"]
        self.assertEqual(saved, ["c_out.gpkg", "b_out.gpkg", "a_out.gpkg"])

    def test_result_is_subprogram_last_layer(self):
        self.write("tail.niva", "load t.gpkg | save final.gpkg")
        self.write("main.niva", "load x.gpkg | save y.gpkg\ncall tail.niva")
        _, result = self.run_file("main.niva")
        self.assertEqual(result.ref, "final.gpkg")

    # --- errors --------------------------------------------------------------

    def test_self_cycle(self):
        self.write("loop.niva", "call loop.niva")
        with self.assertRaises(FlowError) as ctx:
            self.run_file("loop.niva")
        self.assertIn("cycle", str(ctx.exception))

    def test_indirect_cycle(self):
        self.write("a.niva", "call b.niva")
        self.write("b.niva", "call a.niva")
        with self.assertRaises(FlowError) as ctx:
            self.run_file("a.niva")
        self.assertIn("cycle", str(ctx.exception))

    def test_missing_called_file(self):
        self.write("main.niva", "call nope.niva")
        with self.assertRaises(FlowError) as ctx:
            self.run_file("main.niva")
        self.assertIn("nope.niva", str(ctx.exception))

    def test_error_in_called_file_propagates(self):
        self.write("bad.niva", "buffer 10m")  # op before load
        self.write("main.niva", "call bad.niva")
        with self.assertRaises(FlowError) as ctx:
            self.run_file("main.niva")
        self.assertIn("load", str(ctx.exception))

    def test_same_file_called_twice_is_not_a_cycle(self):
        self.write("once.niva", "load o.gpkg | save o_out.gpkg")
        self.write("main.niva", "call once.niva\ncall once.niva")
        backend, _ = self.run_file("main.niva")
        self.assertEqual([c[0] for c in backend.calls], ["load", "save", "load", "save"])


if __name__ == "__main__":
    unittest.main()
