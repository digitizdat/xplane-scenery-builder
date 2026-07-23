# Backlog

## Table of Contents

- [Current Backlog Analysis](#current-backlog-analysis)
  - [Scoring](#scoring)
  - [Impact / Effort Matrix](#impact--effort-matrix)
  - [Recommended Sequencing](#recommended-sequencing)
  - [Structural Dependencies](#structural-dependencies)
- [Backlog Items](#backlog-items)
  - Implemented
    - [ORTHO-001 — Orthophoto ground texture generation](#ortho-001--orthophoto-ground-texture-generation)
    - [GEO-001 — Place name geocoding](#geo-001--place-name-geocoding)
    - [PERF-001 — Tiled NDVI processing to prevent OOM](#perf-001--tiled-ndvi-processing-to-prevent-oom)
    - [PERF-002 — Parallel orthophoto fetch and Bedrock classification](#perf-002--parallel-orthophoto-fetch-and-bedrock-classification)
    - [FACADE-001 — Physical-attribute-based facade selection](#facade-001--physical-attribute-based-facade-selection)
    - [SUBSET-001 — Extract smaller scenery from existing output](#subset-001--extract-smaller-scenery-from-existing-output)
    - [ROAD-002 — Suppress default road network in ortho-covered areas](#road-002--suppress-default-road-network-in-ortho-covered-areas)
  - Proposed
    - [ROAD-003 — Align OSM road vectors to orthophoto imagery](#road-003--align-osm-road-vectors-to-orthophoto-imagery)
    - [ROAD-001 — Road classification granularity](#road-001--road-classification-granularity)
    - [ALIGN-001 — Building footprints offset from orthophoto imagery](#align-001--building-footprints-offset-from-orthophoto-imagery)
    - [HEIGHT-001 — Shadow-based building height estimation](#height-001--shadow-based-building-height-estimation)
    - [CLASSIFY-001 — Reduce LLM escalation rate](#classify-001--reduce-llm-escalation-rate)
    - [RENDER-001 — Missing buildings investigation](#render-001--missing-buildings-investigation)
    - [ASSET-001 — Expanded asset placement (FR-8 through FR-18)](#asset-001--expanded-asset-placement-fr-8-through-fr-18)
    - [DDS-001 — DDS texture compression for ortho tiles](#dds-001--dds-texture-compression-for-ortho-tiles)
    - [RENDER-002 — Headless scenery rendering to raster for LLM analysis](#render-002--headless-scenery-rendering-to-raster-for-llm-analysis)
    - [REFINE-001 — Closed-loop scenery refinement via render-and-compare](#refine-001--closed-loop-scenery-refinement-via-render-and-compare)
    - [GATEWAY-001 — Explore X-Plane Scenery Gateway API as a data source](#gateway-001--explore-x-plane-scenery-gateway-api-as-a-data-source)
    - [WED-001 — Explore reusing or building on the WorldEditor (WED) codebase](#wed-001--explore-reusing-or-building-on-the-worldeditor-wed-codebase)

---

## Current Backlog Analysis

The backlog contains 19 items: 7 implemented and 12 proposed. The matrix below
covers only the 12 open (proposed) items; completed items carry no remaining
decision. Each item is rated on Impact (1-5) and Effort (1-5) from its backlog
description, then ranked by ROI (impact / effort). These ratings are planning
estimates and can be reweighted as priorities change.

### Scoring

| Rank | ID | Item | Impact | Effort | ROI | Notes |
|------|-----|------|:------:|:------:|:---:|-------|
| 1 | RENDER-001 | Missing buildings investigation | 5 | 2 | 2.5 | Core-output correctness bug; investigation is cheap |
| 2 | CLASSIFY-001 | Reduce LLM escalation rate | 5 | 2 | 2.5 | Affects cost, quality, and review burden on every run; has a live Opus AccessDenied bug |
| 3 | DDS-001 | DDS texture compression | 3 | 2 | 1.5 | 250 MB to ~50 MB, faster load; well-scoped |
| 4 | WED-001 (LibraryMgr port) | Port WED library resolution | 4 | 3 | 1.33 | Correctness plus enabler; OBJ8 spike already done, de-risked |
| 5 | RENDER-002 | Headless rendering | 4 | 4 | 1.0 | Strategic enabler that unblocks REFINE-001 and speeds visual QA |
| 6 | ROAD-001 | Road classification granularity | 3 | 3 | 1.0 | Rural realism plus actually rendering .net roads |
| 7 | GATEWAY-001 | Gateway API spike | 1 | 1 | 1.0 | Cheap, but GPLv2 blocks content use; marginal over OSM |
| 8 | REFINE-001 | Closed-loop refinement | 4 | 5 | 0.8 | Highest payoff if realized; most ambitious; depends on RENDER-002 |
| 9 | HEIGHT-001 | Shadow-based height estimation | 3 | 4 | 0.75 | Most buildings default to 8 m today; LLM shadow measurement is the risk |
| 10 | ASSET-001 | Expanded asset placement | 3 | 4 | 0.75 | Phase 2; broad scope; benefits from WED-001 port first |
| 11 | ALIGN-001 | Building footprint alignment | 2 | 4 | 0.5 | Backlog itself questions ROI; "accept and document" is a valid cheap path |
| 12 | ROAD-003 | Road-to-ortho alignment | 2 | 4 | 0.5 | Competes with the shipped --no-roads approach; CV-heavy |

### Impact / Effort Matrix

```
                 LOW EFFORT                    |            HIGH EFFORT
   ------------------------------------------- + -------------------------------------------
H  |  QUICK WINS                               |  BIG BETS                                  |
I  |                                           |                                            |
G  |   RENDER-001   (missing buildings)        |   RENDER-002   (headless render, enabler)  |
H  |   CLASSIFY-001 (LLM escalation)           |   REFINE-001   (closed-loop, moonshot)     |
   |   WED-001*     (LibraryMgr port)          |                                            |
I  |                                           |                                            |
M  | ------------------------------------------+------------------------------------------- |
P  |                                           |                                            |
A  |  INCREMENTAL / FILL-INS                   |  RECONSIDER / LOW ROI                       |
C  |                                           |                                            |
T  |   DDS-001      (compression)              |   HEIGHT-001  (shadow heights)             |
   |   ROAD-001     (road granularity, center) |   ASSET-001   (expanded assets)            |
L  |   GATEWAY-001  (spike, low value)         |   ALIGN-001   (building alignment)         |
O  |                                           |   ROAD-003    (road alignment)             |
W  |                                           |                                            |
   ------------------------------------------- + -------------------------------------------

* WED-001's LibraryMgr port is the self-contained, high-value slice. The full
  item (render-engine reuse) belongs in BIG BETS alongside RENDER-002.
  ROAD-001 sits near dead-center (medium/medium); placed in fill-ins by ROI.
```

### Recommended Sequencing

1. **Do now (Quick Wins).** RENDER-001 first, because it is a correctness bug in
   the core deliverable: buildings not rendering undermines everything else.
   Then CLASSIFY-001, which fixes a live bug, cuts Bedrock cost, and reduces
   review load on every run. Both are high-impact, low-effort. DDS-001 is an
   easy follow-on.
2. **Do next (strategic infrastructure).** The WED-001 LibraryMgr port. It is the
   highest-ROI of the larger items, the OBJ8 spike already de-risked it, and it
   unblocks ASSET-001 while keeping output Gateway-valid (never emitting
   deprecated or private assets).
3. **Plan deliberately (Big Bets).** RENDER-002 then REFINE-001 form a dependency
   chain and represent the project's strategic direction: automated visual QA and
   self-correction. RENDER-002 also pays back immediately by making
   RENDER-001-style debugging faster. Commit only when ready for a multi-week
   effort.
4. **Defer or downscope (Low ROI).** ALIGN-001 and ROAD-003 are CV-heavy alignment
   problems with modest payoff, and ROAD-003 partly duplicates the shipped
   --no-roads feature. HEIGHT-001 is interesting but gated on unreliable LLM
   shadow measurement; run a small spike before committing. GATEWAY-001 is cheap
   but low-value given the GPLv2 content constraint; keep it reference-only.

### Structural Dependencies

- ALIGN-001 and ROAD-003 should be evaluated together, since both need the same
  computer-vision alignment machinery. Build it once if either is pursued.
- ASSET-001 depends on the WED-001 LibraryMgr port to handle asset types beyond
  facades and forests, so sequence WED-001 before ASSET-001.

---

## Backlog Items

### ORTHO-001 — Orthophoto ground texture generation

**Status**: Implemented  
**Priority**: Complete  
**Source**: Analysis of Xometry KCRW commercial scenery pack

**Implemented**:
- `ortho.py` module with Sentinel-2 and NAIP sources
- `--ortho-source sentinel2|naip` CLI flag
- `fetch_ortho` pipeline stage (resumable, tile-based)
- PNG tiles resized to power-of-2 dimensions (LANCZOS downscale)
- `.pol` files with correct X-Plane format (TEXTURE_NOWRAP, SCALE, LAYER_GROUP TERRAIN 1)
- DSF integration: draped polygons placed with UV-mapped corners
- Edge slivers (<256px) automatically skipped
- NAIP uses requester-pays S3 access; Sentinel-2 uses anonymous

**Remaining improvements**:
- DDS compression for faster loading (currently PNG)
- Tile seam blending at boundaries
- Cloud-free compositing for Sentinel-2 source

---

### GEO-001 — Place name geocoding

**Status**: Implemented (3892b74)  
**Priority**: Complete  
**Source**: Usability — specifying lat/lon bboxes manually is tedious

#### Problem

Users must look up and type exact lat/lon bounding boxes for every area they
want to generate scenery for. This is error-prone and unfriendly.

#### Solution

Added `--placename` CLI flag (mutually exclusive with `--bbox`). Geocodes the
place name via Nominatim API and uses the returned bounding box. Example:
`--placename "Pocahontas County, WV"` → `38.0365,-80.3648,38.7398,-79.6179`.

---

### PERF-001 — Tiled NDVI processing to prevent OOM

**Status**: Implemented (839c54d, b69bf59)  
**Priority**: Complete  
**Source**: Laptop crash when annotating county-sized bboxes

#### Problem

The annotate stage loaded the entire Sentinel-2 NDVI raster for the full bbox
into memory. For large areas (e.g. Pocahontas County, ~0.7° × 0.75°), this
consumed 4+ GB and caused OOM kills. Additionally, the SCL cloud mask band
(20m resolution) was read using the 10m red band's window, causing out-of-bounds
errors.

#### Solution

Split NDVI processing into 0.15° tiles (~50 MB peak memory per tile). Replaced
per-polygon `rasterio.mask.mask` with direct `geometry_mask` on the numpy array
(no MemoryFile copies). Fixed SCL band to compute its own window from its own
dataset transform before resampling to match the 10m grid.

---

### PERF-002 — Parallel orthophoto fetch and Bedrock classification

**Status**: Implemented (a61c781, 2fb283c)  
**Priority**: Complete  
**Source**: Hours-long classify and fetch_ortho stages for large areas

#### Problem

Both the ortho fetch (downloading tiles from S3) and the classify stage
(calling Bedrock per-feature) ran sequentially. For Pocahontas County with
~1,300 ortho tiles and ~23k classifiable features, this took hours.

#### Solution

Added `--workers N` CLI flag (default 5). Both `fetch_ortho_tiles` and
`_stage_classify` now use `ThreadPoolExecutor` for concurrent execution.
GeoJSON writes and the review queue are protected with threading locks for
crash safety. Classify stage saves progress every 10 items; LLM cache ensures
no re-calls on resume after interruption.

---

### FACADE-001 — Physical-attribute-based facade selection

**Status**: Implemented (8bf6847, 20f4021, 66c2b0e)  
**Priority**: Complete  
**Source**: Poor facade quality from functional-type-only selection

#### Problem

Facade selection was based on building function (residential/commercial/etc)
and footprint size. A "school" or "synagogue" could look like anything — the
functional type tells you nothing about the building's visual appearance. This
produced mismatched facades.

#### Solution

1. Created `scripts/analyze_facades.py` that sends all 1,403 X-Plane facade
   textures (17 unique atlases) to Bedrock Haiku for visual classification
2. Generated `assets/facade_attributes.yaml` with per-facade physical
   attributes: wall_material, wall_color, window_shape, window_density,
   stories_min/max, roof_type, roof_color, style
3. Rewrote the classifier's building tool to output only visual attributes
   (stories, wall_material, wall_color, window_density, roof_type)
4. Rewrote `catalog.py` to score all facades against the building's observed
   attributes and pick the best match (weighted: stories 3, material 2,
   window_density 1.5, wall_color 1, roof_type 0.5)
5. Falls back to size-based default in `--auto` mode (no LLM)

---

### SUBSET-001 — Extract smaller scenery from existing output

**Status**: Implemented (d0b75c1)  
**Priority**: Complete  
**Source**: Usability — large county runs produce huge scenery packs

#### Problem

After generating scenery for a large area (e.g. an entire county), users may
want to extract just a portion for testing or distribution without re-running
the full pipeline.

#### Solution

Added `xplane-gen subset` command. Takes an existing scenery output folder,
a bbox or placename, and an output folder. Extracts the subset of features
and ortho tiles that fall within the specified area.

---

### ROAD-002 — Suppress default road network in ortho-covered areas

**Status**: Implemented (b1bd078, 356a26d)  
**Priority**: Complete  
**Source**: Visual conflict between rendered roads and ortho imagery roads

#### Problem

X-Plane renders its default road network on top of our orthophoto tiles. The
default roads don't align with the actual roads visible in the aerial imagery,
creating a confusing criss-cross pattern.

#### Solution

Added `--no-roads` CLI flag. When set and ortho tiles are present, emits
`sim/exclude_net west/south/east/north` in the DSF to suppress X-Plane's
default road rendering. Also skips road classification in the classify stage
to avoid wasting Bedrock calls on roads that won't be rendered.

#### Tradeoffs

- Roads in ortho areas won't have 3D traffic or physics surfaces
- Acceptable for visual scenery overlays

---

### ROAD-003 — Align OSM road vectors to orthophoto imagery

**Status**: Proposed  
**Priority**: Medium  
**Source**: Visual conflict between rendered roads and ortho imagery roads

#### Problem

OSM road vectors and satellite/aerial imagery often have 2-5m systematic
offsets that vary by region. When both are rendered, roads appear doubled
or misaligned.

#### Approach

1. **Detect offset**: Use image correlation or feature matching between
   OSM road centrelines and road pixels in the ortho imagery
2. **Compute affine transform**: Find the translation (and optionally
   rotation/scale) that best aligns OSM roads to the imagery
3. **Apply correction**: Shift road geometries before DSF compilation
4. **Render aligned roads**: Place corrected road network on top of ortho

#### CLI flag

`--align-roads` — enable road vector alignment to ortho imagery

#### Dependencies

- Orthophoto tiles (ORTHO-001) — implemented
- Road classification (ROAD-001)
- Image processing for road detection (OpenCV or similar)

#### Complexity

High — requires computer vision for road pixel detection and robust
geometric alignment. May need manual calibration points as fallback.

---

### ROAD-001 — Road classification granularity

**Status**: Proposed  
**Priority**: Medium  
**Source**: HITL review session — Green Bank tile

#### Problem

The road classifier defaults to "asphalt, 2 lanes" for most roads. In rural
areas like Green Bank WV, many roads are narrow 1-lane paved or gravel roads.
The review UI only allows changing surface type, not lane count.

#### Improvements needed

1. **Better prompt context**: Include OSM `highway` class in the prompt with
   rural road heuristics (e.g. `highway=residential` + rural area → likely
   1 lane, possibly gravel)
2. **Review UI**: Allow editing lane count during HITL review, not just surface
3. **Width classification**: Add a `width` field (narrow/standard/wide) that
   maps more directly to X-Plane road rendering widths
4. **Road network rendering**: Actually place roads in the DSF using `.net`
   definitions with correct widths based on classification

---

### ALIGN-001 — Building footprints offset from orthophoto imagery

**Status**: Proposed  
**Priority**: Medium  
**Source**: Visual inspection of Green Bank tile with --no-roads

#### Problem

OSM building footprints are offset from the actual buildings visible in the
orthophoto imagery by several meters in some places. This is a known issue
with OSM data — coordinates are traced from different imagery sources with
varying georeferencing accuracy.

#### Possible approaches

1. **Global affine correction**: Compute a single translation offset for the
   tile by correlating OSM building centroids with detected building pixels
   in the ortho imagery (similar to ROAD-003 approach)
2. **Per-building snap**: For each building footprint, search a small radius
   in the ortho for the best-matching building outline and shift to align
3. **Accept and document**: The offset is small (2-5m) and may not justify
   the implementation complexity

#### Dependencies

- Orthophoto tiles (ORTHO-001) — implemented
- Image processing for building detection (OpenCV or LLM vision)

---

### HEIGHT-001 — Shadow-based building height estimation

**Status**: Proposed  
**Priority**: Medium  
**Source**: Observation during Green Bank NAIP ortho review

#### Concept

NAIP aerial imagery contains building shadows. Combined with sun position
metadata (date/time from STAC + lat/lon), shadow length can be converted to
building height geometrically:

```
height = shadow_length_m × tan(sun_elevation_angle)
```

#### Approach

1. **Extract sun angle**: Compute solar elevation from NAIP scene `datetime`
   metadata + tile centre lat/lon (use `pvlib` or simple solar geometry)
2. **Calibrate with known heights**: Use OSM `height` tags (e.g. GBT = 178m)
   as ground truth to compute a calibration factor for the image
3. **LLM shadow measurement**: Send building patch + shadow to Bedrock with
   prompt: "Measure the shadow length in pixels for this building. The image
   resolution is 1m/pixel. Sun elevation is X degrees."
4. **Compute height**: `height = shadow_pixels × 1m × tan(sun_elevation)`
5. **Write to GeoJSON**: Store as `xplane_height_m` property

#### Benefits over current approach

Current: OSM `height` tag (rare) → `building:levels × 3.5` (uncommon) → type
heuristic (8m default). Most Green Bank buildings get 8m.

Shadow-based: actual measured height per building from imagery.

#### Dependencies

- NAIP ortho tiles (ORTHO-001) implemented
- Solar geometry calculation (new, ~20 lines)
- LLM prompt for shadow measurement (extend classifier)

---

### CLASSIFY-001 — Reduce LLM escalation rate

**Status**: Proposed  
**Priority**: High  
**Source**: Green Bank classification run — 76/556 items queued for review

#### Problem

The tiered routing (Haiku → Sonnet → Opus) escalates too aggressively:
- ~60% of buildings escalate past Haiku
- ~40% reach Opus
- Opus always returns 94 tokens (likely hitting AccessDenied fallback)
- Most escalations are for `building=yes` with no distinguishing OSM tags

#### Root causes

1. **Confidence thresholds too high**: 0.85 for Haiku is aggressive for
   ambiguous rural buildings where even humans would be uncertain
2. **Prompt lacks context**: Only passes `building=yes` — no footprint area,
   no surrounding land use, no road proximity
3. **Opus fallback masking**: AccessDenied returns the fallback dict with
   confidence 0.0, which always queues for review

#### Proposed fixes

1. Lower thresholds: Haiku ≥0.70, Sonnet ≥0.50
2. Enrich prompt with: footprint area m², nearest road type, surrounding
   ESA land cover class, building density in neighbourhood
3. Skip Opus tier entirely if AccessDenied (use Sonnet result as final)
4. For `building=yes` in rural areas with area <200m², default to
   "residential" without LLM call

---

### RENDER-001 — Missing buildings investigation

**Status**: Proposed  
**Priority**: High  
**Source**: Green Bank test — "many (not all) buildings appearing"

#### Problem

Some buildings in the DSF don't render in X-Plane despite being present in
the compiled file. The DSF loads without errors and shows facades for most
buildings but not all.

#### Possible causes

1. **Polygon winding**: some buildings may have CW winding despite `_ensure_ccw`
   (edge case with self-intersecting or degenerate polygons)
2. **Zero-area polygons**: very small buildings may collapse to zero area after
   coordinate quantization in DSFTool
3. **Facade compatibility**: some facade `.fac` files may not support the
   height range we're requesting
4. **Object density**: despite `sim/require_facade 1/0`, some may still be
   culled

#### Investigation steps

- Decompile DSF and count facade polygons vs buildings in GeoJSON
- Check which specific buildings are missing (compare in-sim vs OSM)
- Test with a single known-good facade type for all buildings

---

### ASSET-001 — Expanded asset placement (FR-8 through FR-18)

**Status**: Proposed  
**Priority**: Low (Phase 2)  
**Source**: X-Plane 12 asset inventory analysis (20,539 paths)

#### Features documented in REQUIREMENTS.md §12

- Species-specific forests (oak, maple, pine → individual `.for`)
- Fencing and barriers (47 types from OSM `barrier=*`)
- Industrial area clutter (containers, tanks, goods)
- Street furniture (streetlights, benches, bins)
- Parked vehicles in parking lots
- Sports facilities
- Solar installations
- Communication towers
- Ground cover polygons (asphalt, sidewalks)
- Walkways and paths
- Ships in harbors

#### Prerequisite

Requires the classify stage to support additional tool specs beyond
the current three (building, forest, road).

---

### DDS-001 — DDS texture compression for ortho tiles

**Status**: Proposed  
**Priority**: Low  
**Source**: ORTHO-001 remaining improvements

#### Problem

PNG ortho tiles are 8-24 MB each (18 tiles = ~250 MB). DDS DXT1 compression
would reduce this to ~2-5 MB per tile with minimal quality loss, and X-Plane
loads DDS faster than PNG.

#### Options

1. ImageMagick: `convert input.png -define dds:compression=dxt1 output.dds`
2. `crunch` (Binomial): best quality, requires building from source
3. Python `Pillow` DDS plugin: limited compression support

#### Implementation

Add `--dds` flag to `generate` command. After PNG tiles are written, convert
to DDS and update `.pol` references. Keep PNG as default for simplicity.

---

### RENDER-002 — Headless scenery rendering to raster for LLM analysis

**Status**: Proposed  
**Priority**: Medium (research spike)  
**Source**: Idea — enable automated visual QA without launching X-Plane 12

#### Concept

Render a generated scenery pack from one or more viewpoints to a raster image
(PNG) programmatically, without running X-Plane 12. X-Plane is slow to load,
requires manual camera positioning, and cannot run unattended. An offline
renderer would let us screenshot scenery for LLM visual analysis inside an
automated pipeline.

#### What has to be rendered

A pack is a DSF overlay that references X-Plane library assets by virtual path:
- Facades (`.fac`) — procedural wall geometry extruded along building footprint rings
- Forests (`.for`) — scattered tree billboards at a density value
- Draped polygons (`.pol`) — orthophoto textures draped on the terrain mesh
- The overlay carries no base terrain mesh; a DEM is needed to drape ortho and seat buildings

#### Approach options

1. **Approximate renderer (recommended first step)**: Resolve library virtual
   paths to asset files via `library.txt`, then render a simplified scene —
   extruded boxes with facade wall textures, tree billboards for forests, and
   ortho draped on a flat or DEM-derived surface. Use an offline engine
   (Blender `bpy` headless, `pyrender`/`trimesh`, `moderngl`, or PyVista/VTK).
   Fidelity is coarse but likely sufficient for LLM comparison.
2. **Asset-accurate renderer**: Load actual `.obj` geometry and reproduce
   X-Plane's procedural `.fac`/`.for` generation. Much higher effort; the
   facade and forest engines are non-trivial to replicate.
3. **Reuse existing tooling**: Community X-Plane OBJ importers (e.g.
   XPlane2Blender) handle `.obj`, but not the procedural `.fac`/`.for` assets
   that dominate our output.

#### Difficulty assessment

- Approximate approach: moderate. The hard parts are procedural facade
  extrusion and obtaining a base DEM to drape ortho.
- Asset-accurate approach: high in principle, but **substantially de-risked** by
  the WED source (see WED-001, explored 2026-07-05). X-Plane's own asset code is
  available under MIT: `Obj/XObjReadWrite.cpp` (GL-free OBJ8 parser),
  `Obj/ObjDraw.cpp` (callback-based traversal — supply callbacks that emit
  triangles instead of drawing GL), `WEDEntities/WED_FacadePreview.cpp`
  (procedural facade → mesh), and `XPTools/ViewObj.cpp` (headless-render
  template). The remaining work is porting this logic to Python and retargeting
  the draw step to an offscreen renderer (pyrender/moderngl), plus a DEM source.

#### Dependencies

- DSF text form via DSFTool `dsf2text` (available)
- Library path resolution via `library.txt` (implemented in `catalog.py`)
- A DEM source for terrain (new; could reuse existing raster data plumbing)

#### Open questions

- Which engine gives the best headless throughput for an unattended loop?
- Is billboard/box fidelity enough for the LLM to judge correctness, or is real geometry needed?
- How should viewpoints be defined (ground-level, oblique aerial, orthographic top-down)?

#### Enables

- REFINE-001 (closed-loop scenery refinement)

---

### REFINE-001 — Closed-loop scenery refinement via render-and-compare

**Status**: Proposed  
**Priority**: Medium (research; depends on RENDER-002)  
**Source**: Idea — autonomous generate/render/compare/adjust loop

#### Concept

Build an unattended feedback loop that improves scenery by comparing a rendered
version against ground truth and iterating:

1. Generate scenery from current assumptions
2. Render it to a raster from chosen viewpoint(s) (RENDER-002)
3. Have an LLM compare the render against ground truth — descriptive text,
   engineering data, or a real photo of the object or area
4. LLM emits a set of concrete adjustments (facade choice, height, forest
   density, ortho source, placement offset, land-cover mapping, etc.)
5. Apply adjustments, regenerate, and repeat until the comparison converges or
   a stop condition is met

Applies to both landscape (land cover, forests, ortho) and individual objects
(e.g. a specific landmark such as the Green Bank Telescope).

#### Why it is interesting

Removes the human from the visual-QA loop and lets the system self-correct
toward a target it can see, rather than toward assumptions it cannot verify.

#### Design considerations

- **Action space**: define the discrete set of adjustments the LLM may request,
  each mapped to a concrete pipeline input (catalog overrides, per-feature
  attribute overrides, height, density, ortho source, alignment offsets). The
  loop can only fix what the action space exposes.
- **Ground truth ingestion**: support text specs, engineering data, and photos;
  normalize viewpoint between render and reference photo (camera pose, focal
  length, sun angle).
- **Convergence and stopping**: score each iteration; stop on score threshold,
  diminishing returns, or max iterations. Guard against oscillation.
- **Cost control**: each iteration is a full generate + render + LLM cycle;
  cache aggressively and scope iterations to changed features.
- **Scope granularity**: per-object loop (single building) vs per-tile loop
  (whole landscape). Start with a single object for tractability.

#### Dependencies

- RENDER-002 (headless rendering) — prerequisite
- Per-feature attribute override mechanism (partly exists via GeoJSON
  `xplane_*` properties and the review queue)
- A scoring/comparison prompt and a structured adjustment schema (new)

#### Complexity

High — the most ambitious item in the backlog. Recommend starting with a
single-object proof of concept (one building, one reference photo, a small
fixed action space) before generalizing to landscapes.

---

### GATEWAY-001 — Explore X-Plane Scenery Gateway API as a data source

**Status**: Proposed  
**Priority**: Low (research spike)  
**Source**: Idea — evaluate gateway.x-plane.com as an input source

#### Concept

The X-Plane Scenery Gateway (`gateway.x-plane.com`) is Laminar's repository of
community-contributed airport scenery, authored in WorldEditor (WED) and
shipped with the sim. It exposes a public API at `gateway.x-plane.com/api`.
Investigate whether that API can serve as a data source for this pipeline.

#### Potential uses

- Airport layout and boundary data to inform tile selection or masking
- Cross-reference generated overlay scenery against existing Gateway airports
  to avoid conflicts near airfields
- Study how Gateway airports use the Laminar default library (they are
  constrained to it) as a reference for our own asset selection

#### Context

- Gateway scenery is airport-focused and built in WED; this project produces
  DSF overlay packs for arbitrary areas, so the artifact types differ
- The redistributability constraint that governs the Gateway (default library
  only) is already the rationale behind this project's Phase 1 asset strategy
  (see `REQUIREMENTS.md` §4.2)

#### Approach

1. Read the API documentation at `gateway.x-plane.com/api`
2. Enumerate available endpoints and data (airports, scenery packs, metadata)
3. Prototype a fetch of one airport's data and assess format and usefulness
4. Decide whether it warrants a dedicated data-source module

#### API surface (from the docs, `/apiv1/`)

- `GET /apiv1/airports` — all ~37,000 airports (code, name, lat/lon, elevation, counts)
- `GET /apiv1/airport/{code}` — one airport plus its scenery pack list/metadata
- `GET /apiv1/scenery/{id}` — a scenery pack: metadata + base64-encoded ZIP blob
- `GET /apiv1/metadata`, `/apiv1/stats`, `/apiv1/releases`, `/apiv1/release/{version}`
- `PUT /apiv1/scenery` — upload (auth required; discouraged in favor of WED uploader)
- Usage etiquette: no rate metering, but the docs ask callers to avoid
  unnecessary bulk requests
- **Reference implementation**: `WEDImportExport/WED_GatewayImport.cpp` and
  `WED_GatewayExport.cpp` in the local xptools checkout show the exact API usage
  (libcurl + JSON, base64 ZIP handling, auth). MIT-licensed; usable as a guide.

#### Data license — CONFIRMED GPLv2 (verified 2026-07-05)

**Gateway scenery packs are licensed under the GNU General Public License
version 2 (GPLv2).** Verified by downloading a pack via `GET /apiv1/scenery/1753`
(KBOS), decoding the base64 ZIP, and reading the bundled `LICENSING.txt`, which
is the full GPLv2 text. This matches the X-Plane forum consensus (thread 323867).

**Implications for this project (not legal advice — confirm before distributing):**
- GPLv2 is strong copyleft. A distributed work "based on the Program" (a
  derivative) must itself be GPLv2, with corresponding source made available.
- **Low risk — factual/reference use**: reading airport coordinates, elevations,
  or presence from the API to inform tile selection or masking. Facts are not
  copyrightable; GPLv2 §0 notes program *output* is covered only if it is itself
  a work based on the Program.
- **High risk — content incorporation**: bundling Gateway scenery *content*
  (DSF geometry, objects, apt.dat from a pack) into this project's generated
  output would make that output a derivative, forcing GPLv2 copyleft (and source
  disclosure) onto the packs we distribute.
- Distinct from the **MIT/X11** license of the xptools/WED *source code*
  (see WED-001) — that is permissive; Gateway scenery *content* is copyleft.

**Recommendation**: treat the Gateway as a factual reference source (airport
locations/metadata), not a source of scenery content to embed, unless the
project is prepared to release generated packs under GPLv2.

#### Open questions

- Does the API provide anything not already available from OSM? Gateway data is
  airport-focused (layouts, apt.dat, 3D packs); overlap with OSM is partial.
- Confirm this project's own output/redistribution license model before any
  content-level (non-factual) use of Gateway data.

#### Complexity

Low to moderate for the research spike; unknown for any resulting feature.
The GPLv2 copyleft constraint, not availability, is the gating factor.

---

### WED-001 — Explore reusing or building on the WorldEditor (WED) codebase

**Status**: Proposed  
**Priority**: Low (research spike)  
**Source**: Idea — evaluate WED source for reuse

#### Concept

WorldEditor (WED) is X-Plane's official scenery editor. Its C++ source lives in
the same `xptools` repository as DSFTool, already checked out locally at
`/Users/martin/src/xptools/src/` (modules `WEDCore`, `WEDEntities`, `WEDMap`,
`WEDImportExport`, `WEDLibrary`, `WEDResources`, etc.). Investigate whether any
of it can be reused or built upon for this project.

#### Findings (explored 2026-07-05)

Concrete file map and comparison against our code:

- **Library resolution — `WEDCore/WED_LibraryMgr.{cpp,h}`** (the real engine;
  `WEDLibrary/` is only GUI panes). Resolves all resource types
  (obj/fac/for/pol/lin/str/agp/road), handles every `EXPORT_*` directive
  variant, tracks resource **status** (public/deprecated/private — deprecated
  and private fail Gateway validation), handles **variants** (one vpath with
  multiple EXPORTs → randomized appearance), seasonal/regional, and
  default-vs-third-party origin. Our `catalog.py._parse_library_exports` only
  captures `.for`/`.fac` from plain `EXPORT` lines and ignores status,
  variants, other directives, and other asset types.
- **OBJ8 geometry — `Obj/XObjReadWrite.cpp`** parses `.obj` into an `XObj8`
  model. GL-free, directly portable to Python.
- **OBJ8 drawing — `Obj/ObjDraw.cpp`** walks an `XObj8` via a callback struct
  (`ObjDrawFuncs10_t`). WED supplies OpenGL callbacks, but a caller can supply
  its own callbacks to capture triangles instead of drawing — no hard GL
  dependency in the traversal itself.
- **Procedural facades — `WEDEntities/WED_FacadePreview.cpp`** turns a `.fac`
  definition + footprint into mesh geometry. This is the "hard part" flagged in
  RENDER-002, and it already exists.
- **Asset preview pipeline — `WEDMap/WED_PreviewLayer.cpp`** wires it all
  together: `draw_obj`, `draw_agp`, `draw_facade`, line/string previews, and
  draped-polygon (ortho) rendering.
- **Standalone viewer — `XPTools/ViewObj.cpp`** renders an OBJ outside the
  editor: a template for a headless renderer.
- **DSF I/O — `DSF/DSFLib.cpp` + `DSFLibWrite.cpp`** are the actual read/write
  library that DSFTool wraps. We already use it indirectly by shelling out.
- **Gateway — `WEDImportExport/WED_Gateway{Export,Import}.cpp`** are a working
  reference for the Gateway API (libcurl + JSON, base64 ZIP, README/LICENSING
  generation, auth). Informs GATEWAY-001.
- **Ortho — `WEDImportExport/WED_OrthoExport.cpp`** does georeferenced ortho
  export using geotiff/proj; a reference for `ortho.py` `.pol` correctness.

#### Per-area recommendations

- **Port to Python (high value)**: `WED_LibraryMgr`'s parsing + status model to
  replace/extend `catalog.py`'s parser. Needed for ASSET-001 (more asset types)
  and to keep output redistributable/Gateway-valid (never emit deprecated or
  private assets). MIT/X11 permits direct porting.
- **RENDER-002 de-risker**: reuse `XObjReadWrite` (port the parser), the
  `ObjDraw` callback pattern (supply callbacks that emit triangles to
  pyrender/moderngl instead of GL), and `WED_FacadePreview` (port the
  procedural facade logic). This shifts RENDER-002 from "reimplement X-Plane's
  procedural engines" to "port existing MIT logic and retarget the draw step".
- **GATEWAY-001 reference**: `WED_GatewayImport` for our read-only use.
- **DSF I/O**: keep shelling out to DSFTool; linking `DSFLib` only helps if we
  need in-process DSF read/write, which we currently do not.

#### Spike: OBJ8 parser port (completed 2026-07-05)

Validated the "port to Python" approach by porting WED's OBJ8 read grammar
(`Obj/XObjReadWrite.cpp`) to `spikes/obj8_parser.py` (~140 lines, geometry only).

- **Result**: 296/300 randomly sampled default-library `.obj` files parsed, with
  vertex counts and TRIS index sums matching an independent text cross-check
  (0 mismatches). The 4 "failures" are legacy **OBJ7 (version 700)** files, which
  the parser correctly rejects — WED's `XObj8Read` likewise only accepts 800.
- **Grammar ported**: header (`I`/`A`, `800`, `OBJ`), `POINT_COUNTS`, `VT`
  (8 floats), `IDX`/`IDX10`, `TRIS`/`LINES`/`LIGHTS` (offset+count into the index
  list), `TEXTURE*`, and `ATTR_LOD near far` (LOD buckets). Verified on a draped
  terrain obj (4v/6i/2 tris) and an autogen building (49v/87i/29 tris, IDX10).
- **Gotcha found**: `ATTR_LOD_draped` takes a single distance argument and is a
  draped-render attribute, not a geometry LOD bucket like `ATTR_LOD near far`.
- **Conclusion**: porting is straightforward and low-risk — the OBJ8 format is
  simple and GL-free, confirming the RENDER-002 plan. Remaining work for a full
  renderer is the draw step (retarget to pyrender/moderngl) and procedural
  facades (`WED_FacadePreview`), not OBJ parsing. A production port should also
  add a legacy OBJ7 path or explicitly skip v700 assets.

#### Reuse options

1. **Reference only**: study WED's algorithms (library resolution, DSF I/O,
   facade handling) and reimplement the needed parts in Python. Lowest risk.
2. **Port specific modules**: translate a focused module (e.g. library
   resolution) to Python for exact fidelity with X-Plane behavior.
3. **Link/bridge C++**: build a small C++ tool or a `pybind11` binding against
   selected WED/xptools libraries. Highest integration cost.

#### Constraints and open questions

- **Language mismatch**: WED is C++; this project is Python. Any direct reuse
  needs a bridge (subprocess tool or bindings) or a port.
- **License**: confirmed permissive. Per the xptools repo README, code original
  to Laminar Research under `src/` is licensed **MIT/X11**, which allows reuse,
  porting, and linking with attribution. (README caveat: a file with no
  copyright or double/conflicting copyright is likely a clerical error and
  should be reported to Laminar.)
- **Build system**: xptools has its own build tooling; assess effort to build
  the relevant libraries in isolation.

#### Complexity

Moderate, and lower than initially assumed. The library-resolution port is
self-contained (parsing + a status/variant model, no GUI). The RENDER-002 reuse
is the larger effort but is de-risked because the parsing and procedural-facade
logic already exist as MIT code and the draw step is callback-based (retargetable
away from OpenGL). Recommended path: **port** the specific modules we need
(option 2) rather than link C++ (option 3) — the useful logic is
GUI-independent, and porting keeps the project pure-Python.

#### Related

- RENDER-002 (headless rendering) — `Obj/ObjDraw` callbacks, `XObjReadWrite`,
  and `WED_FacadePreview` are the reusable core; `XPTools/ViewObj.cpp` is a
  headless-render template
- GATEWAY-001 — `WED_GatewayImport` is the reference for reading Gateway data
- ASSET-001 (expanded asset placement) — `WED_LibraryMgr` port enables handling
  obj/pol/lin/str/agp asset types beyond the current facade/forest
- `catalog.py` library resolution — `WED_LibraryMgr` is the reference/port source
