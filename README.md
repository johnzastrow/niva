# niva

[![Latest release](https://img.shields.io/github/v/release/johnzastrow/niva?sort=semver)](https://github.com/johnzastrow/niva/releases/latest)
[![License: GPLv3](https://img.shields.io/badge/license-GPLv3-blue.svg)](LICENSE)
[![QGIS](https://img.shields.io/badge/QGIS-3.22%2B%20%7C%204.0%2B-589632.svg?logo=qgis&logoColor=white)](https://qgis.org)
[![Python](https://img.shields.io/badge/python-3.9%2B-3776AB.svg?logo=python&logoColor=white)](https://www.python.org)
[![Dependencies](https://img.shields.io/badge/runtime%20deps-none%20%28QGIS%20only%29-success.svg)](docs/guide/faq.md)

**QGIS from the command line. A concise, readable grammar for QGIS geoprocessing — for people who
don't want to write PyQGIS.** *Easy wins every time.*

<img src="docs/logos/logo_text.png" width="240" alt="niva">

Ever get tired of clicking? Write a whole pipeline on one line — friendly verbs running on QGIS's own Processing
algorithms underneath:

```
load roads.gpkg | buffer 100m dissolve | clip city.gpkg | save roads_local.gpkg
```

or even

```
# ── TEST 24 | add then remove vertices | densify → smooth → simplify
load "{data}/collected.gpkg|layername=park_lines" | densify 5m | smooth iterations=2 | simplify 10 | save /tmp/niva_validation/out/s3_24.gpkg
```

## What it does

Niva turns QGIS automation from PyQGIS code into a readable single lines of text. 

* Runs in QGIS's own Python
* Reaches any of its ~878 algorithms
* Near-zero dependencies on other packages. We're trying to stay within the python standard library.
* ~45 friendly verbs → real QGIS algorithms, across vector geometry, overlay, attributes,  raster or use `run` to any of the ~878 with no dedicated verb alias; `describe` shows their parameters. Every alias is validated against the installed QGIS.
* Discoverable — `describe <verb>` ends with a runnable example; `search <keyword>` fuzzy-finds functions across the
  verbs *and* QGIS ; and `docs <keyword>` emits the full reference for every match — save it out with `to=<file>`. And more!
* Databases via named QGIS connections — read (`load @conn.table`, `sql @conn "SELECT …"`), write (`save @conn.table`, fail-closed with
  `mode=create|replace|append`), and analyze server-side (non-SELECT `sql @conn "CREATE TABLE … AS SELECT …"`). Credentials never leave QGIS.
* Provenance for free — every `save` records processing steps into metadata; `assess` writes data-quality reports; the run journal echoes the exact `processing.run(…)` for each step.
* Composable — chain stages with `|`, compose .niva files with `call mypipeline.niva`, and export a flow to a standalone PyQGIS script (`niva export`) or import one back. - It's just PyQGIS under the hood.
* Utility verbs beyond QGIS — `notify` (ntfy push when a long job finishes), `email` (SMTP, Gmail-aware), `catalog` (recurse a directory and inventory every geospatial dataset — CRS, extent, fields, bands — to a Markdown report), `show` (list the loadable layers/tables at a file, directory, `@conn`, or remote WFS/WMS/ArcGIS REST/XYZ URL — name, type, format, ready-to-load source), and `info` (inspect the local QGIS environment — the registered `@conn` connection names across every profile, providers, versions). Credentials for `notify`/`email` come only from the environment, never the flow text.

## Screenshots

niva in the QGIS plugin dock and on the command line — see **[docs/screenshots.md](docs/screenshots.md)**.

## Docs

**New here? Start with the [Quick start](docs/guide/quickstart.md).**

- **[Quick start](docs/guide/quickstart.md)** — install & run niva, in QGIS or as a CLI on QGIS's own Python
- **[User Guide](docs/guide/user-guide.md)** — install & run niva inside QGIS and standalone, configuration, scratch space, troubleshooting
- **[Reference](docs/guide/reference.md)** — every verb, alias, option, type, env var, CLI command, and Python entry point · **[Algorithm appendix](docs/algorithms/README.md)** — all 878 QGIS
  algorithms with parameters & descriptions
- **[Cookbook](docs/guide/cookbook.md)** — 50 worked recipes, including spatial SQL for SpatiaLite and PostGIS
- **[FAQ](docs/guide/faq.md)** — what libraries you need, how to run niva, scratch space, databases
- [Template projects](docs/guide/templates.md) — author a QGIS project once (layout + styles), reuse it against fresh data with `project from-template=`
- **[Testing](docs/testing.md)** — platform support (QGIS 4.0.3 & 3.44 LTR), running the suite, and the test `.niva`-companion rule (per-run detail: [`tests/TESTING_LOG.md`](tests/TESTING_LOG.md))
- [About & goals](docs/guide/about.md) · [Plugin](plugin/README.md) ·
  [Publishing a QGIS plugin](docs/guide/qgis-plugin-publishing.md) — a reusable playbook ·
  [Verb ↔ algorithm map](docs/planning/14-traceability-matrix.md)
- [Design & risk docs](docs/planning/) — PRD, architecture, grammar, security, the `Oscar` failure register
- [CHANGELOG](CHANGELOG.md)

📘 **The whole guide ([User Guide](docs/guide/) + Reference + Cookbook + FAQ + the 878-algorithm appendix) is also one PDF: [`niva-guide.pdf`](https://github.com/johnzastrow/niva/blob/9206e42d0c55ef96238c514e9bbf3a038bc69c7c/docs/guide/niva-guide.pdf)** (also attached to the [latest release](https://github.com/johnzastrow/niva/releases/latest); rebuild with `python3 scripts/build_guide_pdf.py`, which needs `pandoc` + a LaTeX engine).

## License

[GPLv3](LICENSE) — consistent with the QGIS ecosystem (niva builds on PyQGIS, a GPL
library). Not yet on PyPI; install from source or the plugin zip.
