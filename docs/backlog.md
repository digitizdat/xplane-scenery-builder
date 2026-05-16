# Backlog

---

## ORTHO-001 — Orthophoto ground texture generation

**Status**: Implemented (partial)  
**Priority**: Medium  
**Source**: Analysis of Xometry KCRW commercial scenery pack

**What's done**:
- `ortho.py` module with Sentinel-2 and NAIP sources
- `--ortho-source sentinel2|naip` CLI flag
- `fetch_ortho` pipeline stage (resumable, tile-based)
- PNG + `.pol` output per tile

**Remaining gap**: The `write_dsf` stage does not reference the orthophoto
`.pol` tiles in the DSF. The tiles are generated on disk but not placed as
draped polygons in the overlay. This requires adding `POLYGON_DEF` entries
and polygon placements to `dsf.py`'s `build_overlay()` function.

### Background

Commercial X-Plane scenery packs (e.g. Xometry KCRW) replace the default procedural
terrain textures with real satellite imagery draped onto the terrain mesh. This is done
via a grid of DDS texture tiles, each paired with a `.pol` descriptor file that tells
X-Plane where to place it and how to UV-map it onto the ground. The result is a
significant visual improvement over the generic grass/dirt/asphalt patterns X-Plane
uses by default.

The current xplane-gen pipeline produces an overlay DSF with library facades and ESA
landcover forest polygons, but leaves the ground texture as X-Plane's default. Adding
orthophoto tiles would bring the output much closer to commercial scenery quality
without requiring hand-authored assets.

### Approach

**Data source**: Sentinel-2 L2A RGB bands (B04, B03, B02) at 10m resolution, already
accessible via `pystac-client` on `s3://sentinel-cogs/`. The NDVI fetch in `ndvi.py`
uses the same access pattern and can serve as a reference implementation.

**Pipeline**:
1. Fetch Sentinel-2 RGB bands for the bbox (reuse `pystac-client` + `rasterio` pattern
   from `ndvi.py`)
2. Clip to bbox, merge bands, reproject to EPSG:4326
3. Split into NxM tiles (target: ~2km × 2km per tile, matching Xometry convention)
4. Export each tile as PNG (first pass) or DDS (optimised pass)
5. Write a `.pol` file per tile defining corner coordinates and texture reference
6. Add `POLYGON_DEF` entries and `BEGIN_POLYGON`/`END_POLYGON` placements to the DSF
   writer in `dsf.py`

**New module**: `src/xplane_gen/ortho.py` (~150 lines)  
**New pipeline stage**: `fetch_ortho`, inserted between `fetch_rasters` and `classify`

### X-Plane file formats

**`.pol` file** — defines a draped polygon type:
```
A
850
DRAPED_POLYGON

TEXTURE ../orthophoto/tile_N_W.png
TEXTURE_NOWRAP
DECAL_LIB lib/g8/terrain2/decals/null.dcl
SCALE 1 1
```

**DSF placement** — references the `.pol` index and four corner coordinates as a
polygon winding.

### DDS conversion

X-Plane prefers DXT1/DXT5 compressed DDS for performance. Options in priority order:

1. **PNG** (no extra dependency) — X-Plane accepts PNG in `.pol`; fine for initial
   implementation
2. **ImageMagick** (`brew install imagemagick`) — `convert input.png -define
   dds:compression=dxt1 output.dds`; available on macOS without building from source
3. **crunch** (Binomial, open source) — best quality DXT compression, requires
   building from source

Start with PNG; add optional DDS conversion behind a `--dds` flag later.

### Known risks / open questions

- **Cloud cover**: Sentinel-2 scenes with cloud cover over the bbox will produce
  artefacts. Need to select the least-cloudy scene or composite multiple scenes.
  `pystac-client` supports filtering by `eo:cloud_cover`.
- **Resolution**: 10m/pixel is acceptable at cruise altitude; marginal for low-and-slow
  VFR flying. Higher resolution would require a commercial imagery source.
- **Tile seams**: Adjacent tiles must align exactly at edges to avoid visible seams.
  Rasterio window arithmetic needs care.
- **Colour correction**: Sentinel-2 L2A surface reflectance values need gamma correction
  and brightness scaling to look natural in X-Plane's renderer.

### Acceptance criteria

- [ ] `fetch_ortho` stage fetches Sentinel-2 RGB for the bbox, selecting the scene with
  lowest cloud cover
- [ ] Output is a grid of PNG tiles in `<output_dir>/orthophoto/`
- [ ] Corresponding `.pol` files written alongside each tile
- [ ] DSF overlay references all tiles; they render correctly in X-Plane
- [ ] Pipeline is resumable (stage skipped if `orthophoto/` already populated)
- [ ] `--no-ortho` flag allows skipping the stage
- [ ] Existing tests continue to pass; new unit tests cover tile grid math and `.pol`
  generation
