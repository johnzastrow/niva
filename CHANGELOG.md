# Changelog

All notable changes to **niva** are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project will follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
once it has releases.

> **Status: pre-release.** niva is an early-stage design exploration — no
> versioned release or installable package exists yet. Everything below sits
> under *Unreleased*; the grammar and API are still goals, not shipped features.

## [Unreleased]

### Added
- **Planning materials** (`planning/`): critique & open questions, product
  requirements for the non-programmer text-pipeline grammar, architecture, MVP
  scope, roadmap, and captured concepts.
- **QGIS capability surface reference** (`planning/06-qgis-surface-reference.md`
  + `planning/reference/*.tsv`): a snapshot, enumerated live from QGIS 4.0.3, of
  everything niva could reach — 769 Processing algorithms (8 providers), 406
  expression functions, SpatiaLite's 238 `ST_*` + PostGIS spatial SQL, the
  SQL-capable data providers and OGR/GDAL drivers, and the full version stack —
  with current signatures/access and before/after niva examples.
- **Brand assets** (`logos/`): the niva mark (`logo.svg` / `logo.png`) and
  wordmark (`logo_text.svg` / `logo_text.png`); earlier logo explorations
  archived under `logos/OLD/`.
- **QGIS plugin stub** (`plugin/`): a minimal plugin that previews the niva logo
  on the toolbar and Plugins menu (no geoprocessing yet), Qt5/Qt6-compatible,
  with a `make package` build for the install zip.
- **README** describing the project goals and current (early, exploratory)
  status.
- This changelog.

[Unreleased]: https://github.com/johnzastrow/niva/commits/main
