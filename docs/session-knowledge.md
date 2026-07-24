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

### Facade Rendering / RENDER-001 (RESOLVED 2026-07-23)
Root cause: the duplicate closing vertex. Facade windings repeated the ring's first point as the last; for ring facades X-Plane treats every ring point as a wall start, so the duplicate became a zero-length wall that broke spelling on essentially every building — a uniform failure that presented in-sim as "many but not all" buildings rendering. Fixed by stripping the closing vertex at emission (`dsf._open_ring`, fix "2a").
- Second fix (2b, latent): buildings_to_facades computed make_valid() but emitted the raw ring; now emits the repaired outer ring (largest polygon when a repair splits). Green Bank had 0 invalid geometries, so 2b did not affect this tile but protects other regions.
- Not lost in the pipeline: 167 buildings in GeoJSON -> 167 facades in text DSF -> 167 in the compiled DSF (verified by DSFTool dsf2text round-trip). The drop was at X-Plane render time, caused by the zero-length wall above.
- Facade SELECTION / wall-width / heading was investigated and RULED OUT as the cause:
  1. Pre-baked min/max wall widths do not discriminate: across 1391 facades min_wall_width is 808 @0 m, 567 @1 m, 15 @2 m, 1 @3 m, so ~all facades accept short edges.
  2. A heading-aware spelling predicate reproduced only 1/167 drops when run against the ACTUAL original per-building facade assignments — it does not explain the observed drop.
  3. Clean re-test (spikes, 2026-07-23): re-emitting the ORIGINAL 8-facade selection through the 2a-fixed writer (plus ortho) rendered all buildings in-sim, same as forcing the universal facade. This isolates 2a — not selection — as the cause. The earlier "force universal facade" step-1 diagnostic was a confound: it changed two variables at once (applied 2a AND forced universal), which briefly misdirected the investigation toward selection.
- Status: resolved by the committed 2a/2b fixes. No facade-selection changes were needed; the spelling predicate and facade_widths pre-bake were removed as unneeded (knowledge retained in the next section).
- Distinct, still-open issue: some real-world buildings are absent because they are not in the OSM source at all (coverage gap), not a render problem. See SOURCE-001 in the backlog.

### Facade Spelling and Wall Headings (reference; NOT the RENDER-001 cause)
Retained reference knowledge from the RENDER-001 investigation. Spelling was investigated as a drop cause and ruled out (above), but the mechanics are worth keeping for future facade-quality work.
Terms:
- Winding: the order (CW/CCW) a polygon's vertices are listed; sets which way walls face. `_ensure_ccw` forces CCW.
- Spelling: X-Plane fitting a facade's WALL pieces along each footprint edge. For every edge it needs a WALL rule matching that edge's length AND heading; if any edge matches none, spelling fails and the facade is silently not drawn.
- Spelling predicate: a yes/no function `can_spell(footprint, facade_rules)` reimplementing X-Plane's spelling to predict rendering before launching the sim. (Prototyped and validated as insufficient to explain RENDER-001, then removed.)

Wall headings are RELATIVE, not absolute azimuth. WALL rules are `WALL min_len max_len [h_min h_max] [name]`. The heading is a relative heading (`rel_hdg` in WED_FacadePreview.cpp), degrees 0-360 with wraparound (`in_heading_in_range` handles h_min>h_max through north). The facade builds its own orientation frame from the footprint's first edge (`facRot = atan2(dir.y(), dir.x())`, dir from footprint[1]->footprint[0]). It is NOT absolute compass azimuth and NOT relative to roads. It encodes per-side treatment (front/side/back): walls near 0 deg relative use a storefront texture, side walls near 90/270 use plain walls. Rotating the whole building keeps relative headings constant, so "front stays front".
- Dimension-named autogen facades (e.g. 45x30x6v0.fac) are fixed-shape templates modeled from specific rectangular buildings; their walls expect edges near 0/90/180/270 relative. Universal facades use `WALL ... 0 360` (all headings) on every rule, so they spell any footprint.
- Source: WED_FacadePreview.cpp (`in_heading_in_range`, `REN_facade_wall_filter_t::is_ok`, `facRot`); WED_ResourceMgr.cpp (WALL parse, min_heading/max_heading ~lines 826-851); WED_PreviewLayer.cpp (`choices`).
- Confidence: confirmed from WED source that the heading is relative, in degrees, wrapped, with a facade-local orientation frame. NOT traced line-by-line: the exact zero-reference for each segment's rel_hdg. Verify before any future spelling predicate depends on it.

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
