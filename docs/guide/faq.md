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
