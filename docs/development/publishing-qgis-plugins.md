# Publishing a QGIS Plugin — Full Process & Playbook

A reusable, end-to-end guide for taking a QGIS Python plugin from a working repo to an
approved listing on **[plugins.qgis.org](https://plugins.qgis.org/)** — including the exact
gates the repository runs, the fixes for the findings you'll hit, and the Qt5→Qt6 traps that
bite on QGIS 4. Written from real releases (niva `niva_qgis`, Metadata Manager); every command
here was run for real.

> **Golden rule:** the artifact you upload must be a zip whose **single top-level folder is the
> plugin package name**, containing **every** module the plugin imports, a **LICENSE**, and **no**
> generated files, caches, or VCS dirs. Most failed uploads are a packaging problem, not a code
> problem.

> **📦 Ready-made templates** in [`templates/`](templates/) — drop them into any plugin so they all
> release identically:
> - [`Makefile`](templates/Makefile) — `make check` (ruff+flake8+bandit+secrets+test) · `make build` ·
>   `make tag V=x.y.z`. Only `UNIT_TEST` changes per plugin.
> - [`release.yml`](templates/release.yml) → `.github/workflows/` — on a `v*` tag: runs the gates +
>   unit test, builds via `scripts/build_plugin.sh`, cuts the GitHub Release with the zip.
>
> Both delegate the plugin-specific file list to **`scripts/build_plugin.sh`** (§2), so they're
> identical across every plugin. (Live reference: the `metadatamgr` repo.)

---

## 0. TL;DR checklist

```
[ ] metadata.txt valid: name, qgisMinimumVersion, description, version, author, email,
    about, tracker, repository; experimental set intentionally; changelog trimmed
[ ] qgisMaximumVersion=4.99 IF supporting QGIS 4 (else QGIS 4 rejects it as 3.x-only)
[ ] LICENSE file present at repo root AND copied into the zip (GPLv2+-compatible)
[ ] Icons load from a file path (no compiled resources.py / pyrcc5)
[ ] Security gates pass:  bandit (0 high/critical) · detect-secrets (0) · flake8 (clean)
[ ] Qt6-safe: scoped enums, .exec() not .exec_(), no removed APIs (QRegExp/QDesktopWidget/…)
[ ] Reliable local build script produces the zip and SELF-VERIFIES subpackages + LICENSE
[ ] Version bumped in ALL places (metadata.txt, docs/CHANGELOG.md, any in-file __version__)
[ ] Zip contains no __pycache__ / .git / *.pyc / .ruff_cache
[ ] Installed from ZIP in a real QGIS and every dialog opens without a traceback
```

### Prerequisites (fresh machine)

To run everything below from a clean checkout:
- **git** + **[`gh`](https://cli.github.com/)** authenticated (`gh auth status`) for tagging/releases.
- **`zip`** and a POSIX shell (Linux/macOS, or Git-Bash/WSL/OSGeo4W shell on Windows).
- **[`uv`](https://docs.astral.sh/uv/)** — runs the linters/scanners in throwaway envs, no global installs
  (`uv run --no-project --with <tool> …`). Nothing else to `pip install`.
- **A real QGIS** to smoke-test the zip. Only need **QGIS's Python / `pyrcc5`** if the plugin still uses
  compiled resources (avoid that — §3).
- **A plugins.qgis.org account** (OSGeo ID) to upload. First-time plugins are reviewed before they go
  live; version updates to an approved plugin publish immediately.

---

## 1. Plugin anatomy & `metadata.txt`

A QGIS plugin is a folder on `PYTHONPATH` under `…/python/plugins/<PluginName>/` with an
`__init__.py` exposing `classFactory(iface)`. `metadata.txt` is what the repository and Plugin
Manager read.

**Mandatory fields** (upload is rejected without them):

```ini
[general]
name=Metadata Manager
qgisMinimumVersion=3.40
description=One-line summary shown in the manager list.
version=0.6.5
author=John Zastrow
email=you@example.com
about=A fuller paragraph. State any external Python dependencies here, with install guidance.
tracker=https://github.com/you/repo/issues
repository=https://github.com/you/repo
```

**Recommended / high-value:**

```ini
hasProcessingProvider=no
homepage=https://github.com/you/repo
category=Plugins        ; menu placement — see below
icon=icon.svg           ; path INSIDE the zip; svg or png
experimental=False      ; True hides it by default & requires ticking a box on upload
deprecated=False
tags=metadata, catalog, inventory, geopackage
changelog=              ; keep SHORT — last 3–5 versions only (see §8)
server=False
```

**`category`** sets the QGIS menu the plugin's actions go under. The meaningful values are
**`Raster` · `Vector` · `Database` · `Web`**; `Plugins` puts it in the generic Plugins menu.
Pick by what the plugin *is*, not the data it happens to touch (a cross-datatype catalog/DB tool
→ `Database` or `Plugins`, not `Vector`).

**`experimental`** — keep `True` while iterating; users must opt in to see it. Flip to `False`
for a stable listing (and you no longer need to tick "experimental" on the upload form).

> **⚠ QGIS 4 support hinges on `qgisMaximumVersion`.** If you set `qgisMinimumVersion=3.40` and
> omit `qgisMaximumVersion`, QGIS **defaults the max to `3.99`** — and **QGIS 4.x refuses to load
> the plugin** ("This plugin is incompatible… designed for QGIS 3.40 – 3.99"). To span QGIS 3 and 4,
> add it explicitly:
> ```ini
> qgisMinimumVersion=3.40
> qgisMaximumVersion=4.99
> ```
> Only do this once the code is actually Qt6-safe (§6) — otherwise it loads and then crashes.

---

## 2. Packaging — the reliable build script (the #1 lesson)

**The trap:** Plugin Builder ships a `Makefile` + `pb_tool.cfg` whose file lists are easy to leave
incomplete. If `pb_tool.cfg` has an empty `extra_dirs:` (or the Makefile's `EXTRA_DIRS` loop is the
stock broken `(foreach …)`), a `make zip` silently omits your subpackages (`db/`, `widgets/`, …) and
the installed plugin dies with `ModuleNotFoundError`. **Do not trust `make`/`pb_tool` blindly.**

**The fix:** a small, self-verifying `scripts/build_plugin.sh` that stages exactly what ships and
**fails loudly** if a required subpackage or the LICENSE is missing. Skeleton:

```bash
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
PLUGIN="MetadataManager"; OUT="$ROOT/$PLUGIN.zip"
WORK="$(mktemp -d)"; STAGE="$WORK/$PLUGIN"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$STAGE"

# Root .py + UI + metadata + icons + LICENSE + README
for f in __init__.py MetadataManager.py MetadataManager_dockwidget.py fix_metadata_status.py \
         MetadataManager_dockwidget_base.ui metadata.txt icon.png icon.svg README.md LICENSE; do
  cp "$ROOT/$f" "$STAGE/$f"
done
# EVERY imported subpackage + asset dir — this is what make/pb_tool drops
for d in db processors widgets icons i18n; do cp -r "$ROOT/$d" "$STAGE/$d"; done

# Strip what plugins.qgis.org rejects
find "$STAGE" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -type d -name '.git'        -prune -exec rm -rf {} + 2>/dev/null || true
find "$STAGE" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete 2>/dev/null || true

rm -f "$OUT"; ( cd "$WORK" && zip -qr "$OUT" "$PLUGIN" )

# SELF-VERIFY — capture the listing ONCE (pipefail + `grep -q` closing the pipe = false SIGPIPE fail)
LISTING="$(unzip -l "$OUT")"
for want in db/ processors/ widgets/ LICENSE metadata.txt; do
  echo "$LISTING" | grep -q "$PLUGIN/$want" || { echo "ERROR: $want missing from zip"; exit 1; }
done
echo "built $OUT — subpackages, LICENSE and metadata all present."
```

Notes that cost real debugging time:
- **Top-level folder = the plugin package name.** If you vendor a package (see niva below), do NOT
  name the top folder the same as the vendored package, or it shadows it.
- **`set -o pipefail` + `grep -q`**: `grep -q` exits on first match and closes the pipe; the upstream
  `unzip` then dies with SIGPIPE (141) and pipefail fails the whole line even though the match
  succeeded. Capture the listing into a variable first, then `grep` the variable.
- **Keep the CI build and the local build identical.** The GitHub Actions release job and
  `build_plugin.sh` should stage the same files; otherwise "works in CI, broken locally" (or vice
  versa). Mirror them line-for-line.

**niva's variant — vendoring a zero-dependency package.** If your plugin wraps a pure-Python
package, copy it into `libs/<pkg>` inside the plugin so it installs with **no pip step**, cross-
platform. That only applies when there's an external package to vendor; a plain Plugin-Builder
plugin's own `db/`/`widgets/` code just needs to be included (above).

---

## 3. Icons without compiled Qt resources

**Avoid the `resources.qrc` → `resources.py` (pyrcc5) path.** It adds a build-time compiler
dependency, and QGIS's own guidance says **"no generated files left in the repository."** It's also
fragile: strip the `from .resources import *` side-effect import (e.g. an aggressive `autoflake`)
and every `:/plugins/…` icon silently fails to load.

**Do this instead** — load icons from a plain file path relative to the plugin dir:

```python
self.plugin_dir = os.path.dirname(__file__)
...
icon_path = os.path.join(self.plugin_dir, 'icons', 'icon.svg')   # not ':/plugins/Foo/icons/icon.svg'
action = QAction(QIcon(icon_path), text, parent)
```

Then delete `resources.qrc` + `resources.py`, drop the `pyrcc5` step from CI and the build script,
and remove `from .resources import *`. Ship the `icons/` folder in the zip. (If you keep compiled
resources anyway, `pyrcc5` isn't in modern PyQt5 wheels standalone — but `uv run --no-project
--with pyqt5 -- pyrcc5 -o resources.py resources.qrc` works.)

---

## 4. The plugins.qgis.org gates — Bandit, Secrets, flake8

The repository runs automated checks on upload. **Critical Bandit findings and detected secrets
BLOCK the plugin until resolved.** flake8 runs too (treat it as authoritative for style). Run them
locally first — no install needed, via `uv`:

```bash
# Security (Bandit) — aim for 0 HIGH/MEDIUM; HIGH/critical is a hard block
uv run --no-project --with bandit bandit -r . -x ./test,./tests,./.git,./help,./docs

# Secrets — must be 0
uv run --no-project --with detect-secrets detect-secrets scan --all-files

# Style/lint — the authoritative pre-publish check
uv run --no-project --with flake8 flake8 .
```

### Fixing the findings you'll actually hit

| Finding | What it means | Fix |
|---|---|---|
| **B608** SQL injection | An identifier (table/column) is f-string-interpolated into SQL (params `?` can't bind identifiers) | Validate against a strict allowlist: `re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', name)`; then `# nosec B608 - validated identifier` |
| **B314 / B405** XXE | `xml.etree.ElementTree.parse` on untrusted XML | Use `defusedxml`, **or** if it's only local user-selected files (no external entities): `# nosec B314 - local sidecar, no external entities` |
| **B404 / B603 / B607** subprocess | Shelling out (e.g. `df` for a mount point) with a partial path | Best: remove it. The Unix mount point is pure-Python: walk up with `os.path.ismount()`. Else `# nosec` with justification |
| **B110** try/except/pass | Silently swallowed exceptions | Low severity (rarely blocks). Prefer logging the exception; at minimum use `except Exception:` not bare `except:` |
| **Secret: "Hex High Entropy String" in `.ruff_cache/CACHEDIR.TAG`** | A **false positive** — the ruff cache's magic signature | `.gitignore` the cache (`.ruff_cache/`, `__pycache__/`) and `rm -rf .ruff_cache` before scanning |

**Secrets, real ones:** never commit tokens/passwords. A `detect-secrets` hit that isn't a cache
artifact is a real problem — rotate the credential and purge it from history.

**Bandit `# nosec`** is the accepted way to acknowledge a reviewed non-issue — always with the test
id and a one-line justification (`# nosec B608 - identifier validated above`). Don't blanket-suppress.

---

## 5. Linting — ruff to iterate, flake8 to verify

Iterate fast with **ruff** (`ruff check --fix`), but **run flake8 before publishing** — they differ:
ruff doesn't implement the pycodestyle continuation-indent checks (`E12x`) or `W503/W504`, and gates
a few `E3xx`/`E265` behind `--preview`. Keep a shared config so ruff mirrors flake8 as closely as it
can.

`setup.cfg` (flake8, authoritative):
```ini
[flake8]
max-line-length = 120
extend-ignore = E501, W503, W504, E203, E741, E125, E126, E127, E128, E131
exclude = .git, test, tests, help, i18n, __pycache__, docs, resources.py
```

`ruff.toml` (fast local mirror — ruff lacks the `E12x`/`W50x` codes, so don't list them):
```toml
line-length = 120
preview = true
extend-exclude = ["test", "tests", "help", "i18n", "docs", "resources.py"]
[lint]
select = ["E", "F", "W"]
extend-ignore = ["E501", "E203", "E741"]
[lint.per-file-ignores]
"MetadataManager.py" = ["F403"]   # `from x import *` side-effect import, if any
```

Bulk-fix unused imports with `autoflake` — but it will happily delete a **side-effect star import**
(`from .resources import *`); guard it or, better, remove the compiled-resources approach entirely
(§3). Fix bare excepts mechanically:
`sed -i -E 's/(^[[:space:]]*)except:[[:space:]]*$/\1except Exception:/' file.py`.

---

## 6. Qt5 → Qt6 compatibility (this is what breaks on QGIS 4)

**QGIS 3.x is PyQt5; QGIS 4.x is PyQt6.** A plugin with `qgisMinimumVersion` ≤ 4 must run on both.
(And remember `qgisMaximumVersion=4.99` — §1 — or QGIS 4 won't even *try* to load it.)
The #1 cause of "installs fine, crashes when I open a panel" is **unscoped Qt enums**, which PyQt6
removed. Use the **scoped** forms — they work on PyQt5 ≥ 5.15 (which QGIS 3.28/3.34/3.40 ship) **and**
PyQt6:

| Qt5-only (crashes on Qt6) | Scoped (works on both) |
|---|---|
| `Qt.AlignCenter`, `Qt.AlignLeft` | `Qt.AlignmentFlag.AlignCenter` |
| `Qt.UserRole`, `Qt.DisplayRole` | `Qt.ItemDataRole.UserRole` |
| `Qt.Horizontal` / `Qt.Vertical` | `Qt.Orientation.Horizontal` |
| `Qt.Checked` / `Qt.Unchecked` | `Qt.CheckState.Checked` |
| `Qt.RightDockWidgetArea` | `Qt.DockWidgetArea.RightDockWidgetArea` |
| `Qt.red`, `Qt.darkGreen`, `Qt.darkYellow` (**lowercase** colours!) | `Qt.GlobalColor.red` |
| `Qt.ItemIsEditable` | `Qt.ItemFlag.ItemIsEditable` |
| `QDialogButtonBox.Ok/Cancel` | `QDialogButtonBox.StandardButton.Ok` |
| `QAbstractItemView.SelectRows` | `QAbstractItemView.SelectionBehavior.SelectRows` |
| `QAbstractItemView.SingleSelection` | `QAbstractItemView.SelectionMode.SingleSelection` |
| `QAbstractItemView.NoEditTriggers` | `QAbstractItemView.EditTrigger.NoEditTriggers` |
| `QFrame.StyledPanel` / `NoFrame` | `QFrame.Shape.StyledPanel` |
| `QFont.Bold` | `QFont.Weight.Bold` |
| `QHeaderView.Stretch` | `QHeaderView.ResizeMode.Stretch` |

**Other Qt6 removals to sweep for:** `dialog.exec_()` → **`dialog.exec()`** (both work on PyQt5≥5.15);
`QRegExp` → `QRegularExpression`; `QDesktopWidget` / `QApplication.desktop()` → `screen()` APIs;
`QFontMetrics.width()` → `.horizontalAdvance()`; `layout.setMargin()` → `.setContentsMargins()`;
`.toPyObject()` (gone).

**Find them fast:**
```bash
FILES=$(echo *.py widgets/*.py db/*.py processors/*.py)
# BOTH cases — `[a-zA-Z]`, not `[A-Z]`: the GlobalColor constants (Qt.red, Qt.darkGreen …) are
# lowercase and are the #1 thing a caps-only grep misses.
grep -rhoE "Qt\.[a-zA-Z][a-zA-Z0-9]+" $FILES | grep -vE "Qt\.(QtCore|QtGui|QtWidgets|QtXml)" | sort | uniq -c | sort -rn
grep -rnE "\.exec_\(|QRegExp|QDesktopWidget|\.setMargin\(|\.toPyObject\(" $FILES
```
**Fix in bulk** with word-boundary sed (`\b`), then re-grep for residuals and `py_compile` every file.
Caveat: static grep can't reach enums only referenced in code paths you don't exercise — **install
and click through every dialog** to flush the rest.

---

## 7. Testing under QGIS's Python

Unit tests that don't import `qgis`/`PyQt` run anywhere (wire those into CI). Anything touching QGIS
must run under **QGIS's own Python**:

```bash
export QT_QPA_PLATFORM=offscreen                     # no display
export PYTHONPATH=/usr/share/qgis/python:/usr/lib/python3/dist-packages
python3 -m pytest test/test_something_qgis.py
```
On Windows use the **OSGeo4W shell**; on macOS the `QGIS.app` bundled Python. `py_compile` every
shipped `.py` as a cheap syntax gate:
```bash
python -c "import py_compile,glob; [py_compile.compile(f,doraise=True) for f in glob.glob('**/*.py',recursive=True) if '/test' not in f]; print('OK')"
```

**Install-from-ZIP smoke test.** In QGIS: *Plugins → Manage and Install Plugins → Install from ZIP →*
the built zip. QGIS caches imported modules, so when **reinstalling a new build**, uninstall the old
copy first (or reinstall over it and toggle the plugin off/on) or you'll keep running the old code.
Then exercise **every** panel and dialog — Qt6 enum crashes (§6) only fire on the code path that runs.

---

## 8. Versioning & changelog

Bump the version in **every** place it lives, or the manager and the code disagree:
- `metadata.txt` → `version=`
- `docs/CHANGELOG.md` → a new `## [x.y.z] — YYYY-MM-DD` section (CI often parses this for release notes)
- any in-file `__version__` (easy to leave stale — grep for it)

**Trim the `metadata.txt` `changelog=` field to the last 3–5 versions** and point to the full log:
Plugin Manager renders that field, and a 200-line history is noise. Keep the complete history in
`docs/CHANGELOG.md`.

---

## 9. Release — CI build + manual upload

plugins.qgis.org has **no auto-publish** (unlike PyPI Trusted Publishing). End-to-end, from a clean
checkout on any machine:

```bash
# 0. gates + build, all local (see §4/§5). Fix until clean.
uv run --no-project --with bandit bandit -r . -x ./test,./tests,./.git,./help,./docs
uv run --no-project --with detect-secrets detect-secrets scan --all-files
uv run --no-project --with flake8 flake8 .
bash scripts/build_plugin.sh        # self-verifying local zip

# 1. bump version everywhere (§8), then commit + push
git add -A && git commit -m "vX.Y.Z: …" && git push origin main

# 2. tag → GitHub Actions builds the zip, runs the unit test, cuts a Release with the zip attached
git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z
gh run watch "$(gh run list --workflow=release.yml -L1 --json databaseId -q '.[0].databaseId')" --exit-status

# 3. VERIFY the CI-built asset before uploading (metadata + completeness)
gh release download vX.Y.Z -p "*.zip" -O /tmp/rel.zip
unzip -p /tmp/rel.zip <Plugin>/metadata.txt | grep -E "^version=|^qgisM|^experimental="
unzip -l /tmp/rel.zip | grep -icE "resources.py|__pycache__|\.git"   # must be 0
```

The release workflow triggers on the tag and mirrors `build_plugin.sh`:
```yaml
on: { push: { tags: ['v*'] } }
# checkout → pip install pytest → run the pure-Python unit test → stage the SAME files as
# build_plugin.sh → zip with the plugin folder on top → gh release create <tag> … the.zip
```

4. **Upload** the zip at `https://plugins.qgis.org/plugins/<slug>/version/add/` (first-time: the
   plugin's *"add"* page — needs your OSGeo login). Tick **experimental** if the metadata says so.
   The reviewer does light testing that it installs without crashing QGIS; version bumps to an
   already-approved plugin go live immediately.

### If the plugin is *also* a pip package (niva)

niva ships **two independent artifacts** from one tag:
- **the plugin zip** — `plugin/build_plugin.sh` vendors `libs/niva`; uploaded to plugins.qgis.org as above.
- **the PyPI wheel** — a GitHub **Release** (`gh release create vX.Y.Z --target main …`) triggers
  `.github/workflows/publish-pypi.yml`, which builds and publishes to PyPI via **Trusted Publishing**
  (OIDC, no stored token). One-time PyPI setup: Account → Publishing → add the GitHub trusted publisher
  (owner/repo/workflow/environment). Verify: `curl -s -o /dev/null -w '%{http_code}' https://pypi.org/pypi/<pkg>/X.Y.Z/json` → `200` (the aggregate `/pypi/<pkg>/json` is CDN-cached and lags).

---

## 10. QGIS official requirements — quick reference

From the [plugin repository guidelines](https://plugins.qgis.org/publish/):
- License **compatible with GPLv2 or later**; respect bundled libraries' licenses.
- **No binaries.** Package **< 20 MB**.
- Metadata has valid **homepage, repository, tracker, license** links; at least minimal docs.
- **No generated files** in the repo (`ui_*.py`, `resources_rc.py`, generated help).
- **No `__MACOSX`, `.git`, `__pycache__`** or hidden dirs in the zip.
- Use **`QgsNetworkAccessManager`**, not `urllib`/`requests` (correct proxy handling).
- Public source repo (not just a zip); cross-platform (Windows/Linux/macOS).

---

## 11. Common pitfalls (the greatest hits)

- **`make`/`pb_tool` drops subpackages** → `ModuleNotFoundError` on install. Use `build_plugin.sh`
  and self-verify.
- **Compiled resources fail to load** after import cleanup → icon missing / `:/plugins/…` errors.
  Switch to file-path icons.
- **Missing `qgisMaximumVersion`** → QGIS 4 reports "incompatible … designed for 3.40 – 3.99" and
  won't load it at all. Set `qgisMaximumVersion=4.99` (after making the code Qt6-safe).
- **Unscoped Qt enums** → crashes only when a panel/dialog opens on QGIS 4. Scope them all.
- **`.exec_()`** → `AttributeError` on PyQt6. Use `.exec()`.
- **`.ruff_cache/CACHEDIR.TAG`** flagged as a secret → gitignore + remove caches before scanning.
- **CRLF line endings** in `pb_tool.cfg`/configs (Windows edits) → `sed` patterns silently don't
  match. Account for `\r` or normalize.
- **Stale `__version__`** in a source file while `metadata.txt` moved on.
- **Bloated `changelog=`** in metadata.txt.
- **`set -o pipefail` + `grep -q`** false failures in build scripts (capture to a var first).
```
