# X-Plane GenAI Scenery Generation — Requirements Document

**Version:** 0.1 (Draft)  
**Date:** 2026-05-13  
**Status:** Pre-implementation exploration

---

## 1. Problem Statement

X-Plane's default global scenery has correct road placement and terrain elevation but is visually inaccurate for most of the world. Buildings are generic autogen, forests are wrong species and density, road surfaces are incorrect, and agricultural/field patterns are absent. The goal is to automate the production of high-quality overlay scenery packs using freely available geospatial data and GenAI, dramatically improving visual realism without requiring manual work in WorldEditor (WED).

---

## 2. Scope

### In Scope
- Overlay DSF generation (buildings, forests, roads, land-use polygons, exclusion zones)
- Airport overlay improvements (terminal buildings, hangars, ground markings)
- Human-in-the-loop (HITL) review workflow for ambiguous classifications
- Tile-by-tile processing pipeline (1°×1° DSF tiles)
- Output compatible with X-Plane 11 and 12

### Out of Scope (Phase 1)
- Base mesh terrain replacement (requires MeshTool; separate, more complex pipeline)
- Custom 3D object creation (photogrammetry / NeRF for landmark buildings)
- Aircraft or cockpit assets
- X-Plane 10 or earlier compatibility

---

## 3. Data Sources

### 3.1 Geospatial Vector Data

| Source | Data Provided | License | Access |
|--------|--------------|---------|--------|
| **OpenStreetMap (Overpass API)** | Building footprints, road networks, land use polygons, water bodies, height tags where available | ODbL (open) | Free; ~1M req/day per server; use `overpass-api.de` or self-host |
| **OSM Planet / Geofabrik extracts** | Pre-extracted regional OSM dumps | ODbL | Free download; better for bulk tile processing than live Overpass |

OSM is the primary vector source. Building footprints, road centerlines, and land-use polygons map almost directly to X-Plane DSF overlay primitives.

### 3.2 Building Footprints & Heights

| Source | Coverage | Height Data | License | Notes |
|--------|----------|-------------|---------|-------|
| **OSM `building:height` / `building:levels` tags** | Patchy; good in Europe/Japan | Yes, where tagged | ODbL | First choice; free |
| **Microsoft GlobalMLBuildingFootprints** | 1.4B buildings globally (2014–2024, Bing/Maxar/Airbus imagery) | Partial (174M height estimates via TEMPO model) | ODbL | Best global fallback for footprints; [github.com/microsoft/GlobalMLBuildingFootprints](https://github.com/microsoft/GlobalMLBuildingFootprints) |
| **Microsoft TEMPO dataset** | Global | Yes (37.6m/px density+height) | Research | Building density and height from PlanetScope imagery; useful for height estimation where per-building data is absent |
| **3D-GloBFP** | Global (2020) | Yes | CC-BY | First global 3D building footprint dataset; R² validated |
| **Google Open Buildings** | Africa, Asia, Latin America | No | CC-BY | Fills gaps where OSM/Microsoft coverage is thin |

**Strategy:** Use OSM footprints + height tags as primary. Fall back to Microsoft GlobalMLBuildingFootprints for footprints, TEMPO for height estimation. Use a default height heuristic (residential: 6–9m, commercial: 10–20m, industrial: 8–12m) when no data is available.

### 3.3 Satellite Imagery

| Source | Resolution | Bands | Cost | Access |
|--------|-----------|-------|------|--------|
| **Copernicus Data Space / Sentinel-2 L2A** | 10m (RGB+NIR), 20m (SWIR, Red Edge) | 13 bands | Free | REST API via [dataspace.copernicus.eu](https://dataspace.copernicus.eu); Sentinel Hub Processing API; free tier available |
| **ESRI World Imagery (via WED slippy map)** | ~0.3–1m (varies by region) | RGB | Free for non-commercial | Used in WED as reference; not redistributable; suitable for HITL review display only |
| **Mapbox Satellite** | ~0.5m urban, ~1m rural | RGB | Free tier (50K tiles/mo) | Good for HITL review thumbnails |
| **USGS Earth Explorer / Landsat** | 30m | Multispectral | Free | Useful for large-area land classification; lower resolution than Sentinel-2 |
| **AWS Open Data (Sentinel-2 on S3)** | 10m | 13 bands | Free egress in-region | `s3://sentinel-cogs/` — best option for bulk processing on AWS; no API rate limits |

**Primary imagery source:** Sentinel-2 L2A via AWS Open Data (`s3://sentinel-cogs/`) for pipeline processing. ESRI/Mapbox for HITL review thumbnails only.

**Key derived products from Sentinel-2:**
- **NDVI** (NIR−Red / NIR+Red): forest density proxy (0.0–1.0 maps to X-Plane `.for` density parameter)
- **NDWI**: water body detection
- **Band ratios**: distinguish conifer (high NIR, low SWIR) vs. deciduous (seasonal variation) vs. cropland

### 3.4 Land Classification

| Source | Resolution | Classes | License | Notes |
|--------|-----------|---------|---------|-------|
| **ESA WorldCover 2021** | 10m | 11 classes (tree cover, shrubland, grassland, cropland, built-up, bare, water, wetland, mangrove, snow, moss) | CC-BY | Best free global land cover; [esa-worldcover.org](https://esa-worldcover.org) |
| **ESRI 10m Annual Land Cover (2017–2024)** | 10m | 9 classes | CC-BY | Updated annually; available via Microsoft Planetary Computer |
| **Dynamic World (Google/WRI)** | 10m | 9 classes, near-real-time | CC-BY | Per-scene classification; good for temporal analysis |

**Strategy:** ESA WorldCover as the primary land classification raster. Use Sentinel-2 NDVI to refine forest density within classified forest polygons.

### 3.5 Elevation Data

| Source | Resolution | Notes |
|--------|-----------|-------|
| **Copernicus DEM (GLO-30)** | 30m | Best free global DEM; used for MeshTool base mesh (Phase 2) |
| **SRTM v3** | 30m | Legacy; superseded by Copernicus DEM |

Elevation is out of scope for Phase 1 (overlay only) but documented here for Phase 2 base mesh work.

---

## 4. X-Plane Asset Libraries

### 4.1 Laminar Research Default Library (ships with X-Plane)

Always available; no dependency on user-installed add-ons. Key virtual paths:

**Forests (`.for` files under `lib/g8/`):**

| Virtual Path Pattern | Use Case |
|---------------------|----------|
| `lib/g8/trees_decid_cld_wet.for` | Deciduous, cold/wet (NE USA, N Europe) |
| `lib/g8/trees_decid_tmp_wet.for` | Deciduous, temperate/wet (Central Europe) |
| `lib/g8/trees_decid_vhot_dry.for` | Deciduous, very hot/dry (Mediterranean) |
| `lib/g8/trees_evgr_cld_wet.for` | Evergreen/conifer, cold/wet (Pacific NW, Scandinavia) |
| `lib/g8/trees_evgr_tmp_wet.for` | Evergreen, temperate/wet |
| `lib/g8/trees_tropical.for` | Tropical forest |
| `lib/g8/shrb_cld_dry.for` | Shrubland, cold/dry (tundra edge) |
| `lib/g8/shrb_tmp_rain.for` | Shrubland, temperate/rain |
| `lib/g8/crops_*.for` | Agricultural crops (various) |

Climate zone suffix key: `cld`=cold, `tmp`=temperate, `hot`=hot, `vhot`=very hot; `dry`=dry, `sdry`=semi-dry, `wet`=wet, `rain`=rainy.

**Facades (`.fac` files under `lib/g8/` and `lib/g10/`):**

The default library uses size-coded facade names (e.g., `60_30.fac` = 60m × 30m footprint). These are generic and not region-specific. For Phase 1, a simple size-based lookup is sufficient.

**Terrain polygons (`.pol` files):**
- `lib/g8/airport_grass.pol` — airport grass areas
- `lib/g8/asphalt.pol` — generic asphalt
- Various pavement types for airport surfaces

### 4.2 OpenSceneryX (Optional Dependency)

[opensceneryx.org](https://opensceneryx.org) — free, community-maintained library with higher-quality and more regionally specific assets.

**Pros:** Much better visual quality; region-specific facades (European, Asian, American building styles); better forest variety.  
**Cons:** Requires users to install OpenSceneryX separately; cannot be bundled in a redistributable scenery pack for the Gateway.

**Decision:** Target Laminar default library for Phase 1 (maximum compatibility, no user dependencies). Add OpenSceneryX support as an optional enhancement layer in Phase 2, with the pipeline detecting whether it's installed.

### 4.3 Library Asset Catalog

The pipeline needs a machine-readable catalog mapping:
- Building type + region + size → `.fac` virtual path
- Land cover class + climate zone → `.for` virtual path  
- Surface type → `.pol` virtual path

This catalog will be built as a JSON/YAML file maintained alongside the pipeline code, populated initially from inspection of the X-Plane default library and OpenSceneryX documentation.

---

## 5. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PIPELINE ORCHESTRATOR                        │
│  Input: lat/lon bounding box  →  Output: scenery pack folder         │
└──────────┬──────────────────────────────────────────────────────────┘
           │
     ┌─────▼──────────────────────────────────────────────────┐
     │                   DATA INGESTION LAYER                   │
     │                                                          │
     │  ┌─────────────────┐   ┌──────────────────────────────┐ │
     │  │  OSM Fetcher    │   │  Raster Fetcher              │ │
     │  │                 │   │                              │ │
     │  │ • Building      │   │ • Sentinel-2 L2A (S3)        │ │
     │  │   footprints    │   │ • ESA WorldCover             │ │
     │  │ • Road networks │   │ • Microsoft TEMPO heights    │ │
     │  │ • Land use      │   │                              │ │
     │  │ • Water bodies  │   │ Outputs: GeoTIFF rasters     │ │
     │  │                 │   │ clipped to tile bbox         │ │
     │  │ Outputs: GeoJSON│   └──────────────────────────────┘ │
     │  └─────────────────┘                                     │
     └──────────┬─────────────────────────────────────────────-┘
                │
     ┌──────────▼──────────────────────────────────────────────┐
     │               CLASSIFICATION & ENRICHMENT LAYER          │
     │                                                          │
     │  ┌──────────────────────────────────────────────────┐   │
     │  │  Deterministic Enrichment (no LLM needed)        │   │
     │  │  • NDVI → forest density (0.0–1.0)               │   │
     │  │  • ESA WorldCover class → .for/.pol type         │   │
     │  │  • OSM height tag → facade height                │   │
     │  │  • OSM road type → .net road subtype             │   │
     │  │  • Climate zone lookup (lat/lon → Köppen)        │   │
     │  └──────────────────────────────────────────────────┘   │
     │                                                          │
     │  ┌──────────────────────────────────────────────────┐   │
     │  │  LLM Vision Classification (Bedrock)             │   │
     │  │  • Building type from satellite patch + OSM tags │   │
     │  │  • Height estimation from shadow analysis        │   │
     │  │  • Forest species (conifer/deciduous/mixed)      │   │
     │  │  • Road surface (asphalt/dirt/gravel)            │   │
     │  │  • Confidence score per classification           │   │
     │  └──────────────────────────────────────────────────┘   │
     └──────────┬──────────────────────────────────────────────┘
                │
     ┌──────────▼──────────────────────────────────────────────┐
     │                  REVIEW QUEUE LAYER                      │
     │                                                          │
     │  Items below confidence threshold → review_queue.json   │
     │  Items above threshold → auto-approved                  │
     │                                                          │
     │  Review queue contains:                                  │
     │  • Satellite thumbnail crop (base64 or S3 URL)          │
     │  • Agent's best guess + confidence                      │
     │  • Human decision field (pre-filled, editable)          │
     │  • Batch grouping (similar items grouped)               │
     └──────────┬──────────────────────────────────────────────┘
                │
     ┌──────────▼──────────────────────────────────────────────┐
     │              [OPTIONAL] HUMAN REVIEW STEP               │
     │                                                          │
     │  CLI tool or simple web UI to review queue.json         │
     │  Human confirms/edits → resolved_queue.json             │
     └──────────┬──────────────────────────────────────────────┘
                │
     ┌──────────▼──────────────────────────────────────────────┐
     │                  DSF GENERATION LAYER                    │
     │                                                          │
     │  • Reads approved classifications                        │
     │  • Maps to X-Plane library virtual paths                │
     │  • Generates earth.wed.xml (WED-compatible XML)         │
     │  • Generates exclusion zones for all placed content     │
     │  • Calls DSFTool (xptools CLI) to compile binary DSF    │
     └──────────┬──────────────────────────────────────────────┘
                │
     ┌──────────▼──────────────────────────────────────────────┐
     │                  VALIDATION LAYER                        │
     │                                                          │
     │  • Polygon winding direction check                      │
     │  • No self-intersecting polygons                        │
     │  • Object count / performance budget check              │
     │  • DSF bounding box integrity                           │
     │  • Optional: WED CLI validate pass                      │
     └─────────────────────────────────────────────────────────┘
```

### 5.1 Processing Model

- **Unit of work:** One 1°×1° DSF tile
- **Parallelism:** Tiles are independent; process N tiles concurrently
- **Priority:** Tiles containing airports processed first (highest visual impact during approach/departure)
- **State:** Each tile has a state machine: `pending → ingested → classified → reviewed → generated → validated → done`

### 5.2 Output Structure

```
output/
  My_GenAI_Scenery/
    Earth nav data/
      +47-123/
        +47-122.dsf      ← compiled binary overlay
    earth.wed.xml        ← WED source (for re-editing)
    review_queue.json    ← items needing human review
    resolved_queue.json  ← human-approved decisions
    library.txt          ← if using custom assets
```

---

## 6. LLM Selection

*Last updated: May 2026. The LLM landscape has moved rapidly; this section reflects currently available models.*

### 6.1 Task Taxonomy

The pipeline has three distinct LLM use cases:

| Task | Input | Output | Key Requirements |
|------|-------|--------|-----------------|
| **Vision classification** | Satellite image patch + OSM tags | Building type, forest species, road surface + confidence | Multimodal (image+text), structured JSON output, high throughput |
| **Height estimation** | Satellite image patch + sun angle metadata | Building height in meters + confidence | Multimodal, numerical reasoning |
| **Orchestration / reasoning** | Pipeline state, error conditions, ambiguous cases | Decisions, tool calls | Strong reasoning, tool use, agentic |

### 6.2 Current Model Landscape (May 2026)

#### Anthropic Claude (available on Bedrock)

| Model | Bedrock ID | Context | Vision | Cost (in/out per MTok) | Notes |
|-------|-----------|---------|--------|----------------------|-------|
| **Claude Opus 4.7** | `anthropic.claude-opus-4-7` | 1M tokens | ✓ | $5 / $25 | Most capable; best vision (+13% over 4.6); best agentic coding; released Apr 2026 |
| **Claude Sonnet 4.6** | `anthropic.claude-sonnet-4-6` | 1M tokens | ✓ | $3 / $15 | Best speed/intelligence balance; extended thinking support |
| **Claude Haiku 4.5** | `anthropic.claude-haiku-4-5-20251001-v1:0` | 200k tokens | ✓ | $1 / $5 | Fastest; near-frontier; good for bulk pre-screening |

All three are available on Bedrock today. Opus 4.7 is the current flagship (April 2026 release).

#### Amazon Nova (native Bedrock)

| Model | Bedrock ID | Vision | Cost | Notes |
|-------|-----------|--------|------|-------|
| **Nova Pro** | `amazon.nova-pro-v1:0` | ✓ | ~$0.80 / $3.20 | Multimodal; good cost/quality for classification |
| **Nova Multimodal Embeddings** | `amazon.nova-2-multimodal-embeddings-v1:0` | ✓ | Per embedding | Text+image→vector; asset catalog search |

#### Meta Llama 4 (available on Bedrock)

| Model | Bedrock ID | Vision | Notes |
|-------|-----------|--------|-------|
| **Llama 4 Maverick 17B** | `meta.llama4-maverick-17b-instruct-v1:0` | ✓ | MoE, 1M context, 128 experts; low cost; good bulk triage |
| **Llama 4 Scout 17B** | `meta.llama4-scout-17b-instruct-v1:0` | ✓ | 10M context; most powerful in class for size |

#### Non-Bedrock: Google Gemini 3.1 Pro (Vertex AI)

**Gemini 3.1 Pro** is available in preview on Vertex AI (Feb 2026). Pricing: $2.00/$12.00 per MTok.

This is the one non-Bedrock model worth serious consideration for this project, for a specific reason: **Google has released dedicated geospatial AI foundation models** (Google Earth AI, announced April 2026) that are integrated with BigQuery and can analyze satellite imagery at scale — including building detection, change detection, and land cover classification. These are purpose-built for exactly our use case in a way that general-purpose LLMs are not.

However, this creates a Google Cloud dependency. The decision is: use Gemini 3.1 Pro + Google Earth AI for the imagery analysis pipeline (where it has a genuine domain advantage), while keeping orchestration and DSF generation on Bedrock/AWS.

**GPT-5.5** (OpenAI, released April 2026) — not justified. Strong model but no domain advantage over Claude Opus 4.7 for this task, and adds an unnecessary third-party dependency.

### 6.3 Recommended Model Assignments

```
Vision classification (building type, forest species, road surface):
  → Claude Sonnet 4.6 (Bedrock) — primary
    Good balance of vision quality and cost; 1M context for batch processing
  → Claude Haiku 4.5 (Bedrock) — high-volume pre-screening
    First pass on all items; escalate low-confidence to Sonnet 4.6

Height estimation from shadows:
  → Claude Opus 4.7 (Bedrock)
    Best spatial/visual reasoning; worth the cost for accuracy on this harder task

Orchestration / agentic pipeline control:
  → Claude Opus 4.7 (Bedrock) via Strands Agents
    Best agentic behavior; handles ambiguity and multi-step reasoning

Asset catalog semantic search:
  → Nova Multimodal Embeddings (Bedrock)
    Native; no external dependency; image+text→vector for .fac/.for matching

Bulk triage / confidence scoring:
  → Llama 4 Maverick (Bedrock)
    Cheapest multimodal option; use to assign confidence scores before routing

Satellite imagery analysis (land cover, building detection at scale):
  → Google Earth AI / Gemini 3.1 Pro (Vertex AI) — EVALUATE in Phase 2
    Purpose-built geospatial models; potential substantial advantage for raster
    analysis; introduces Google Cloud dependency; evaluate vs. deterministic
    ESA WorldCover approach before committing

Building footprint segmentation (OSM-sparse regions):
  → SAM2 on SageMaker (non-Bedrock, justified by task specificity)
    No equivalent on Bedrock; pixel-level segmentation is a distinct capability
```

### 6.4 Routing Strategy

```
For each scenery element:
  1. Run Llama 4 Maverick (cheap) → get confidence score
  2. If confidence ≥ 0.85 → auto-approve, use result
  3. If confidence 0.60–0.85 → escalate to Claude Sonnet 4.6
  4. If confidence < 0.60 → escalate to Claude Opus 4.7 OR queue for human review
```

This keeps the majority of calls on cheap models while reserving expensive models for genuinely hard cases.

### 6.5 Cost Model (Rough Estimate per 1°×1° Tile)

A typical populated 1°×1° tile: ~5,000 buildings, ~50 forest polygons, ~200 road segments = ~5,250 classification calls.

Assuming routing distributes as 70% Haiku / 20% Sonnet / 10% Opus at ~500 tokens/call:

| Model | Calls | Tokens | Cost |
|-------|-------|--------|------|
| Haiku 4.5 | 3,675 | 1.84M | ~$1.84 |
| Sonnet 4.6 | 1,050 | 0.53M | ~$1.59 |
| Opus 4.7 | 525 | 0.26M | ~$1.30 |
| **Total** | | | **~$4.73/tile** |

This is within the $5/tile target. Tiles with sparse OSM data (requiring more vision work) will cost more; rural/ocean tiles will cost far less.

---

## 7. Functional Requirements

### FR-1: Tile Processing
- The system SHALL accept a lat/lon bounding box and produce a valid X-Plane overlay DSF for each 1°×1° tile within it.
- The system SHALL process tiles independently (no cross-tile dependencies in Phase 1).

### FR-2: Data Ingestion
- The system SHALL fetch OSM building footprints, road networks, and land-use polygons via Overpass API or Geofabrik extracts.
- The system SHALL fetch Sentinel-2 L2A imagery from AWS Open Data S3 bucket for the tile area.
- The system SHALL fetch ESA WorldCover land classification for the tile area.
- The system SHALL attempt to retrieve building heights from OSM tags, then Microsoft TEMPO, then apply heuristics.

### FR-3: Classification
- The system SHALL classify each building footprint into a building type (residential, commercial, industrial, agricultural, religious, etc.).
- The system SHALL assign a confidence score (0.0–1.0) to each classification.
- The system SHALL compute NDVI from Sentinel-2 bands and use it as the forest density value.
- The system SHALL map land cover classes to X-Plane `.for` virtual paths using climate zone lookup.

### FR-4: Review Queue
- The system SHALL route all classifications with confidence < configurable threshold (default: 0.75) to a review queue.
- The review queue SHALL include a satellite thumbnail, the agent's best guess, and a human-editable decision field.
- The system SHALL group similar items in the review queue (e.g., all buildings of the same type in a block).
- The system SHALL be able to run in fully-automated mode (skip human review, use best-guess for all items).

### FR-5: DSF Generation
- The system SHALL generate a valid `earth.wed.xml` file for each tile.
- The system SHALL generate exclusion zones for all areas where custom content is placed, suppressing X-Plane's default autogen.
- The system SHALL compile the XML to binary DSF using DSFTool (xptools).
- The system SHALL respect X-Plane's object density budget (configurable max objects per tile).

### FR-6: Validation
- The system SHALL validate all polygon winding directions before DSF compilation.
- The system SHALL detect and reject self-intersecting polygons.
- The system SHALL warn if object count exceeds the performance budget threshold.

### FR-7: Library Compatibility
- Phase 1 output SHALL use only Laminar Research default library virtual paths (no external dependencies).
- Phase 2 SHALL optionally use OpenSceneryX paths when the library is detected as installed.

---

## 8. Non-Functional Requirements

- **Throughput:** Process one tile in under 10 minutes on a single machine (excluding human review time).
- **Cost:** Target under $5/tile all-in (compute + LLM API calls).
- **Reproducibility:** Given the same input data, the pipeline SHALL produce identical output (deterministic where possible; LLM calls cached by input hash).
- **Resumability:** A failed tile SHALL be retryable from the last completed stage without reprocessing earlier stages.
- **X-Plane compatibility:** Output SHALL be valid for X-Plane 11.50+ and X-Plane 12.

---

## 9. Open Questions

1. **DSFTool availability:** Confirm DSFTool CLI can be invoked headlessly on macOS/Linux without a full X-Plane install. The xptools repo is open source but build process needs verification.

2. **WED XML schema:** The `earth.wed.xml` format is not formally documented. It needs to be reverse-engineered from existing WED exports. Alternatively, write DSF directly via DSFTool's text format, bypassing WED entirely.

3. **Sentinel-2 cloud cover:** Tiles with >20% cloud cover need fallback imagery or temporal compositing. Strategy: use the least-cloudy scene within a 90-day window.

4. **OpenSceneryX licensing:** Confirm whether scenery packs using OpenSceneryX virtual paths can be distributed, or whether users must install it separately. (Current understanding: separate install required.)

5. **Performance budget per tile:** Need to empirically determine the maximum number of facade/forest/object placements before X-Plane frame rate degrades unacceptably. Likely 2,000–5,000 objects per tile at medium settings.

6. **Base mesh interaction:** Overlay DSFs sit on top of the default base mesh. The default base mesh terrain textures (grass, desert, etc.) will still show through where no `.pol` polygon covers the ground. Determine whether adding ground-cover `.pol` polygons for the entire tile is feasible or whether it requires base mesh replacement.

---

## 10. Phased Delivery Plan

### Phase 1 — Core Pipeline (MVP)
- OSM → WED XML converter for buildings and forests
- Sentinel-2 NDVI → forest density
- ESA WorldCover → land cover classification (deterministic, no LLM)
- Exclusion zone generation
- DSFTool compilation
- CLI tool: `generate-tile --bbox <lat_min,lon_min,lat_max,lon_max>`
- Target: one working tile demonstrating clear visual improvement over default scenery

### Phase 2 — LLM Enhancement
- Bedrock vision classification for building types and heights
- Confidence-based review queue
- HITL review CLI/UI
- Climate-zone-aware forest type selection
- OpenSceneryX optional support

### Phase 3 — Scale & Quality
- Parallel tile processing (SQS queue or local multiprocessing)
- Airport-priority queue
- Feedback loop: human corrections improve classifier priors
- SAM2 integration for footprint extraction in OSM-sparse regions
- Base mesh pipeline (MeshTool) exploration

---

## 11. Technology Stack (Proposed)

| Component | Technology |
|-----------|-----------|
| Language | Python 3.12+ |
| OSM data | `overpy` or `osmium` + Geofabrik extracts |
| Raster processing | `rasterio`, `numpy`, `shapely` |
| Sentinel-2 access | `boto3` (S3), `sentinelhub` SDK |
| LLM calls | `boto3` Bedrock runtime (Converse API) |
| Agentic orchestration | Strands Agents (AWS) or Bedrock Agents |
| DSF compilation | `DSFTool` CLI (xptools, open source) |
| WED XML generation | Python `xml.etree` or `lxml` |
| Review UI | Simple CLI (`rich` library) or minimal Flask app |
| Testing | `pytest` |
| Infrastructure (Phase 3) | AWS Lambda + SQS for tile queue; S3 for intermediate data |

---

## 12. Expanded Asset Placement Requirements (Phase 2+)

Based on analysis of the X-Plane 12 default library (20,539 exported virtual paths),
the following additional feature types should be classified and placed by the LLM
annotation stage. These extend the original FR-3 (Classification) requirements.

### FR-8: Species-Specific Forest Classification
- The system SHALL use LLM vision to identify dominant tree species (oak, maple, birch, pine, spruce, fir) from satellite imagery.
- The system SHALL map identified species to `lib/vegetation/trees/deciduous/*.for` or `lib/vegetation/trees/coniferous/*.for` paths.
- The system SHALL use `lib/vegetation/forests/broadleaves/*.for`, `conifers/*.for`, or `mixed/*.for` for area forests, selecting the climate-appropriate variant.
- The system SHALL fall back to generic `broadleaf.for`/`conifer.for` when confidence is below threshold.

### FR-9: Fencing and Barriers
- The system SHALL identify fences, walls, and hedges from OSM `barrier=*` tags and satellite imagery.
- The system SHALL classify fence type (wood, metal, mesh, hedge, brick wall, concrete) and map to `lib/constructions/fencing/*.fac` paths.
- The system SHALL place fences as facade polygons along property boundaries.
- Available types: wood (9), metal (8), mesh (12), hedge (6), brick (4), wall (17), industrial (2), garden (1).

### FR-10: Industrial Area Clutter
- The system SHALL identify industrial/commercial areas from OSM `landuse=industrial` or `landuse=commercial` tags.
- The system SHALL place contextually appropriate objects: storage tanks, shipping containers, goods/pallets, construction equipment.
- The system SHALL use LLM vision to determine the specific industrial activity (container yard, lumber yard, fuel depot, construction site) and select matching objects from `lib/industrial_area/`.

### FR-11: Street Furniture and Urban Detail
- The system SHALL place streetlights along roads using OSM `highway=street_lamp` nodes or by inferring from road class.
- The system SHALL place waste bins, benches, and bollards in urban areas using `lib/street/furniture/` and `lib/street/waste_management/` objects.
- The system SHALL use LLM vision to assess urban density and place appropriate quantities.

### FR-12: Parked Vehicles
- The system SHALL identify parking areas from OSM `amenity=parking` polygons.
- The system SHALL place static vehicle objects (`lib/cars/car_static.obj`, `lib/vehicles/static/trucks/`) within parking polygons.
- The system SHALL drape `lib/terrain/urban/asphalt_worn_*.pol` ground texture on parking areas.
- The system SHALL use LLM vision to estimate parking lot fullness and vehicle mix.

### FR-13: Sports and Recreation Facilities
- The system SHALL identify sports facilities from OSM `leisure=pitch` and `leisure=sports_centre` tags.
- The system SHALL place appropriate equipment objects (goals, hoops, nets) from `lib/public_area/sports/`.
- The system SHALL use LLM vision to identify sport type when OSM `sport=*` tag is absent.

### FR-14: Solar Installations
- The system SHALL identify solar farms from OSM `landuse=solar` or `power=generator` + `generator:source=solar` tags.
- The system SHALL place solar panel objects/strings from `lib/constructions/solar_plant/`.
- The system SHALL use LLM vision to estimate panel row orientation and density.

### FR-15: Communication Towers and Antennas
- The system SHALL identify antenna/tower locations from OSM `man_made=antenna`, `man_made=mast`, `tower:type=communication` tags.
- The system SHALL select appropriate antenna objects from `lib/constructions/antennas/` (33 variants).

### FR-16: Ground Cover Polygons
- The system SHALL drape ground texture polygons for identified surface types:
  - Parking lots: `lib/terrain/urban/asphalt_worn_*.pol`
  - Sidewalks: `lib/terrain/urban/sidewalk_1.pol`
- The system SHALL use LLM vision to identify paved areas not tagged in OSM.

### FR-17: Walkways and Paths
- The system SHALL place walkway line features from OSM `highway=footway`, `highway=path`, `highway=cycleway`.
- The system SHALL select surface-appropriate line type: `lib/g10/autogen/walkway/dirt.lin`, `concrete.lin`, or `asphalt.lin`.
- The system SHALL use LLM vision or OSM `surface=*` tag to determine material.

### FR-18: Ships and Watercraft (Coastal/Harbor Areas)
- The system SHALL identify harbors and marinas from OSM `leisure=marina`, `waterway=dock` tags.
- The system SHALL place appropriate vessel objects from `lib/ships/` based on harbor type (commercial → cargo ships, recreational → sailboats).

---

## 13. LLM Annotation Scope (Revised)

The LLM classify stage processes ALL feature types, not just ambiguous buildings.
For each feature, the LLM receives a satellite image patch + OSM context and returns
structured classification used to select from the full 20,539-path asset library.

### Classification Categories

| Feature Type | LLM Output | Asset Selection |
|-------------|-----------|-----------------|
| Building (ambiguous) | type, height, roof material | `.fac` path |
| Forest polygon | species mix, density | `.for` path (species-specific) |
| Road segment | surface, lanes, condition | `.net` or exclusion |
| Fence/barrier | material, height | `.fac` path |
| Industrial area | activity type | `.obj` selection |
| Parking lot | fullness, vehicle mix | `.pol` + `.obj` placement |
| Sports facility | sport type | `.obj` selection |
| Solar installation | panel orientation, density | `.obj`/`.str` placement |
| Urban area | density, character | Street furniture density |
| Waterfront | harbor type | Ship `.obj` selection |

### Cost Impact

Additional features increase per-tile LLM calls from ~567 (buildings+forests+roads only)
to ~1,500–2,000 (all feature types). At the same 70/20/10 tier distribution:
- Estimated cost: ~$1.50–2.00/tile (still well under $5 budget)
- Most new features (fences, parking, streetlights) are simple classifications resolved by Haiku
