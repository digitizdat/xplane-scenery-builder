"""ESA WorldCover land classifier: raster → land-cover GeoJSON with X-Plane .for paths."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
import rasterio.features
import rasterio.mask
import rasterio.transform
from rasterio.crs import CRS
from rasterio.warp import transform_bounds
from rich.console import Console
from shapely.geometry import mapping, shape
from shapely.validation import make_valid

console = Console()

# ESA WorldCover S3 location (requester-pays bucket, public read)
_WC_S3_PREFIX = "s3://esa-worldcover/v200/2021/map"

# ESA WorldCover class codes → (label, X-Plane .for virtual path stub)
# .for path is climate-zone-agnostic here; AssetCatalog refines by lat/lon in Task 4.
_ESA_CLASSES: dict[int, tuple[str, str]] = {
    10: ("tree_cover", "lib/g8/trees_decid_tmp_wet.for"),
    20: ("shrubland", "lib/g8/shrb_tmp_rain.for"),
    30: ("grassland", "lib/g8/crops_tmp_wet.for"),
    40: ("cropland", "lib/g8/crops_tmp_wet.for"),
    50: ("built_up", ""),  # no .for — buildings handled by OSM pipeline
    60: ("bare", ""),
    70: ("snow_ice", ""),
    80: ("water", ""),
    90: ("wetland", "lib/g8/shrb_cld_wet.for"),
    95: ("mangrove", "lib/g8/trees_tropical.for"),
    100: ("moss_lichen", "lib/g8/shrb_cld_dry.for"),
}

_SIMPLIFY_TOLERANCE = 0.001  # degrees — keeps polygons under ~500 vertices


def classify_tile(
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    output_dir: str,
) -> Path:
    """Fetch ESA WorldCover for bbox, vectorise, and write landcover.geojson.

    Returns path to the written GeoJSON file.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    console.print(
        f"[cyan]Fetching ESA WorldCover for bbox:[/cyan] {lat_min},{lon_min},{lat_max},{lon_max}"
    )

    raster_path = _find_worldcover_tile(lat_min, lon_min, lat_max, lon_max)
    features = _vectorise(raster_path, lat_min, lon_min, lat_max, lon_max)

    path = out / "landcover.geojson"
    _write_geojson(features, path)

    counts: dict[str, int] = {}
    for f in features:
        label = f["properties"]["label"]
        counts[label] = counts.get(label, 0) + 1
    for label, count in sorted(counts.items()):
        console.print(f"  [green]{label}:[/green] {count} polygons")
    console.print(f"  → {path}")

    return path


def _find_worldcover_tile(lat_min: float, lon_min: float, lat_max: float, lon_max: float) -> str:
    """Return the S3 (or local) path to the WorldCover GeoTIFF covering the bbox.

    WorldCover tiles are 3°×3° named by their SW corner in steps of 3°.
    E.g. the tile covering +47,-123 is ESA_WorldCover_10m_2021_v200_N45W126_Map.tif
    """
    tile_lat = int(np.floor(lat_min / 3) * 3)
    tile_lon = int(np.floor(lon_min / 3) * 3)
    lat_str = f"N{tile_lat:02d}" if tile_lat >= 0 else f"S{abs(tile_lat):02d}"
    lon_str = f"E{abs(tile_lon):03d}" if tile_lon >= 0 else f"W{abs(tile_lon):03d}"
    filename = f"ESA_WorldCover_10m_2021_v200_{lat_str}{lon_str}_Map.tif"
    return f"{_WC_S3_PREFIX}/{filename}"


def _vectorise(
    raster_path: str,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
) -> list[dict[str, Any]]:
    """Open raster, clip to bbox, vectorise contiguous regions by class code."""
    with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"), rasterio.open(raster_path) as src:
        # Transform bbox to raster CRS if needed
        bbox_crs = CRS.from_epsg(4326)
        if src.crs != bbox_crs:
            west, south, east, north = transform_bounds(
                bbox_crs, src.crs, lon_min, lat_min, lon_max, lat_max
            )
        else:
            west, south, east, north = lon_min, lat_min, lon_max, lat_max

        window = src.window(west, south, east, north)
        data = src.read(1, window=window)
        transform = src.window_transform(window)

    features: list[dict[str, Any]] = []
    for geom_dict, value in rasterio.features.shapes(data.astype(np.int16), transform=transform):
        code = int(value)
        if code == 0 or code not in _ESA_CLASSES:
            continue
        label, for_path = _ESA_CLASSES[code]

        geom = make_valid(shape(geom_dict))
        geom = geom.simplify(_SIMPLIFY_TOLERANCE, preserve_topology=True)
        if geom.is_empty:
            continue

        features.append(
            {
                "type": "Feature",
                "geometry": mapping(geom),
                "properties": {
                    "esa_class": code,
                    "label": label,
                    "for_path": for_path,
                },
            }
        )

    return features


def _write_geojson(features: list[dict[str, Any]], path: Path) -> None:
    collection = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
