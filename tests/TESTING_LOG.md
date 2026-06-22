# niva — Testing Log

Tracks every formal test run against a release: platform, suite-by-suite counts, and overall
status. The goal is to accumulate evidence that each release reaches **100 % on every tested
platform** before it is considered fully validated.

Legend: ✅ = all tests in that run passed · ⚠️ = some failed · ❌ = all/most failed · — = not yet run

---

## Platform Coverage Matrix

One row per release. One column per distinct platform that has been tested.
A cell shows the overall result of the **best run** for that release × platform combination
(link to the detailed entry in the Run Log below).

| Release | macOS 26.5 · QGIS 4.0.3 · x86\_64 |
|---|---|
| [0.34.1](#run-2026-06-22--macos-265--qgis-403--niva-0341) | ✅ 668/668 + 3 skip |

> Add new platform columns as runs on Linux, Windows, or different QGIS versions are completed.
> Add new rows when a release is cut and tested.

---

## Run Log

Entries are newest-first within each release. Each entry records platform details, the result of
every suite, and any notable failures or skips.

---

### Run 2026-06-22 — macOS 26.5 — QGIS 4.0.3 — niva 0.34.1

**Result: ✅ all tests passed**

#### Platform

| Key | Value |
|---|---|
| Date / time (UTC) | 2026-06-22T21:07–21:10 |
| niva version | 0.34.1 |
| QGIS version | 4.0.3-Norrköping (40003) |
| Python | 3.12.11 |
| OS | Darwin / macOS 26.5.1 |
| Kernel | 25.5.0 |
| Architecture | x86\_64 |
| Host | MacBookPro.localdomain |
| RAM | 16 GB |
| CPU cores | 8 |

#### Suite Results

| Suite | Runner | Passed | Total | Skipped | Result |
|---|---|---|---|---|---|
| pytest (unit + integration) | pytest | 452 | 452 | 3 | ✅ |
| portable\_suite | run\_assert\_suite.py | 21 | 21 | 0 | ✅ |
| numerical\_suite | run\_assert\_suite.py | 21 | 21 | 0 | ✅ |
| round\_trip\_suite | run\_assert\_suite.py | 17 | 17 | 0 | ✅ |
| security\_suite | run\_assert\_suite.py | 14 | 14 | 0 | ✅ |
| error\_path\_suite | run\_assert\_suite.py | 20 | 20 | 0 | ✅ |
| validation\_suite | run\_validation\_suite.py | 41 | 41 | 0 | ✅ |
| validation\_suite\_2 | run\_validation\_suite.py | 41 | 41 | 0 | ✅ |
| validation\_suite\_3 | run\_validation\_suite.py | 41 | 41 | 0 | ✅ |
| **TOTAL** | | **668** | **668** | **3** | **✅ 100 %** |

#### Notes

- The 3 skipped pytest tests are gated on features/environments not present on this host (expected).
- `portable_suite` must be run **without** `NIVA_TESTDATA` set so it falls back to
  `examples/testdata/` (which holds `niva_testdata.gpkg`). The other suites are run with
  `NIVA_TESTDATA=/path/to/niva/data`.
- pytest is run first, before any suite process touches PostGIS, to avoid QGIS connection-pool
  state left by suite processes from affecting `TestPyqgisPostgres`.
- `validation_suite` TEST 08 uses `dem_clip.tif` (TIF passthrough) in place of the original
  JPEG2000 source, which is not present on this host.
- Per-suite timestamped reports are written to `~/niva-test-results/` by the suite runners.

---

## How to Update This File

After each test run, prepend a new entry to the Run Log in this format:

```
### Run YYYY-MM-DD — <OS short name> — QGIS <version> — niva <version>

**Result: ✅ / ⚠️ / ❌ <brief summary>**

#### Platform
... (key/value table) ...

#### Suite Results
... (counts table) ...

#### Notes
... (anything unexpected, skips, known failures, environment quirks) ...
```

Then update the **Platform Coverage Matrix** at the top:
- If this is a new platform column, add it.
- If this is a new release, add a new row.
- Update the cell with the overall result and anchor link.

The anchor for each run entry follows the pattern:
`#run-YYYY-MM-DD--os-short--qgis-XYZ--niva-XYZW`
(GitHub Markdown lowercases, replaces spaces and dots with hyphens, strips other punctuation.)
