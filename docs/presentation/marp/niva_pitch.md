---
marp: true
theme: niva
paginate: true
size: 16:9
footer: 'niva · Easy wins every time'
---

<!-- _class: center -->
<!-- _paginate: false -->
<!-- _footer: '' -->

![w:230](../../logos/logo_text.png)

# Readable geoprocessing for everyone

Spatial analysis a non-programmer can write, reproduce, and share.

**Easy wins every time**

<span class="note">Decision-maker &amp; analyst briefing</span>

---

> The opportunity

# Spatial questions are everywhere

<p class="big">The people who need the answers — analysts, scientists, planners — <strong>mostly aren't programmers.</strong></p>

<p class="lead">Yet to <strong>automate</strong> the work — to make it repeatable and shareable — today's tools demand that they write code. So the work waits, or doesn't happen.</p>

---

> The problem

# Automating QGIS means writing PyQGIS

<p class="lead">To script even simple geoprocessing today, you must:</p>

- **Initialize a `QgsApplication`** — boilerplate before any work begins
- **Memorize algorithm IDs** — `native:buffer`, `native:dissolve`, `native:clip`
- **Build ALL_CAPS parameter dicts** — and juggle `TEMPORARY_OUTPUT`
- **Thread each output into the next** — by hand, step after step

That's a <span style="color:#b85c3c;font-weight:700">programming task</span> — out of reach for the GUI-first analysts who need it most, and tedious even for those who can.

---

<!-- _class: graphic -->

> The shift

# Automation shouldn't require a programmer

![w:1060](../graphics/before_after.svg)

---

> The product

# Meet niva

<p class="big">A concise, readable <strong>text-pipeline grammar</strong> for QGIS geoprocessing — for people who don't want to write PyQGIS.</p>

```
load roads.gpkg | buffer 100 dissolve | clip city.gpkg | save roads_local.gpkg
```

A whole pipeline on one line — that a non-programmer can **write and read** — running on QGIS's own Processing algorithms underneath.

<span class="note">Easy wins every time.</span>

---

> Audience

# Who niva is for

<div class="cols">
<div class="card"><h3>Decision-makers</h3><p>Faster answers without hiring scarce GIS programmers. Work that's auditable, reproducible, and shareable across the org.</p></div>
<div class="card warm"><h3>Data scientists<br>(non-programmers)</h3><p>Already use Marimo for repeatable, shareable analysis. Now add geoprocessing — in the same readable, reactive workflow.</p></div>
<div class="card"><h3>Downstream consumers</h3><p>Explore the results in QGIS, in Marimo, or as static files — whichever fits, no GIS expertise required.</p></div>
</div>

---

> Marimo-native

# It fits the workflow you already have

<p class="lead">Marimo is how your team makes analysis repeatable and shareable. niva runs right inside it:</p>

- **Write niva in a Marimo cell** — beside your Python and charts
- **Reactive** — change an input, the map and tables update live
- **Repeatable** — the notebook is the analysis; re-run any time, same result
- **Shareable** — hand someone the notebook, or export it; no setup ritual

**No new tool to adopt** — niva meets your people where they already work.

---

<!-- _class: graphic -->

> Flexible by design

# One grammar, many surfaces

![w:980](../graphics/surfaces.svg)

---

> Trust the result

# Reproducible &amp; shareable — by design

<p class="lead">The value decision-makers care about most: results you can re-run, audit, and defend.</p>

- **Pipelines are the record** — the one-line flow (or YAML) *is* the documentation
- **Provenance as a byproduct** — every step auto-recorded as lineage metadata
- **Assess your inputs** — profile incoming data for quality before you trust it
- **Version-controlled flows** — diff and review analysis like any other text

---

<!-- _class: graphic -->

> For every stakeholder

# Produce once — explore it anywhere

![w:980](../graphics/explore_anywhere.svg)

---

<!-- _class: graphic -->

> Without niva

# The workflow today

![w:1060](../graphics/without_niva.svg)

---

<!-- _class: graphic -->

> With niva

# The workflow with niva

![w:1060](../graphics/with_niva.svg)

---

> Thin, not limiting

# All of QGIS — in plain language

<div class="stats">
<div class="stat"><div class="num">769</div><div class="lab">Processing algorithms</div></div>
<div class="stat"><div class="num">406</div><div class="lab">expression functions</div></div>
<div class="stat"><div class="num">SQL</div><div class="lab">SpatiaLite &amp; PostGIS</div></div>
</div>

<p class="lead">niva is a <strong>thin wrapper</strong> — friendly verbs mapped onto QGIS's own algorithms, not a re-implementation of GIS. The full power of the world's leading open-source GIS, in one readable line.</p>

---

> The tailwinds

# Why niva, why now

- **QGIS is the de-facto open GIS** — ubiquitous, trusted, free; the foundation we build on
- **Reproducible analysis is the norm** — Marimo and notebooks are how modern teams work
- **The automation gap is real &amp; unserved** — GUI analysts still can't automate without code
- **Open and clean-room** — GPLv3, built on PyQGIS; no proprietary lock-in to fear

---

> The value

# What niva delivers

<div class="cols">
<div class="card"><h3>Speed</h3><p>Answers the same day — no queue behind a programmer.</p></div>
<div class="card"><h3>Capacity</h3><p>Existing analysts automate their own work.</p></div>
<div class="card"><h3>Trust</h3><p>Reproducible, provenance-tracked, auditable results.</p></div>
</div>
<div class="cols">
<div class="card warm"><h3>Reach</h3><p>Share to QGIS, Marimo, or static files — for anyone.</p></div>
<div class="card warm"><h3>Lower cost</h3><p>Less custom scripting, less specialized hiring.</p></div>
<div class="card warm"><h3>No lock-in</h3><p>Open source, on open foundations.</p></div>
</div>

---

> Status · built and shipping

# What's working today

<p class="lead">niva ships as a <strong>QGIS plugin</strong> (v0.29) and runs real analysis end-to-end, on QGIS's own algorithms:</p>

<div class="cols">
<div class="card"><h3>Grammar &amp; engine</h3><p>✓ Readable lexer + parser → pipeline stages<br>✓ Pipe-chaining engine: layer handles, lineage<br>✓ PyQGIS backend — runs real geoprocessing</p></div>
<div class="card warm"><h3>Verbs &amp; algorithms</h3><p>✓ ~45 alias verbs + 14 built-ins (vector + raster)<br>✓ <code>sql @conn</code> — SELECT → layer, and server-side writes<br>✓ <code>run</code> — reach ANY of QGIS's 769 algorithms</p></div>
</div>
<div class="cols">
<div class="card"><h3>Data &amp; cartography</h3><p>✓ PostGIS &amp; SpatiaLite — read · write · analyse<br>✓ <code>project</code> — repoint / build / templates · bookmarks<br>✓ <code>style</code> — apply / export .qml · .sld · .qlr</p></div>
<div class="card warm"><h3>Discovery, delivery &amp; quality</h3><p>✓ <code>show</code> / <code>info</code> / <code>catalog</code> — list data, inspect the environment<br>✓ QGIS plugin (Install from ZIP) · CLI · Python API<br>✓ 300+ tests, live-QGIS + PostGIS CI · full docs</p></div>
</div>

---

> Roadmap · shipped &amp; next

# The road ahead

- **v0.1 – 0.29 — Shipped** <span class="tan">· available now</span><br><span class="lead">Grammar · ~45 verbs + raster · <code>run</code> → 769 algorithms · PostGIS read·write·analyse · project / template / style · <code>show</code> / <code>info</code> discovery · QGIS plugin + CLI + Python · provenance · full docs</span>
- **v1.0 — Stable release**<br><span class="lead">Grammar freeze (SemVer) · PyPI publish · worked Marimo–QGIS integration</span>
- **v2.0 — Power features**<br><span class="lead">Named intermediates &amp; variables · SQL-driven quality rules &amp; constraints</span>
- **v2.x — Service mode**<br><span class="lead">Service / daemon mode · richer layout &amp; symbology export</span>

---

<!-- _class: dark center -->
<!-- _footer: '' -->

![w:140](../../logos/logo.png)

# Let your analysts do the analysis.

<p class="big">Bring readable, reproducible geoprocessing to the people who need it.</p>

**Easy wins every time.**

<span class="note">github.com/johnzastrow/niva &nbsp;·&nbsp; Let's run a pilot.</span>
