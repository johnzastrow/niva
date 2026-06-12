# niva — QGIS logo-demo plugin (stub)

A minimal QGIS plugin that previews the **niva** logo (`logo.svg`) in the QGIS
UI: it adds a toolbar button and a **Plugins ▸ niva** menu entry, and clicking
either opens a dialog showing the logo larger. The icon is an SVG, so it stays
crisp at any toolbar size and has a transparent background.

This is a stub to preview branding. The niva project (a PyQGIS wrapper for
higher-level geoprocessing) can grow into a full plugin from this skeleton.

## Install

Build the installer zip (from the repo root):

```bash
make -C plugin package        # → plugin/niva.zip
```

Then in QGIS: **Plugins ▸ Manage and Install Plugins ▸ Install from ZIP**, pick
`niva.zip`. Enable *"Show also experimental plugins"* in the Plugin Manager
settings if it doesn't appear (the stub is marked `experimental=True`).

The **niva** toolbar button then appears; click it (or **Plugins ▸ niva ▸
niva — logo demo**) to see the logo.

## Develop from source

Symlink this folder into your QGIS profile's plugin directory as `niva`:

```bash
ln -s "$(pwd)" \
  ~/.local/share/QGIS/QGIS4/profiles/default/python/plugins/niva   # Linux, QGIS 4
```

Then enable **niva (logo demo)** in the Plugin Manager. Restart QGIS after adding
new modules.

## Files

| File | Role |
|------|------|
| `__init__.py` | `classFactory()` — QGIS entry point |
| `plugin.py` | `NivaPlugin` — toolbar/menu action + the logo dialog |
| `metadata.txt` | plugin name, version, QGIS minimum version, icon |
| `icon.svg` | the toolbar/menu icon (a copy of `logos/logo.svg`) |
| `Makefile` | `make package` → `niva.zip` |
