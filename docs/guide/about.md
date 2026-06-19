# About niva

## The idea

Automating geoprocessing in QGIS today means writing PyQGIS — initialize a
`QgsApplication`, memorize algorithm IDs like `native:buffer`, build `ALL_CAPS`
parameter dicts, juggle `TEMPORARY_OUTPUT`, and thread each tool's output into the
next. That is a *programming* task, which puts everyday automation out of reach for
the GUI-first analysts who most need it — and is tedious even for those who can.

niva's answer is a **short, readable text grammar** — a whole pipeline on one line
that a non-programmer can write *and* read:

```
load roads.gpkg | buffer 100 dissolve | clip city.gpkg | save roads_local.gpkg
```

…running on QGIS's own Processing algorithms underneath.

## Goals

- **Readable over powerful.** Favor a grammar a non-programmer can pick up — not a
  new programming language.
- **Thin over clever.** A wrapper over PyQGIS / QGIS Processing (friendly alias names
  → `native:*` algorithms), not a reimplementation of GIS.
- **Meet people where they are.** A text-pipeline grammar, a Python API
  (`niva.flow(...)`), a CLI, and a QGIS plugin dock — pick the surface that fits.
- **One backend first.** In-process PyQGIS for v1; headless `qgis_process` later for
  batch.
- **Clean-room.** The grammar is derived from QGIS Processing's own model and plain
  readability — not from any proprietary GIS scripting language.
- **Provenance as a byproduct.** Every `save` records lineage; `assess` profiles data
  quality. You get a documented, reproducible pipeline without extra effort.

## Status & open questions

niva **runs** (v0.2.0): the full path — grammar → registry/binder → engine → PyQGIS
backend — executes real geoprocessing, validated against real GIS data on QGIS 4.0.3
(122 unit + 19 niva-script integration checks). The verb set is still a starter set
and will grow.

The design is worked out in [`planning/`](../planning/) (PRD, architecture, grammar
spec, security model, the `Oscar_the_Grouch.md` failure register, and the
[traceability matrix](../planning/14-traceability-matrix.md) of every verb ↔ algorithm).

Deliberately still-open questions:

- library vs CLI vs plugin as the *primary* surface for the target user;
- raster `save` and multi-layer GeoPackage write (`save … as <layer>` / append);
- a friendly-error layer that translates cryptic QGIS/GDAL messages;
- whether the premise holds — that GUI-first analysts will adopt a text grammar at
  all (the risk `Oscar_the_Grouch.md` calls out first).
