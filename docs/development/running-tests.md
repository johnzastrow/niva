# Running the test suite

niva's tests are plain stdlib [`unittest`](https://docs.python.org/3/library/unittest.html)
— no third-party test runner is required. Because niva runs inside QGIS's own
Python interpreter, the suite must be run with that same interpreter so the
`qgis.*` bindings import. `pytest` works too (it discovers the same tests) but is
only an optional convenience listed under the `dev` extra; the canonical
invocation below uses `unittest`.

## Quick start

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

If QGIS's bindings are on the default path, that's all you need. Most tests use a
mock backend and run without a working QGIS install; the QGIS-dependent tests
skip themselves when the bindings are absent.

## When the bindings aren't on the default path

QGIS ships its Python bindings outside the normal `site-packages`, so you may
need to point the interpreter at them. The exact paths are distribution-specific;
on a typical Debian/Ubuntu-style system with a system QGIS they look like:

```bash
export PYTHONPATH=/usr/share/qgis/python:/usr/lib/python3/dist-packages
python3 -m unittest discover -s tests -v
```

- `/usr/share/qgis/python` holds the compiled bindings (`_core.so`, …).
- `/usr/lib/python3/dist-packages` holds PyQt (e.g. `PyQt6`), which the bindings
  import.

Use the same Python version QGIS was built against — check with
`qgis_process --version`, which prints the Qt, Python, and GDAL versions in use.

## Troubleshooting: `libspatialite … undefined symbol: xmlNanoHTTPCleanup`

On rolling/bleeding-edge distributions, importing `qgis.core` can fail with:

```
ImportError: libspatialite.so.8: undefined symbol: xmlNanoHTTPCleanup
```

This is a library load-order problem, not a niva bug: an earlier-loaded
`libxml2` shadows the symbol that `libspatialite` needs, even though the system's
main `libxml2` does export it. Force the correct `libxml2` to load first with
`LD_PRELOAD` (adjust the path/soname to your system):

```bash
export LD_PRELOAD=/usr/lib/x86_64-linux-gnu/libxml2.so.16
```

`qgis_process` itself is unaffected; only the in-process bindings hit this.

## A known cosmetic quirk

The run may end with a segmentation fault (exit code `139`) **after** all tests
have finished. This is QGIS's C++ singletons not tearing down cleanly at
interpreter shutdown — it happens after `unittest` has already printed its
`OK` / `FAILED` summary. Judge success by that summary line, not by the process
exit code.
