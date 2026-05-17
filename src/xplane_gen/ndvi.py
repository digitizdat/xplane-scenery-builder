"""Sentinel-2 NDVI → per-polygon forest density.

Fetches the least-cloudy Sentinel-2 L2A scene within a 90-day window
from s3://sentinel-cogs/ via STAC, computes NDVI, and annotates each
forest polygon in a landcover GeoJSON with an ndvi_density value.

Large bboxes are processed in tiles to avoid OOM.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.features import geometry_mask
from rasterio.warp import transform_bounds

_STAC_URL = "https://earth-search.aws.element84.com/v1"
_COLLECTION = "sentinel-2-l2a"
_WINDOW_DAYS = 90
_CLOUD_THRESHOLD = 80  # skip scenes with >80% cloud cover

# NDVI range typical for vegetated land; map linearly to [0.2, 1.0]
_NDVI_MIN = 0.3
_NDVI_MAX = 0.9
_DENSITY_MIN = 0.2
_DENSITY_MAX = 1.0

# SCL (Scene Classification Layer) values to mask as cloud/shadow
_CLOUD_SCL = {8, 9, 10}  # cloud medium, cloud high, thin cirrus

# Maximum tile size in degrees for chunked processing
_TILE_DEG = 0.15


def annotate_forest_density(
    landcover_geojson: Path,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
) -> Path:
    """Compute per-polygon NDVI density and write it back to the GeoJSON in-place.

    Adds/updates the ``ndvi_density`` property on each forest polygon.
    Returns the path to the updated file.
    """
    fc: dict[str, Any] = json.loads(landcover_geojson.read_text(encoding="utf-8"))
    features = fc.get("features", [])

    # Only process vegetated classes
    vegetated = [
        f
        for f in features
        if f.get("properties", {}).get("label", "") not in {"built_up", "bare", "snow_ice", "water"}
    ]
    if not vegetated:
        return landcover_geojson

    # Process in tiles to limit memory
    from shapely.geometry import box, shape

    tiles = _make_tiles(lat_min, lon_min, lat_max, lon_max)

    for tile_bbox in tiles:
        t_lat_min, t_lon_min, t_lat_max, t_lon_max = tile_bbox
        tile_box = box(t_lon_min, t_lat_min, t_lon_max, t_lat_max)

        # Find polygons intersecting this tile
        tile_feats = []
        for f in vegetated:
            if f["properties"].get("ndvi_density") is not None:
                continue  # already annotated
            geom = shape(f["geometry"])
            if geom.intersects(tile_box):
                tile_feats.append(f)

        if not tile_feats:
            continue

        ndvi_result = _fetch_ndvi(t_lat_min, t_lon_min, t_lat_max, t_lon_max)
        if ndvi_result is None:
            continue

        ndvi_raster, ndvi_transform, ndvi_crs = ndvi_result

        for feat in tile_feats:
            density = _mean_ndvi_for_polygon(
                feat["geometry"], ndvi_raster, ndvi_transform, ndvi_crs
            )
            feat["properties"]["ndvi_density"] = round(density, 3)

        # Free raster memory between tiles
        del ndvi_raster, ndvi_result

    landcover_geojson.write_text(json.dumps(fc, indent=2), encoding="utf-8")
    return landcover_geojson


def _make_tiles(
    lat_min: float, lon_min: float, lat_max: float, lon_max: float
) -> list[tuple[float, float, float, float]]:
    """Split bbox into tiles of at most _TILE_DEG on each side."""
    tiles: list[tuple[float, float, float, float]] = []
    lat = lat_min
    while lat < lat_max:
        lon = lon_min
        lat_end = min(lat + _TILE_DEG, lat_max)
        while lon < lon_max:
            lon_end = min(lon + _TILE_DEG, lon_max)
            tiles.append((lat, lon, lat_end, lon_end))
            lon = lon_end
        lat = lat_end
    return tiles


def _fetch_ndvi(
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
) -> tuple[np.ndarray, Any, CRS] | None:
    """Fetch B04+B08 from the least-cloudy S2 scene; return (ndvi_array, transform, crs)."""
    import pystac_client

    client = pystac_client.Client.open(_STAC_URL)
    end = datetime.now(tz=UTC)
    start = end - timedelta(days=_WINDOW_DAYS)

    results = client.search(
        collections=[_COLLECTION],
        bbox=[lon_min, lat_min, lon_max, lat_max],
        datetime=f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        query={"eo:cloud_cover": {"lt": _CLOUD_THRESHOLD}},
        sortby=["+properties.eo:cloud_cover"],
        max_items=5,
    )

    items = list(results.items())
    if not items:
        return None

    item = items[0]
    b04_href = item.assets["red"].href
    b08_href = item.assets["nir"].href

    with (
        rasterio.Env(AWS_NO_SIGN_REQUEST="YES"),
        rasterio.open(b04_href) as src_red,
        rasterio.open(b08_href) as src_nir,
    ):
        crs = src_red.crs
        bbox_crs = CRS.from_epsg(4326)
        if crs != bbox_crs:
            west, south, east, north = transform_bounds(
                bbox_crs, crs, lon_min, lat_min, lon_max, lat_max
            )
        else:
            west, south, east, north = lon_min, lat_min, lon_max, lat_max

        window = src_red.window(west, south, east, north)
        red = src_red.read(1, window=window).astype(np.float32)
        transform = src_red.window_transform(window)

        nir = src_nir.read(1, window=window, out_shape=red.shape).astype(np.float32)

        # Mask clouds using SCL band if available
        if "scl" in item.assets:
            with rasterio.open(item.assets["scl"].href) as src_scl:
                scl_window = src_scl.window(west, south, east, north)
                scl = src_scl.read(1, window=scl_window, out_shape=red.shape)
            cloud_mask = np.isin(scl, list(_CLOUD_SCL))
            red[cloud_mask] = np.nan
            nir[cloud_mask] = np.nan
            del scl, cloud_mask

    denom = nir + red
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = np.where(denom != 0, (nir - red) / denom, np.nan)

    del red, nir, denom
    return ndvi, transform, crs


def _mean_ndvi_for_polygon(
    geometry: dict[str, Any],
    ndvi: np.ndarray,
    transform: Any,
    crs: CRS,
) -> float:
    """Compute mean NDVI within a polygon and map to X-Plane density [0.2, 1.0]."""
    import pyproj
    from shapely.geometry import mapping, shape
    from shapely.ops import transform as shp_transform

    geom = shape(geometry)

    # Reproject polygon to raster CRS if needed
    if crs != CRS.from_epsg(4326):
        project = pyproj.Transformer.from_crs("EPSG:4326", crs.to_epsg(), always_xy=True).transform
        geom = shp_transform(project, geom)

    try:
        # Use geometry_mask directly on the ndvi array — no MemoryFile copy
        mask = geometry_mask(
            [mapping(geom)],
            out_shape=ndvi.shape,
            transform=transform,
            invert=True,
        )
        values = ndvi[mask]
        valid = values[~np.isnan(values)]
        if valid.size == 0:
            return 0.7
        mean_ndvi = float(np.mean(valid))
    except Exception:
        return 0.7

    return _ndvi_to_density(mean_ndvi)


def _ndvi_to_density(ndvi: float) -> float:
    """Map NDVI [_NDVI_MIN, _NDVI_MAX] linearly to density [_DENSITY_MIN, _DENSITY_MAX]."""
    clamped = max(_NDVI_MIN, min(_NDVI_MAX, ndvi))
    t = (clamped - _NDVI_MIN) / (_NDVI_MAX - _NDVI_MIN)
    return _DENSITY_MIN + t * (_DENSITY_MAX - _DENSITY_MIN)
