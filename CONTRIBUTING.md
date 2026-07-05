# Contributing to niva — developer paved road

Everything a build station (or an agent) needs to reproduce CI **locally** before pushing. niva has
**zero runtime dependencies**; the tooling below is dev-only.

> Multiple machines work on niva in parallel. Pin the tool versions in this file to whatever CI
> pins (`.github/workflows/ci.yml`). A different `ruff` will reformat differently and fail
> `ruff format --check`; a different `bandit` can find/miss things. **Bump the pin here, in CI, and
> reformat, all in one commit.**

## Pinned dev tools (must match `.github/workflows/ci.yml`)

| Tool | Version | Purpose |
|---|---|---|
| `ruff` | **0.15.19** | lint (`ruff check`) + format (`ruff format`) — format is byte-for-byte, so the version must match CI |
| `bandit` | **1.9.4** | Python security SAST — the same tool plugins.qgis.org runs |
| `detect-secrets` | **1.5.0** | hardcoded-secret scan — also run by plugins.qgis.org |

### Install (recommended: `uv tool`, so they're on `PATH`)

```bash
uv tool install "ruff==0.15.19"
uv tool install "bandit==1.9.4"
uv tool install "detect-secrets==1.5.0"
# ensure ~/.local/bin is on PATH:  export PATH="$HOME/.local/bin:$PATH"
```

> **Gotcha (git worktrees):** `uv run ruff …` fails to spawn ruff when the cwd is a **git worktree**
> (not the primary checkout). Installing ruff with `uv tool install` puts it on `PATH` and sidesteps
> this — always prefer the `PATH` binary over `uv run` for these checks.

Plain `pip` works too: `pip install "ruff==0.15.19" "bandit==1.9.4" "detect-secrets==1.5.0"`.

## The four CI gates — run them before you push

CI (`ci.yml`) fails the build on any of these; run them locally first:

```bash
# 1. lint
ruff check .

# 2. format (enforced — no drift). To auto-fix: `ruff format .`
ruff format --check --diff .

# 3. security SAST — gates on MEDIUM+ (the plugin-store blocking threshold).
#    LOW findings (best-effort try/except; the shell=False PDAL/SAGA subprocess harness) are OK.
bandit -r niva plugin --severity-level medium

# 4. secrets — must be zero
detect-secrets scan niva plugin
```

Plus the **unit suite** (no QGIS needed — pure-Python layers over the MockBackend):

```bash
python -m unittest discover -s tests -t .
```

## Running the full suite / the CLI **with** QGIS

The PyQGIS tier and a real `niva run` need QGIS's own interpreter and its Python path:

```bash
PYTHONPATH=/path/to/niva:/usr/share/qgis/python:/usr/share/qgis/python/plugins:/usr/lib/python3/dist-packages \
QT_QPA_PLATFORM=offscreen /usr/bin/python3.<ver> -m unittest tests.test_pyqgis -v
```

Notes:
- Headless QGIS can **segfault on interpreter teardown after the tests pass** (exit 139) — gate on
  unittest's `OK`/`FAILED` marker, not the process exit code (CI does this).
- If Qt complains about `libxml2`, `LD_PRELOAD` the system `libxml2.so` before launching.

## Conventions

- **Versioning is lockstep** across `pyproject.toml`, `niva/__init__.py`, and `plugin/metadata.txt`
  — bump all three together (semver). `CHANGELOG.md` is the full history; `metadata.txt`'s
  `changelog=` mirrors the top 1–2 entries.
- **Test/example companions** are generated — after changing tests, run
  `python scripts/gen_test_niva.py && python scripts/gen_run_niva.py` (CI fails on drift).
- **Lint config:** ruff runs on defaults (no `[tool.ruff]` in `pyproject.toml`). Two older modules
  (`niva/remote.py`, `niva/utilities.py`) use manual continuation alignment; `ruff format` now owns
  their layout too.

## Cutting a release (maintainers)

1. All four CI gates green on `main` (so the store scan will pass — see
   [`docs/guide/qgis-plugin-publishing.md`](docs/guide/qgis-plugin-publishing.md)).
2. Bump the version (three files) + `CHANGELOG.md` + `metadata.txt` `changelog=`.
3. Build the plugin zip: `bash plugin/build_plugin.sh` (the zip is gitignored — release-only).
4. `gh release create vX.Y.Z <zip> …` and, when ready, upload the same zip to plugins.qgis.org.
