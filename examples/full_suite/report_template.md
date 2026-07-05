---
title: "Hydrologic Assessment of the Youngstown AOI: Past and Present (2001–2024)"
author: "Hydrologic Analyst — Town of Porter, Niagara County, New York"
date: "2026"
---

<!--
  This is the SCIENTIFIC REPORT template for the full_suite study (see use_case.md).
  Fill the {{PLACEHOLDERS}} from the stage outputs after a real run:
    figures → outputs/figures/*.png   tables → outputs/tables/*.{csv,html}
    data    → outputs/data/*.gpkg     stats  → outputs/tables/stats_*.html
  Render to PDF (with figures) via build_report.sh (pandoc). niva produced the
  summary maps (08_report.niva) and the data catalog (outputs/report/).
-->

## Abstract

We assess the past-and-present hydrologic state of the Village of Youngstown, New York, at the
mouth of the lower Niagara River on Lake Ontario, for two epochs (2001, 2024). We (1) delineate
the shorelines of both waterfronts, (2) rate shoreline erosion risk, (3) quantify impervious
surface within each HUC12 hydrologic unit and ownership parcel — derived by **fusing LiDAR with
4-band aerial imagery** and benchmarked against NLCD, (4) quantify, locate, rank, and statistically
assess change, and (5) evaluate the potential for increased stream scour. {{KEY_FINDINGS: e.g.
"Impervious cover rose from X% to Y% (Δ = Z pts); N HUC12 units and M parcels exceed a 5-pt
increase; the Lake Ontario front shows a mean end-point erosion rate of R m/yr; K stream reaches
show rising scour potential."}} All processing is reproducible from raw inputs via the niva flows
`01–08`.

## 1. Introduction

The AOI has two distinct waterfronts — the **Niagara River** (west) and **Lake Ontario** (north) —
and drains through several HUC12 units before discharging to the lake. Shoreline recession,
watershed imperviousness, and channel scour are the hydrologic pressures of interest for the Town
of Porter Hazard Mitigation Plan. This study establishes an auditable, repeatable baseline and
change record across 2001→2024. Prior shoreline-change and stream-power methods are followed
where possible (§4) and cited in §References.

## 2. Study area and data

Study area: Village of Youngstown / AOI (`derived/aoi_6346.gpkg`); working SRS **EPSG:6346**
(NAD83(2011)/UTM 18N). Data (raw in `inputs/`, documented in `outputs/notes/`):

| Dataset | Role | Source |
|---|---|---|
| USGS 3DEP LiDAR (all vintages) | DTM/DSM/nDSM, shoreline contour, flow accumulation | USGS 3DEP |
| 2024 4-band (R,G,B,NIR) ortho, 1 ft | shoreline (NDWI), impervious (NDVI/NIR) | NYS GIS 2024 |
| Historical ortho (~2001) | past shoreline & impervious | NAIP / NYS |
| NLCD % impervious 2001 & 2021 | benchmark only | MRLC |
| WBD HUC12 | hydrologic units | USGS WBD |
| NHD flowlines | stream reaches | USGS NHD |
| Parcels (assessed value, owner) | ownership units | Niagara County |

Data-quality reports: `outputs/notes/quality_*.md`. Full inventory: `outputs/report/final_data_catalog.md`.

## 3. Overview figure

![Study summary — shorelines, impervious change, and scour potential over the AOI.](outputs/figures/08_cover_map.png)

## 4. Methods

All steps are reproducible niva flows; the run journal (`NIVA_LOG`) records the exact,
parameterized processing chain, and every alias verb's **effective parameters (including injected
defaults)** are recoverable with `niva … --explain`.

- **Software.** QGIS Processing (QGIS Development Team, 2024) via **niva** v0.40; GDAL/OGR
  (GDAL/OGR contributors, 2024); GRASS GIS `r.watershed` (Neteler et al., 2012) for flow
  accumulation; PDAL / `pdal_wrench` (PDAL Contributors, 2024) for LiDAR. No SAGA, no OTB.
- **Shoreline delineation (§Stage 03).** Present shoreline from the LiDAR DTM water-surface
  **contour** at the Lake Ontario low-water datum (≈74.2 m IGLD 1985; `gdal:contour`) reconciled
  with an imagery **NDWI** water mask (McFeeters, 1996; `gdal:rastercalculator` → `gdal:polygonize`
  → `native:polygonstolines`); past shoreline by the same NDWI on the historical ortho.
- **Erosion risk (§Stage 04).** DSAS-style perpendicular transects (`native:transectfixeddistance`;
  Himmelstoss et al., 2021), End-Point Rate between epochs, combined with physical vulnerability
  (bluff height from the DTM, wave/fetch exposure by front, bank cover from NDVI [Rouse et al.,
  1974]). Documented weights: EPR 0.45 / bluff 0.25 / exposure 0.20 / cover 0.10.
- **Impervious surface (§Stage 05).** Fused from LiDAR (nDSM, building class, intensity,
  roughness) and the 4-band ortho (NDVI/NDWI/NIR) at 1 m (Hodgson et al., 2003); rule-based;
  **independent of NLCD**. Impervious area/percent per HUC12 and per parcel via
  `zonalstats`; NLCD (Dewitz/USGS, 2023; Yang et al., 2018) used as a benchmark comparison only.
- **Change and statistics (§Stage 06).** Per-zone Δ impervious (2024−2001), feature-level
  gained/lost polygons (`native:difference`), descriptive statistics
  (`native:basicstatisticsforfields`), ranking of top movers, and per-front summaries
  (`qgis:statisticsbycategories`).
- **Stream scour (§Stage 07).** Flow accumulation (`grass:r.watershed`), Stream Power Index
  SPI = A·tan β (Moore et al., 1991) as the DEM proxy for specific stream power ω = ρgQS/w
  (Bagnold, 1977; Bull, 1979), multiplied by the upstream catchment's Δ impervious to flag
  reaches of **increasing** scour potential.

## 5. Results

### 5.1 Shoreline change and erosion risk
{{Summarize EPR by front (mean ± uncertainty, m/yr); High-risk segments.}}
![Shoreline erosion risk.](outputs/figures/08_map_erosion_risk.png)

### 5.2 Impervious surface and change
{{Impervious % by epoch and Δ; top HUC12 and parcels; fused-vs-NLCD agreement.}}
![Impervious change 2001→2024 by HUC12.](outputs/figures/08_map_imperv_change.png)
Statistics: `outputs/tables/stats_dimp_huc12.html`, `stats_dimp_parcel.html`.

### 5.3 Stream scour potential
{{Reaches ranked High for increased scour; where energetic channel meets urbanizing catchment.}}
![Increased stream-scour potential.](outputs/figures/08_map_scour.png)

## 6. Conclusions

{{State the AOI's hydrologic state and notable 2001→2024 changes.}} **Limitations:** the past
epoch depends on historical-imagery availability (NDWI needs NIR); the DSAS EPR and factor
normalizations, the exposure-by-front assignment, and true upstream tracing for scour are
documented approximations; specific stream power uses regional bankfull-discharge regression
(USGS StreamStats). NLCD is a benchmark, not the impervious source of record.

## References

**Methods.** Himmelstoss, E.A., et al. (2021) *DSAS v5.1 user guide*, USGS OFR 2021-1091 ·
Gornitz, V. (1991) *Palaeogeogr. Palaeoclimatol. Palaeoecol.* 89(4) · Bagnold, R.A. (1977)
*Water Resour. Res.* 13(2) · Bull, W.B. (1979) *GSA Bull.* 90(5) · Moore, I.D., et al. (1991)
*Hydrol. Process.* 5(1) · Lumia, R., et al. (2006) USGS SIR 2006-5112; USGS StreamStats ·
McFeeters, S.K. (1996) *Int. J. Remote Sens.* 17(7) · Rouse, J.W., et al. (1974) NASA SP-351 ·
Hodgson, M.E., et al. (2003) *PE&RS* 69(9) · Yang, L., et al. (2018) *ISPRS J.* 146.
**Data.** USGS 3DEP; USGS NHD; USGS/USDA-NRCS WBD; MRLC NLCD (Dewitz/USGS, 2023); NYS GIS
orthoimagery; Coordinating Committee (1995) *IGLD 85*.
**Software.** QGIS Development Team (2024) qgis.org · GDAL/OGR contributors (2024) gdal.org ·
Neteler, M., et al. (2012) *Environ. Model. Softw.* 31 · PDAL Contributors (2024) pdal.io ·
niva v0.40, github.com/johnzastrow/niva.

## Tables
{{Insert result tables from outputs/tables/ (impervious by HUC12/parcel, ranked movers, stats).}}

## Figures
See §3, §5. Full figure trail: `outputs/figures/`.
