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

Install into **QGIS's own Python** — this is what makes `niva run` *execute*, because that
interpreter is the one with PyQGIS:

```bash
<qgis-python> -m pip install qgis-niva                    # pip, into QGIS's Python
uv pip install --python <qgis-python> qgis-niva           # …or uv, targeting that same interpreter
# dev/source install:  <qgis-python> -m pip install git+https://github.com/johnzastrow/niva.git
```

The deciding factor is the **target interpreter**, not the tool: both commands above land niva in
QGIS's Python, so both execute. By contrast `uv tool install` / `uvx` / `pipx` build their *own*
isolated Python (no PyQGIS) — great for offline authoring, but they can't run flows. See the note
below and the [FAQ](faq.md#its-the-install-mode-not-pip-vs-uv).

> **On PyPI** as **[`qgis-niva`](https://pypi.org/project/qgis-niva/)** (the import package and
> `niva` command stay `niva`, like `scikit-learn` → `sklearn`): `pip install qgis-niva`, or with
> [uv](https://docs.astral.sh/uv/): `uv tool install qgis-niva`, or run it with no install via
> `uvx --from qgis-niva niva …`. Add the rich REPL/TUI with the extra: `qgis-niva[cli]`.
>
> **One caveat with `uv tool` / `uvx` / `pipx`:** they install niva into their *own* isolated
> Python, which has **no PyQGIS** — so that install is the **offline** CLI (validate / explain /
> search / setup / plan / manifest / repl / export) only. To *execute* flows, niva has to run on
> QGIS's own Python: install the **plugin** (runs in QGIS) or `pip install qgis-niva` into
> `<qgis-python>` as above. Full breakdown in the
> [FAQ](faq.md#does-uv-tool-install-qgis-niva-connect-to-qgis-do-i-need-the-plugin).

#### Ubuntu (system QGIS) — install for all users or one user

On Ubuntu/Debian, QGIS uses the **system Python** (e.g. `/usr/bin/python3.14`; its PyQGIS
bindings live at `/usr/share/qgis/python`, added to the path at runtime). Confirm the exact
interpreter in the QGIS **Python Console**:

```python
import sys; print(sys.executable)      # → /usr/bin/python3.14 on Ubuntu
```

That interpreter is **externally-managed** (PEP 668), so every install below passes
`--break-system-packages` — safe here because niva is **pure-Python with zero runtime
dependencies** (it adds nothing to the system but niva itself).

**All users (system-wide, needs `sudo`)** — installs into the interpreter's global
`site-packages`, so the `niva` command and `import niva` work for every account and inside
QGIS's Python Console:

```bash
# with uv (recommended): --system installs into the interpreter, not a venv
sudo uv pip install --python /usr/bin/python3.14 --system --break-system-packages qgis-niva
# …or with pip:
sudo /usr/bin/python3.14 -m pip install --break-system-packages qgis-niva
```

This lands the package in `/usr/local/lib/python3.14/dist-packages/niva` and the launcher at
`/usr/local/bin/niva` (root-owned, on everyone's `PATH`). Verify from any directory:

```bash
niva --version            # or:  /usr/bin/python3.14 -c "import niva; print(niva.__version__)"
```

**One user (no `sudo`)** — installs into your personal user-site, which the same interpreter
also reads (nothing system-wide changes):

```bash
/usr/bin/python3.14 -m pip install --user --break-system-packages qgis-niva
```

This lands niva in `~/.local/lib/python3.14/site-packages` and the launcher at
`~/.local/bin/niva`. Make sure that bin dir is on your `PATH` (add to `~/.bashrc` if needed):

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Either way, because niva is installed **into QGIS's own interpreter**, `niva run` *executes*
flows (not just the offline commands) — and since **0.55.1** niva auto-discovers QGIS's bindings
(`/usr/share/qgis/python` on Ubuntu), so **the `niva` command just works from any directory** with
no `PYTHONPATH` needed. Verify: `niva info` should report the Processing providers (not
`Backend: mock`). Upgrade later with the same command plus `--upgrade`; uninstall with
`… pip uninstall qgis-niva`. Add the rich REPL/TUI with the `[cli]` extra: `… qgis-niva[cli]`.

> If your QGIS lives somewhere non-standard and `niva info` still shows `Backend: mock`, point niva
> at the bindings once via `export NIVA_QGIS_PYTHONPATH=/path/to/qgis/python` (the dir containing
> the `qgis/` package — find it in the QGIS Python Console with
> `import qgis, os; print(os.path.dirname(os.path.dirname(qgis.__file__)))`).

#### Make `niva` a terminal command

**If you `pip install`ed `qgis-niva` into QGIS's Python (above), you already have a `niva`
command — skip this section.** It's only for running niva **straight from a git clone** (no
install), where you need to point `niva` at QGIS's Python and add the repo to `PYTHONPATH`. The
portable way is a small alias/function in your shell profile. Substitute **`<qgis-python>`** — the
full path to QGIS's Python; find it in the QGIS **Python Console** with
`import sys; print(sys.executable)` — and **`/path/to/niva`** (your repo root).
`QT_QPA_PLATFORM=offscreen` keeps it headless.

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

**Windows · PowerShell (Windows Terminal) — add to `$PROFILE`** (open it with `notepad $PROFILE`),
then reload with `. $PROFILE`:

```powershell
function niva {
  $env:QT_QPA_PLATFORM = 'offscreen'
  & 'C:\OSGeo4W\bin\python-qgis.bat' -m niva.cli.main @args
}
# standalone installer instead of OSGeo4W? use e.g. 'C:\Program Files\QGIS 3.40\bin\python-qgis.bat'.
```

**Windows · Git Bash / MSYS2 (Windows Terminal) — add to `~/.bashrc`**, then reload with
`source ~/.bashrc`. Prefer bash over PowerShell in Windows Terminal? Use this instead. Call the
same `python-qgis.bat` — Git Bash runs Windows `.bat` files directly; quote the path with forward
slashes (`/c/...`):

```bash
niva() {
  QT_QPA_PLATFORM=offscreen "/c/OSGeo4W/bin/python-qgis.bat" -m niva.cli.main "$@"
}
# standalone installer instead of OSGeo4W? use e.g. "/c/Program Files/QGIS 3.40/bin/python-qgis.bat".
# running from a git clone (no pip install)? add the repo to PYTHONPATH as a *Windows* path so
# MSYS doesn't rewrite it — put it before the `"/c/OSGeo4W/...` on the line above:
#   QT_QPA_PLATFORM=offscreen PYTHONPATH='C:\Users\me\Github\niva' "/c/OSGeo4W/bin/python-qgis.bat" -m niva.cli.main "$@"
```

The **OSGeo4W Shell** (Start menu → *OSGeo4W Shell*) already has QGIS's Python on `PATH`, so there
you can `pip install qgis-niva` and just call `niva` — or run `python-qgis -m niva.cli.main` — with
no function needed.

`python-qgis.bat` sets up the QGIS environment itself, so no `PYTHONPATH` is needed on Windows
(except the git-clone case noted above). After reloading your profile, `niva run myflow.niva` works
from any terminal — verify with `niva info` (it should report the QGIS providers, not
`Backend: mock`). More detail (finding QGIS's Python, troubleshooting) is in the
**[User Guide](user-guide.md)**.

> **Git Bash path-rewriting gotcha:** MSYS auto-translates arguments that look like Unix paths when
> handing them to a Windows `.bat`. That usually helps (`/c/data/x.gpkg` → `C:\data\x.gpkg`), but if
> an argument ever gets mangled, prefix the call with `MSYS_NO_PATHCONV=1` to turn translation off
> for that command.

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
