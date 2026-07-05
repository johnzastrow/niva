# Use case — Hydrologic assessment of the Youngstown AOI: past & present

**Role:** Hydrologic analyst.
**Study area (AOI):** Village of Youngstown, Town of Porter, Niagara County, New York — at the
**mouth of the lower Niagara River where it enters Lake Ontario**, so the AOI has *two*
distinct water fronts: the **Niagara River** (west) and **Lake Ontario** (north).
**AOI geometry:** `demo.gpkg :: aoi` / `AOISM` (study extent), `ny_youngstown` (village).
**Working SRS:** `EPSG:6346` — NAD83(2011) / UTM 18N (meters); all analysis in a projected,
metric CRS so distances, areas, and rates are true.

**Status:** DRAFT brief — the "define the problem & methods" artifact. Runnable `*.niva`
flow(s) implementing it will live beside this file. As of **niva v0.40** most steps map to
curated verbs; only four operations still use the `run <algorithm> KEY=value` escape hatch
(contour, flow accumulation, band math, transects) — all filed as candidate verbs in
[`TODO.md`](../../TODO.md).

> **Why this example exists / how it improves on the others.** The prior examples each show one
> slice: [`youngstown_cat_canvassing.niva`](../youngstown_cat_canvassing.niva) is vector +
> routing; [`analyst_plan.niva`](../analyst_plan.niva) is data-prep. This study is a **complete
> scientific investigation** — it adds a **temporal (past vs present) change analysis with
> statistics**, **raster terrain hydrology**, **zonal summarization over two independent unit
> systems**, and ends in a **reproducible deliverable package with a peer-review-style report**.
> It is the widest realistic pass through niva in one coherent story, and it exercises the
> documentation/provenance verbs (`assess`, `catalog`, `metadata`, `docs`) as first-class
> deliverables, not afterthoughts.

---

## Objective

Document the **past and present hydrologic state** of the Youngstown AOI and characterize
**change**, delivering:

1. **Shoreline delineation** of the Niagara River and Lake Ontario, for a **past** and a
   **present** epoch.
2. **Shoreline erosion risk** for both water fronts.
3. **Impervious surface amounts** within each **HUC12** hydrologic unit **and** within each
   **ownership parcel** in the AOI.
4. **Change quantification** — locate, quantify, and **rank** changes, with a **statistical
   assessment**.
5. **Stream scour-potential** evaluation — where is the potential for *increased* scour rising?
6. A **reproducible deliverable package** (`inputs/` → `derived/` → `outputs/`) ending in a
   **scientific report**.

### Temporal frame (define the two epochs up front)

"Past vs present" needs fixed epochs. **Settled:**

| Epoch | Date | Shoreline source | Impervious source |
|---|---|---|---|
| **Past** | **2001** | historical ortho / published shoreline / earliest LiDAR | NLCD 2001 % impervious |
| **Present** | **2024** | 2024 4-band ortho + LiDAR DTM contour / NHD | NLCD 2021 % impervious |

Rates and change metrics are always normalized **per year** so the specific dates are explicit
in every result.

---

## Tooling & providers (constraint)

niva's provider preference is **native → gdal → QGIS → PDAL → GRASS (last)**. For this study:

- **Avoid SAGA and OTB.** Do not depend on — or bake into niva — SAGA or Orfeo Toolbox (OTB).
  Where SAGA/OTB would be the "easy" path (SAGA flow accumulation, OTB image
  segmentation/classification), use a native / gdal / GRASS / PDAL alternative instead.
- **LiDAR → PDAL via the `pdalcli:` harness (v0.38).** Derive terrain/surface products from raw
  LAS/LAZ with `run pdalcli:to_raster` (DTM/DSM), `pdalcli:height_above_ground` (CHM),
  `pdalcli:classify_ground`, `pdalcli:boundary` — no COPC step, no SAGA/OTB.
- **Aerial imagery → gdal / native.** Derive water lines and impervious from imagery with gdal
  raster algebra (spectral indices + thresholds) and native vectorize — **not** OTB
  classification.
- **One watch item:** hydrologic **flow accumulation** (§5) has no native/gdal equivalent; the
  realistic options are **GRASS `r.watershed`** or SAGA. Since SAGA is out, the plan uses
  **GRASS** (a `run` escape hatch, not a baked-in dependency). If GRASS is *also* unwanted, the
  fallback is a D8 accumulation derived from the LiDAR DTM via `run` — flag `!! ALERT`.

> **niva verb mapping (v0.40).** niva now ships curated verbs covering most of this study:
> `zonalstats`, `slope`/`aspect`/`hillshade`, `map` + `figure` (cartography →
> PNG/PDF/SVG), and the **`pdalcli:` LiDAR harness**. (There is **no** `stats` verb — descriptive
> statistics use `run native:basicstatisticsforfields` / `qgis:statisticsbycategories`.) Only
> these operations still use the `run`
> escape hatch — **contour** (`gdal:contour`), **flow accumulation** (`grass:r.watershed`),
> **NDWI/NDVI band math** (`gdal:rastercalculator`), and **transects** (`qgis:transectsalongline`)
> — all filed as candidate verbs in [`TODO.md`](../../TODO.md). No SAGA, no OTB.

---

## Resolved decisions (client, 2026-07-05)

**Data acquisition** — the flow *fetches and documents* its own sources; raw copies land in
`inputs/` (read-only), provenance to `outputs/notes/`:

- **LiDAR — fetch ALL available.** Pull all LiDAR coverage for the AOI (USGS 3DEP; NYS if finer)
  and document every tile (source, collection date, point density, CRS). Multiple vintages ⇒
  LiDAR-based terrain & shoreline change. Processed with **PDAL** (`run pdal:*`).
- **Present imagery — already in hand.** `~/Downloads/twn_Porter_sp24/` holds the **2024 4-band
  (R,G,B,NIR) orthophoto** of the Town of Porter — **202 tiles + merged `porter_ortho.jp2`**,
  **1-ft pixel**, NY State Plane West (ftUS, ~EPSG:6541). **Band 4 = NIR**, so **NDWI (water) and
  NDVI (veg/impervious) work directly** — no NAIP needed for the present epoch. Reproject to
  EPSG:6346 for analysis.
- **Past imagery — fetch.** Pull a historical ortho for the "past" epoch (older NYS ortho or
  **NAIP** historical — also 4-band) for shoreline & impervious change.
- **HUC12 + NLCD — pull both.** Fetch **WBD HUC12** and **NLCD % impervious (2001 & 2021)** for
  the AOI, documented into `inputs/`.

**Tooling:** native → gdal first; **GRASS only where no native/gdal algorithm exists** (e.g.
flow accumulation). **SAGA and OTB remain excluded.**

**Impervious — FUSED from `.las` LiDAR + aerial imagery (primary method; NLCD *not* relied on):**

The study's impervious surface of record is **derived by fusing the `.las` LiDAR with the 4-band
ortho**, at ~1 m — a genuine multi-sensor product, **independent of NLCD**. Neither sensor alone
is reliable (imagery confuses bright **bare soil** with pavement; LiDAR alone confuses low
vegetation with flat ground), so they are **combined** (after Hodgson et al. 2003):

- **From `.las` (`run pdalcli:*`):** ground classification → DTM; DSM → **nDSM = DSM − DTM**
  (object height); building-class (class 6) → roof footprints; return-count / intensity /
  point-density rasters; local Z-roughness (smooth pavement vs. rough canopy).
- **From the 4-band ortho (`run gdal:rastercalculator`):** **NDVI** (reject vegetation), **NDWI**
  (reject water), and the **NIR/brightness** contrast that separates bright **bare soil** (high
  NIR) from **pavement** (lower NIR).
- **Fusion rule (transparent, rule-based):** impervious ⇐ *non-vegetated* (NDVI < t) **and**
  *non-water* (NDWI < t) **and** *hard surface per LiDAR* (building-class / high-nDSM **roofs**, or
  ground-class **low-roughness pavement** with a non-soil NIR signature). Output a **1 m impervious
  raster per epoch** (present: 2024 ortho + newest LiDAR; past: 2001 ortho + earliest LiDAR, any
  gap documented).

**NLCD comparison is a defined part of the study** (a benchmark component — not the source of
truth). The fused 1 m product **is** compared to NLCD % impervious (30 m): agreement, bias, and
where the higher-resolution product diverges (narrow driveways, small outbuildings NLCD's 30 m
misses), reported as its own benchmark section. But NLCD is **not** the reference and **no** result
depends on it — the impervious of record is the sensor-derived surface.

---

## Study components (method per task)

Each component states its **goal**, **method** (niva verbs; `run` escape hatch where no alias
exists), **inputs**, and **outputs** (which land in `derived/` or `outputs/`).

### 1 · Shoreline delineation (Niagara River + Lake Ontario), past & present

- **Goal:** a clean land–water line for each water front, for each epoch → four shoreline
  linework layers (2 fronts × 2 epochs), plus a merged, attributed `shorelines.gpkg`
  (`front`, `epoch`, `date`, `source`, `method`).
- **Method (present)** — derive from **LiDAR + imagery** (no SAGA/OTB), reconciling three lines:
  1. **LiDAR DTM contour** — bare-earth DTM via `run pdalcli:to_raster attribute=Z
     filter="Classification==2" resolution=1`, then the water-surface **contour**
     (`run gdal:contour` — no `contour` verb yet) at the local datum (Lake Ontario low-water
     ≈ 74.2 m IGLD 1985; Niagara River pool near the mouth). LiDAR water/ground returns cross-check.
  2. **Imagery water index** — from current aerial imagery, compute an **NDWI-style water index**
     via `run gdal:rastercalculator`, threshold to a water mask, `run gdal:polygonize`, and take
     the land–water ring.
  3. **NHD water-area polygon boundary** — authoritative reconciliation.
  Keep the agreed line; record disagreement between the three in `outputs/notes/`.
- **Method (past)** — the same NDWI threshold on **historical aerial imagery** (added data),
  and/or an older LiDAR DTM contour where an earlier lidar epoch exists; else digitize from a
  historical topo / published shoreline vintage. Same attribute schema as present.
- **Normalize:** clip to each front's reach; smooth lightly; snap endpoints; tag attributes.
- **Verbs:** `load`, `clip`, `dissolve`, `fixgeom`, `save`; `run pdalcli:to_raster` (DTM),
  `run gdal:contour` / `gdal:rastercalculator` (NDWI) / `gdal:polygonize`.

### 2 · Shoreline erosion risk (both fronts)

- **Goal:** an erosion-risk rating along each shoreline, combining **measured historical
  change** with **physical vulnerability**.
- **Method — historical change rate (DSAS-style):**
  1. Build a **baseline** offshore of both shorelines (`buffer` the present shoreline seaward,
     take the outer edge).
  2. Cast **transects** perpendicular to the baseline at a fixed spacing —
     `!! ALERT` no `transects` verb; `run qgis:transectsalongline` (or points-along +
     perpendicular construction).
  3. Intersect transects with each epoch's shoreline; measure the along-transect distance to
     each date; compute **End-Point Rate (EPR, m/yr)** = Δdistance ÷ Δyears (and note where a
     linear-regression rate would apply if >2 dates exist).
  4. Attribute each transect with its retreat/advance rate and an uncertainty band.
- **Method — physical vulnerability factors** (per shoreline segment, 0–1 normalized):
  - **bluff height / backshore slope** from the **LiDAR DTM/DSM** (sharper than the coarse
    `dem.tif`; Lake Ontario bluffs erode faster) — elevation profiles / zonal stats near the line;
  - **fetch / wave exposure** proxy (open-lake Ontario front > sheltered river front);
  - **bank landcover** (bare/erodible vs vegetated) from `landcover.tif`.
- **Combine:** add a weighted erosion-risk index field (`run native:fieldcalculator`); classify High/Med/Low. **Documented
  default weights** (tunable; passed to the flow):

  | Factor | Weight | Rationale |
  |---|---|---|
  | Measured change rate (EPR) | **0.45** | direct evidence of erosion; dominates when two shorelines exist |
  | Bluff height / backshore slope | **0.25** | taller/steeper banks fail faster (Lake Ontario bluffs) |
  | Wave / fetch exposure | **0.20** | open-lake front ≫ sheltered river front |
  | Bank landcover (bare vs vegetated) | **0.10** | vegetation resists erosion |

  If no past shoreline exists, EPR drops out and the three vulnerability factors renormalize to
  sum 1.0 (a **vulnerability-only** rating, clearly labeled).
- **Verbs:** `buffer`, `intersect`, `zonalstats` (bluff/cover near the line), `run native:fieldcalculator`,
  `filter`, `style`, `save`; `run qgis:transectsalongline` (transects).

### 3 · Impervious surface within each HUC12 and each parcel

- **Goal:** impervious **area (m²)** and **percent** per **HUC12** unit and per **parcel**, for
  each epoch (so §4 can difference them).
- **Method:** compute impervious **area (m²)** and **percent** per zone by **`zonalstats`** over
  the **fused LiDAR+imagery impervious raster** (the study's impervious of record; see Resolved
  decisions), for each epoch, over two zone systems:
  - `huc12.gpkg` (WBD) → `imperv_by_huc12.gpkg`;
  - `parcels` → `imperv_by_parcel.gpkg` (joined to owners via `PrintKey`).
  - `zonalstats raster=impervious_2024.tif stats=sum,mean,count prefix=imp_`. At 1 m one pixel =
    1 m², so the sum of the 0/1 impervious mask is directly the impervious **area**; percent =
    area ÷ zone area.
- **NLCD benchmark (a defined part of the study, not the source of truth):** run the same zonal
  summary over NLCD % impervious and report agreement / bias vs. the sensor-derived product per
  HUC12 and parcel — including where the 1 m product captures features NLCD's 30 m misses
  (driveways, small outbuildings). No result depends on NLCD.
- **Verbs:** `load`, `clip`, `join`, `zonalstats`, `run native:fieldcalculator`, `save`; `run pdalcli:*` (LiDAR
  metrics) + `run gdal:rastercalculator` (indices + fusion).

### 4 · Change: quantify, locate, rank, and assess statistically

- **Goal:** a defensible statement of *what changed, where, by how much, and whether it's
  significant.*
- **Metrics:**
  - **Shoreline change** — per-transect EPR (m/yr) and total retreat (m); by front.
  - **Impervious change** — Δ impervious % and Δ area per HUC12 and per parcel (present − past).
  - (Optional) **landcover change** — cross-tab of past vs present classes (`run` gdal raster
    calc / change matrix).
- **Locate & rank:** `filter`/`run native:fieldcalculator` to rank zones and transects by magnitude; map the top
  movers; optional **hotspot** clustering (`run` Getis-Ord Gi\*) to find spatially significant
  clusters of change.
- **Statistical assessment (the "improve on existing" core):**
  - descriptive stats (mean, median, SD, IQR, min/max) per metric and per front/unit;
  - shoreline-rate **uncertainty** (positional error of each shoreline ÷ Δyears);
  - a **trend/significance test** where applicable (e.g., regression of impervious % vs year
    across NLCD epochs if ≥3 are used; paired comparison of parcels past vs present);
  - distributions as histograms/box plots (figures for the report).
  - Descriptive statistics via **`run native:basicstatisticsforfields`** (per field) and
    **`run qgis:statisticsbycategories`** (per group), plus `sql` aggregate queries; heavier
    tests (regression / paired) via a documented `run` step. *(There is no `stats` verb.)*
- **Verbs:** `sql`, `run native:fieldcalculator`, `filter`, `save`, `map`/`figure`; `run native:basicstatisticsforfields`
  (stats), `run` for hotspot / raster change.

### 5 · Stream scour-potential (increase) evaluation

- **Goal:** identify stream reaches where the **potential for increased scour** is rising —
  i.e., steep/confined reaches whose contributing area is **urbanizing** (impervious ↑ → higher
  peak flows / shear).
- **Method:**
  1. Hydrologically condition the **LiDAR DTM** (or `dem.tif`): fill sinks, flow direction,
     **flow accumulation** — `!! ALERT` no hydrology verbs; `run grass7:r.watershed` (GRASS;
     **SAGA deliberately avoided** — see Tooling). D8-from-DTM `run` fallback if GRASS is out too.
  2. **Energy metric.** Primary = **specific stream power** ω = ρ g Q S / w (W/m²), the physical
     driver of bed scour: slope **S** from the LiDAR DTM along each reach, bankfull discharge **Q**
     from a regional drainage-area regression (USGS StreamStats NY), channel width **w** from
     imagery/NHD. Where Q/w aren't resolvable per reach, fall back to the DEM-only proxy
     **SPI = A · tan β** (A = flow-accumulation area, β = slope), from the §5.1 accumulation grid
     + `slope`.
  3. **The "increase" driver (temporal).** Attribute each reach's upstream HUC12 with its
     **Δ impervious %** (§3–4): urbanization raises peak flows and thus shear.
  4. **Increased-scour index** = normalized(ω or SPI) × normalized(Δ impervious). High where the
     channel is already energetic **and** its catchment is urbanizing. Classify and rank reaches.
- **Verbs:** `slope`, `zonalstats`, `intersect`, `run native:fieldcalculator`, `filter`, `save`;
  `run grass:r.watershed` (flow accumulation) + raster algebra (SPI / ω).

### 6 · Deliverable package

The exact structure the client specified — **raw inputs are never modified**:

```
youngstown_hydro/
├── inputs/     # RAW source data, READ-ONLY. Copied here verbatim; nothing writes back.
│   └── catalog.md            (auto: `catalog inputs/`)
├── derived/    # intermediate/working data produced by the flow (reprojected, clipped,
│               #   transects, zonal tables, flow-accumulation, SPI, …)
└── outputs/    # FINAL products only
    ├── data/                 final GeoPackages, rasters, CSVs (shorelines, risk, imperv, change, scour)
    ├── notes/                intermediate documentation (.md): learning & processing steps
    │                         not central to the study but recorded for reproducibility
    ├── figures/              maps + charts referenced by the report
    ├── tables/               result tables (CSV) referenced by the report
    └── report/
        └── youngstown_hydrologic_assessment.md   # the scientific report (below)
```

- **`inputs/` immutability** is a rule the flow honors by only ever *reading* from `inputs/`
  and only ever *writing* to `derived/` and `outputs/`. (An `assess` report per input is
  written to `outputs/notes/`, not into `inputs/`.)
- **niva mapping:** `catalog` (inputs + outputs catalogs), `assess` (input quality → notes),
  `save`/`metadata` (final data + lineage), **`map`** (composed layout → **PDF/PNG**, legend +
  scale bar + north arrow; `from=<project.qgz>` for atlases) and **`figure`** (quick images) for
  `outputs/figures/`, `run native:basicstatisticsforfields`+`save` (tables), authored markdown + **`docs`/pandoc → PDF**
  (report), `notify` (progress).

- **Visualization convention:** **every processing step saves a `figure`** — a quick,
  pass-through PNG of that step's output into `outputs/figures/` — giving a **visual audit trail**
  of the whole pipeline (DTM, nDSM, NDVI, impervious mask, transects, shorelines, scour reaches, …).
  Because `figure` is pass-through, it chains directly after `save` without changing the flow.
  The study then composes **`map`** layouts (legend + scale bar + north arrow → PDF) **as needed**
  for the report and public deliverables. So: *figure at each step; maps where they communicate.*

**Scientific report — required sections** (`outputs/report/…md` **→ PDF with figures embedded**;
figures by `map`/`figure`, tables by `run native:basicstatisticsforfields`/`save`, PDF via the `docs`/pandoc path):

> **Abstract** · **Introduction** (setting, the two water fronts, questions, prior work with
> citations) · **Methods** — data provenance & CRS; epochs; then **every processing step as an
> ordered, reproducible chain** (each step named as a niva verb or `run <algorithm-id>`, with its
> parameters, resolutions, thresholds, weights, datum, and **software version**), covering
> shoreline extraction, DSAS rates, zonal impervious, change statistics, and ω/SPI scour —
> **citing both the science and the software/algorithms used**, as a reproducible Methods section
> does · **Results** (shoreline change by front, erosion-risk map, impervious by HUC12 & parcel +
> change, ranked movers, scour reaches; with **tables & figures**) · **Conclusions** (state of the
> AOI, notable changes, limitations) · **References** (science *and* software — see the References
> section of this brief) · **Tables** · **Figures**.

---

## Data

### Shipped vs fetched (what ships with the example vs pulled at run time)

The example **ships light** — a small **study-area visualization set** derived from
`examples/demo/` (AOI, village, hydrography, a hillshade) so anyone can open the example and *see*
Youngstown immediately via a one-line `map`. Everything heavy and value-added — **LiDAR (3DEP),
NLCD 2001/2021, WBD HUC12, the historical ortho** — is **fetched at run time from primary sources**
into read-only `inputs/`, using a mix of **commands outside niva** (curl / `gdal` `/vsicurl` for the
downloads) and **inside niva** (`load`/`catalog`/`assess` to document what arrived). **Every fetch
is scripted and explained** (source URL, date, checksum → `outputs/notes/`), so the package is both
immediately viewable *and* fully reproducible from primary sources.

### Present in the demo dataset (`examples/demo/`) — the "present"/base layers

| Role | Layer(s) |
|---|---|
| AOI / village | `aoi`, `AOISM`, `ny_youngstown` |
| Terrain | `dem.tif`, `slope.tif`, `aspect.tif`, `hillshade.tif` |
| Hydrography (streams/reaches) | `ytown_nhdflowline`, `ny_streams`, `nhd_flowlines`, `ny_hydrolines_clip` |
| Catchments (NHDPlus) | `watersheds`, `nhdplus_catchment` (NHDPlusID) — *not HUC12* |
| Landcover | `landcover.tif`, `landcover_woodland` |
| Parcels (ownership zones) | `parcels` (2,790: `PrintKey`, `OwnrName`, `ACRES`, value fields) |
| Owner names | `owners.csv` (`PrintKey`) |
| Waterbody/flood context | `floodzone`, `nhdplus_burnwaterbody` |

### "Add a bit more" — data this study genuinely needs (temporal + hydrologic units)

The demo is a **single-epoch** snapshot; a *past & present* study needs multi-date and a few
hydrologic layers. Each is a small, well-known public source:

1. **HUC12 boundaries (USGS WBD)** for the AOI — required by §3 ("each HUC12"). The demo has
   NHDPlus catchments, **not** WBD HUC12s. *(USGS WBD / TNM.)*
2. **NLCD % Developed Imperviousness, two epochs** (e.g., 2001 & 2021) — required by §3–4.
   *(MRLC NLCD.)* Fallback: derive impervious from the demo `landcover.tif` developed classes,
   single-epoch only (no change) — a documented stand-in.
3. **LiDAR point cloud(s)** (USGS 3DEP / NYS) — the workhorse for this study, processed with
   **PDAL** (no SAGA/OTB): bare-earth **DTM**, surface **DSM**, **bluff height / backshore
   slope** (§2), a **water-surface contour** for the present shoreline (§1), and a D8
   flow-accumulation fallback (§5). One epoch minimum; two epochs enable LiDAR-based terrain &
   shoreline change.
4. **Aerial imagery** — **present is already in hand**: the **2024 4-band (R,G,B,NIR)** ortho in
   `~/Downloads/twn_Porter_sp24/` (1-ft, 202 tiles + merged `porter_ortho.jp2`, NY-West ftUS).
   **Fetch only a historical ortho** (older NYS / NAIP, also 4-band) for the "past" epoch. Drives
   NDWI water lines (§1–2), NDVI/impervious (§3), and change context — gdal raster algebra, no OTB.
5. **A published past-shoreline vintage** (NOAA/USACE or USGS historical topo) — optional
   independent check on the imagery/LiDAR-derived past shoreline.
6. **(Optional) bathymetry / water-surface elevation** to pin the DTM contour datum precisely.

> Where an "add" is missing, the flow still runs with a **clearly-labeled stand-in** (e.g.
> single-epoch impervious, vulnerability-only erosion risk) so the pipeline and package are
> demonstrable end-to-end, and the report states the limitation.

---

## Acceptance criteria (built into the flow, not just prose)

- `inputs/` is **byte-for-byte unmodified** after a full run (checksums logged to notes).
- Every input has an `assess` report; every output carries lineage `metadata`.
- Shoreline rates carry an explicit **± uncertainty** and a stated Δyears.
- Impervious percentages are bounded 0–100 and reconcile (Σ parcel impervious ≈ zonal total
  within tolerance).
- The report renders with all required sections and every figure/table it references exists.
- Re-running reproduces `derived/` and `outputs/` from `inputs/` with no manual steps.

---

## Settled parameters (all prior open questions resolved)

- **Epochs:** past = **2001** (matches NLCD 2001), present = **2024** (ortho/LiDAR); NLCD present
  = 2021. All rates normalized per-year.
- **Erosion-risk weights:** EPR **0.45** / bluff **0.25** / wave exposure **0.20** / bank cover
  **0.10** (documented, tunable — §2).
- **Scour metric:** **specific stream power** ω = ρgQS/w, with **SPI = A·tan β** as the DEM-only
  proxy, × upstream **Δ-impervious** for the "increase" (§5).
- **Report:** Markdown **and PDF with embedded figures** (`map`/`figure` + `docs`/pandoc).
- **Tooling:** native → gdal → GRASS (only where needed) → PDAL (`pdalcli:`); **SAGA & OTB
  excluded**.

---

## References — scientific basis (methods this study relies on)

Cited inline in the methods above and carried into the report's **References** section. Each
method choice traces to a primary source:

**Shoreline change & erosion**
- Himmelstoss, E.A., Henderson, R.E., Kratzmann, M.G., & Farris, A.S. (2021). *Digital Shoreline
  Analysis System (DSAS) version 5.1 user guide.* USGS Open-File Report 2021–1091. — transects,
  End-Point Rate (EPR), and shoreline-position uncertainty (§2, §4).
- Gornitz, V. (1991). Global coastal hazards from future sea level rise. *Palaeogeography,
  Palaeoclimatology, Palaeoecology, 89*(4), 379–398. — coastal vulnerability factor weighting (§2).

**Stream scour / stream power**
- Bagnold, R.A. (1977). Bed load transport by natural rivers. *Water Resources Research, 13*(2),
  303–312. — (specific) stream power as the driver of bed transport/scour (§5).
- Bull, W.B. (1979). Threshold of critical power in streams. *GSA Bulletin, 90*(5), 453–464. — the
  critical-power threshold concept for scour (§5).
- Moore, I.D., Grayson, R.B., & Ladson, A.R. (1991). Digital terrain modelling: a review of
  hydrological, geomorphological, and biological applications. *Hydrological Processes, 5*(1),
  3–30. — Stream Power Index SPI = A·tan β from a DEM (§5).

**Bankfull discharge (Q for ω)**
- Lumia, R., Freehafer, D.A., & Smith, M.J. (2006). *Magnitude and frequency of floods in New York.*
  USGS Scientific Investigations Report 2006–5112; and USGS **StreamStats** (NY). — regional
  drainage-area regression for bankfull Q (§5).

**Spectral indices & multi-sensor impervious mapping**
- McFeeters, S.K. (1996). The use of the Normalized Difference Water Index (NDWI) in the
  delineation of open water features. *Int. J. Remote Sensing, 17*(7), 1425–1432. — NDWI (Green,
  NIR) for the shoreline (§1).
- Rouse, J.W., Haas, R.H., Schell, J.A., & Deering, D.W. (1974). *Monitoring vegetation systems in
  the Great Plains with ERTS.* NASA SP-351. — NDVI, used to separate vegetation from impervious (§3).
- Hodgson, M.E., Jensen, J.R., Tullis, J.A., Riordan, K.D., & Archer, C.M. (2003). Synergistic use
  of lidar and color aerial photography for mapping urban parcel imperviousness. *Photogrammetric
  Engineering & Remote Sensing, 69*(9), 973–980. — the **fused LiDAR + aerial-imagery impervious**
  method (§3), the NLCD-independent primary product.

**Reference datasets**
- Dewitz, J., & USGS (2023). *National Land Cover Database (NLCD) 2021 Products.* USGS; Yang, L., et
  al. (2018), *ISPRS J. Photogramm. Remote Sens., 146*, 108–123. — NLCD % Developed Imperviousness
  (§3, reference for the LiDAR/imagery derivations).
- U.S. Geological Survey & USDA-NRCS. *Watershed Boundary Dataset (WBD)* — HUC12 units (§3).
- U.S. Geological Survey. *National Hydrography Dataset (NHD / NHDPlus HR).* — watercourses,
  catchments (§1, §5).
- U.S. Geological Survey. *3D Elevation Program (3DEP) LiDAR.* — point clouds for DTM/DSM/CHM
  (§1, §2, §5).
- Coordinating Committee on Great Lakes Basic Hydraulic and Hydrologic Data (1995).
  *International Great Lakes Datum 1985 (IGLD 85).* — Lake Ontario water-surface datum for the
  contour-based shoreline (§1).

**Software & processing tools** (cited in Methods, and named at each processing step)
- QGIS Development Team (2024). *QGIS Geographic Information System.* Open Source Geospatial
  Foundation. https://qgis.org — the Processing framework hosting `native:*` algorithms.
- GDAL/OGR contributors (2024). *GDAL/OGR Geospatial Data Abstraction Library.* OSGeo.
  https://gdal.org — `gdal:contour`, `gdal:rastercalculator` (NDWI/NDVI/SPI), `gdal:warpreproject`,
  `gdal:polygonize`.
- Neteler, M., Bowman, M.H., Landa, M., & Metz, M. (2012). GRASS GIS: A multi-purpose open source
  GIS. *Environmental Modelling & Software, 31*, 124–130. — `r.watershed` (flow accumulation),
  `r.geomorphon`.
- PDAL Contributors (2024). *PDAL: Point Data Abstraction Library* (and `pdal_wrench`).
  https://pdal.io — LiDAR DTM/DSM/CHM, ground classification, boundary (the `pdalcli:` harness).
- niva (this project), **v0.40** — the pipeline grammar orchestrating the above; each `run`
  records the exact algorithm id + parameters, each `save` records lineage metadata.

### Processing provenance & reproducibility (paper-standard)

**The processing steps are documented to the standard of a scientific paper's Methods.** For
every step the record captures: the **input** (source, acquisition date, CRS, resolution), the
**operation** (niva verb *or* `run <algorithm-id>`), **all parameters** (thresholds, resolutions,
weights, CRS, datum), and the **software version**. niva makes this largely automatic:

- `assess` / `catalog` profile every input (schema, CRS, extent, validity) → `outputs/notes/`;
- every `save` writes **lineage `metadata`** (the operation chain that produced the layer);
- `NIVA_LOG=<base>` emits a machine **journal** (`<base>.jsonl`) + human **log** (`<base>.log`) of
  the entire run — the ordered, parameterized processing chain.
- **niva's injected defaults are part of the method and must be documented.** Aliases pass
  backend defaults that *change the data* — e.g. `warp` → `RESAMPLING=nearest`,
  `CREATION_OPTIONS=COMPRESS=DEFLATE|TILED=YES`; `reproject` → `CONVERT_CURVED_GEOMETRIES=False`.
  These are shown by `niva … --explain` (and, per niva issue #25, should be surfaced by
  `describe`) and captured in the journal. The report's Methods records **the effective
  parameters, not just the options we typed**, so every output is explainable from the documented
  parameters alone.

So the study is reproducible from `inputs/` exactly as a Methods section requires, and the report
can cite its own `derived/` lineage and journal as the processing record.

> Where a method is adapted rather than followed exactly (e.g. the impervious-weighted
> "increased-scour" index combining Bagnold/Moore stream power with an NLCD-change term), the
> **report's Methods section states the adaptation and cites the primary sources it builds on.**
