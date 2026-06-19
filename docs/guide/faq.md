# FAQ

Short answers to common questions. See the [User Guide](user-guide.md) for setup, the
[Reference](reference.md) for the full surface, and the [Cookbook](cookbook.md) for recipes.

## What software libraries are needed to use niva?

Almost nothing beyond **QGIS** itself. niva is **pure Python with zero third-party runtime
dependencies** — it runs on QGIS's own bundled Python.

- **Required:** **QGIS 3.22+ (or 4.x)** with its Processing framework. QGIS already ships
  everything niva relies on — GDAL/OGR, PROJ, GEOS, and the `native:`, `qgis:`, and `gdal:`
  algorithm providers. There is **no `pip install`** for the plugin (it bundles niva), and
  even the standalone package installs into QGIS's Python with no extra dependencies.
- **Optional providers** (only if you call those algorithms via `run`): **GRASS GIS** for the
  `grass:` algorithms and **PDAL** for the `pdal:` point-cloud algorithms. Install these the
  usual way for your platform; niva just calls them through QGIS Processing.
- **Databases:** handled entirely by QGIS's own providers — **PostgreSQL/PostGIS** (libpq) and
  **SpatiaLite** (mod_spatialite), both bundled with QGIS. You configure a connection in QGIS;
  niva references it as `@conn`.
- **`notify` / `email`:** Python standard library only (`urllib`, `smtplib`) — no extra libs.

The only thing that needs extra tools is **building the guide as a PDF**
(`scripts/build_guide_pdf.py`): that needs **pandoc** + a LaTeX engine (e.g. `xelatex`). Those
are *not* needed to use niva.

## Do I need to know Python or PyQGIS?

No. That's the point — you write a readable one-line flow instead of PyQGIS code:

```
load roads.gpkg | buffer 100m dissolve | clip city.gpkg | save roads_local.gpkg
```

If you *want* the Python, niva can **export any flow to a standalone PyQGIS script**
(`niva export`, or the plugin's Convert tab).

## How do I run niva — in QGIS or from the command line?

Both, identically:

- **In QGIS** — install the plugin, open its dock, type a flow, hit **Run**. No pip step.
- **Standalone** — the `niva` CLI / Python API, run with QGIS's own Python (it boots QGIS
  headless). See the [User Guide](user-guide.md#3-standalone--cli).

## I typed `niva` in a terminal and nothing happened (or "command not found")

Two things have to be true for the `niva` command to work, and a fresh shell usually has
neither:

1. **There's a `niva` command on your `PATH`.** niva isn't installed as a command until you
   either `pip install` it into a Python (which creates the `niva` script) or alias it (below).
2. **It runs on QGIS's Python.** niva needs the PyQGIS bindings (`qgis.core`, Processing) — your
   system `python3` usually can't import them, only the Python that QGIS ships with.

The quickest fix — **no install, just an alias**. **Two parts must point at *your* system —
don't paste the line as-is:**

- replace `/path/to/niva` with the directory that contains the `niva/` package (the repo
  root), and
- use the **full path to QGIS's Python**, not a bare `python3`. A bare `python3` often
  resolves to a Homebrew / pyenv / conda Python that *can't* import QGIS — you'll get
  `No module named 'niva'` or a PyQGIS `ImportError`.

```bash
# Template — substitute both placeholders:
alias niva='PYTHONPATH=/path/to/niva:/usr/share/qgis/python:/usr/lib/python3/dist-packages QT_QPA_PLATFORM=offscreen /path/to/qgis/python3 -m niva.cli.main'

# Concrete example (Linux, distro QGIS, repo at ~/Github/niva):
alias niva='PYTHONPATH=/home/jcz/Github/niva:/usr/share/qgis/python:/usr/lib/python3/dist-packages QT_QPA_PLATFORM=offscreen /usr/bin/python3.14 -m niva.cli.main'
niva describe buffer            # now it works
```

To find QGIS's Python + paths, open the QGIS **Python Console** and run:
`import sys, qgis; print(sys.executable); print([p for p in sys.path if 'qgis' in p.lower()])`
— use that `sys.executable` as the interpreter above. Then `niva info` confirms it's wired to
your real QGIS profile (it lists your `@conn` connections). Or install the command into QGIS's
Python — full instructions in the [User Guide](user-guide.md#3-standalone--cli). Sanity-check
the parser without QGIS using `--explain`:
`<qgis-python> -m niva.cli.main "load a.gpkg | buffer 100m | save b.gpkg" --explain`.

## Is niva on PyPI? How do I install it?

Not yet on PyPI. Get it as the **plugin zip** (`niva_qgis.zip`, from the
[latest release](https://github.com/johnzastrow/niva/releases/latest) or
`plugin/build_plugin.sh`) and *Install from ZIP* in QGIS, or install the package from source
into QGIS's Python:

```bash
<qgis-python> -m pip install git+https://github.com/johnzastrow/niva.git
```

## Which QGIS versions are supported?

QGIS **3.22+** (Qt5) and **QGIS 4.x** (Qt6). The plugin declares
`qgisMinimumVersion=3.22`; development targets QGIS 4.0.3.

## A raster job fails with "disk quota exceeded" or "No space left" even though I have free disk — why?

Raster steps write multi-gigabyte intermediates, and by default they land in the system temp
dir — often a small RAM-backed `/tmp`. Point niva's scratch at a roomy disk-backed folder:

```bash
export NIVA_TMPDIR=$HOME/niva_scratch
```

(or set the **Raster scratch** field in the plugin's Setup tab). Scratch is purged on every
run, even a failed one. See the [User Guide](user-guide.md#6-scratch-space--large-rasters).

## How do I read and write a database?

Configure a PostGIS or SpatiaLite connection in QGIS, then reference it by name as `@conn`:

```
load @pg.public.roads | clip aoi.gpkg | save @pg.public.roads_clip mode=replace
sql @pg "SELECT id, ST_Buffer(geom,100) AS geom FROM homes WHERE has_cat" | save targets.gpkg
```

Only the connection **name** appears in a flow — credentials stay in QGIS. See the
[Reference](reference.md#7-database-connections-conn).

## How do I see what layers/tables are in a file or database?

Use `show` — it lists the loadable layers at one location with each one's kind, geometry/raster
type, format, and a copy-pasteable `load` source:

```bash
show data.gpkg            # layers in a GeoPackage (or any container/shapefile/GeoTIFF)
show data/                # everything directly under a directory
show @gisdb3              # all tables in a PostGIS connection
show @gisdb3.public       # just one schema
```

It's the quick *"what can I load here?"* glance; for a deep recursive inventory (CRS, extent,
fields, feature counts) use `catalog` instead. For files you can take `show`'s source column
straight to `ogrinfo <file> <layer>` for more detail.

## How do I find my database connection names (the `@conn` values)?

Run `info`. From a shell — where the QGIS Browser isn't in front of you — this is the quickest
way to see the registered PostGIS/SpatiaLite connections, plus your QGIS/GDAL/PROJ versions,
the reachable algorithm count, and the niva environment variables (secrets masked):

```bash
niva info                 # prints the report; the "Database connections" section lists each @conn
niva info to=env.md       # or save it to a file
```

It's the CLI counterpart of the plugin's Setup-tab **Environment report**. See the
[Reference](reference.md#info--inspect-the-local-qgis-environment-terminal).

## Standalone niva shows different connections than my QGIS — why?

Connections are **per QGIS user profile**. A standalone niva reads the **same profile your
QGIS desktop last used**, so the `@conn` names match the GUI. (Earlier builds accidentally read
a generic, empty Qt settings store and saw none of your connections — fixed in 0.28.0.) If you
still see a mismatch, you're probably looking at a *different* profile than you think — run
`niva info` and check the **QGIS profiles** section, which lists every profile and its
connections.

## Can niva use a connection from another QGIS profile?

Yes — niva uses **one** profile at a time. `niva info` lists all profiles and their connections;
to use a connection that lives in another profile, point niva at it:

```bash
NIVA_QGIS_PROFILE=staging niva load @prod_db.public.roads | save roads.gpkg
```

(Inside QGIS, niva always uses the profile you have open.)

## Can I use an algorithm that doesn't have a niva verb?

Yes. The ~45 [alias verbs](reference.md#5-alias-verbs-the-registry) are conveniences; **every**
QGIS algorithm (769 in QGIS 4.0.3) is reachable with `run <id> KEY=value …`. Discover one with
`niva describe <id>`, or browse the [algorithm appendix](../algorithms/README.md) — each entry
has a worked example.

## How do I turn a niva flow into a normal PyQGIS script?

`niva export flow.niva -o flow.py` (or the plugin's Convert tab) writes a standalone PyQGIS
script — one `processing.run(...)` per step. `niva import` reverses it for niva-shaped scripts.

## Does niva send my data anywhere, or need an internet connection?

No. niva runs locally on QGIS Processing; it never transmits your data or credentials. The
only outbound features are **opt-in**: `notify` (ntfy), `email` (SMTP), and any algorithm that
is itself online (e.g. a geocoder you call via `run`). Their credentials come **only** from
the environment, never from flow text.

## How do I get the whole guide as one document?

Build a single PDF of this guide (and the full algorithm appendix) with:

```bash
python3 scripts/build_guide_pdf.py     # -> docs/guide/niva-guide.pdf
```

It's also attached to each [release](https://github.com/johnzastrow/niva/releases/latest) as
`niva-guide.pdf`.
