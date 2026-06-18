# Template projects

A **niva template is just a saved QGIS project.** There is no special format: you design a
project in QGIS — print layout, styled layers, bookmarks, the lot — and niva reuses it against
fresh data. `project from-template=` copies the template and **repoints each layer to your
same-named data**, so everything you designed rides along.

```
# instantiate a template against your data
project from-template="my_basemap.qgz" to="acme.qgz" data="acme/clips/"

# …or use the bundled example, by name
project from-template=example to="acme.qgz" data="acme/clips/"
```

This page explains **what a template can carry**, **how slots are matched**, and **how to
author a good one** — including the bundled `example` you can open in QGIS as a starting point.

---

## How instantiation works

`project from-template=<name|path> to=<out> data=<dir|glob> [missing=keep|fail|drop]`

1. niva **copies the whole template project** — so every project-level thing you designed
   (layouts, bookmarks, themes, layer tree, title, CRS) is preserved verbatim.
2. For each layer (a **slot**), niva **repoints its datasource** to the dataset in `data=`
   whose name matches the slot, **preserving the layer's symbology and subset filter**.
3. The result is written to `to=` (`.qgs` or `.qgz` by extension). Nothing else changes.

`data=` is resolved like `each` / `project new`: a **directory** (recursed), a **glob**, or a
**multi-layer container** (a GeoPackage, expanded per layer). Each dataset's **name** is its
file stem (`parcels.gpkg` → `parcels`) or its `|layername=` inside a container.

### Slot matching — by display name

A slot's identity is the **layer's display name** — the label in the QGIS *Layers* panel —
falling back to the datasource name (`|layername=`, else file stem) when the display name
isn't found. So a layer shown as **`parcels`** is filled by **`parcels.gpkg`** in `data=`,
*regardless of the placeholder data the template currently points at*.

> **Author tip:** name your template's layers exactly what you'll name the matching data
> files. Rename a layer in the *Layers* panel (double-click) to set its slot name.

Slots with no match in `data=` follow `missing=`:

| `missing=` | Unmatched slot behaviour |
|------------|--------------------------|
| `keep` *(default)* | left pointing at the template's example data — **preserves layout/legend structure** |
| `drop` | removed from the project |
| `fail` | error (never silently produce a half-filled map) |

---

## What a template can carry

Because `from-template` copies the project and only swaps datasources, **everything in the
project file rides along.** Author it once; it all comes through.

### Project-level — carried verbatim

| Element | Carried? | Notes |
|---|---|---|
| **Print layouts** | ✅ | All items: map frames, titles/labels, **legend**, **scale bar**, pictures / north arrows, attribute tables, HTML frames, and **atlas** configuration. |
| **Spatial bookmarks** | ✅ | Jump-to extents (see `project … bookmark=`). |
| **Map themes** | ✅ | Visibility / style presets. |
| **Layer tree** | ✅ | Group structure, layer order, visibility, expanded state. |
| **Project title & CRS** | ✅ | |
| **Project metadata, colors, variables** | ✅ | Project color scheme, custom project variables. |

### Per-layer (per-slot) — carried, datasource repointed

| Element | Carried? | Notes |
|---|---|---|
| **Symbology / renderer** | ✅ | The *style* — single/categorized/graduated/rule-based, including data-defined overrides. Rides along onto the new data. |
| **Display name** | ✅ | This is the **slot key**. |
| **Opacity & blend mode** | ✅ | |
| **Labels** | ✅ | Label placement / expressions. |
| **Subset / filter string** | ✅ | Re-applied to the **new** data (so the filter's fields must exist there — see caveats). |
| **Layer metadata** | ✅ | |
| **Joins, diagrams, actions, form/field config** | ✅ | Carried as layer properties; schema-dependent ones assume matching fields. |
| **Datasource** | 🔁 **repointed** | To the same-named dataset in `data=` (vector → `ogr`, raster → `gdal`). |

### Not carried / unchanged

- **Layers that aren't vector or raster** are left untouched.
- **Slots with no matching data** follow `missing=` (above).
- `from-template` does **not** rewrite datasource **path storage** — that's a `to-template`
  option (`paths=relative`).

---

## Caveats when authoring

- **Schema-dependent styling.** A categorized/graduated/rule-based renderer, a subset filter,
  a join, or a label expression references **field names / values**. The style rides along,
  but it only *renders* correctly if your data has those fields. Keep slot schemas consistent,
  or use simple symbology in the template.
- **Layout map extent.** A layout map frame stores a fixed extent (the template's example
  area). After instantiation it still shows that extent — which may not cover your data. Pan
  the layout map to your area, or add a **bookmark** at your AOI and use it. (A future option
  may auto-fit the layout map to the new data.)
- **Geometry type.** Symbology assumes a geometry type — fill the `boundary` (polygon) slot
  with polygon data, `roads` (line) with lines, etc. Mismatched geometry still repoints but
  the symbol won't apply meaningfully.

---

## Authoring a template, end to end

1. **Design in QGIS.** Add your layers, style them, build a print layout, set bookmarks /
   themes / title / CRS. Save as `.qgz`.
2. **Name the slots.** Rename each layer in the *Layers* panel to the name you'll give the
   matching data file (e.g. `parcels`, `roads`, `boundary`).
3. *(Optional)* **Make it portable.** Register it into your library with relative paths:
   ```
   project to-template=parcel_map from="MyParcelMap.qgz" paths=relative
   ```
   `to-template=<name>` copies the project into the **template library** — `$NIVA_TEMPLATES`
   if set, else `~/.niva/templates` — so `from-template=<name>` finds it. A **path** value
   (`to-template="out/tmpl.qgz"`) writes anywhere instead.
4. **Instantiate** against any dataset whose layers are named for your slots:
   ```
   project from-template=parcel_map to="acme.qgz" data="acme/parcels/"
   ```

### Where named templates resolve

`from-template=<name>` (a bare name, no path) is looked up in order:

1. `$NIVA_TEMPLATES` (if set)
2. `~/.niva/templates` (your personal library)
3. the **bundled** templates that ship inside niva (e.g. `example`)

An earlier hit shadows a later one, so a personal `example.qgz` overrides the bundled one. An
unknown name errors with the available names listed.

---

## The bundled `example` template

niva ships a fully-populated `example` template (under `niva/templates/`, regenerated by
`templates/build_example.py`) so you can see exactly what a good template contains. It has:

- **Three styled slots:** `boundary` (polygon outline), `roads` (line), `places` (point) —
  each with distinct symbology.
- **A print layout** (`Map`): title, map frame, legend, scale bar.
- **A spatial bookmark** (`Study Area`) and a project **title** + **CRS**.

Open `niva/templates/example.qgz` in QGIS to inspect it, or instantiate it directly:

```
project from-template=example to="my_map.qgz" data="my_data/"
```

where `my_data/` holds `boundary.*`, `roads.*`, and `places.*` (any OGR vector format). The
slots repoint to your data; the layout, legend, scale bar, bookmark, title, and CRS all ride
along. Copy it into `~/.niva/templates/` and edit it to make your own.
