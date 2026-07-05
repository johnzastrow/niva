# niva User Guide

How to install and run niva — **inside QGIS** (the plugin) and **standalone** (the CLI and
Python API) — plus configuration, logging, and troubleshooting. For the full verb/option
catalogue see the [Reference](reference.md); for worked examples see the
[Cookbook](cookbook.md).

- [1. What niva is](#1-what-niva-is)
- [2. Inside QGIS — the plugin](#2-inside-qgis--the-plugin)
- [3. Standalone — CLI](#3-standalone--cli)
- [4. Standalone — Python API](#4-standalone--python-api)
- [5. Configuration & environment](#5-configuration--environment)
- [6. Scratch space & large rasters](#6-scratch-space--large-rasters)
- [7. The run journal](#7-the-run-journal)
- [8. Export to / import from PyQGIS](#8-export-to--import-from-pyqgis)
- [9. Databases & credentials](#9-databases--credentials)
- [10. Troubleshooting](#10-troubleshooting)

---

## 1. What niva is

niva is a small text language for QGIS geoprocessing. You write a **flow** — a chain of
verbs joined by `|` — and niva resolves each verb to a QGIS Processing algorithm and runs it:

```
load roads.gpkg | reproject EPSG:2262 | buffer 100m dissolve | save roads_buf.gpkg
```

It runs the same two ways: as a **QGIS plugin** (a dock panel, using the QGIS session's own
Processing engine) and **standalone** (a `niva` CLI / Python API that boots QGIS headless).
The language and results are identical; pick whichever fits the job. niva is pure Python with
zero runtime dependencies beyond QGIS itself.

---

## Dependencies — required & optional

**Required — that's the whole list:**

| Requirement | Notes |
|---|---|
| **QGIS 3.22+ (Qt5) or 4.x (Qt6)** | niva runs *inside* QGIS's own Python and Processing engine. Install QGIS from [qgis.org/download](https://qgis.org/download/) (Windows standalone/OSGeo4W, macOS, or Linux packages). |
| **Python** | Provided by QGIS — you do **not** install a separate Python. niva itself is pure Python, vendored in the plugin zip (no `pip` step for the plugin). |

Everything below is **optional** — install a piece only when you use the feature that needs it.
The bundled providers (`native:`, `gdal:`, `qgis:`, and usually `grass:` and `pdal:`) come with
QGIS and need nothing extra; `run <id>` reaches all of them.

| Feature | Needs | How to get it |
|---|---|---|
| **`figure` / `map`** (rendering) | Nothing extra — QGIS renders both. `basemap=osm` needs network access | built in |
| **`run grass:*`** (terrain/hydrology/classification) | GRASS | Bundled with most QGIS installs; nothing to do |
| **`run pdal:*`** (QGIS point-cloud provider) | QGIS built with PDAL; raw `.las`/`.laz` may need a COPC index | Usually built in on Windows/macOS; on Linux see the [PDAL/LAStools guide](pdal-lastools-qgis4.md) |
| **`run pdalcli:*`** (PDAL on raw LAS/LAZ/COPC — DTM/DSM/classify/merge/clip) | `pdal_wrench` + `QGIS_WRENCH_EXECUTABLE` | `micromamba/conda install -c conda-forge pdal_wrench`, then set the env var to its path |
| **`run saga:*`** (SAGA CLI harness) | `saga_cmd` | Linux `apt install saga` · macOS `brew install saga-gis` · conda `saga` · set `NIVA_SAGA_CMD` if not on `PATH` |
| **`run otb:*`** (Orfeo ToolBox) | OTB binaries + the OTB provider plugin | [orfeo-toolbox.org/download](https://www.orfeo-toolbox.org/download/) + set OTB folders (see [guide](pdal-lastools-qgis4.md)) |
| **`run lastools:*`** (LAStools) | LAStools binaries (+ `libjpeg62` on Linux; a licence for production) | [rapidlasso](https://rapidlasso.de/) — optional; PDAL covers most of it |
| **`notify`** (ntfy push) | Network + an ntfy topic | Set `NIVA_NTFY_TOPIC` (and optionally `NIVA_NTFY_SERVER` / `NIVA_NTFY_TOKEN`) |
| **`email`** (SMTP) | An SMTP account | Set the `NIVA_SMTP_*` env vars (see §5) |
| **PostGIS `@conn`** | A saved QGIS PostgreSQL connection | Configure it in QGIS's Data Source Manager — niva only ever sees the connection *name* |
| **Editor highlighting/snippets** | Your editor | One command: `bash .vscode/niva/install.sh` — see the [editor guide](editor-integration.md) |

Nothing here is needed to write, dry-run, `describe`, or `search` flows — those work with niva
alone. See the **[PDAL/LAStools/OTB/SAGA guide](pdal-lastools-qgis4.md)** for the full point-cloud
and raster-analysis setup, and **[editor integration](editor-integration.md)** for IDE support.

---

## 2. Inside QGIS — the plugin

### Install

1. Build the plugin zip from the repo: `bash plugin/build_plugin.sh` → produces
   `plugin/niva_qgis.zip`. (Each tagged release also attaches `niva_qgis.zip` — download it
   from the [Releases](https://github.com/johnzastrow/niva/releases) page.)
2. In QGIS: **Plugins ▸ Manage and Install Plugins ▸ Install from ZIP**, choose
   `niva_qgis.zip`, install.
3. If it doesn't appear, enable **Show also experimental plugins** in the Plugin Manager
   settings (niva is marked experimental). It works on QGIS 3.22+ (Qt5) and QGIS 4 (Qt6),
   with no pip step — the package is vendored inside the zip.
4. Click the **niva** toolbar button (or the `niva` menu) to toggle the dock.

### The dock — three tabs

**Flow tab** — write and run flows.
- Type one or more flows in the editor (one flow per line; `#` comments). **Open…** loads a
  `.niva` file so `call` and relative paths resolve from it.
- **Run** executes for real in a background task (the UI stays responsive); progress streams
  to the output panel and the final output layer is added to the map.
- **Dry-run** validates without touching data — it parses, resolves each verb to its QGIS
  algorithm and parameters, and lists what it *would* run.
- **Stop** cancels a running flow; **Clear output** clears the panel.

**Convert tab** — bridge to PyQGIS (see §8). Export the current flow to a standalone PyQGIS
script, save it, or import a niva-shaped script back into a flow.

**Setup tab** — configure the session:
- **Raster scratch** — the folder for large raster intermediates (sets `NIVA_TMPDIR`).
  Defaults to a real-disk folder under your QGIS profile. Point it at a roomy drive for big
  raster jobs (see §6).
- **Run log** — log each run to one file per QGIS session, in a folder you choose (§7).
- **Email & notifications** — fields for the `notify`/`email` environment (ntfy topic/server,
  SMTP host/user/from, and the "Notify on errors / warnings" toggles), with **Send test
  notification / email** buttons. Non-secret values persist; secrets (passwords, tokens) are
  session-only unless you save them to the QGIS encrypted store.
- **Environment report** — niva version, install path, the verbs and algorithms available,
  your saved database connections, and QGIS/GDAL/PROJ versions.

---

## 3. Standalone — CLI

> **A bare `niva` in a fresh shell usually does nothing — "command not found".** That's
> expected: there's no `niva` command until you put one on your `PATH`, *and* it must run on
> **QGIS's own Python** (niva imports `qgis.core` + the Processing providers — the system
> `python3` typically can't). Fix it one of two ways:

### Make `niva` runnable

**Option A — no install (run it as a module).** Point QGIS's Python at the niva package and
run the CLI module. **Two placeholders below must be replaced for your machine — copying the
line verbatim will fail:**

- **`/path/to/niva`** — the directory holding the `niva/` package (your repo root).
- **`/path/to/qgis/python3`** — the **full path to QGIS's Python interpreter**, *not* a bare
  `python3`. A bare `python3` frequently resolves to a Homebrew / pyenv / conda Python that
  cannot import QGIS, giving `No module named 'niva'` or a PyQGIS `ImportError`. On Linux with a
  distro QGIS this is typically `/usr/bin/python3.NN` (match QGIS's exact minor version).

```bash
# Substitute both placeholders:
PYTHONPATH=/path/to/niva:/usr/share/qgis/python:/usr/lib/python3/dist-packages \
  QT_QPA_PLATFORM=offscreen /path/to/qgis/python3 -m niva.cli.main describe buffer
```

Wrap it in a shell alias so `niva …` just works (put it in your `~/.bashrc`):

```bash
# Template:
alias niva='PYTHONPATH=/path/to/niva:/usr/share/qgis/python:/usr/lib/python3/dist-packages QT_QPA_PLATFORM=offscreen /path/to/qgis/python3 -m niva.cli.main'

# Concrete example (Linux, distro QGIS 4.x, repo at ~/Github/niva):
alias niva='PYTHONPATH=/home/jcz/Github/niva:/usr/share/qgis/python:/usr/lib/python3/dist-packages QT_QPA_PLATFORM=offscreen /usr/bin/python3.14 -m niva.cli.main'
```

Not sure of QGIS's Python or paths? In the QGIS **Python Console** run:
`import sys, qgis; print(sys.executable); print([p for p in sys.path if 'qgis' in p.lower()])`
— use that `sys.executable` as the interpreter. Then run `niva info`: if it lists your database
connections, the alias is correctly wired to your real QGIS profile.

**Option B — install the `niva` command.** Install niva *into QGIS's Python* so it creates a
`niva` console script, then make sure that interpreter's `bin`/`Scripts` is on your `PATH`:

```bash
<qgis-python> -m pip install git+https://github.com/johnzastrow/niva.git
```

On **Windows** run this from the **OSGeo4W shell**; on **macOS** use `QGIS.app`'s bundled
Python — both already have the bindings importable (no `PYTHONPATH` needed). On Linux, the
QGIS bindings may still need to be on `PYTHONPATH`, so Option A's alias is often simplest.

> `--dry-run` and `--explain` work on **any** Python (they don't import QGIS), so
> `python3 -m niva.cli.main "…" --explain` is a quick way to sanity-check your install.

### Commands

```
niva run <file.niva> [--dry-run | --explain] [--log <base>]
niva "<flow>"        [--dry-run | --explain] [--log <base>]
niva describe <verb-or-algorithm-id> [to=<file>]
niva export <file.niva> [-o <file.py>]
niva import <file.py>   [-o <file.niva>]
```

- `niva run flow.niva` / `niva "load … | save …"` — execute a file or an inline flow.
- `--dry-run` — print the plan and validate it with no QGIS, no data touched.
- `--explain` — print the resolved algorithm and parameters for each stage.
- `--log <base>` — also write the journal (`<base>.jsonl` + `<base>.log`).
- `niva describe buffer` / `niva describe gdal:warpreproject [to=out.md]` — introspect a verb or
  algorithm (with a runnable example).
- `niva "search <keyword>"` / `niva "docs <keyword> to=guide.md"` — fuzzy-find functions across the
  verbs and the live QGIS catalog, or build a saved mini-guide. (Flow verbs, so they also run in
  the plugin dock; both need QGIS.)

**Exit codes:** `0` ok · `1` runtime error · `2` usage/parse error · `3` QGIS not importable.

### Running headless (Linux example)

```bash
export QT_QPA_PLATFORM=offscreen          # no display needed
export QGIS_PREFIX_PATH=/usr              # your QGIS install prefix
export PYTHONPATH=/usr/share/qgis/python:/usr/lib/python3/dist-packages
export NIVA_TMPDIR=$HOME/niva_scratch     # roomy disk for raster scratch (§6)

niva run myflow.niva
# or, if the console script isn't on PATH:
python3 -m niva.cli.main run myflow.niva
```

On Windows/macOS use the Python that ships with QGIS (the OSGeo4W shell on Windows, or
`QGIS.app`'s bundled Python on macOS); the same env vars apply with platform-appropriate
paths. `--dry-run` and `--explain` work on **any** Python (they don't import QGIS).

---

## 4. Standalone — Python API

```python
import niva

# run an inline flow (needs QGIS on PYTHONPATH)
layer = niva.flow('load "data.gpkg|layername=roads" | buffer 100m dissolve | save out.gpkg')
print(layer.ref)          # '/abs/path/out.gpkg'

# run a file, with live progress
niva.run_file("myflow.niva")
niva.flow(open("myflow.niva").read(), file="myflow.niva",
          progress=lambda msg: print(msg))

# introspect a verb (no QGIS needed)
print(niva.describe("buffer"))
```

`flow(text, *, backend=None, file=None, log=None, log_append=False, progress=None,
cancel=None)` returns the final layer handle (or `None` for a terminal flow). Pass
`backend=niva.engine.MockBackend()` to dry-run without QGIS. Importing `niva` is always safe;
QGIS is imported lazily only when a real run executes. See the [Reference](reference.md#10-python-api)
for the full signatures.

---

## 5. Configuration & environment

niva is configured entirely through environment variables (the plugin Setup tab sets them for
you). The full table is in the [Reference](reference.md#8-environment-variables); the ones you
are most likely to set:

| Variable | Why |
|---|---|
| `NIVA_TMPDIR` | scratch dir for raster intermediates — set it to a roomy disk (§6) |
| `NIVA_LOG` | default journal base path (§7) |
| `NIVA_TEMPLATES` | extra directory of named project templates |
| `NIVA_NTFY_TOPIC` (+ `…_SERVER`, `…_TOKEN`) | the `notify` verb |
| `NIVA_SMTP_HOST` / `…_USER` / `…_PASSWORD` / `…_FROM` | the `email` verb |
| `QGIS_PREFIX_PATH`, `QT_QPA_PLATFORM` | standalone QGIS bootstrap |

Credentials for `notify`/`email` and for databases come **only** from the environment / QGIS
— never from flow text.

---

## 6. Scratch space & large rasters

Raster steps (`warp`, `clipraster`, `hillshade`, resampling, …) each write a full
intermediate GeoTIFF — often gigabytes — before `save` re-encodes the final product. By
default these land in the system temp dir, which on Linux is frequently a small RAM-backed
`/tmp` (e.g. 16 GB). A multi-GB raster pipeline can exhaust it and abort with a "disk quota
exceeded" error **even with terabytes of real disk free**.

**Fix:** set `NIVA_TMPDIR` (or the plugin's *Raster scratch* field) to a roomy, disk-backed
folder:

```bash
export NIVA_TMPDIR=$HOME/niva_scratch
```

niva routes its intermediates there (and points GDAL's own `CPL_TMPDIR` at the same place).
Scratch is **purged on every run, even a failed one**, so a crash never strands gigabytes;
the run's final output is spared, and a niva-created scratch dir is removed when emptied. The
plugin defaults this to a folder under your QGIS profile, always on real disk.

---

## 7. The run journal

Pass `--log <base>` (CLI), `log=<base>` (`flow`), or `NIVA_LOG`, or enable per-session logging
in the plugin Setup tab, to record a run to two files:

- **`<base>.log`** — human-readable, one line per operation: timestamp, the stage text, the
  resolved algorithm, the output path, and the duration; warnings (`⚠`) and failures
  (`✗ FAILED`) are inlined.
- **`<base>.jsonl`** — machine-readable JSON Lines: a run-start record, one record per
  operation (including the exact `processing.run(...)` equivalent), and a run-finished summary.

The journal records the niva stage text and output paths — never raw parameter dicts,
credentials, or SQL text. `log_append=True` (the plugin's per-session mode) keeps one growing
log; the default truncates per invocation.

---

## 8. Export to / import from PyQGIS

niva flows convert to and from plain PyQGIS, so you can hand a script to someone without niva,
or drop a flow into a larger Python tool:

- **Export** — `niva export flow.niva -o flow.py` (or the plugin Convert tab) writes a
  standalone PyQGIS script, one `processing.run(...)` per step.
- **Import** — `niva import flow.py -o flow.niva` recovers a flow from a **niva-shaped** script
  (a flat list of `processing.run(...)` calls, like Export produces). Arbitrary PyQGIS with
  loops/conditionals/functions can't round-trip and is reported, not guessed.

This is the audit trail: every niva run is reducible to the exact QGIS calls it made.

---

## 9. Databases & credentials

niva reads and writes SpatiaLite and PostGIS through **saved QGIS connections**, referenced
as `@name` (see the [Reference](reference.md#7-database-connections-conn)):

```
load @pg.public.roads | clip aoi.gpkg | save @pg.public.roads_clip mode=replace
sql @pg "SELECT id, ST_Buffer(geom,100) AS geom FROM homes WHERE has_cat" | save targets.gpkg
```

Set up the connection once in the **QGIS Browser** (Data Source Manager → PostgreSQL /
SpatiaLite → New) or the plugin Setup tab. Only the connection *name* appears in a flow; host,
database, user, and password stay in QGIS's own store. niva never logs or transmits
credentials. See the SQL recipes in the [Cookbook](cookbook.md#g-spatial-sql-in-spatialite).

---

## 10. Troubleshooting

**"could not import QGIS — run niva with QGIS's own Python."** You ran the CLI/API on a plain
Python. Use QGIS's interpreter or set `PYTHONPATH` to its bindings (§3). `--dry-run` /
`--explain` work without QGIS if you only need to validate.

**A raster run aborts with "disk quota exceeded" / "No space left" despite free disk.** Your
scratch is on a small RAM-backed `/tmp`. Set `NIVA_TMPDIR` to a roomy disk folder (§6).

**`notify` fails with "needs a topic."** Set `NIVA_NTFY_TOPIC` (or pass `to=<topic>`), or fill
the ntfy fields in the plugin Setup tab. niva won't send to an unconfigured topic.

**`load mydata.gpkg` errors and lists layer names.** A multi-layer container needs an explicit
layer: `load "mydata.gpkg|layername=roads"`.

**`save @pg.table` fails because the table exists.** That's the fail-closed default
(`mode=create`). Use `mode=replace` to overwrite or `mode=append` to add rows.

**A `sql` write piped into another stage errors.** A write statement (`CREATE`/`UPDATE`/…) is
terminal — it returns no layer. Only `SELECT`/`WITH`/`VALUES`/`TABLE`/`EXPLAIN`/`SHOW` produce
a pipeable layer.

**One file in an `each` batch failed but the run continued.** That's intended — a bad *data*
item is skipped, logged, and counted so it can't abort the batch. A usage error (bad option,
bad target) still stops everything. Check the output/journal for the skipped item.

**Headless QGIS exits with a segfault after the run finishes.** Known QGIS teardown race; the
CLI hard-exits to avoid it, and results are already written. If you script the Python API
directly, let the process exit rather than re-running in a loop.
