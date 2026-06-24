# niva — Testing Log

Formal test runs per **release × platform**, plus a catalog of what each suite covers so results
stay interpretable as the suites evolve. Goal: every release reaches **100 % on every tested
platform** (caveats — like missing host data — recorded explicitly).

**Legend:** ✅ all passed · ⚠️ some failed · ❌ most failed · — not run · n/a not applicable

The file has four parts:
1. **[Test Suites](#1-test-suites)** — what each suite is (update when suites change).
2. **[Runs](#2-runs)** — one row per run; scales across platforms / versions / dates.
3. **[Run details](#3-run-details)** — the full per-suite breakdown for each run, newest first.
4. **[Updating this log](#4-updating-this-log)**.

---

## 1. Test Suites

What each suite checks and what data it needs — so a result is meaningful even as suites are added
or reworked. **Update this table in the same commit that changes a suite.** "Since" is the niva
version the suite first appeared in.

| Suite | Runner | Tests | Data needed | Since | Covers |
|---|---|---:|---|---|---|
| unit · pure | `python -m unittest` (no QGIS) | ~370 | none (MockBackend) | 0.1 | grammar, registry, binder, engine, `remove` policy — QGIS-free |
| unit · live | `…` under QGIS python | +live | QGIS | 0.5 | real `PyqgisBackend`: load/run/save, CRS, sql, connections |
| unit · postgres | `TestPyqgisPostgres` | 6 | PostGIS (`NIVA_TEST_PG`) | 0.18 | DB read/write/append/sql round-trips — gated, skipped if unset |
| validation_suite | `run_validation_suite.py` | 41 | `data/` + `@localpg` | 0.33 | formats × verbs, simple→complex; asserts **non-empty geometry** |
| validation_suite_2 | `run_validation_suite.py` | 41 | `data/` + `@localpg` | 0.33 | field ops, point/line creation geom, `@conn` overlays, sql-computed geom |
| validation_suite_3 | `run_validation_suite.py` | 41 | `data/` + `@localpg` | 0.34 | deep 5–10-op chains; hand-off artifacts at stage seams |
| portable_suite | `run_assert_suite.py` | 25 | generated + committed | 0.34 | core verbs on transportable data + committed real GeoJSON/KMZ |
| format_matrix_suite | `run_assert_suite.py` | 16 | generated (+ `@localpg`) | 0.35 | raw FileGDB/KML/CSV/JP2 → each store (gpkg/spatialite/shp/PostGIS) → geoprocess |
| numerical_suite | `run_assert_suite.py` | 21 | committed/generated | 0.34 | **values** correct: buffer area ≈ π·r², counts, reproject round-trips |
| round_trip_suite | `run_assert_suite.py` | 17 | `data/` + `@localpg` | 0.34 | load→save→reload fidelity (count/CRS/fields/values) across formats |
| security_suite | `run_assert_suite.py` | 14 | `@localpg` | 0.34 | creds never leak, identifier quoting, `remove` allowlist |
| error_path_suite | `run_assert_suite.py` | 20 | committed | 0.34 | bad flows **fail closed** with useful messages, no partial output |
| benchmark_suite | `run_benchmark_suite.py` | 25 | generated (`make_bigdata.py`) | 0.34 | CPU/memory/disk/network **metrics** (records timings; not pass/fail) |

**Data provisioning** (see [`tests/datagen/REPRODUCE_TESTS.md`](datagen/REPRODUCE_TESTS.md)):
*committed* = in the repo · *generated* = `make_testdata.py` / `make_bigdata.py` / `make_data.py`
(all under `tests/datagen/`) · *`@localpg`* = PostGIS fixtures pushed into a **user-designated** DB
by `make_data.py` · *downloaded* (optional, harder runs) = `fetch_testdata.sh`.

**Path tokens** the suites use: `{data}` → `$NIVA_TESTDATA` else `data/` else
`tests/datagen/testdata` · `{testdata}` → `tests/datagen/testdata` · `{realworld}` →
`tests/datagen/realworld` (committed real-world .geojson/.kmz) · `{tmp}` → scratch.

> Suites and runners live in [`tests/suites/`](suites/); fixture generators and data in
> [`tests/datagen/`](datagen/). (Both moved out of `examples/` — which is now user-facing
> examples only.)

---

## 2. Runs

One row per run, newest first. `Pass/Total` sums unit tests + all suite blocks for that run.

| Date (UTC) | niva | OS | QGIS | Python | Result | Pass / Total | Skip | Details |
|---|---|---|---|---|---|---|---|---|
| 2026-06-24 | 0.35.1 | macOS 26.5 · arm64 | 4.0.3 | 3.12.11 | ✅ | 718 / 718 | 3 | [↓](#0351--macos-265--2026-06-24) |
| 2026-06-23 | 0.35.1 | Linux 7.0 · x86_64 | 4.0.3 | 3.14.4 | ✅ | 718 / 718 | 10 | [↓](#0351--linux--2026-06-23) |
| 2026-06-23 | 0.35.0 | Windows 11 · x86_64 | 4.0.3 | 3.12.13 | ✅ | 718 / 718 | 3 | [↓](#0350--windows-11--2026-06-23) |
| 2026-06-23 | 0.35.0 | Windows 11 · x86_64 | 3.44.11 | 3.12.13 | ✅ | 718 / 718 | 3 | [↓](#0350--windows-11--2026-06-23) |
| 2026-06-22 | 0.35.0 | macOS 26.5 · x86_64 | 4.0.3 | 3.12.11 | ✅ | 715 / 715 | 3 | [↓](#0350--macos-265--2026-06-22) |
| 2026-06-22 | 0.35.0 | Linux 7.0 · x86_64 | 4.0.3 | 3.14.4 | ✅ | 718 / 718 | 10 | [↓](#0350--linux--2026-06-22) |
| 2026-06-22 | 0.34.1 | macOS 26.5 · x86_64 | 4.0.3 | 3.12.11 | ✅ | 668 / 668 | 3 | [↓](#0341--macos-265--2026-06-22) |

### Coverage matrix (release × platform)

| Release | Linux · QGIS 4.0.3 | macOS 26.5 · QGIS 4.0.3 | Windows 11 · QGIS 4.0.3 / 3.44.11 |
|---|---|---|---|
| 0.35.1 | ✅ 718/718 | ✅ 718/718 (arm64) | — |
| 0.35.0 | ✅ 718/718 | ✅ 715/715 | ✅ 718/718 (both QGIS) |
| 0.34.1 | — | ✅ 668/668 | — |

---

## 3. Run details

### 0.35.1 · macOS 26.5 · 2026-06-24

**Result: ✅ all tests passed (718/718, 3 skipped)** — the **first Apple-Silicon (arm64) macOS run**
in this log (prior macOS entries were x86_64) and the first macOS run of 0.35.1. Matches the
Windows/Linux 0.35.1 totals byte-for-byte; the live PostGIS tier ran (3 skipped, not 10), so the
arm64 macOS build of QGIS 4 reaches a local PostgreSQL 18 / PostGIS 3.6 cleanly.

| Key | Value |
|---|---|
| Date (UTC) | 2026-06-24 |
| niva | 0.35.1 |
| QGIS | 4.0.3-Norrköping (40003) |
| Python | 3.12.11 |
| OS / kernel | Darwin / macOS 26.5.1 · 25.5.0 |
| Architecture | arm64 (Apple Silicon) |
| Host | Marisas-iMac.local |
| RAM / CPU | 24 GB / 10 cores (Apple M4) |
| Geo stack | QGIS bundle: GDAL 3.12.0 · PROJ 9.7.1 · GEOS 3.14.1 |
| PostGIS | local PostgreSQL 18.4 / PostGIS 3.6.4, `niva_test`, unix-socket peer auth (`NIVA_TEST_PG` / `@localpg`) |

| Suite | Passed | Total | Result | Note |
|---|---:|---:|---|---|
| unit (full discover, under QGIS) | 457 | 457 | ✅ | 3 skipped (remote-gated); includes the 7 live PostGIS unit tests via `NIVA_TEST_PG` |
| validation_suite | 41 | 41 | ✅ | |
| validation_suite_2 | 41 | 41 | ✅ | |
| validation_suite_3 | 41 | 41 | ✅ | |
| portable_suite | 25 | 25 | ✅ | committed + generated data |
| format_matrix_suite | 16 | 16 | ✅ | incl. PostGIS targets via `@localpg` |
| numerical_suite | 21 | 21 | ✅ | |
| round_trip_suite | 17 | 17 | ✅ | |
| security_suite | 14 | 14 | ✅ | |
| error_path_suite | 20 | 20 | ✅ | |
| benchmark_suite | 25 | 25 | ✅ | metrics only; all blocks ran clean on generated `bench.*` |
| **TOTAL** | **718** | **718** | **✅ 100 %** | 3 skipped |

#### Notes

- Ran on **QGIS's own Python** via the `.app` wrapper
  (`/Applications/QGIS-final-4_0_3.app/Contents/MacOS/python`), which sets `PYTHONHOME` to the
  bundled Frameworks. macOS needs `PROJ_DATA`/`PROJ_LIB` and `GDAL_DATA` pointed at
  `…/Contents/Resources/qgis/{proj,gdal}` to silence the PROJ/GDAL data-dir warnings; with them set,
  `make_testdata.py`/`make_bigdata.py`/`make_data.py` and all suites run clean.
- **PostGIS provisioning from scratch on this host:** installed `postgis` + `postgresql@18` via
  Homebrew (PostgreSQL 18.4 / PostGIS 3.6.4), `createdb niva_test`,
  `CREATE EXTENSION postgis`. Local **peer/socket** auth: `NIVA_PG_HOST=""` (empty) so QGIS connects
  via the unix socket as the OS user — no password in `pg_hba`. `make_data.py` pushed all 7
  hostile-name fixtures (`My Roads`, `café points`, `Mixed.Case.Dots`, `select`, `123_leading`,
  `name-with-dash#hash`, `two_geoms`) into `@localpg`.
- `make_data.py` prints a `mutex lock failed` line from `libc++abi` **at interpreter teardown** —
  after every fixture is written and committed (verified via `psql \dt` + the populated `data/`).
  It's a known QGIS-on-exit teardown crash, not a data error; the same data drives the green suites.
- Data: `examples/testdata/` (`make_testdata.py`: gpkg/dem/sqlite/kml/.gdb/.jp2/`_points.csv`),
  `data/` (`make_data.py`), benchmark `bench.gpkg` + `bench_dem.tif` (`make_bigdata.py`, scale=1.0).
  All suites run together with `NIVA_TESTDATA` set.
- Per-suite timestamped reports written to `~/niva-test-results/`.

### 0.35.1 · Linux · 2026-06-23

**Result: ✅ all tests passed (718/718, 10 skipped)** — regression check after merging the
`windows-test-support` work to `main`. Confirms the cross-platform harness changes and the
SpatiaLite system-table filter (0.35.1) left Linux byte-for-byte green.

| Key | Value |
|---|---|
| Date (UTC) | 2026-06-23 |
| niva | 0.35.1 |
| QGIS | 4.0.3-Norrköping (40003) |
| Python | 3.14.4 |
| OS / kernel | Linux 7.0.0-22-generic |
| Architecture | x86_64 |
| Host | RAINBOZEN |
| PostGIS | local `gisdb3` clone, `@localpg` |

| Suite | Passed | Total | Result | Note |
|---|---:|---:|---|---|
| unit (full discover, under QGIS) | 457 | 457 | ✅ | 10 skipped (postgres/remote gated) |
| validation_suite | 41 | 41 | ✅ | |
| validation_suite_2 | 41 | 41 | ✅ | |
| validation_suite_3 | 41 | 41 | ✅ | |
| portable_suite | 25 | 25 | ✅ | |
| format_matrix_suite | 16 | 16 | ✅ | incl. PostGIS targets via `@localpg` |
| numerical_suite | 21 | 21 | ✅ | |
| round_trip_suite | 17 | 17 | ✅ | |
| security_suite | 14 | 14 | ✅ | |
| error_path_suite | 20 | 20 | ✅ | |
| benchmark_suite | 25 | 25 | ✅ | metrics only; all blocks clean |
| **TOTAL** | **718** | **718** | **✅ 100 %** | 10 skipped |

#### Notes

- Same `data/` and `@localpg` setup as the 0.35.0 Linux run; no data regeneration needed.
- The merge's only code change (the SpatiaLite system-table filter in `list_tables`) is exercised
  by the unit + `show`/discovery tests, which all pass — no real layer is hidden on Linux/QGIS 4.

### 0.35.0 · Windows 11 · 2026-06-23

**Result: ✅ all tests passed (718/718, 3 skipped)** — and **identical on both QGIS 4.0.3-Norrköping
and QGIS 3.44.11-Solothurn (LTR)**. First Windows entry in this log; first run to exercise the
**QGIS 3.x** line.

| Key | Value |
|---|---|
| Date (UTC) | 2026-06-23 |
| niva | 0.35.0 |
| QGIS | 4.0.3-Norrköping (40003) **and** 3.44.11-Solothurn (LTR) — both via OSGeo4W |
| Python | 3.12.13 (OSGeo4W) |
| OS / kernel | Windows 11 Pro · 10.0.26200 |
| Architecture | x86\_64 (AMD64) |
| Host | T14Gen3 |
| RAM / CPU | 24 GB / 12 cores (Intel, Alder Lake) |
| Geo stack | OSGeo4W: GDAL 3.13.1 · PROJ 9.8.1 · GEOS 3.14.1 · SpatiaLite 5.1.0 |
| PostGIS | local PostgreSQL 18.4 / PostGIS 3.6.2, `localhost:5432/niva_test`, trust auth (test-only) |

Per-suite results — **the same table holds for QGIS 4.0.3 and 3.44.11**:

| Suite | Passed | Total | Result | Note |
|---|---:|---:|---|---|
| unit (full discover, under QGIS) | 457 | 457 | ✅ | 3 skipped (remote-gated); includes the 7 live PostGIS unit tests via `NIVA_TEST_PG` |
| validation_suite | 41 | 41 | ✅ | |
| validation_suite_2 | 41 | 41 | ✅ | |
| validation_suite_3 | 41 | 41 | ✅ | |
| portable_suite | 25 | 25 | ✅ | committed + generated data |
| format_matrix_suite | 16 | 16 | ✅ | incl. PostGIS targets via `@localpg` |
| numerical_suite | 21 | 21 | ✅ | |
| round_trip_suite | 17 | 17 | ✅ | |
| security_suite | 14 | 14 | ✅ | |
| error_path_suite | 20 | 20 | ✅ | |
| benchmark_suite | 25 | 25 | ✅ | metrics only; Windows RSS via `GetProcessMemoryInfo`, CPU via `os.times()` |
| **TOTAL** | **718** | **718** | **✅ 100 %** | 3 skipped |

#### Notes

- Runs on **QGIS's own Python** via OSGeo4W `python-qgis.bat` (4.0.3) and `python-qgis-ltr.bat`
  (3.44.11). Both interpreters are Python 3.12.13 and share one OSGeo4W geo stack; the only
  difference is the QGIS version. niva reads each QGIS's **own** profile, so `@localpg` was
  registered in both the `QGIS4` and `QGIS3` profiles (by running `make_data.py` under each).
- **Cross-platform harness fixes (POSIX behaviour unchanged — every change guarded on `os.name`):**
  - The suite runners hardcoded `/tmp/...` scratch dirs; the benchmark imported the Unix-only
    `resource` module and used `os.sysconf` / `/proc`. They now fall back to the OS temp dir and to
    ctypes (`GetProcessMemoryInfo`) + `os.times()` on Windows. On Linux/macOS the literal `/tmp`
    paths and `getrusage`/`/proc` probes are preserved exactly.
  - Windows-only **test-assertion** portability: QGIS `.source()` returns `/`-separated paths on
    every OS (`test_pyqgis`); a Windows scratch path broke a `re.sub` replacement (`test_cascade`);
    `~`-expansion leaves a mixed `\`/`/` separator that is functionally fine (`test_registry`).
  - The validation runner reused one `_assess.gpkg`; on Windows the previous assessment's open
    `QgsVectorLayer` locks the file, so `os.remove` raised `WinError 32` — now a unique scratch
    file per `@`-assessment.
- **niva code fix (helps every platform, surfaced on QGIS 3.x):** `PyqgisBackend.list_tables` now
  filters SpatiaLite's internal metadata/virtual tables (KNN/KNN2, `ElementaryGeometries`,
  `SpatialIndex`, `data_licenses`, the `*_geometry_columns` registries). QGIS 4 hides these, but
  QGIS 3.44 listed `KNN2` and `data_licenses` as ordinary spatial layers, so `show @conn`
  advertised them as loadable — the two `test_cascade` failures seen on 3.44. Now `show` lists only
  real layers consistently across QGIS versions.
- Data: `make_testdata.py` (portable fixtures incl. `.gdb`/`.kml`/`.jp2`/`_points.csv`),
  `make_data.py` (file fixtures + the 7 hostile-name PostGIS fixtures), `make_bigdata.py`
  (`bench.gpkg` + `bench_dem.tif`, scale=1.0). PostGIS pushed into a local PostgreSQL 18 designated
  via `NIVA_PG_*`.
- Per-suite timestamped reports written to `~/niva-test-results/`.

### 0.35.0 · macOS 26.5 · 2026-06-22

**Result: ✅ all tests passed (715/715, 3 skipped)**

| Key | Value |
|---|---|
| Date (UTC) | 2026-06-22 |
| niva | 0.35.0 |
| QGIS | 4.0.3-Norrköping (40003) |
| Python | 3.12.11 |
| OS / kernel | Darwin / macOS 26.5.1 · 25.5.0 |
| Architecture | x86\_64 |
| Host | MacBookPro.localdomain |
| RAM / CPU | 16 GB / 8 cores |
| PostGIS | local `niva_test`, TCP `localhost:5432`, peer auth (`NIVA_TEST_PG`) |

| Suite | Passed | Total | Result | Note |
|---|---:|---:|---|---|
| pytest (unit + integration) | 454 | 454 | ✅ | 3 skipped (remote-gated, expected) |
| portable\_suite | 25 | 25 | ✅ | includes 4 new real GeoJSON/KMZ tests |
| format\_matrix\_suite | 16 | 16 | ✅ | FileGDB/KML/CSV/JP2 → all stores; incl. PostGIS via `@localpg` |
| numerical\_suite | 21 | 21 | ✅ | |
| round\_trip\_suite | 17 | 17 | ✅ | |
| security\_suite | 14 | 14 | ✅ | |
| error\_path\_suite | 20 | 20 | ✅ | |
| validation\_suite | 41 | 41 | ✅ | |
| validation\_suite\_2 | 41 | 41 | ✅ | |
| validation\_suite\_3 | 41 | 41 | ✅ | |
| benchmark\_suite | 25 | 25 | ✅ | metrics only; all 25 blocks ran; scale=1.0 |
| **TOTAL** | **715** | **715** | **✅ 100 %** | 3 skipped |

#### Notes

- `examples/testdata/` regenerated with `make_testdata.py` to pick up the 0.35.0 additions
  (`niva_testdata.gdb`, `.kml`, `.jp2`, `_points.csv`). Requires `PROJ_LIB` on macOS:
  `PROJ_LIB=/Applications/QGIS-final-4_0_3.app/Contents/Resources/qgis/proj`.
- `data/` regenerated with `make_data.py`; `bench.gpkg` + `bench_dem.tif` generated with
  `make_bigdata.py` (scale=1.0: 60k polygons, 60k points, 5k lines, 2000×2000 DEM).
- **benchmark runner fix:** `_RSSSampler` named its stop flag `self._stop`, shadowing
  `threading.Thread._stop()` — Python 3.12's `join()` then called the Event as a function
  and crashed. Renamed to `self._done`. Fixed in `examples/run_benchmark_suite.py`.
- `portable_suite` now uses `{testdata}` token; all suites run together with `NIVA_TESTDATA` set.
- `validation_suite` TEST 08 still uses `dem_clip.tif` passthrough (JP2 tested via
  `format_matrix_suite` TEST 04 using the generated `niva_testdata.jp2`).
- Per-suite timestamped reports written to `~/niva-test-results/`.

### 0.35.0 · Linux · 2026-06-22

**Result: ✅ all tests passed (718/718, 10 skipped)** — on a `make_data.py`-regenerated `data/`.

| Key | Value |
|---|---|
| Date (UTC) | 2026-06-22 |
| niva | 0.35.0 |
| QGIS | 4.0.3-Norrköping (40003) |
| Python | 3.14.4 |
| OS / kernel | Linux 7.0.0-22-generic |
| Architecture | x86_64 |
| Host | RAINBOZEN |
| RAM / CPU | 32 GB / 12 cores |
| PostGIS | local `gisdb3`, unix-socket peer auth (`@localpg`) |

| Suite | Passed | Total | Result | Note |
|---|---:|---:|---|---|
| unit (full discover, under QGIS) | 457 | 457 | ✅ | 10 skipped (postgres/remote gated) |
| validation_suite | 41 | 41 | ✅ | |
| validation_suite_2 | 41 | 41 | ✅ | |
| validation_suite_3 | 41 | 41 | ✅ | |
| portable_suite | 25 | 25 | ✅ | committed + generated data |
| format_matrix_suite | 16 | 16 | ✅ | incl. PostGIS targets via `@localpg` |
| numerical_suite | 21 | 21 | ✅ | |
| round_trip_suite | 17 | 17 | ✅ | |
| security_suite | 14 | 14 | ✅ | |
| error_path_suite | 20 | 20 | ✅ | |
| benchmark_suite | 25 | 25 | ✅ | metrics only — all blocks ran clean on generated `bench.*` |
| **TOTAL** | **718** | **718** | **✅ 100 %** | 10 skipped |

#### Notes

- `data/` was (re)generated for this run with `python examples/make_data.py` (from the committed
  `examples/example.gpkg` + `examples/testdata/`) and `make_bigdata.py` (benchmark `bench.*`). An
  earlier pass of this run on the host's *legacy* hand-curated `data/` had 8 suite failures
  (validation file mismatches, a gpkg FID-bookkeeping quirk, a SpatiaLite artifact) — **all data
  provisioning, none code**; regenerating `data/` cleared every one. Confirms the suites are green
  on the canonical generated data on Linux as on macOS.
- **PostGIS gotcha:** `make_data.py` writes `host` from `NIVA_PG_HOST`. For local **peer/socket
  auth** set `NIVA_PG_HOST=""` (empty) so QGIS uses the unix socket — TCP `localhost` here requires
  `scram-sha-256` (a password). With the right host it pushes all 7 hostile-name fixtures fine.
- The 10 skipped unit tests are gated on `NIVA_TEST_PG` / remote features (expected).
- New since 0.34.1: **format_matrix_suite** (16) + **native CSV lon/lat point loading**; the macOS
  **`.app`-prefix provider fix**. Per-suite timestamped reports under `~/niva-test-results/`.

### 0.34.1 · macOS 26.5 · 2026-06-22

**Result: ✅ all tests passed**

| Key | Value |
|---|---|
| Date (UTC) | 2026-06-22T21:07–21:10 |
| niva | 0.34.1 |
| QGIS | 4.0.3-Norrköping (40003) |
| Python | 3.12.11 |
| OS / kernel | Darwin / macOS 26.5.1 · 25.5.0 |
| Architecture | x86_64 |
| Host | MacBookPro.localdomain |
| RAM / CPU | 16 GB / 8 cores |

| Suite | Passed | Total | Result |
|---|---:|---:|---|
| pytest (unit + integration) | 452 | 452 | ✅ |
| portable_suite | 21 | 21 | ✅ |
| numerical_suite | 21 | 21 | ✅ |
| round_trip_suite | 17 | 17 | ✅ |
| security_suite | 14 | 14 | ✅ |
| error_path_suite | 20 | 20 | ✅ |
| validation_suite | 41 | 41 | ✅ |
| validation_suite_2 | 41 | 41 | ✅ |
| validation_suite_3 | 41 | 41 | ✅ |
| **TOTAL** | **668** | **668** | **✅ 100 %** |

#### Notes

- 3 skipped pytest tests gated on features/environments absent on this host (expected).
- `portable_suite` run **without** `NIVA_TESTDATA` (falls back to `examples/testdata/`); other suites
  with `NIVA_TESTDATA=/path/to/niva/data`. *(On 0.35.0+ the `{testdata}`/`{examples}` tokens remove
  this juggling — all suites run together.)*
- pytest run first, before suite processes touch PostGIS, to avoid connection-pool state affecting
  `TestPyqgisPostgres`.
- `validation_suite` TEST 08 uses `dem_clip.tif` in place of the original JPEG2000 source (absent here).
- Predates the `format_matrix_suite`, hence 668 vs the 0.35.0 suite set.

---

## 4. Updating this log

After a run:

1. **If a suite changed**, update [§1 Test Suites](#1-test-suites) (counts, "Since", Covers) in the
   same commit.
2. **Prepend a row** to [§2 Runs](#2-runs) and update the coverage matrix (add a release row / a
   platform column as needed).
3. **Prepend a detailed entry** to [§3 Run details](#3-run-details) using the newest entry as a
   template: a platform key/value table, a per-suite counts table (with ✅/⚠️ and a one-line note on
   any miss), and Notes (skips, environment quirks, whether a miss is code vs. data provisioning).

Anchor pattern for a detail entry: lowercase the heading, drop `·`, collapse spaces to `-`, strip
dots → e.g. `### 0.35.0 · Linux · 2026-06-22` → `#0350--linux--2026-06-22`.

Get the numbers with:

```bash
# unit (authoritative total, under QGIS python)
python -m unittest discover -s tests -t .
# each .niva suite (the runner prints "<n>/<N> blocks passed")
python tests/suites/run_validation_suite.py tests/suites/<suite>.niva
python tests/suites/run_assert_suite.py     tests/suites/<suite>.niva
python tests/suites/run_benchmark_suite.py  tests/suites/benchmark_suite.niva
```
