# Session Knowledge — xplane-scenery-builder

## Project Summary

Automated X-Plane 12 overlay scenery pack generator. Takes a lat/lon bbox, fetches geospatial data (OSM, ESA WorldCover, Sentinel-2, NAIP), classifies features via Bedrock LLM, and compiles a DSF overlay with buildings, forests, and orthophoto ground textures.

## Key Technical Learnings

### DSFTool 2.4.0 Quirks
- `BEGIN_POLYGON` params MUST be integers (`%d` in sscanf). Floats silently fail.
- Forest density: 0-255 integer (not 0.0-1.0 float)
- Facade height: integer meters
- Draped orthophoto polygons: param=65535, depth=4 (lon,lat,s,t), polygon must be closed (repeat first vertex)
- param=65535 is the magic flag meaning "ST texture coords are in the DSF per-vertex; ignore SCALE"
- Any other param value (e.g. 1) means texture rotation in degrees — X-Plane will tile via SCALE and ignore your UVs
- DSFTool source at `/Users/martin/src/xptools/src/DSFTools/DSF2Text.cpp`

### X-Plane 12 DSF Format
- Tile path: `Earth nav data/+30-080/+38-080.dsf` (10° parent folder, 1° tile)
- `sim/overlay 1` required for overlay DSFs
- `sim/require_facade 1/0` forces facades to load at all density settings
- `sim/exclude_fac` only affects LOWER priority DSFs, not the same overlay
- Draped polygons report `0 tris` in log — that's normal (not mesh triangles)
- `.pol` files for orthophotos need: `TEXTURE_NOWRAP`, `SCALE`, `LOAD_CENTER`, `LAYER_GROUP TERRAIN 1`
- `.pol` files for orthophotos must NOT have `DECAL_LIB` (that's for repeating ground textures)
- Spec: https://developer.x-plane.com/article/draped-polygon-polfac-file-format-specification/

### X-Plane 12 Asset Library
- 20,539 virtual paths exported via `library.txt` EXPORT directives
- Bare filenames (e.g. `broadleaf.for`) DON'T work in DSFs — must use exported virtual paths
- Valid forest paths: `lib/vegetation/forests/broadleaves/*.for`, `lib/g8/shrb_*.for`
- Valid facade paths: `lib/buildings/facades/generic/*`, `commercial/*`, `industrial/*`
- `EXPORT_SEASON` variants are valid (resolved at runtime by X-Plane)
- Validate with: `uv run xplane-gen catalog validate --xplane-path "/path/to/X-Plane 12"`

### Overpass API
- Must send User-Agent header (406 without it)
- Use `urllib.request.Request` directly — `overpy` library doesn't support custom headers
- Fallback endpoints: overpass-api.de, overpass.kumi.systems, overpass.openstreetmap.ru

### S3 Data Access
- Sentinel-2, ESA WorldCover: anonymous (`AWS_NO_SIGN_REQUEST=YES` via `rasterio.Env`)
- NAIP: requester-pays (`AWS_REQUEST_PAYER=requester`) — requires valid AWS credentials

### Bedrock LLM Classification
- Model IDs must use cross-region inference profiles: `us.anthropic.claude-haiku-4-5-20251001-v1:0`
- Sonnet 4.6: `us.anthropic.claude-sonnet-4-6`
- Opus 4.6: `us.anthropic.claude-opus-4-6-v1` (4.7 requires enterprise agreement)
- Handle `AccessDeniedException` gracefully — fall back instead of crashing
- Cache key: `sha256(image_b64 + prompt)[:16]` — invalidated by any code change to prompts
- GeoJSON-level skip (`xplane_confidence` property) is more robust than LLM cache across code changes

### Ortho Tiles
- NAIP: 1m/pixel, US-only, requester-pays S3
- Textures MUST be power-of-2 dimensions (round down per axis with LANCZOS)
- Skip slivers <256px on either axis
- `.pol` texture reference is just the filename (same directory)
- DSF polygon param MUST be 65535 for orthophotos (enables per-vertex ST coords)
- UV coords: (0,0) bottom-left to (1,1) top-right, polygon closed (repeat first vertex)
- LOAD_CENTER format: `lat lon radius texture_res` — radius and texres are NOT w/h dimensions
- Use SCALE line (`w_m h_m`) + LOAD_CENTER (`clat clon`) to compute tile geographic bounds

## Current Pipeline Stages
```
fetch_osm → fetch_rasters → annotate → fetch_ortho → classify → review → write_dsf → validate
```

## Current Issues / Next Steps

### ORTHO rendering (RESOLVED)
- Root cause: polygon param must be 65535 for per-vertex ST coords, NOT 1
- param=1 means "rotate texture 1 degree" — X-Plane tiles via SCALE and ignores UV coords
- param=65535 means "read ST from DSF vertices" — X-Plane maps texture exactly as specified
- `.pol` must NOT include `DECAL_LIB` (causes blending with a library decal texture)
- Tile bounds must be computed from SCALE (w_m, h_m) + LOAD_CENTER (clat, clon), not from LOAD_CENTER radius field

### Backlog priorities
1. **ROAD-002** (High): Suppress default road network in ortho areas (`--no-roads`)
2. **ROAD-003** (Medium): Align OSM road vectors to ortho imagery (`--align-roads`)
3. **CLASSIFY-001** (High): Reduce LLM escalation rate — lower thresholds, enrich prompts
4. **RENDER-001** (High): Some buildings not rendering — investigate specific failures
5. **ROAD-001** (Medium): Road classification granularity — lane count, width
6. **HEIGHT-001** (Medium): Shadow-based building height from NAIP + sun angle
7. **DDS-001** (Low): DDS compression for ortho tiles
8. **ASSET-001** (Low): Expanded asset placement (FR-8 through FR-18)

### Workflow Notes
- `--regen` preserves fetch stages + annotate + classify + review; re-runs write_dsf + validate
- `--auto` skips LLM classification entirely (deterministic only)
- `--review-all` forces all items to human review
- Classify stage saves GeoJSON after EACH item (crash-safe)
- Classify stage skips items with existing `xplane_confidence` property

## File Locations
- X-Plane install: `/Users/martin/Library/Application Support/Steam/steamapps/common/X-Plane 12/`
- Scenery pack: `Custom Scenery/WV52 Green Bank - Sentinel/`
- DSFTool: `/Users/martin/src/xplane/tools/DSFTool`
- DSFTool source: `/Users/martin/src/xptools/src/DSFTools/`
- Test tile: `green_bank/` (bbox 38.4,-79.9,38.45,-79.8)
