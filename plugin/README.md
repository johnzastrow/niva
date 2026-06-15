# niva — QGIS plugin

Run **niva** flows from a dock inside QGIS. Write or open a `.niva` file, click
**Run**, and the flow executes in the current QGIS session — results land on the map.

niva is a concise, readable text-pipeline grammar for QGIS geoprocessing:

```
load "data.gpkg|layername=roads" | buffer 100m dissolve | save out.gpkg
```

## Why there's no install step

The plugin **bundles niva** (it is zero-dependency, pure Python) and runs it
**in-process** on QGIS's own Python and Processing algorithms. So:

- **No `pip`, on any OS.** Works the same on Windows (OSGeo4W), macOS, and Linux —
  no interpreter detection, no subprocess, no dependency conflicts with QGIS.
- If you *do* have a `pip`-installed `niva`, the plugin prefers it; otherwise it
  uses the copy vendored at `libs/niva`.

## Install

Build the installer zip from the repo root:

```bash
plugin/build_plugin.sh        # → plugin/niva_qgis.zip
```

Then in QGIS: **Plugins ▸ Manage and Install Plugins ▸ Install from ZIP**, choose
`niva_qgis.zip`. Enable *"Show also experimental plugins"* if it doesn't appear
(it's marked `experimental=True`). A **niva** button appears on the toolbar; click
it to open the dock.

## Using the dock

- **Open…** loads a `.niva` file (so `call` and relative paths resolve from it).
- **Run** executes the flow in this QGIS session; a saved output is added to the map.
- **Dry-run** validates the flow over a mock backend (no geoprocessing) and prints
  the operation sequence — handy to check a flow before running it.

Flows run synchronously on the GUI thread in v0.1, so a long job briefly blocks the
UI (niva flows are serial within a process anyway).

## Files

| File | Role |
|------|------|
| `__init__.py` | `classFactory()`; makes the vendored `niva` importable |
| `plugin.py` | `NivaPlugin` — toolbar/menu action + dock toggle |
| `dock.py` | `NivaDock` — flow editor, Run/Dry-run, output, add-to-map |
| `runner.py` | GUI-free execution core (`run_flow`) — runs niva in-process |
| `metadata.txt` | plugin name, version, QGIS minimum version, icon |
| `icon.svg` | toolbar/menu icon (the niva logo) |
| `build_plugin.sh` | vendors niva + builds `niva_qgis.zip` |

The zip's top-level folder is `niva_qgis` (not `niva`, which would shadow the
vendored `niva` package).
