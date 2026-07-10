# 21 — Frictionless install & the plugin-driven bootstrap (launcher, PATH, editors, marimo)

_Status: design for review._ How niva stops being fiddly to install. The core insight: **the niva
QGIS plugin already runs inside QGIS's own Python**, so it can bootstrap the entire OS-level setup —
a real `niva` command on `PATH`, editor integration, even sibling tools like
[marimo-qgis](https://github.com/johnzastrow/marimo-qgis) — from **buttons**, with no terminal and
no admin. This doc records the motivating incident, the options considered, the security analysis,
cross-platform behavior, gotchas, and a concrete design for a shared **setup-core** consumed by both
the CLI (`niva setup …`) and a new plugin **Setup tab**.

Related: [09 — deployment & operation](09-deployment-and-operation.md),
[12 — security model](12-security-model.md),
[20 — CLI & TUI architecture](20-cli-and-tui-architecture.md) (where `niva setup`, LSP live),
and the user-facing [editor-integration guide](../guide/editor-integration.md).

---

## 1. The problem: why install is fiddly today

niva executes inside **QGIS's bundled Python** (the only interpreter with PyQGIS). That interpreter
is deliberately *not* on the system `PATH`. Every current bridge over that gap is a **hand-written,
per-shell shell function**:

- Windows PowerShell — a `function niva { … }` in `$PROFILE`.
- Git Bash / Linux / macOS — an `alias`/function in `~/.bashrc` / `~/.zshrc`.

Shell functions are the wrong tool, and they fail in three predictable ways:

1. **They don't cross shells.** A function defined in `$PROFILE` is invisible in Git Bash, and vice
   versa. → niva "works in PowerShell but not Git Bash."
2. **They're invisible to GUI apps and child processes.** VS Code, Notepad++, or any spawned process
   cannot see a shell function. → the editor language server can't find `niva`.
3. **They rot silently.** A wrong path in the function isn't caught until runtime. → a stale
   `/usr/local/bin/niva` (a Linux path) sitting in a Windows VS Code `settings.json`.

### 1.1 Motivating incident (2026-07, this design's origin)

All three failure modes hit one Windows + OSGeo4W user in a single session:

- niva ran in PowerShell (a `$PROFILE` function) but **not** in Git Bash (no function there).
- VS Code **couldn't start the language server**: the extension defaulted to a bare `niva` command,
  which isn't on `PATH`; and the user's `settings.json` had a dead `"niva.lsp.command":
  "/usr/local/bin/niva"` (Linux path on Windows) plus `"*.niva": "sh"` forcing `.niva` files to the
  shell grammar so niva wasn't even selectable.
- Two additional latent bugs surfaced: the VS Code extension couldn't spawn a Windows `.bat`
  without a shell (Node/Electron `EINVAL` since CVE-2024-27980), and the PowerShell editor-installer
  aborted because `$ErrorActionPreference='Stop'` turned a benign `vsce` stderr warning into a fatal
  error.

Every one of these traces back to the same root cause: **niva is not a real command.** The fix is
not better documentation of shell functions — it's to stop using shell functions.

### 1.2 Environment facts (verified on the reference machine)

- QGIS via **OSGeo4W** at `C:\OSGeo4W`; launcher `C:\OSGeo4W\bin\python-qgis.bat` sets up the full
  QGIS environment (Qt/GDAL/PROJ on `PATH`) — confirmed it runs niva headless.
- niva is **already pip-installed** into that interpreter: `qgis_niva 0.62.4` in
  `C:\osgeo4w\apps\Python312\Lib\site-packages` → proving that site-packages is **writable** and
  PyPI installs work there.
- `python-qgis.bat -m niva.cli.main lsp` starts the language server and answers a real LSP
  `initialize` handshake — the *server* is fine; only the *spawn/PATH* wiring was broken.

---

## 2. The fix, in one idea: a real launcher file

Replace the shell function with a **launcher file on disk** that any program can execute. It is
tiny and simply forwards to QGIS's Python.

**Windows** — `%LOCALAPPDATA%\niva\bin\niva.cmd`:

```bat
@echo off
"C:\OSGeo4W\bin\python-qgis.bat" -m niva.cli.main %*
```

**macOS / Linux** — `~/.local/bin/niva`:

```bash
#!/usr/bin/env bash
exec "/path/to/qgis/python3" -m niva.cli.main "$@"
```

With that one file on `PATH`, `niva` is a real command in **every** shell *and* every GUI app. The
VS Code extension's default `niva lsp` "just works" with no settings; the Git-Bash-vs-PowerShell
split disappears; there are no more `$PROFILE` / `.bashrc` functions to maintain.

> **Why not the pip `niva.exe`?** pip already produced `…\Scripts\niva.exe`. But that launcher runs
> QGIS's Python **without** the environment `python-qgis.bat` establishes (the Qt/GDAL/PROJ `PATH`
> entries), so offline commands work but `niva run` and live hover can fail to load providers. The
> `.cmd`/shell shim routes *through* `python-qgis.bat`, so it always has the full QGIS environment.
> That reliability difference is why the shim is preferred over exposing the raw `Scripts` dir.

---

## 3. Options considered (an escalating ladder)

Three "make it installable" options, each building on the previous, plus the one that supersedes
them all.

| Option | What it is | Effort | User action | Notes |
|---|---|---|---|---|
| **A — launcher on PATH** | `niva setup command`: write the launcher + add its dir to the per-user PATH | Small | run one command | Foundation for everything else |
| **B — bootstrap installer** | one script that does A + detect QGIS + `pip install` + editor integration + `doctor` | Medium | paste one line | In-repo `bootstrap.ps1`/`.sh`, or a remote `irm … | iex` one-liner |
| **C — native package** | `.msi` / Homebrew / `.deb`, double-click | High | double-click | Separate build pipeline per OS; still must detect an existing QGIS |
| **D — plugin-driven bootstrap** | **buttons in the QGIS plugin** that do A/B (and editors, marimo) from QGIS's Python | Medium | click | **Recommended.** No terminal, no discovery, one Qt codebase for all OSes |

**A** is the load-bearing foundation. **B** is A plus glue. **C** is heavy and, because niva always
needs a pre-existing QGIS (you can't bundle ~1 GB of QGIS into a niva installer), still reduces to
"detect QGIS, then wire up niva" — the same core as A, wrapped in a GUI installer. Best deferred to
a 1.0 polish pass.

**D supersedes the terminal installers** for most users and is the subject of the rest of this doc.

---

## 4. Why the plugin-driven bootstrap (D) is the right primary path

The niva plugin runs *inside* QGIS's Python. That single fact removes the largest source of install
bugs:

- **No discovery, no wrong paths.** The terminal installers must *guess* where QGIS's Python is (and
  get it wrong — that is how `/usr/local/bin/niva` happened). The plugin doesn't guess: it **is**
  that interpreter. `sys.prefix` and `QgsApplication.prefixPath()` give the exact location of
  `python-qgis.bat`.
- **One codebase, every OS.** Python + Qt buttons replace the `.ps1` / `.sh` / `.msi` trio. The same
  button works on Windows, macOS, and Linux.
- **Per-user, no admin.** Everything writes to `%LOCALAPPDATA%` / `~/.local` and `HKCU` — no
  elevation prompt.
- **Matches the mental model.** "Installing a plugin is simple" — this makes setup just as simple: a
  click, no terminal.

The plugin already contains system-integration actions (e.g. *"Save secrets to QGIS encrypted
store"* in `plugin/dock.py`), so a **Setup tab** is a natural, in-keeping addition rather than a new
kind of behavior.

---

## 5. Security analysis

### 5.1 The framing that matters most

**A QGIS plugin already runs arbitrary Python with the user's full privileges.** Installing the niva
plugin is already a trust decision equivalent to running any program. These buttons grant the plugin
**no new capability** — it could already edit PATH or pip-install today. The security work is
therefore about **doing it transparently and reversibly**, not about crossing a new privilege
boundary.

### 5.2 Per-action risk & controls

| Action | Risk | Control |
|---|---|---|
| **Append dir to PATH** | An executable later dropped in that dir becomes a runnable command; a *front-of-PATH* entry could shadow `python`/`git` | **Append at the end**, never prepend. Dir under per-user `%LOCALAPPDATA%` (ACL'd to the user, not world-writable). Put **only** `niva.cmd` there. **Per-user `HKCU` only — never system `HKLM`, never admin.** |
| **pip install from PyPI** | Supply chain: a compromised/typosquatted package runs code at install time (sdist `setup.py`) | Pin the exact name `qgis-niva`; **prefer wheels** (`--only-binary=:all:`) so no arbitrary install-time code runs; HTTPS + cert (pip default); niva is **zero-dependency** → one package trusted, not a transitive tree; only on explicit click, never on load |
| **Write `niva.lsp.command`** | VS Code will later *spawn* that command → RCE if attacker-influenced | Value is computed by us from the QGIS prefix — **never** from untrusted input (e.g. a project file). Absolute path we control |
| **Edit `settings.json` / editor configs** | Corrupting the user's file | Back up first; non-destructive JSONC-aware merge; only on explicit action |
| **Registry + file writes** | AV/EDR heuristics may flag "QGIS writing `HKCU\Environment` + dropping a `.cmd`" | Standard locations, documented behavior, optional plugin signing — this is trust-noise, not a vulnerability |

### 5.3 Design rules (security-first defaults applied)

- **Never require a tool the user doesn't already have.** QGIS's Python always ships `pip`, so the
  setup-core installs with **`<qgis-python> -m pip`** and the **stdlib only** — never `uv`, never a
  compiler, never a package the user must install first. (`uv` may be *used* as a faster path *if
  already present*, but is never required.) marimo-qgis happens to use `uv`; because niva **delegates**
  the marimo install (§10.1), that choice stays inside marimo-qgis and niva never inherits a `uv`
  dependency.
- **Least privilege** — per-user everything, no elevation, single launcher file, append-not-prepend.
- **Informed consent** — every button shows a dialog stating *exactly* what it will create/modify
  before acting; **nothing happens on plugin load**.
- **Fail closed & reversible** — back up before mutating; if a PATH edit can't complete cleanly, roll
  back rather than leave it half-written; every "install" has a matching "remove."
- **Auditability** — log every action to the QGIS message log: what changed, and where.
- **No secrets** — the launcher holds only a path; nothing sensitive is written.

The two genuinely sensitive operations are **PATH editing** (wrong registry semantics can damage a
user's environment) and **pip** (supply chain). Both are manageable with the controls above, and
both are things the user explicitly clicks. See [12 — security model](12-security-model.md) for the
project-wide threat model this extends.

---

## 6. Precedent — this pattern is well established

"A GUI app installs its own launcher onto PATH / edits shell init" is common and expected:

- **VS Code** — *"Shell Command: Install 'code' command in PATH"* (the closest analog: a UI action
  that adds the app's own launcher to PATH).
- **JetBrains IDEs** — *"Create Command-line Launcher."*
- **Sublime (`subl`), Atom (`atom`)** — CLI launcher installers.
- **rustup / nvm / pyenv / conda** — bootstrap tools that write launchers **and edit the shell
  profile** (`conda init` rewrites `.bashrc` / PowerShell profile). The more invasive precedent, and
  it's mainstream.
- **QGIS plugins that pip-install dependencies at runtime** — an established (if debated) practice;
  the **QPIP** plugin exists specifically to manage it. Notably, **marimo-qgis already ships this
  exact pattern**: a plugin Setup tab that reports the environment and pip-bootstraps into QGIS's
  Python with read-only fallbacks (see §10).

**Caveat on the QGIS-specific precedent:** the community is wary of plugins that pip-install into the
shared QGIS Python and cause dependency breakage. niva sidesteps the usual objection because it is
**pure-Python, stdlib-only** — installing it cannot drag in conflicting binary wheels. Follow the
respectful version of the pattern: explicit consent, no silent env mutation, pure-python only. (This
caveat does **not** transfer to marimo — see §10.2.)

---

## 7. Cross-platform support

One Python/Qt codebase covers all three, behind a small platform layer.

| | Launcher | PATH mechanism | Main headache |
|---|---|---|---|
| **Windows** | `%LOCALAPPDATA%\niva\bin\niva.cmd` → `python-qgis.bat -m niva.cli.main %*` | `HKCU\Environment` (as `REG_EXPAND_SZ`) + broadcast `WM_SETTINGCHANGE` via ctypes | Registry correctness; "restart terminal to see PATH" |
| **macOS** | `~/.local/bin/niva` → `QGIS.app/Contents/MacOS/bin/python3 -m niva.cli.main "$@"` | append to `~/.zprofile` / `~/.zshrc`; `~/.local/bin` often not on PATH by default | GUI apps launched from Finder don't inherit shell PATH; **QGIS.app is a signed bundle** → can't pip into it, must use `--user` |
| **Linux** | `~/.local/bin/niva` (pip `--user` usually already creates it) | usually already on PATH; else append to shell rc | PEP 668 externally-managed envs need `--break-system-packages`; **Flatpak/Snap QGIS is sandboxed** → can't touch host PATH / other apps |

**Universal mitigation** for "GUI apps don't see the new PATH" (Windows *and* macOS): do not make VS
Code depend on PATH — the editor button **also writes `niva.lsp.command` directly**. The LSP works
immediately; PATH is only for terminal use.

---

## 8. Limitations & gotchas

- **PATH propagation lag (all OSes):** already-open terminals and a running VS Code won't see the
  change until restart. Tell the user; write editor settings directly to cover VS Code.
- **pip into a *running* QGIS:** an upgraded package may not import cleanly until QGIS restarts
  (module caching). "Install/Upgrade" should say *"restart QGIS to use the new version."*
- **macOS signed bundle:** pip **must** use `--user` (into `~/Library/Python/x.y/…`) and that path
  must be importable by QGIS — writing into `QGIS.app/Contents` can break the code signature or be
  read-only.
- **PEP 668 (Linux system QGIS):** needs `--break-system-packages`.
- **Sandboxed QGIS (Flatpak/Snap):** setup buttons can't reach host PATH or other apps' configs —
  **detect and gray them out with an explanation** rather than fail.
- **Windows registry pitfalls:** never use `setx` (truncates PATH at ~1024 chars and can corrupt it);
  use the registry API. **Preserve the value type** — writing `REG_SZ` over a `REG_EXPAND_SZ` breaks
  `%VAR%` expansion elsewhere. Guard the ~2047-char user-PATH limit.
- **`code` CLI absent:** installing the VS Code extension via CLI needs `code` on PATH; fall back to
  shipping the `.vsix` path with instructions.
- **Uninstall must be surgical:** remove *our* PATH entry without disturbing others; remove the
  launcher and editor configs; restore backups.
- **Dev machines with two nivas:** a pip install *and* a git clone can both be importable; the
  launcher uses whichever wins on `sys.path`. Fine for end users (one install); a note for devs.
- **Corporate GPO / locked env:** `HKCU` is usually writable even when `HKLM` isn't, but some
  policies lock user env — detect the failure and message clearly.
- **AV false positives & unsigned plugin:** possible support noise; not a vulnerability.

---

## 9. Design

### 9.1 Button layout — a new "Setup" tab in `NivaDock`

Consistent with the existing tabbed dock. Status chips (✓/✗/⚠) update after each action; every action
opens a confirm dialog and runs in a background `QgsTask` (like `plugin/flowtask.py`) so QGIS never
freezes.

```
┌─ Setup ─────────────────────────────────────────────────────┐
│  Environment                                    [ Re-check ] │
│    QGIS Python … C:\OSGeo4W\apps\Python312\python.exe    ✓    │
│    niva package … 0.62.4 (pip)   ·   latest 0.62.5      ⬆    │
│    On PATH …      no                                    ✗    │
│ ─────────────────────────────────────────────────────────── │
│  1  niva package                                             │
│     [ Install / Upgrade ]   [ Remove ]                       │
│     ⓘ pip install qgis-niva into QGIS's Python (wheel)       │
│                                                              │
│  2  Command line  —  make `niva` work everywhere             │
│     [ Create niva command ]   [ Remove ]                     │
│     ⓘ writes %LOCALAPPDATA%\niva\bin\niva.cmd + adds to PATH │
│                                                              │
│  3  Editor support                                           │
│     ☑ VS Code    ☑ Notepad++    ☐ Vim / Neovim               │
│     [ Install selected ]      [ Remove ]                     │
│     ⓘ VS Code also gets niva.lsp.command set automatically   │
│                                                              │
│  4  Notebooks — marimo (optional)          QGIS 4.0+  ⚠      │
│     [ Install Marimo QGIS ]   [ Open marimo docs ]           │
│     ⓘ installs the marimo-qgis *plugin* only; marimo itself  │
│        is installed later by that plugin's own Setup tab.     │
│ ─────────────────────────────────────────────────────────── │
│  ▸ Details / log                                             │
│    12:04 created niva.cmd → %LOCALAPPDATA%\niva\bin          │
│    12:04 PATH: appended (restart terminals to pick it up)    │
└──────────────────────────────────────────────────────────────┘
```

Confirm-dialog example (button 2): *"This will create
`C:\Users\you\AppData\Local\niva\bin\niva.cmd` and add that folder to your user PATH. No admin
needed; reversible with Remove. Continue?"*

### 9.2 Setup-core API

The key principle (the same one that lets the repl and LSP share `niva.intelligence`): **the core
does the work and returns *data*; it never prints, prompts, or exits.** The CLI renders that data as
text; the plugin renders it as chips and log lines — they cannot drift. Consent lives in each **UI
layer**, not the core.

New pure-Python package `niva/setup/` (no Qt, no `print`):

```python
# niva/setup/core.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

PYPI_NAME = "qgis-niva"          # pinned; never taken from input

@dataclass
class StepResult:
    ok: bool
    changed: bool                # idempotency signal (did anything actually change)
    message: str                 # one-line human summary
    detail: str = ""             # paths touched, prior value (for undo), stderr, …
    undo_hint: str = ""          # e.g. "niva setup command --remove"

@dataclass
class EnvReport:
    platform: str                        # "windows" | "macos" | "linux"
    qgis_python: Path
    qgis_launcher: Optional[Path]        # python-qgis.bat on Windows, else None
    niva_installed: Optional[str]        # installed version or None
    niva_latest: Optional[str] = None    # from PyPI if check_pypi=True
    on_path: bool = False
    launcher_path: Optional[Path] = None
    sandboxed: bool = False              # Flatpak/Snap → disable OS actions
    warnings: list[str] = field(default_factory=list)

# ---- detection (trivial & reliable: we're *inside* QGIS's Python) ----
def detect_environment(check_pypi: bool = False) -> EnvReport: ...

# ---- 1. package ----  (uses `<qgis-python> -m pip`; never requires uv — see §5.3)
def install_niva(*, upgrade: bool = False, dry_run: bool = False) -> StepResult: ...
def uninstall_niva(*, dry_run: bool = False) -> StepResult: ...

# ---- 2. command / launcher + PATH  (CLI: `niva setup command`) ----
def install_command(*, dry_run: bool = False) -> StepResult: ...
def uninstall_command(*, dry_run: bool = False) -> StepResult: ...
def launcher_target() -> Path: ...        # where niva.cmd / niva goes on this OS

# ---- 3. editors (reuses the .vscode/niva assets) ----
def install_editors(*, vscode=True, notepadpp=True, vim=False,
                     dry_run: bool = False) -> list[StepResult]: ...
def uninstall_editors(*, vscode=False, notepadpp=False, vim=False,
                      dry_run: bool = False) -> list[StepResult]: ...

# ---- 4. marimo on-ramp (see §10) — installs the marimo-qgis *plugin* only; never marimo itself ----
def install_marimo_qgis_plugin(*, dry_run: bool = False) -> StepResult: ...
#   guards: requires QGIS >= 4.0; fetches the marimo_launcher release zip into the plugin dir and
#   prompts for restart. Does NOT pip/uv-install marimo — marimo-qgis's own Setup tab does that,
#   on separate explicit consent. Returns available=False on QGIS < 4.0 / sandboxed / macOS-warn.

# ---- health ----
def doctor() -> list[StepResult]: ...
```

Platform specifics hide behind an internal module so the public API stays flat:

```python
# niva/setup/_platform.py   (dispatches to _windows.py / _posix.py)
def write_launcher(path: Path, python_cmd: str, module: str) -> bool     # returns changed
def ensure_on_path(directory: Path) -> tuple[bool, str]                  # (changed, prior_value)
def remove_from_path(directory: Path) -> tuple[bool, str]
def broadcast_env_change() -> None                                       # WM_SETTINGCHANGE / no-op
```

**Security-relevant choices baked into the API**

- `install_niva` pins `PYPI_NAME`, prefers wheels (`pip install --only-binary=:all:`), no arbitrary
  sdist code.
- `ensure_on_path` **appends** and returns the **prior value** in `StepResult.detail` so
  `uninstall_command` can restore it; preserves `REG_EXPAND_SZ`.
- Every mutating call accepts `dry_run=True`, returning the same `StepResult` describing *what would
  change* — this powers both the confirm dialogs and a `niva setup … --dry-run` CLI flag.
- Every mutator is idempotent and reports `changed` (re-running is safe and says "nothing to do").

### 9.3 Wiring (both front-ends call the identical core)

`niva setup` already exists with `doctor | wizard | show | init | path | get | set | unset`
(dispatched in `niva/cli/main.py`). **Note `path` is taken** (it prints the config-file path), so the
launcher action is named **`command`**. New subcommands:

```python
# CLI  (niva/cli/main.py, in _setup)
#   niva setup command  [--remove] [--dry-run]
#   niva setup editors  [--vscode] [--notepadpp] [--vim] [--remove]
#   niva setup install  [--upgrade]        (doctor / wizard / path already exist)
#   niva setup marimo   [--remove]
res = core.install_command(dry_run=args.dry_run)
print(res.message); return 0 if res.ok else 1

# Plugin  (plugin/dock.py, Setup tab)
def _on_create_command(self):
    preview = core.install_command(dry_run=True)          # show in confirm dialog
    if not self._confirm(preview.message, preview.detail):
        return
    self._run_task(core.install_command, on_done=self._refresh_status)  # QgsTask
```

Net effect: the plugin buttons, the `niva setup …` CLI, and `niva setup doctor` become three faces of
one tested core. No logic lives in the Qt layer, so nothing can silently diverge — and the core is
unit-testable without QGIS.

---

## 10. marimo-qgis integration

[marimo-qgis](https://github.com/johnzastrow/marimo-qgis) runs reactive
[marimo](https://marimo.io) notebooks on QGIS's own Python, with a localhost HTTP bridge that lets
notebooks read layers/selection/canvas extent from a running QGIS project and push results back as
new layers. The eventual goal: **marimo as the coding, execution, and analysis platform for QGIS,
with niva as the concise geoprocessing grammar inside it.**

### 10.0 Non-negotiable: marimo is strictly optional, and niva stays out of marimo's dependency tree

Two hard constraints frame everything below:

1. **niva core never depends on marimo.** No niva import, verb, test, or default path may require
   marimo. The integration is an opt-in button and a Python-API convenience, nothing more. niva must
   install, run, and pass its suite with marimo entirely absent.
2. **niva does not pip-install marimo itself.** marimo's dependency tree and localhost server are an
   attack surface we don't want to own. niva's button **delegates** to marimo-qgis, which already has
   its own bootstrap — see §10.1. This keeps marimo's ~15–20 packages, its `uv`/pip machinery, and
   its web server entirely inside marimo-qgis's trust boundary, not niva's.

### 10.1 The onboarding button — delegate, don't reimplement

**Finding (from reading marimo-qgis source, `plugin/runtime.py` + `plugin/environment.py`):**

- It resolves the interpreter with `qgis_python()` **derived from the live process** (`sys.prefix` /
  `sys.executable`, Windows `python.exe`/`pythonw.exe` handling) — *no hardcoded version or path*.
  This is the same strategy §9.2 proposes for niva; adopt the convention, not the code.
- It manages packages with **`uv`** (`uv_executable()` with a `MARIMO_QGIS_UV` env override and PATH
  probing that explicitly accounts for the OSGeo4W shell dropping `~/.local/bin`), **not** plain pip.
- Its actual marimo install + read-only fallbacks live in its **own Setup tab / process manager**, not
  in a reusable library.

**Verdict — do NOT share code, and do NOT have niva install marimo.** The overlap is only ~a few
interpreter-detection functions; niva's real weight (launcher-on-PATH, editor wiring, zero-dep pip) is
absent from marimo-qgis, and the two use different installers (`uv` vs pip). Coupling two
independently-versioned plugins for that small overlap costs more than it saves today.

So niva's **"Install Marimo QGIS"** button does exactly one thing:

1. **Install the `marimo_launcher` plugin** — fetch a **pinned release asset**
   (`.../releases/download/v0.6.0/marimo_launcher.zip`) into the QGIS plugins dir (with a zip-slip
   guard), enable it, then start marimo's install via that plugin's own
   `MarimoProcessManager().install_marimo()`. Pinning to a tagged release (not `main`) keeps the
   on-ramp reproducible; bump `MARIMO_QGIS_TAG` in `niva/setup/marimo.py` to adopt a newer one. The
   heavy dependency install is still marimo-qgis's, on its own async pip — never niva's.

This makes niva a pure **on-ramp**: it hands the user to marimo-qgis and steps back. niva's attack
surface gains only "download a plugin zip and register it," not marimo's entire runtime.

### 10.2 The critical difference: niva's pip-safety story does NOT transfer — so niva won't own it

**niva is zero-dependency; marimo is not.** marimo pulls a real tree — starlette, uvicorn,
websockets, jedi, psutil, pygments, and more. That changes the risk profile of the pip step:

- **Env pollution / version conflicts** — installing ~15–20 packages into QGIS's *shared*
  site-packages can collide with versions QGIS bundles (Jinja2, pygments, markupsafe, …) and subtly
  break QGIS or the notebook. This is exactly the QGIS-community objection niva sidesteps.
- **Supply chain** — many maintainers to trust instead of one.
- **Local web server** — marimo runs a notebook server and marimo-qgis injects a localhost HTTP
  bridge. That is a network surface: notebooks execute arbitrary Python by design (same trust as any
  notebook).

**This is precisely why niva delegates (§10.1).** Every one of these risks is marimo-qgis's to manage
inside its own trust boundary — pinning the marimo version, choosing wheels/isolation, and binding the
server to `127.0.0.1`. niva neither performs nor owns any of it. niva's exposure from the button is
limited to *"download a plugin zip and register it,"* and even that happens only on an explicit click,
guarded by the QGIS-4.0 check in §10.3. If marimo-qgis is absent, niva is completely unaffected.

### 10.3 Compatibility gotchas

- **QGIS floor mismatch:** niva supports **QGIS 3.22+/4.x**; marimo-qgis requires **QGIS 4.0+**. The
  button must **detect QGIS < 4.0 and disable itself** with an explanation, or it will onboard 3.x
  users into a broken install.
- **macOS untested** for marimo-qgis — gray out / warn on macOS.
- **Version drift** between the two plugins — pin the marimo-qgis release installed and surface it.

### 10.4 The deeper integration (near-term hooks)

niva's role is the terse geoprocessing grammar inside marimo cells; the pieces already exist:

- `niva.flow("load … | buffer 100m | save …")` is a **Python API** — it drops straight into a marimo
  cell today, no glue.
- niva already **exports flows to PyQGIS scripts**; an analogous **`niva export --to marimo`** would
  emit reactive cells (leaning on the existing `jupyter-to-marimo` conversion knowledge).
- marimo-qgis's **localhost bridge** is the channel for a *standalone* marimo to talk back to a
  running QGIS; niva flows become the terse verbs that drive it.
- niva's **provenance/journal** + marimo's **reactivity** → reproducible, re-runnable analysis.

#### What the marimo-qgis bridge actually exposes (verified from `qgis_bridge/`)

The QGIS↔notebook integration is **entirely marimo-qgis's** feature; niva installing marimo-qgis
neither adds nor removes it. The bridge (available only when the notebook is **launched via
marimo-qgis**, which injects `MARIMO_QGIS_PORT`/`TOKEN`) is bidirectional and includes rendered
graphics:

| Direction | Bridge call | Result |
|---|---|---|
| QGIS → notebook (read) | `list_layers()`, `get_layer(name)`, `get_selected_features()`, `layer_info()`, `get_canvas_extent()`, `project()` | layers as GeoDataFrame/xarray, selection, extent, metadata |
| notebook → QGIS map | `insert_layer(gdf, name=…)` | pushes a result in as a new memory layer — **geometry appears on the QGIS map** |
| QGIS → notebook (image) | `render_map(width, height)` | **PNG bytes of the live QGIS canvas** for `mo.image(…)` |
| processing | `run_algorithm(alg_id, params)` | run Processing from a cell |

So both directions the design cares about are first-class: `insert_layer` (geometry onto the map)
and `render_map` (QGIS graphics into the notebook).

#### Does `niva.flow("… | map plot.png")` show `plot.png` in the notebook?

Partly — and importantly, **this path does not use the bridge at all**. The `map` (and `figure`)
verbs render a PNG/PDF/SVG **to disk**; that runs fine in a marimo cell on QGIS's Python (offscreen
layout export, no running QGIS app needed). But `niva.flow(...)` returns the final **layer handle**,
not the image, so the file does not auto-display. To show it, reference the file:
`mo.image("plot.png")`. This is independent of `render_map()` (which is for the *live* canvas).

A small, high-value niva-side enhancement would close this: have `map`/`figure` outputs come back as
a **displayable object** (with a MIME/`_repr_` hook), so `niva.flow("… | map plot.png")` as a cell's
last expression renders inline automatically. That is the concrete `niva.flow`-in-cells glue.

#### What kind of cell runs niva DSL in marimo? (marimo is pure-Python)

niva flows are a DSL, not Python — so it's natural to ask whether marimo needs a "niva cell." The
answer, from marimo's docs: **a marimo notebook is always a pure-Python `.py` file, and every cell is
Python.** marimo's own non-Python cells (SQL, Markdown) are **editor sugar that compiles to a Python
call** — a SQL cell is stored/run as `output = mo.sql(f"SELECT … {ui.value}")`, a Markdown cell as
`mo.md(…)`. There is **no public extension point for adding a third-party cell language.**

Implications for niva:

- **Today:** niva runs in an ordinary Python cell as `niva.flow(f"load … | buffer {dist}m | save …")`
  — *exactly* the SQL-cell pattern (`mo.sql(f"…")` ↔ `niva.flow(f"…")`), including f-string
  interpolation of marimo UI values. No new cell type needed to *use* niva.
- **The "niva cell" feel** we control without marimo internals: a helper that returns a **displayable**
  (so `map`/`figure` outputs render inline, per the previous subsection) and accepts marimo UI
  elements for parameters. That gets ~90% of a native cell.
- **A genuine niva cell** (write bare `.niva` grammar, editor-highlighted, no `niva.flow("…")`
  wrapper) would require an **upstream marimo contribution** — a sugar cell type that compiles to
  `niva.flow(…)`, the same way SQL compiles to `mo.sql(…)` — or a marimo fork. Track this together
  with the parked niva-LSP-in-marimo idea below; both are upstream-marimo asks, not niva-only work.

#### Marimo in niva's plugin: yes to the on-ramp, no to duplicating its dock

niva users should be able to **get marimo for free** — one click, from inside niva. That on-ramp is a
first-class part of the design (the "Notebooks — marimo" section of the Setup tab, §9.1). What niva
should **not** do is re-implement marimo-qgis's *notebook-management* UI (its Browse / Running /
bridge tabs): once marimo-qgis is installed, the user drives notebooks from **marimo-qgis's own
dock**. Duplicating that dock inside niva would pull marimo's whole surface into niva and violate the
optional/minimal-surface rule (§10.0).

So: **install affordance — yes** (prominent, one click); **management UI — no** (hand off to
marimo-qgis).

**The one real trade-off — how "free" is one click?** niva installs the marimo-qgis *plugin*; marimo
itself (the ~15–20-package tree) is installed by marimo-qgis's own bootstrap. Two ways to wire the
button:

- **(a) Delegated, two steps (recommended default):** niva's button installs & enables the
  marimo-qgis plugin; after a QGIS restart, the user clicks *marimo-qgis's* Setup tab to install
  marimo. Cleanest boundary — niva never touches marimo's dependency tree, uv, or web server (§10.2).
- **(b) One click, via marimo-qgis's own installer:** niva's button installs the plugin **and calls
  marimo-qgis's own install function** to fetch marimo. Feels "free" in one click, and the pip/uv
  logic still lives in marimo-qgis (its trust boundary) — but it adds a runtime coupling and needs
  marimo-qgis to expose a stable install API.

Both keep niva out of *owning* marimo's install (rules §10.0/§10.2 hold). (b) is strictly a
convenience layer over (a). Not doing: niva running marimo's pip/uv itself — that would put marimo's
attack surface inside niva.

Honest framing: the button is an **onboarding convenience** now; the real integration is the
`niva.flow`-in-cells (displayable `map`/`figure` outputs) and `niva export --to marimo` layer.

#### Parked for later — niva LSP inside marimo

marimo supports language servers and GitHub Copilot in its editor
([marimo LSP docs](https://docs.marimo.io/guides/editor_features/language_server/#github-copilot)).
niva already ships **`niva lsp`** (§ the LSP work / editor-integration guide). Worth exploring once
the on-ramp lands: whether niva's LSP can provide `.niva`-grammar completion/diagnostics/hover for
niva flows written inside marimo cells (or a marimo extension that speaks to `niva lsp`), so the
same niva intelligence users get in VS Code/Neovim follows them into the notebook. Parked, not
scheduled.

---

## 11. Recommended build sequence

1. **`niva/setup/` core + `install_command`** with the Windows/POSIX PATH layer — the load-bearing,
   security-sensitive piece. Write it **test-first** (PATH append/remove, `REG_EXPAND_SZ`
   preservation, idempotency, dry-run). No QGIS needed to test. **✅ Done (0.63.0)** — `niva/setup/`
   (`core.py` + `pathenv.py`), 16 unittest cases, verified with a real install→run→remove roundtrip on
   Windows/OSGeo4W (PATH restored byte-for-byte). Two behaviors added during the build:
   `find_qgis_launcher()` also **probes well-known QGIS locations** (OSGeo4W, `Program Files\QGIS*`) so
   the standalone CLI works even when not run under QGIS's Python; and `install_command` **refuses**
   (returns `ok=False`) rather than write a launcher pointing at a non-QGIS interpreter when no
   `python-qgis.bat` is found.
2. **Wire the CLI** subcommands (`setup command` ✅; `setup editors`, `setup install` — pending).
   Note: `--dry-run` is a *global* niva flag that `main()` strips before dispatch, so it is threaded
   into `_setup(dry_run=…)` rather than read from the subcommand args.
3. **Add the plugin tab** to `plugin/dock.py`, calling the same core, with confirm dialogs and a
   status line. **✅ Done (0.63.0)** — an **"Install" tab** (the existing "Setup" tab name is taken by
   the secrets config): *Create/Remove niva command* → `install_command`, and *Install Marimo QGIS* →
   `install_marimo_qgis`. Confirm dialogs via `QMessageBox` (Qt5/Qt6-safe); status to a label + the
   QGIS message log. (Actions run synchronously for now; a `QgsTask` wrapper is a later refinement.)
   **marimo Phase 1 (on-ramp) landed here too** — see §10.1; the plugin download/enable path awaits
   live-QGIS validation.
4. **Editors** — port the `.vscode/niva/install.*` logic into `install_editors` (portable Python),
   including the auto-write of `niva.lsp.command`.
5. **marimo button** — last, and thin: `install_marimo_qgis_plugin` only (fetch + register the
   marimo-qgis plugin behind the QGIS-4.0 guard). niva never installs marimo itself (§10.1); the
   button stays fully optional and off by default.
6. **(Later, optional)** Option B remote bootstrap and/or Option C native packages for a 1.0.

---

## 12. Open questions

- **Share vs reimplement the bootstrap with marimo-qgis — RESOLVED for now: neither.** Reading
  marimo-qgis source (`plugin/runtime.py`, `plugin/environment.py`) shows the overlap is only a few
  interpreter-detection functions, and the two use different installers (marimo-qgis uses `uv`; niva
  wants zero-dep pip). niva **delegates** the marimo install rather than sharing code (§10.1). Revisit
  extracting a shared `qgis-python-bootstrap` micro-library **only if** a third consumer appears or
  both stabilize; until then, align *conventions* (live-interpreter detection, an env-var override,
  `StepResult`-style reporting) but keep the code separate.
- **Isolated marimo install** — deliberately **out of niva's scope** (marimo-qgis owns it). Tracked
  here only so niva's docs can point users at marimo-qgis's own guidance.
- **PATH consent granularity** — one dialog per action, or a single "set up everything" flow with a
  combined preview?
- **Uninstall depth** — should "Remove" also `pip uninstall` niva, or only remove the launcher/PATH
  and leave the package? (Leaning: separate, explicit.)
- **Signing** — is signing the plugin (and any future native installer) worth it to cut AV/SmartScreen
  friction?
