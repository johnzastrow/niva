# Quick start

Install and run niva — inside QGIS (no install needed) or as a CLI on QGIS's own Python.

> **Dependencies:** the only requirement is **QGIS 3.22+/4.x** (niva runs in its Python) — core
> geoprocessing needs nothing else. Point clouds (`pdalcli:`/`pdal:`) need a PDAL backend
> (`pdal_wrench`) — bundled in QGIS on Windows/macOS, a one-line conda install on Linux: see the
> **[point-cloud setup guide](pdal-setup.md)**. SAGA, OTB, LAStools, `notify`/`email`,
> and editor highlighting are **optional** add-ons; see
> **[Dependencies — required & optional](user-guide.md#dependencies--required--optional)**.

### In QGIS — no install needed (easiest)

1. Get `niva_qgis.zip` — download it from the
   [latest release](https://github.com/johnzastrow/niva/releases/latest), or build it
   with `plugin/build_plugin.sh`.
2. In QGIS: **Plugins ▸ Manage and Install Plugins ▸ Install from ZIP** → pick the
   zip. (Enable *"Show also experimental plugins"* if it doesn't appear.)
3. Click the **niva** toolbar button, type a flow, hit **Run** — results land on the
   map. The plugin bundles niva, so there's no pip step on Windows, macOS, or Linux.

### As a package — CLI + Python

Install into **QGIS's own Python** (niva runs on QGIS's Processing):

```bash
<qgis-python> -m pip install git+https://github.com/johnzastrow/niva.git
```

> **On PyPI** (distribution **`qgis-niva`**; the import package and `niva` command are
> unchanged): once published this becomes `pip install qgis-niva`, or with
> [uv](https://docs.astral.sh/uv/): `uv tool install qgis-niva`, or run it without installing
> via `uvx --from qgis-niva niva …`. Add the rich REPL/TUI with the extra: `qgis-niva[cli]`.
> niva installed this way is the **offline** authoring CLI (validate / explain / search /
> setup / plan / manifest / repl); *running* flows still reaches out to a QGIS runtime.

#### Make `niva` a terminal command

`niva` runs on **QGIS's own Python**, so the `niva` command has to point at *that*
interpreter — not a Homebrew/pyenv/conda `python3`. The most portable way (it works whether you
`pip install`ed niva or run it straight from a clone) is a small alias/function in your shell
profile. Substitute **`<qgis-python>`** — the full path to QGIS's Python; find it in the QGIS
**Python Console** with `import sys; print(sys.executable)` — and, only when running from a clone,
**`/path/to/niva`** (your repo root). `QT_QPA_PLATFORM=offscreen` keeps it headless.

**Linux — add to `~/.bashrc`** (zsh: `~/.zshrc`), then `source ~/.bashrc`:

```bash
alias niva='QT_QPA_PLATFORM=offscreen PYTHONPATH=/path/to/niva:/usr/share/qgis/python:/usr/lib/python3/dist-packages <qgis-python> -m niva.cli.main'
# pip-installed (no clone)? drop the /path/to/niva: prefix from PYTHONPATH.
# Concrete: alias niva='QT_QPA_PLATFORM=offscreen PYTHONPATH=/home/me/Github/niva:/usr/share/qgis/python:/usr/lib/python3/dist-packages /usr/bin/python3.12 -m niva.cli.main'
```

**macOS — add to `~/.zshrc`**, then `source ~/.zshrc`:

```zsh
# QGIS.app's bundled Python already imports the bindings — no PYTHONPATH needed when pip-installed.
alias niva='QT_QPA_PLATFORM=offscreen /Applications/QGIS.app/Contents/MacOS/bin/python3 -m niva.cli.main'
# running from a clone? add the repo: PYTHONPATH=/path/to/niva /Applications/QGIS.app/Contents/MacOS/bin/python3 -m niva.cli.main
```

**Windows (Windows Terminal / PowerShell) — add to `$PROFILE`** (open it with `notepad $PROFILE`),
then reload with `. $PROFILE`:

```powershell
function niva {
  $env:QT_QPA_PLATFORM = 'offscreen'
  & 'C:\OSGeo4W\bin\python-qgis.bat' -m niva.cli.main @args
}
# standalone installer instead of OSGeo4W? use e.g. 'C:\Program Files\QGIS 3.40\bin\python-qgis.bat'.
```

`python-qgis.bat` sets up the QGIS environment itself, so no `PYTHONPATH` is needed on Windows.
After reloading your profile, `niva run myflow.niva` works from any terminal. More detail
(finding QGIS's Python, troubleshooting) is in the **[User Guide](user-guide.md)**.

Then run flows from the shell or Python:

```bash
niva run myflow.niva                              # execute a .niva file
niva "load a.gpkg | buffer 100m | save b.gpkg"    # a one-liner
niva describe buffer                              # how a verb maps to a QGIS algorithm
niva "load a.gpkg | buffer 100m | save b.gpkg" --dry-run   # validate — no QGIS needed
```

```python
import niva
niva.flow('load "data.gpkg|layername=roads" | buffer 100m dissolve | save out.gpkg')
```

> A GeoPackage holds many layers — name one with `|layername=…`. Databases:
> `load @conn.table`, `sql @conn "SELECT …"`, and write back with `save @conn.table`
> or a non-SELECT `sql @conn "…"` (credentials stay in QGIS).
