# xplane-scenery-builder

Automates the production of X-Plane 11/12 overlay scenery packs from freely
available geospatial data (OpenStreetMap, ESA WorldCover, Sentinel-2) and
optionally Amazon Bedrock LLM classification.

## How it works

For a given lat/lon bounding box the pipeline:

1. Fetches building footprints, roads, and land-use polygons from OpenStreetMap
2. Fetches ESA WorldCover land classification (10 m raster)
3. Annotates forest polygons with NDVI-derived density from Sentinel-2
4. Maps features to X-Plane library assets via a YAML catalog
5. Writes a DSF overlay and compiles it with DSFTool
6. Optionally runs Bedrock LLM classification for ambiguous buildings and
   produces a human review queue

The output is a scenery pack folder you drop into X-Plane's `Custom Scenery/`
directory.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **DSFTool** from [xptools](https://github.com/X-Plane/xptools) — build from
  source or place the binary on `PATH` (or at `tools/DSFTool` in this repo)
- AWS credentials configured (for Sentinel-2 on S3 and optionally Bedrock)

## Installation

```bash
git clone https://github.com/digitizdat/xplane-scenery-builder.git
cd xplane-scenery-builder
make install
```

This installs all runtime and dev dependencies into a local `.venv` via `uv`.
All commands are run via `uv run` so you never need to activate the virtualenv manually.

## Usage

### Generate a scenery tile

```bash
uv run xplane-gen generate --bbox LAT_MIN,LON_MIN,LAT_MAX,LON_MAX --output ./my_scenery
```

Example — Seattle area:

```bash
uv run xplane-gen generate --bbox 47.5,-122.5,48.5,-121.5 --output ./seattle_scenery
```

The pipeline runs five stages (`fetch_osm → fetch_rasters → classify →
write_dsf → validate`) and writes state to `tile_state.json` so a failed run
can be resumed from where it left off.

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Run all stages but skip DSFTool compilation; writes a text preview instead |
| `--auto` | Skip human review; use best-guess classifications for all items |
| `--dsftool PATH` | Path to DSFTool binary if not on `PATH` |

### Install the output in X-Plane

```bash
cp -r ./my_scenery "/path/to/X-Plane 12/Custom Scenery/my_scenery"
```

Restart X-Plane and fly over the area.

### Review ambiguous classifications (Phase 2 / LLM mode)

After a run with LLM classification enabled, low-confidence items are written
to `review_queue.json`. Review them interactively:

```bash
uv run xplane-gen review --queue ./my_scenery/review_queue.json \
                         --output ./my_scenery/resolved_queue.json
```

Press **Enter** to accept the suggestion, or type a replacement building type.
Similar items are grouped for batch approval. Re-run `generate` after reviewing
to apply your decisions without re-calling Bedrock.

### Other commands

```bash
# Fetch OSM data only
uv run xplane-gen fetch-osm --bbox 47.5,-122.5,48.5,-121.5 --output ./data

# Classify land cover only
uv run xplane-gen classify-land --bbox 47.5,-122.5,48.5,-121.5 --output ./data

# Validate asset catalog against an X-Plane install
uv run xplane-gen catalog validate --xplane-path "/path/to/X-Plane 12"
```

## Development

```bash
make lint        # ruff check
make typecheck   # mypy
make test        # pytest
make precommit   # full suite: lint + typecheck + secscan + test
make lintfix     # auto-fix ruff issues
```

All commits must pass `make precommit` and follow
[Conventional Commits](https://www.conventionalcommits.org/).

## Data sources

| Data | Source | License |
|------|--------|---------|
| Building footprints, roads, land use | OpenStreetMap via Overpass API | ODbL |
| Land classification (10 m) | ESA WorldCover 2021 (`s3://esa-worldcover/`) | CC-BY |
| Satellite imagery / NDVI | Sentinel-2 L2A (`s3://sentinel-cogs/`) | Free / Copernicus |
| Building heights (fallback) | Microsoft GlobalMLBuildingFootprints | ODbL |

## AWS permissions required

For Sentinel-2 and ESA WorldCover (public S3 buckets, no auth needed beyond
standard AWS credentials):

```
s3:GetObject on arn:aws:s3:::sentinel-cogs/*
s3:GetObject on arn:aws:s3:::esa-worldcover/*
```

For Bedrock LLM classification (optional):

```
bedrock:InvokeModel on the Haiku, Sonnet, and Opus model ARNs in us-east-1
```

## Project structure

```
src/xplane_gen/
  dsf.py          DsfWriter, build_overlay — DSF text format and compiler
  osm.py          OSM data fetcher (Overpass API)
  landcover.py    ESA WorldCover raster → land-cover GeoJSON
  ndvi.py         Sentinel-2 NDVI → forest density annotation
  buildings.py    OSM building footprints → FacadeFeature placements
  catalog.py      Asset catalog: building type / climate zone → library paths
  pipeline.py     TileProcessor — resumable stage state machine
  classifier.py   Bedrock LLM classifier with tiered routing + review queue
  review.py       HITL review CLI
  cli.py          Click CLI entry point
assets/
  catalog.yaml    Building type and forest type → X-Plane virtual path mappings
```
