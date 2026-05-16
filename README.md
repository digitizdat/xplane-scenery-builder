# xplane-scenery-builder

Automates the production of X-Plane 11/12 overlay scenery packs from freely
available geospatial data (OpenStreetMap, ESA WorldCover, Sentinel-2, NAIP) and
optionally Amazon Bedrock LLM classification.

## How it works

For a given lat/lon bounding box the pipeline:

1. Fetches building footprints, roads, and land-use polygons from OpenStreetMap
2. Fetches ESA WorldCover land classification (10 m raster)
3. Annotates forest polygons with NDVI-derived density from Sentinel-2
4. Optionally fetches orthophoto ground texture tiles (Sentinel-2 RGB or NAIP)
5. Optionally classifies buildings, forests, and roads via Bedrock LLM vision
6. Optionally pauses for interactive human review of low-confidence items
7. Maps features to X-Plane library assets via a YAML catalog
8. Writes a DSF overlay and compiles it with DSFTool

The output is a scenery pack folder you drop into X-Plane's `Custom Scenery/`
directory.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/) — `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **DSFTool** from [xptools](https://github.com/X-Plane/xptools) — build from
  source or place the binary on `PATH` (or at `tools/DSFTool` in this repo)
- AWS credentials configured for Bedrock only (public S3 data uses anonymous access)

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

Example — Green Bank, WV:

```bash
uv run xplane-gen generate --bbox 38.4,-79.9,38.45,-79.8 --output ./green_bank
```

The pipeline runs eight stages and writes state to `tile_state.json` so a
failed run can be resumed from where it left off:

```
fetch_osm → fetch_rasters → annotate → fetch_ortho → classify → review → write_dsf → validate
```

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Skip DSFTool compilation; write a text preview instead |
| `--auto` | Skip LLM classification and human review; use deterministic mapping only |
| `--dsftool PATH` | Path to DSFTool binary if not on `PATH` |
| `--ortho-source sentinel2\|naip` | Fetch orthophoto ground texture tiles. Omit to skip |
| `--regen` | Regenerate from cached data without re-downloading |
| `--review-all` | Force all LLM classifications to human review |

### Install the output in X-Plane

```bash
cp -r "./my_scenery/Earth nav data" "/path/to/X-Plane 12/Custom Scenery/my_scenery/"
```

Restart X-Plane and fly over the area.

### Review ambiguous classifications

After a run with LLM classification, low-confidence items are written to
`review_queue.json`. Review them interactively:

```bash
uv run xplane-gen review --queue ./my_scenery/review_queue.json \
                         --output ./my_scenery/resolved_queue.json
```

Press **Enter** to accept the suggestion, or type a replacement building type.
Similar items are grouped for batch approval. Re-run `generate --regen` after
reviewing to rebuild the DSF with your decisions.

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
| Orthophoto (US, 1 m) | NAIP (`s3://naip-analytic/`) | Public domain |

## AWS permissions required

Sentinel-2, ESA WorldCover, and NAIP are public S3 buckets accessed with
anonymous requests — no AWS credentials needed.

For Bedrock LLM classification (optional):

```
bedrock:InvokeModel on the Haiku, Sonnet, and Opus model ARNs in us-east-1
```

## Project structure

```
src/xplane_gen/
  cli.py          Click CLI entry point
  pipeline.py     TileProcessor — resumable 8-stage state machine
  osm.py          OSM data fetcher (Overpass API, multi-endpoint failover)
  landcover.py    ESA WorldCover raster → land-cover GeoJSON
  ndvi.py         Sentinel-2 NDVI → forest density annotation
  ortho.py        Orthophoto tiles (Sentinel-2 RGB or NAIP) → PNG + .pol
  classifier.py   Bedrock LLM classifier (buildings, forests, roads) with tiered routing
  buildings.py    OSM building footprints → FacadeFeature placements
  catalog.py      Asset catalog: building type / climate zone → library paths
  review.py       HITL review CLI
  dsf.py          DsfWriter, build_overlay — DSF text format and compiler
assets/
  catalog.yaml    Building type and forest type → X-Plane 12 virtual path mappings
docs/
  asset-catalog.md         How the X-Plane virtual library system works
  xp12-asset-inventory.md  Complete inventory of X-Plane 12 default library (20,539 paths)
  llm-annotation-design.md Design for LLM-based feature classification
  backlog.md               Feature backlog
```
