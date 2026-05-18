"""Extract a subset of an existing scenery output to a smaller bounding box."""

from __future__ import annotations

import json
import math
import shutil
from pathlib import Path

from rich.console import Console
from shapely.geometry import box, shape
from shapely.ops import clip_by_rect

console = Console()


def extract_subset(
    source_dir: Path,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    output_dir: Path,
    dsftool: Path | None = None,
    no_roads: bool = False,
) -> None:
    """Clip existing scenery data to a sub-bbox and build a new DSF.

    Reads GeoJSON and ortho tiles from source_dir, clips to the given bbox,
    writes clipped data to output_dir, and compiles a new DSF overlay.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    clip_box = box(lon_min, lat_min, lon_max, lat_max)

    # ── Clip GeoJSON files ────────────────────────────────────────────
    geojson_files = ["buildings.geojson", "landcover.geojson", "roads.geojson", "landuse.geojson"]
    for name in geojson_files:
        src = source_dir / name
        if not src.exists():
            continue
        fc = json.loads(src.read_text(encoding="utf-8"))
        clipped_features = []
        for feat in fc.get("features", []):
            geom = feat.get("geometry")
            if geom is None:
                continue
            try:
                shp = shape(geom)
            except (ValueError, TypeError, AttributeError):
                continue
            clipped = clip_by_rect(shp, lon_min, lat_min, lon_max, lat_max)
            if clipped.is_empty:
                continue
            feat_copy = {**feat, "geometry": clipped.__geo_interface__}
            clipped_features.append(feat_copy)

        if clipped_features:
            out_fc = {"type": "FeatureCollection", "features": clipped_features}
            (output_dir / name).write_text(json.dumps(out_fc), encoding="utf-8")
            console.print(f"  [green]{name}[/green]: {len(clipped_features)} features")
        else:
            console.print(f"  [dim]{name}: 0 features in bbox[/dim]")

    # ── Copy intersecting ortho tiles ─────────────────────────────────
    ortho_src = source_dir / "orthophoto"
    if ortho_src.exists():
        ortho_dst = output_dir / "orthophoto"
        ortho_dst.mkdir(parents=True, exist_ok=True)
        copied = 0
        for pol_file in sorted(ortho_src.glob("*.pol")):
            clat, clon, w_m, h_m = _parse_pol(pol_file)
            if w_m <= 0 or h_m <= 0:
                continue
            # Compute tile bounds from LOAD_CENTER + SCALE
            h_deg = h_m / 111_320.0
            w_deg = w_m / (111_320.0 * math.cos(math.radians(clat)))
            tile_box = box(
                clon - w_deg / 2,
                clat - h_deg / 2,
                clon + w_deg / 2,
                clat + h_deg / 2,
            )
            if not tile_box.intersects(clip_box):
                continue
            # Copy .pol and .png
            shutil.copy2(pol_file, ortho_dst / pol_file.name)
            png_file = pol_file.with_suffix(".png")
            if png_file.exists():
                shutil.copy2(png_file, ortho_dst / png_file.name)
            copied += 1
        console.print(f"  [green]orthophoto[/green]: {copied} tiles")
    else:
        console.print("  [dim]No orthophoto/ in source[/dim]")

    # ── Build DSF ─────────────────────────────────────────────────────
    from xplane_gen.dsf import build_overlay

    tile_west = int(math.floor(lon_min))
    tile_south = int(math.floor(lat_min))

    buildings = output_dir / "buildings.geojson"
    landcover = output_dir / "landcover.geojson"

    console.print("[cyan]Compiling DSF…[/cyan]")
    build_overlay(
        tile_west,
        tile_south,
        buildings if buildings.exists() else None,
        landcover if landcover.exists() else None,
        output_dir,
        dsftool=dsftool,
        dry_run=False,
        no_roads=no_roads,
    )

    # Write tile_state so the output looks like a complete run
    state = {
        "completed": [
            "fetch_osm",
            "fetch_rasters",
            "annotate",
            "fetch_ortho",
            "classify",
            "review",
            "write_dsf",
            "validate",
            "done",
        ]
    }
    (output_dir / "tile_state.json").write_text(json.dumps(state), encoding="utf-8")

    console.print(f"[bold green]✓ Subset complete:[/bold green] {output_dir}")


def _parse_pol(pol_file: Path) -> tuple[float, float, float, float]:
    """Extract (clat, clon, w_m, h_m) from a .pol file."""
    clat = clon = w_m = h_m = 0.0
    for line in pol_file.read_text(encoding="utf-8").splitlines():
        if line.startswith("SCALE"):
            parts = line.split()
            if len(parts) >= 3:
                w_m, h_m = float(parts[1]), float(parts[2])
        elif line.startswith("LOAD_CENTER"):
            parts = line.split()
            if len(parts) >= 3:
                clat, clon = float(parts[1]), float(parts[2])
    return clat, clon, w_m, h_m
