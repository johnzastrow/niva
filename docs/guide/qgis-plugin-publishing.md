# Publishing a QGIS plugin — a reusable playbook

A distilled, repo-agnostic guide to packaging and publishing a QGIS plugin to the official
**[QGIS Plugin Repository](https://plugins.qgis.org)** (`plugins.qgis.org`), written from niva's
own setup so it can serve as a **template for other plugins**. Where a step is niva-specific it is
called out; everything else transfers.

> Ground truth: the QGIS docs win over this file. Verify against
> **[Migrate to QGIS 4](https://plugins.qgis.org/docs/migrate-qgis4)** and the
> **[plugin metadata reference](https://plugins.qgis.org/publish/)** before trusting anything here.

---

## 1. `metadata.txt` — the contract with the repository

The repo ingests a zip whose top folder contains a `metadata.txt`. Fields niva sets, and why:

| Field | niva value | Notes |
|---|---|---|
| `name` | `niva` | Display name. |
| `qgisMinimumVersion` | `3.22` | Oldest QGIS you support. |
| `qgisMaximumVersion` | `4.99` | **This alone gates QGIS 4 readiness** (see §2). |
| `description` | one line | Short; shown in listings. |
| `about` | paragraph | Longer; indented continuation lines. |
| `version` | `0.42.4` | Must be **unique per upload** — bump every upload. |
| `author` / `email` | — | Required. |
| `repository` | GitHub URL | **Required** by the repo. |
| `tracker` / `homepage` | URLs | Recommended. |
| `category` | `Plugins` | Menu placement (Vector/Raster/Database/Web/Plugins). |
| `tags` | `processing,automation,…` | Comma-separated; drives discoverability. |
| `icon` | `icon.png` | Raster preferred for the website thumbnail (see §4). |
| `experimental` | `True` | Only shown to users who opt into experimental plugins. Flip to `False` when stable. |
| `deprecated` | `False` | — |
| `changelog` | latest 1–2 versions | Shown in the Plugin Manager; keep concise. |

**Do NOT set `plugin_dependencies` unless you truly need a pip package** — a self-contained plugin
installs with no extra steps (niva vendors its pure-Python package; see §4).

---

## 2. QGIS 4 / Qt6 readiness — the part that trips people up

The **`supportsQt6` flag is removed from QGIS core and no longer recognised.** Do not set it.
QGIS-4 readiness is determined **solely** by:

```
qgisMaximumVersion=4.99
```

Setting that (with your existing `qgisMinimumVersion=3.xx`) lists the plugin for **both** QGIS 3.x
and QGIS 4.x. (The niva repo learned this from a plugins.qgis.org reviewer message on v0.42.3.)

**Code must actually work on Qt6.** The safe, dual-version pattern — used throughout niva's
`plugin/` — is to import Qt through the QGIS-provided compatibility layer **`qgis.PyQt`**, never raw
`PyQt5`/`PyQt6`:

```python
from qgis.PyQt.QtCore import Qt          # not `from PyQt5.QtCore import Qt`
from qgis.PyQt.QtWidgets import QDockWidget
```

Watch for classes **relocated between Qt5 and Qt6** — most notably `QAction` moved from
`QtWidgets` (Qt5) to `QtGui` (Qt6). Handle both:

```python
try:                                        # Qt6
    from qgis.PyQt.QtGui import QAction
except ImportError:                         # Qt5
    from qgis.PyQt.QtWidgets import QAction
```

Then **test on a real QGIS 4 build** before publishing.

---

## 3. License

- Ship an **OSI-approved** license (QGIS itself is GPL; GPL-compatible is expected).
- Keep the license **consistent** across `LICENSE`, `pyproject.toml`, README badges, and any deck —
  a mismatch is a red flag. (niva declares **GPL-3.0-or-later** and bundles the full GPL-3 text.)
- **Bundle the `LICENSE` inside the plugin zip**, not just in the git repo (see §4).

---

## 4. Packaging the zip (niva's `plugin/build_plugin.sh` pattern)

Requirements the repo enforces, and how niva meets them:

1. **Exactly one top-level folder**, and its name must be a **valid Python identifier** — it becomes
   the plugin's import package. niva uses `niva_qgis/` (not `niva/`, which would shadow the vendored
   library).
2. **Self-contained** — no pip step for users. niva vendors its zero-dependency pure-Python package
   under `niva_qgis/libs/niva/` and adds `libs/` to `sys.path` at load.
3. **Bundle `LICENSE`** and an **`icon.png`** (render from SVG with `rsvg-convert -w 256 -h 256
   --background-color=none icon.svg -o icon.png`).
4. **Strip `__pycache__` / `*.pyc`** so the zip is clean.

Sketch (see `plugin/build_plugin.sh` for the full script):

```bash
STAGE="$WORK/niva_qgis"
cp plugin/{__init__,plugin,dock,runner,…}.py plugin/metadata.txt plugin/icon.{svg,png} "$STAGE/"
cp LICENSE "$STAGE/LICENSE"                 # ship the license inside the package
cp -r niva "$STAGE/libs/niva"              # vendor the pure-Python lib
find "$STAGE" -name __pycache__ -prune -exec rm -rf {} +
( cd "$WORK" && zip -qr niva_qgis.zip niva_qgis )
```

Verify before shipping:

```bash
unzip -l niva_qgis.zip | grep -E 'niva_qgis/(metadata.txt|LICENSE|icon.png)$'
unzip -p niva_qgis.zip niva_qgis/metadata.txt | grep -E '^version|^qgisMaximumVersion'
```

**Distribution:** niva keeps the built zip **gitignored** and attaches it to a **GitHub Release**
per version (`gh release create vX.Y.Z <zip>`), rather than committing the binary. The same zip is
what you upload to plugins.qgis.org.

---

## 5. Publishing to plugins.qgis.org

1. **Register / log in** with an **OSGeo ID** (the plugins.qgis.org account).
2. **Share a plugin → upload** the zip.
3. **First upload of a new plugin goes to an approval queue** — a human on the QGIS plugin-approval
   team reviews it (allow a few days). After approval, subsequent version uploads publish
   automatically.
4. With `experimental=True`, it appears only to users who tick **"Show experimental plugins"**.
   Flip to `False` and re-upload (new version) once you've tested and are confident.

---

## 6. Security scanning — clear it BEFORE you upload

Every upload to plugins.qgis.org is **automatically scanned**. Two scanners are **BLOCKING** — a
finding delists the version until you upload a fixed one — and two are informational:

| Tool | Status | Catches |
|---|---|---|
| **Bandit** | 🔴 blocking | Python security issues — shell/`eval`/`pickle`, SQL injection, weak crypto, unsafe URL/XML, … |
| **detect-secrets** | 🔴 blocking | Hardcoded secrets: cloud creds, API keys/tokens, SSH keys, DB strings, high-entropy strings |
| **Flake8** | 🟡 info | PEP 8 style, syntax, unused names |
| **File analysis** | 🟡 info | Executable/hidden files, suspicious types, odd permissions |

**Only Bandit findings at MEDIUM or HIGH severity block** — LOW findings (e.g. `try/except/pass`
`B110`, `subprocess` `B404`/`B603`) are reported but do not block. Fix the blockers; document the
rest.

### Run the exact tools locally first

```bash
pip install bandit detect-secrets flake8            # or: uv tool install bandit detect-secrets
bandit -r path/to/plugin/            # scan the plugin tree; add --severity-level medium for blockers
detect-secrets scan path/to/plugin/
flake8 path/to/plugin/               # informational
```

Scan the **built** plugin tree (what the repo actually sees), not just your source — for niva that
means unzipping `niva_qgis.zip` and running `bandit -r niva_qgis/`, because the scanner reads the
vendored `libs/` too.

### How niva cleared its 5 blockers (v0.42.5) — prefer real fixes over `# nosec`

The docs don't promise `# nosec` is honoured, so **change the code** wherever a genuine fix exists:

| Bandit | Where | Real fix |
|---|---|---|
| **B324** weak SHA-1 | a geometry-dedup digest | add `usedforsecurity=False` — tells Bandit (and Python) it isn't a security hash. Needs Python ≥ 3.9. |
| **B608** SQL injection | string-built `INSERT` | write through `sqlite3` with **bound `?` parameters** (`executemany`), not an f-string. If your DB API has no bind params, validate identifiers against a strict allowlist. |
| **B310** urlopen scheme ×2 | `urllib` fetches | enforce an **http/https scheme allowlist**, and fetch via an `OpenerDirector` that carries **only** `HTTPHandler`/`HTTPSHandler` (+redirect/error) — no `FileHandler`/`FTPHandler`, so no request or redirect can read `file://`. Using `OpenerDirector.open` instead of `urllib.request.urlopen` also sidesteps Bandit's B310 blacklist at the AST level. |
| **B314/B405** XML parse | `xml.etree` on remote XML | reject any `DOCTYPE` before parsing (kills XXE / billion-laughs), then `# nosec B314`/`B405`. **No stdlib XML parser passes Bandit** — the only Bandit-clean option is `defusedxml`; niva stays zero-dependency and relies on the DOCTYPE guard + a justified `# nosec`. |

Rules of thumb learned here:
- **`usedforsecurity=False`** clears B324 for any non-security hash (cache keys, dedup, ETags).
- **Bound parameters** are the only real fix for B608 — never hand-escape SQL.
- For **B310**, the `OpenerDirector`-with-only-http/https-handlers pattern is both a real SSRF/`file://`
  mitigation *and* AST-clean, so you don't depend on `# nosec`.
- For **XML**, if you can take the dependency, `defusedxml` is the Bandit-blessed fix; otherwise refuse
  `DOCTYPE` and justify a `# nosec`.
- `# nosec B<id>` (space, then the ID) suppresses one check on that line; standard Bandit honours it,
  but treat it as a last resort and always pair it with a real mitigation + a comment saying why.

### detect-secrets

Keep **all** credentials in the environment or a secret manager — never in code, config, or the
example flows. niva reads tokens (e.g. `NIVA_NTFY_TOKEN`) only from the environment and never logs or
echoes them, so the scan is clean.

---

## 7. Pre-publish checklist

- [ ] `qgisMaximumVersion=4.99`, **no `supportsQt6`** field
- [ ] Qt imports via `qgis.PyQt`; `QAction`-style relocations handled; tested on a QGIS 4 build
- [ ] `version` bumped (unique per upload); `changelog` line added
- [ ] License consistent everywhere and **bundled in the zip**
- [ ] `tags`, `description`, `about`, `repository`, `tracker`, `homepage` set
- [ ] Icon present (PNG referenced by `icon=`)
- [ ] **`bandit -r` on the built tree = 0 MEDIUM/HIGH**, and `detect-secrets scan` = 0 (see §6)
- [ ] Zip has exactly one identifier-named top folder, no `.pyc`, self-contained
- [ ] Installed from ZIP in a clean QGIS (3.x **and** 4.x) and it loads + runs
- [ ] Release cut (tag + GitHub Release with the zip attached)

---

## niva-specific extras

- **`niva validate <flow.niva>`** lints flows offline; run it (and the test suite) before releasing.
- Versions are kept in lockstep across `pyproject.toml`, `niva/__init__.py`, and
  `plugin/metadata.txt`; `CHANGELOG.md` is the full history and `metadata.txt`'s `changelog=` mirrors
  the top 1–2 entries.
