# LLM Annotation Stage Design

## Overview

The `classify` pipeline stage sends satellite image patches + OSM context to
Bedrock for vision-based classification of all scenery features. This replaces
the narrow `classify_buildings` stage with a unified annotation pass.

## Pipeline Position

```
fetch_osm → fetch_rasters → annotate (NDVI) → fetch_ortho → classify → review → write_dsf → validate
```

The `classify` stage runs after ortho imagery is available so it can crop
real satellite patches for each feature.

## Feature Types Classified

### Buildings
- **Input**: building footprint polygon + OSM tags + satellite patch
- **Output**: building_type, height_m, roof_material, facade_style, confidence
- **Prompt context**: OSM tags (building=yes/residential/etc), footprint area, surrounding land use
- **Skip condition**: buildings with specific OSM type tags (building=residential, building=commercial, etc.) — only classify ambiguous ones (building=yes, building=roof, no building tag)

### Forests
- **Input**: forest polygon + ESA class + satellite patch
- **Output**: species_mix (deciduous/conifer/mixed), canopy_density, understory_type, confidence
- **Prompt context**: ESA WorldCover class, NDVI value, latitude (climate zone), polygon area
- **Enriches**: overrides the simple Köppen lookup with visual species identification

### Roads
- **Input**: road segment + OSM tags + satellite patch
- **Output**: surface_type (asphalt/gravel/dirt), lane_count, shoulder_width, condition, confidence
- **Prompt context**: OSM highway tag, surface tag if present, road width
- **Use case**: validates OSM classification, identifies unpaved roads misclassified as paved

### Land Transitions (future)
- **Input**: boundary between two land cover types + satellite patch
- **Output**: transition_type (abrupt/gradual), margin_vegetation
- **Deferred**: not in initial implementation

## Image Patch Extraction

For each feature, crop a satellite image patch:

1. Compute feature centroid and bounding box
2. Buffer bbox by 20% for context
3. If ortho tiles exist (`orthophoto/` dir): crop from the relevant PNG tile
4. If no ortho: crop from Sentinel-2 RGB bands (lower resolution but always available)
5. Resize patch to 256×256 px for consistent LLM input

## Tiered Routing (per requirements §6.4)

```
1. Haiku 4.5 (cheapest) → confidence ≥ 0.85 → accept
2. Sonnet 4.6 (mid-tier) → confidence ≥ 0.60 → accept
3. Opus 4.7 (best) → accept regardless, queue for review if < 0.75
```

## Tool Definitions (Bedrock Converse API)

### classify_building
```json
{
  "building_type": "residential|commercial|industrial|religious|agricultural|generic",
  "height_m": 8.0,
  "roof_material": "shingle|metal|flat|tile",
  "confidence": 0.92
}
```

### classify_forest
```json
{
  "species_mix": "deciduous|conifer|mixed",
  "canopy_density": 0.8,
  "understory": "grass|shrub|bare",
  "confidence": 0.88
}
```

### classify_road
```json
{
  "surface_type": "asphalt|gravel|dirt|concrete",
  "lane_count": 2,
  "shoulder_present": true,
  "condition": "good|fair|poor",
  "confidence": 0.75
}
```

## Cost Estimate

For the Green Bank tile (167 buildings, 144 landuse, 256 roads = 567 features):
- 70% resolved by Haiku: 397 calls × ~500 tokens × $1/MTok = $0.20
- 20% escalated to Sonnet: 113 calls × ~500 tokens × $3/MTok = $0.17
- 10% escalated to Opus: 57 calls × ~500 tokens × $5/MTok = $0.14
- **Total: ~$0.51 for this tile**

Well under the $5/tile budget.

## GeoJSON Enrichment

The stage writes classification results back into the source GeoJSON files
as additional properties:

```json
{
  "type": "Feature",
  "properties": {
    "building": "yes",
    "xplane_type": "residential",
    "xplane_height_m": 7.5,
    "xplane_confidence": 0.91,
    "xplane_model": "haiku-4.5"
  }
}
```

The `write_dsf` stage reads `xplane_type` (if present) in preference to the
raw OSM `building` tag.

## Skip Conditions

- `--auto` flag: skip entire stage, use deterministic classification only
- No satellite imagery available: skip, fall back to OSM tags + heuristics
- Feature already has `xplane_confidence` property ≥ 0.85: skip (cached from previous run)

## Implementation Plan

1. Refactor `BedrockClassifier` to support multiple tool specs (building, forest, road)
2. Add `_crop_patch()` function to extract image patches from ortho/Sentinel-2
3. Replace `_stage_classify_buildings` with unified `_stage_classify` that iterates all feature types
4. Update `write_dsf` / `buildings_to_facades` to read `xplane_type` properties
5. Add forest species → .for path mapping that uses LLM output instead of Köppen lookup
