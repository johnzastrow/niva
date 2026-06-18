"""`style` verb — apply/save a `.qml` style or `.qmd` metadata sidecar. Mock-backed
parsing/dispatch tests; the real apply/persist behaviour is in
test_pyqgis.py::TestPyqgisStyle."""

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


class TestStyleVerb(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="niva_style_")
        self.gpkg = os.path.join(self.tmp, "a.gpkg")
        open(self.gpkg, "w").close()
        self.qml = os.path.join(self.tmp, "s.qml")
        open(self.qml, "w").close()  # engine checks `apply` source exists

    def _flow(self, tail):
        return f'load "{self.gpkg}" | style {tail}'

    def test_save_records(self):
        out = os.path.join(self.tmp, "out.qml")
        backend = _run(self._flow(f'save "{out}"'))
        self.assertEqual(backend.calls[-1], ("style", "save", out))

    def test_apply_records(self):
        backend = _run(self._flow(f'apply "{self.qml}"'))
        self.assertEqual(backend.calls[-1], ("style", "apply", self.qml))

    def test_qmd_metadata_extension_accepted(self):
        out = os.path.join(self.tmp, "m.qmd")
        backend = _run(self._flow(f'save "{out}"'))
        self.assertEqual(backend.calls[-1][2], out)

    def test_is_pass_through(self):
        # `style` returns the layer so a save can follow.
        backend = _run(self._flow(f'apply "{self.qml}" | save "{self.tmp}/o.gpkg"'))
        self.assertIn(("save", f"{self.tmp}/o.gpkg"), backend.calls)

    def test_bad_action_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'frobnicate "{self.qml}"'))

    def test_bad_extension_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'save "{self.tmp}/x.txt"'))

    def test_apply_missing_file_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow(f'apply "{self.tmp}/nope.qml"'))

    def test_needs_a_loaded_layer(self):
        with self.assertRaises(FlowError):
            _run(f'style save "{self.tmp}/o.qml"')  # no `load` first

    def test_wrong_arity_is_error(self):
        with self.assertRaises(FlowError):
            _run(self._flow("save"))


if __name__ == "__main__":
    unittest.main()
