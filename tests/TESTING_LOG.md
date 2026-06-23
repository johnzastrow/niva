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
| benchmark_suite | `run_benchmark_suite.py` | 24 | generated (`make_bigdata.py`) | 0.34 | CPU/memory/disk/network **metrics** (records timings; not pass/fail) |

**Data provisioning** (see [`examples/REPRODUCE_TESTS.md`](../examples/REPRODUCE_TESTS.md)):
*committed* = in the repo · *generated* = `make_testdata.py` / `make_bigdata.py` / `make_data.py`
· *`@localpg`* = PostGIS fixtures pushed into a **user-designated** DB by `make_data.py` ·
*downloaded* (optional, harder runs) = `fetch_testdata.sh`.

**Path tokens** the suites use: `{data}` → `$NIVA_TESTDATA` else `data/` else `examples/testdata` ·
`{testdata}` → `examples/testdata` · `{examples}` → committed real-world data · `{tmp}` → scratch.

---

## 2. Runs

One row per run, newest first. `Pass/Total` sums unit tests + all suite blocks for that run.

| Date (UTC) | niva | OS | QGIS | Python | Result | Pass / Total | Skip | Details |
|---|---|---|---|---|---|---|---|---|
| 2026-06-22 | 0.35.0 | macOS 26.5 · x86_64 | 4.0.3 | 3.12.11 | ✅ | 690 / 690 | 3 | [↓](#0350--macos-265--2026-06-22) |
| 2026-06-22 | 0.35.0 | Linux 7.0 · x86_64 | 4.0.3 | 3.14.4 | ✅ | 718 / 718 | 10 | [↓](#0350--linux--2026-06-22) |
| 2026-06-22 | 0.34.1 | macOS 26.5 · x86_64 | 4.0.3 | 3.12.11 | ✅ | 668 / 668 | 3 | [↓](#0341--macos-265--2026-06-22) |

### Coverage matrix (release × platform)

| Release | Linux · QGIS 4.0.3 | macOS 26.5 · QGIS 4.0.3 | Windows |
|---|---|---|---|
| 0.35.0 | ✅ 718/718 | ✅ 690/690 | — |
| 0.34.1 | — | ✅ 668/668 | — |

---

## 3. Run details

### 0.35.0 · macOS 26.5 · 2026-06-22

**Result: ✅ all tests passed (690/690, 3 skipped)**

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
| benchmark\_suite | n/a | — | — | not run — `make_bigdata.py` data not generated on this host |
| **TOTAL** | **690** | **690** | **✅ 100 %** | 3 skipped |

#### Notes

- `examples/testdata/` regenerated with `make_testdata.py` to pick up the 0.35.0 additions
  (`niva_testdata.gdb`, `.kml`, `.jp2`, `_points.csv`). Requires `PROJ_LIB` on macOS:
  `PROJ_LIB=/Applications/QGIS-final-4_0_3.app/Contents/Resources/qgis/proj`.
- `data/` regenerated with `make_data.py` (new 0.35.0 env-var interface for PostGIS creds:
  `NIVA_PG_HOST`, `NIVA_PG_PORT`, `NIVA_PG_DB`, `NIVA_PG_USER`, `NIVA_PG_PASSWORD`).
- `portable_suite` now uses `{testdata}` token (no longer needs to be run separately without
  `NIVA_TESTDATA`); all suites can be run together.
- `validation_suite` TEST 08 still uses `dem_clip.tif` passthrough (JP2 format tested via
  `format_matrix_suite` TEST 04 instead, using the generated `niva_testdata.jp2`).
- benchmark_suite skipped — `bench.gpkg` / `bench_dem.tif` were not generated (`make_bigdata.py`
  not run); not a code failure.
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
python examples/run_validation_suite.py examples/<suite>.niva
python examples/run_assert_suite.py     examples/<suite>.niva
python examples/run_benchmark_suite.py  examples/benchmark_suite.niva
```
