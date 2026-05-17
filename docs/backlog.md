# Backlog

---

## ORTHO-001 — Orthophoto ground texture generation

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

## ROAD-001 — Improve road classification granularity

**Status**: Proposed  
**Priority**: Medium  
**Source**: HITL review session — Green Bank tile

### Problem

The road classifier defaults to "asphalt, 2 lanes" for most roads. In rural
areas like Green Bank WV, many roads are narrow 1-lane paved or gravel roads.
The review UI only allows changing surface type, not lane count.

### Improvements needed

1. **Better prompt context**: Include OSM `highway` class in the prompt with
   rural road heuristics (e.g. `highway=residential` + rural area → likely
   1 lane, possibly gravel)
2. **Review UI**: Allow editing lane count during HITL review, not just surface
3. **Width classification**: Add a `width` field (narrow/standard/wide) that
   maps more directly to X-Plane road rendering widths
4. **Road network rendering**: Actually place roads in the DSF using `.net`
   definitions with correct widths based on classification

---

## HEIGHT-001 — Shadow-based building height estimation

**Status**: Proposed  
**Priority**: Medium  
**Source**: Observation during Green Bank NAIP ortho review

### Concept

NAIP aerial imagery contains building shadows. Combined with sun position
metadata (date/time from STAC + lat/lon), shadow length can be converted to
building height geometrically:

```
height = shadow_length_m × tan(sun_elevation_angle)
```

### Approach

1. **Extract sun angle**: Compute solar elevation from NAIP scene `datetime`
   metadata + tile centre lat/lon (use `pvlib` or simple solar geometry)
2. **Calibrate with known heights**: Use OSM `height` tags (e.g. GBT = 178m)
   as ground truth to compute a calibration factor for the image
3. **LLM shadow measurement**: Send building patch + shadow to Bedrock with
   prompt: "Measure the shadow length in pixels for this building. The image
   resolution is 1m/pixel. Sun elevation is X degrees."
4. **Compute height**: `height = shadow_pixels × 1m × tan(sun_elevation)`
5. **Write to GeoJSON**: Store as `xplane_height_m` property

### Benefits over current approach

Current: OSM `height` tag (rare) → `building:levels × 3.5` (uncommon) → type
heuristic (8m default). Most Green Bank buildings get 8m.

Shadow-based: actual measured height per building from imagery.

### Dependencies

- NAIP ortho tiles (ORTHO-001) ✅ implemented
- Solar geometry calculation (new, ~20 lines)
- LLM prompt for shadow measurement (extend classifier)

---

## CLASSIFY-001 — Reduce LLM escalation rate

**Status**: Proposed  
**Priority**: High  
**Source**: Green Bank classification run — 76/556 items queued for review

### Problem

The tiered routing (Haiku → Sonnet → Opus) escalates too aggressively:
- ~60% of buildings escalate past Haiku
- ~40% reach Opus
- Opus always returns 94 tokens (likely hitting AccessDenied fallback)
- Most escalations are for `building=yes` with no distinguishing OSM tags

### Root causes

1. **Confidence thresholds too high**: 0.85 for Haiku is aggressive for
   ambiguous rural buildings where even humans would be uncertain
2. **Prompt lacks context**: Only passes `building=yes` — no footprint area,
   no surrounding land use, no road proximity
3. **Opus fallback masking**: AccessDenied returns the fallback dict with
   confidence 0.0, which always queues for review

### Proposed fixes

1. Lower thresholds: Haiku ≥0.70, Sonnet ≥0.50
2. Enrich prompt with: footprint area m², nearest road type, surrounding
   ESA land cover class, building density in neighbourhood
3. Skip Opus tier entirely if AccessDenied (use Sonnet result as final)
4. For `building=yes` in rural areas with area <200m², default to
   "residential" without LLM call

---

## RENDER-001 — Missing buildings investigation

**Status**: Proposed  
**Priority**: High  
**Source**: Green Bank test — "many (not all) buildings appearing"

### Problem

Some buildings in the DSF don't render in X-Plane despite being present in
the compiled file. The DSF loads without errors and shows facades for most
buildings but not all.

### Possible causes

1. **Polygon winding**: some buildings may have CW winding despite `_ensure_ccw`
   (edge case with self-intersecting or degenerate polygons)
2. **Zero-area polygons**: very small buildings may collapse to zero area after
   coordinate quantization in DSFTool
3. **Facade compatibility**: some facade `.fac` files may not support the
   height range we're requesting
4. **Object density**: despite `sim/require_facade 1/0`, some may still be
   culled

### Investigation steps

- Decompile DSF and count facade polygons vs buildings in GeoJSON
- Check which specific buildings are missing (compare in-sim vs OSM)
- Test with a single known-good facade type for all buildings

---

## ASSET-001 — Expanded asset placement (FR-8 through FR-18)

**Status**: Proposed  
**Priority**: Low (Phase 2)  
**Source**: X-Plane 12 asset inventory analysis (20,539 paths)

### Features documented in REQUIREMENTS.md §12

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

### Prerequisite

Requires the classify stage to support additional tool specs beyond
the current three (building, forest, road).

---

## DDS-001 — DDS texture compression for ortho tiles

**Status**: Proposed  
**Priority**: Low  
**Source**: ORTHO-001 remaining improvements

### Problem

PNG ortho tiles are 8-24 MB each (18 tiles = ~250 MB). DDS DXT1 compression
would reduce this to ~2-5 MB per tile with minimal quality loss, and X-Plane
loads DDS faster than PNG.

### Options

1. ImageMagick: `convert input.png -define dds:compression=dxt1 output.dds`
2. `crunch` (Binomial): best quality, requires building from source
3. Python `Pillow` DDS plugin: limited compression support

### Implementation

Add `--dds` flag to `generate` command. After PNG tiles are written, convert
to DDS and update `.pol` references. Keep PNG as default for simplicity.
