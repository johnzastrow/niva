# Testing

How niva is tested, and where the results live. ([← back to README](../README.md))

## Tested platforms

The table below records platforms where the full test suite has been run against a release.
See [`tests/TESTING_LOG.md`](../tests/TESTING_LOG.md) for per-run details (suite counts, notes,
and a how-to-update template for adding new platforms).

| Platform | OS | QGIS | Python | niva | Result | Date |
|---|---|---|---|---|---|---|
| Windows 11 · x86\_64 | 10.0.26200 | 4.0.3-Norrköping | 3.12.13 | 0.35.0 | ✅ 718/718 + 3 skip | 2026-06-23 |
| Windows 11 · x86\_64 | 10.0.26200 | 3.44.11-Solothurn | 3.12.13 | 0.35.0 | ✅ 718/718 + 3 skip | 2026-06-23 |
| macOS 26.5.1 · x86\_64 | Darwin 25.5.0 | 4.0.3-Norrköping | 3.12.11 | 0.35.0 | ✅ 715/715 + 3 skip | 2026-06-22 |
| Linux 7.0 · x86\_64 | Linux 7.0.0 | 4.0.3-Norrköping | 3.14.4 | 0.35.0 | ✅ 718/718 + 10 skip | 2026-06-22 |
| macOS 26.5.1 · x86\_64 | Darwin 25.5.0 | 4.0.3-Norrköping | 3.12.11 | 0.34.1 | ✅ 668/668 + 3 skip | 2026-06-22 |

> Linux, macOS, and Windows all pass 0.35.0; Windows covers both the QGIS **4.0.3** and **3.44 LTR**
> lines. See [`tests/TESTING_LOG.md`](../tests/TESTING_LOG.md) for per-run detail.

## Running the suite

The suite is stdlib `unittest` and must run under **QGIS's own Python** (the PyQGIS tier skips
cleanly when QGIS is unimportable, so the pure-Python layers also run on a plain interpreter):

```bash
python -m unittest discover -s tests -t .
```

The example/validation suites under `tests/suites/` (validation, portable, numerical, round-trip,
security, error-path, format-matrix, benchmark) are run via their `run_*_suite.py` harnesses; see
[`tests/datagen/REPRODUCE_TESTS.md`](../tests/datagen/REPRODUCE_TESTS.md).

## Test `.niva` companions (project rule)

Every test file has a human-readable companion under [`tests/niva/`](../tests/niva/) —
`tests/test_engine.py` → `tests/niva/test_engine.niva` — showing **what each test exercises in
niva form**: the real flow lines where a test runs them, or a short comment stanza for pure-Python
tests. They make suite coverage skimmable without reading Python.

**The rule:** whenever a test is added or changed, regenerate the companions:

```bash
python scripts/gen_test_niva.py
```

This is enforced two ways, so the companions never drift:

- **CI** — the `test .niva companions are up to date` job regenerates and fails the build if the
  committed `.niva` files differ.
- **A Claude Code hook** (`.claude/settings.json`) regenerates them automatically whenever a
  `tests/test_*.py` file is edited in this repo.

The companions are *illustrative, not runnable* — flows lifted from f-strings keep their
`{python}` placeholders, which is honest about what the test actually runs.

### Two kinds of test file — don't confuse them

niva has tests in two places, and only one kind gets a generated companion:

| Where | What it is | Companion |
|---|---|---|
| **`tests/test_*.py`** | Python `unittest` modules (grammar, engine, binder, search, the live-QGIS tier) | **generated** → `tests/niva/<module>.niva` by `gen_test_niva.py` |
| **`tests/suites/*_suite*.niva`** | Suites written *directly in niva*, run by `run_*_suite.py` under `tests/suites/` (validation, portable, numerical, round-trip, security, error-path, format-matrix, benchmark) | already niva — they *are* the readable artifact |

So the answer to "where is the `.niva` for `validation_suite_3`?" is: it **is**
[`tests/suites/validation_suite_3.niva`](../tests/suites/validation_suite_3.niva) — there's nothing to
generate, the suite is niva to begin with.

The **validation** suites additionally ship a pure, `niva run`-able companion
(`<suite>.run.niva`) with the test directives (`#@out`, `#@cleanup`) stripped, emitted by
`run_validation_suite.py --emit`. Those are **generated**, so they're under the same drift rule —
regenerate with `python scripts/gen_run_niva.py` (also run by the CI job and the Claude Code hook).
The assert and benchmark suites use ordinary niva comments, so they're directly runnable and have
no generated companion.
