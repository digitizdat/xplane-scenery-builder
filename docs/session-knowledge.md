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

### Scenery Pack Prioritization (scenery_packs.ini)
- Official guidance: https://www.x-plane.com/kb/prioritization-scenery-packs/
- File: `Custom Scenery/scenery_packs.ini`. Header is three lines: `I`, `1000 Version`, `SCENERY`, then a blank line, then `SCENERY_PACK <path>/` entries (trailing slash).
- Load order = priority: entries at the TOP are loaded first and override packs below them.
- The default global airports appear as the literal marker line `SCENERY_PACK *GLOBAL_AIRPORTS*`.
- Rule (from the KB): Global Airports must be higher priority than any base meshes but lower priority than custom airports. So the canonical order is: custom airports/overlays → `*GLOBAL_AIRPORTS*` → base meshes. Our overlay packs (buildings/forests/draped ortho) belong ABOVE `*GLOBAL_AIRPORTS*`.
- Disable a pack in place with `SCENERY_PACK_DISABLED <path>/` instead of deleting the line (reversible; documented by Laminar).
- Auto-add: X-Plane adds any pack not yet in the .ini on launch. The KB (X-Plane 10 era) says "to the top"; X-Plane 12 was observed (2026-07-23) to insert a new pack just ABOVE `*GLOBAL_AIRPORTS*`, not at the very top. A full restart is required to pick up new packs.
- Do NOT delete/rebuild scenery_packs.ini or rename default packs — the updater restores them.
- Install gotcha (observed 2026-07-23): a pack must be `Custom Scenery/<name>/Earth nav data/+NN-NNN/*.dsf`. Copying with `cp -r "Earth nav data" dest/` when `dest` does not exist makes `dest` a rename of "Earth nav data", dropping the `Earth nav data` level — X-Plane then registers the pack but loads no DSF (no error, no load line). Verify the `Earth nav data` folder level exists.

### Facade Rendering / RENDER-001
- Missing buildings in-sim were NOT lost in the pipeline: 167 buildings in GeoJSON to 167 facades in the text DSF to 167 in the compiled DSF (verified by DSFTool dsf2text round-trip). The drop happens at X-Plane render time.
- X-Plane facade builder (WED_FacadePreview.cpp): for each footprint segment it must find a wall spelling whose min_width..max_width range contains the segment length (fltrange). If no spelling fits, out_choice is empty and the facade is not drawn. Facade drops are driven by footprint edge lengths vs the .fac's supported wall widths.
- catalog._score_facade selects on visual attributes only (stories, material, window density, wall color, roof) and ignores footprint geometry, so a visually-good facade can be geometrically unspellable for short-edged buildings. Green Bank: 24/167 buildings have an edge <2 m, 57/167 have a shortest edge <4 m.
- Two geometry defects fixed (RENDER-001 2a/2b): (a) facade windings repeated the ring's first point, making a zero-length wall for ring facades; now stripped at emission via dsf._open_ring. (b) buildings_to_facades computed make_valid() but emitted the raw ring; now emits the repaired outer ring (largest polygon when a repair splits).
- Step-1 diagnostic (spikes/render001_single_facade.py): forcing all buildings onto lib/buildings/facades/generic/high_universal_01.fac (RING 1, walls 0-200 m) with ortho draped underneath renders buildings across the tile (confirmed in-sim 2026-07-23). Confirms selection/wall-width as the primary cause.
- Remaining (RENDER-001 step 3): make facade selection *spelling-aware*, not just width-aware (see next section — a min/max width gate was found insufficient). Gate on whether a facade can spell the footprint (length AND heading per WALL rule), with an all-heading universal facade as fallback.

### Facade Spelling and Wall Headings (RENDER-001)
Terms:
- Winding: the order (CW/CCW) a polygon's vertices are listed; sets which way walls face. `_ensure_ccw` forces CCW.
- Spelling: X-Plane fitting a facade's WALL pieces along each footprint edge. For every edge it needs a WALL rule matching that edge's length AND heading; if any edge matches none, spelling fails and the facade is silently not drawn.
- Spelling predicate: a yes/no function `can_spell(footprint, facade_rules)` that reimplements X-Plane's spelling to predict rendering before launching the sim.

Pre-baked min/max wall width does NOT discriminate (finding 2026-07-23): across 1391 facades, min_wall_width is 808 @0 m, 567 @1 m, 15 @2 m, 1 @3 m. So ~all facades accept short edges; a "shortest edge vs facade min width" gate excludes almost nothing and cannot explain the drops. assets/facade_widths.yaml (envelope only) is therefore insufficient on its own.

Heading is the real discriminator. WALL rules are `WALL min_len max_len [h_min h_max] [name]`. The heading is a RELATIVE heading (`rel_hdg` in WED_FacadePreview.cpp), in degrees 0-360 with wraparound (`in_heading_in_range` handles h_min>h_max through north). The facade builds its own orientation frame from the footprint's first edge (`facRot = atan2(dir.y(), dir.x())`, dir from footprint[1]->footprint[0]). It is NOT absolute compass azimuth and NOT relative to roads. It encodes per-side treatment (front/side/back): e.g. walls near 0 deg relative use a storefront texture, side walls near 90/270 use plain walls. Rotating the whole building keeps relative headings constant, so "front stays front".
- Consequence: dimension-named autogen facades (e.g. 45x30x6v0.fac) are fixed-shape templates modeled from specific rectangular buildings; their walls expect edges near 0/90/180/270 relative. Irregular OSM footprints have edges at odd relative angles that match no WALL rule -> facade drops. Universal facades use `WALL ... 0 360` (all headings) on every rule, so they spell any footprint (why forcing high_universal_01 rendered all Green Bank buildings).
- Source: WED_FacadePreview.cpp (`in_heading_in_range`, `REN_facade_wall_filter_t::is_ok`, `facRot`); WED_ResourceMgr.cpp (WALL parse, min_heading/max_heading ~lines 826-851); WED_PreviewLayer.cpp (`choices`).
- Confidence: confirmed from WED source that the heading is relative, in degrees, wrapped, with a facade-local orientation frame. NOT traced line-by-line: the exact zero-reference for each segment's rel_hdg (first edge vs another datum). Verify that computation before a spelling predicate depends on it.

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
1. ~~**ROAD-002** (High): Suppress default road network in ortho areas (`--no-roads`)~~ ✅ Done
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
- `--no-roads` suppresses default road network in ortho areas
- `--workers N` controls parallelism for ortho fetch and Bedrock classify (default: 5)
- `--placename` geocodes a place name to bbox via Nominatim
- Classify stage saves GeoJSON every 10 items (crash-safe; cache ensures no re-calls on resume)
- Classify stage skips items with existing `xplane_confidence` property
- NDVI annotation uses tiled processing (0.15° tiles) to avoid OOM on large bboxes
- Ortho fetch and Bedrock classify run in parallel via ThreadPoolExecutor

## File Locations
- X-Plane install: `/Users/martin/Library/Application Support/Steam/steamapps/common/X-Plane 12/`
- Scenery pack: `Custom Scenery/WV52 Green Bank - Sentinel/`
- DSFTool: `/Users/martin/src/xplane/tools/DSFTool`
- DSFTool source: `/Users/martin/src/xptools/src/DSFTools/`
- Test tile: `green_bank/` (bbox 38.4,-79.9,38.45,-79.8)
