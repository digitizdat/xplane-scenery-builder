"""Orthophoto ground texture: fetch satellite imagery and write .pol tiles.

Supports two sources:
  - sentinel2: Sentinel-2 L2A RGB (10 m, global, free)
  - naip:      NAIP aerial RGB (1 m, US-only, free)

Output per tile:
  <output_dir>/orthophoto/<row>_<col>.png   — RGB image
  <output_dir>/orthophoto/<row>_<col>.pol   — X-Plane draped polygon descriptor
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Protocol

import numpy as np
from rich.console import Console

console = Console()

_STAC_URL = "https://earth-search.aws.element84.com/v1"
_CLOUD_THRESHOLD = 30  # percent; skip scenes cloudier than this
_WINDOW_DAYS = 90

# Target tile size in degrees. ~0.02° ≈ 2 km at mid-latitudes.
_TILE_DEG = 0.02


# ------------------------------------------------------------------ #
# Protocol                                                             #
# ------------------------------------------------------------------ #


class OrthoSource(Protocol):
    """Fetch an RGB uint8 array (H, W, 3) for the given bbox in EPSG:4326."""

    def fetch_rgb(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
    ) -> np.ndarray | None: ...


# ------------------------------------------------------------------ #
# Sentinel-2 source                                                    #
# ------------------------------------------------------------------ #


class Sentinel2Source:
    """Sentinel-2 L2A RGB (B04/B03/B02) at 10 m resolution."""

    def fetch_rgb(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
    ) -> np.ndarray | None:
        from datetime import UTC, datetime, timedelta

        import pystac_client
        import rasterio
        from rasterio.crs import CRS
        from rasterio.warp import transform_bounds

        client = pystac_client.Client.open(_STAC_URL)
        end = datetime.now(tz=UTC)
        start = end - timedelta(days=_WINDOW_DAYS)

        results = client.search(
            collections=["sentinel-2-l2a"],
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
        bbox_crs = CRS.from_epsg(4326)

        bands: list[np.ndarray] = []
        shape_hw: tuple[int, int] | None = None
        with rasterio.Env(AWS_NO_SIGN_REQUEST="YES"):
            for asset_key in ("red", "green", "blue"):
                href = item.assets[asset_key].href
                with rasterio.open(href) as src:
                    crs = src.crs
                    if crs != bbox_crs:
                        w, s, e, n = transform_bounds(
                            bbox_crs, crs, lon_min, lat_min, lon_max, lat_max
                        )
                    else:
                        w, s, e, n = lon_min, lat_min, lon_max, lat_max
                    window = src.window(w, s, e, n)
                    if shape_hw is None:
                        data = src.read(1, window=window)
                        shape_hw = data.shape
                    else:
                        data = src.read(1, window=window, out_shape=shape_hw)
                    bands.append(data.astype(np.float32))

        return _reflectance_to_uint8(np.stack(bands, axis=-1))


# ------------------------------------------------------------------ #
# NAIP source                                                          #
# ------------------------------------------------------------------ #


class NAIPSource:
    """NAIP aerial imagery (1 m, US-only, RGBI — bands 1-3 used)."""

    def fetch_rgb(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
    ) -> np.ndarray | None:
        import pystac_client
        import rasterio
        from rasterio.crs import CRS
        from rasterio.warp import transform_bounds

        client = pystac_client.Client.open(_STAC_URL)
        results = client.search(
            collections=["naip"],
            bbox=[lon_min, lat_min, lon_max, lat_max],
            max_items=5,
        )
        items = list(results.items())
        if not items:
            return None

        # NAIP items are sorted newest-first by default; take the first
        item = items[0]
        href = item.assets["image"].href
        bbox_crs = CRS.from_epsg(4326)

        with rasterio.Env(AWS_REQUEST_PAYER="requester"), rasterio.open(href) as src:
            crs = src.crs
            if crs != bbox_crs:
                w, s, e, n = transform_bounds(bbox_crs, crs, lon_min, lat_min, lon_max, lat_max)
            else:
                w, s, e, n = lon_min, lat_min, lon_max, lat_max
            window = src.window(w, s, e, n)
            # NAIP is RGBI; read bands 1-3 (R, G, B)
            data = src.read([1, 2, 3], window=window)  # (3, H, W) uint8

        result: np.ndarray = np.moveaxis(data, 0, -1)
        return result.astype(np.uint8)  # → (H, W, 3)


# ------------------------------------------------------------------ #
# Tile grid + .pol writer                                              #
# ------------------------------------------------------------------ #


def fetch_ortho_tiles(
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    output_dir: str,
    source: OrthoSource,
) -> list[Path]:
    """Fetch orthophoto tiles for the bbox and write PNG + .pol files.

    Returns list of .pol paths written.
    """
    out = Path(output_dir) / "orthophoto"
    out.mkdir(parents=True, exist_ok=True)

    tiles = _tile_grid(lat_min, lon_min, lat_max, lon_max, _TILE_DEG)
    pol_paths: list[Path] = []

    console.print(
        f"[cyan]Fetching orthophoto ({source.__class__.__name__}) "
        f"for bbox:[/cyan] {lat_min},{lon_min},{lat_max},{lon_max}"
    )

    for row, col, t_lat_min, t_lon_min, t_lat_max, t_lon_max in tiles:
        stem = f"{row:03d}_{col:03d}"
        png_path = out / f"{stem}.png"
        pol_path = out / f"{stem}.pol"

        if pol_path.exists():
            pol_paths.append(pol_path)
            continue

        rgb = source.fetch_rgb(t_lat_min, t_lon_min, t_lat_max, t_lon_max)
        if rgb is None:
            console.print(f"[yellow]  no imagery for tile {row},{col} — skipping[/yellow]")
            continue

        _write_png(rgb, png_path)
        _write_pol(pol_path, png_path.name, t_lat_min, t_lon_min, t_lat_max, t_lon_max)
        pol_paths.append(pol_path)

    console.print(f"  [green]{len(pol_paths)} orthophoto tiles[/green] → {out}")
    return pol_paths


def _tile_grid(
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    tile_deg: float,
) -> list[tuple[int, int, float, float, float, float]]:
    """Return list of (row, col, lat_min, lon_min, lat_max, lon_max) tiles."""
    n_rows = max(1, math.ceil((lat_max - lat_min) / tile_deg))
    n_cols = max(1, math.ceil((lon_max - lon_min) / tile_deg))
    tiles = []
    for row in range(n_rows):
        for col in range(n_cols):
            t_lat_min = lat_min + row * tile_deg
            t_lon_min = lon_min + col * tile_deg
            t_lat_max = min(lat_max, t_lat_min + tile_deg)
            t_lon_max = min(lon_max, t_lon_min + tile_deg)
            tiles.append((row, col, t_lat_min, t_lon_min, t_lat_max, t_lon_max))
    return tiles


def _write_png(rgb: np.ndarray, path: Path) -> None:
    from PIL import Image

    img = Image.fromarray(rgb.astype(np.uint8))
    # X-Plane requires power-of-2 texture dimensions; round down per axis
    w = 1 << (img.width.bit_length() - 1)
    h = 1 << (img.height.bit_length() - 1)
    img = img.resize((w, h), Image.Resampling.LANCZOS)
    img.save(path)


def _write_pol(
    path: Path,
    texture_name: str,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
) -> None:
    """Write an X-Plane draped polygon (.pol) descriptor."""
    import math

    centre_lat = (lat_min + lat_max) / 2
    h_m = _deg_to_m(lat_max - lat_min)
    w_m = _deg_to_m(lon_max - lon_min) * math.cos(math.radians(centre_lat))
    path.write_text(
        "A\n"
        "850\n"
        "DRAPED_POLYGON\n"
        "\n"
        f"TEXTURE_NOWRAP {texture_name}\n"
        f"SCALE {w_m:.1f} {h_m:.1f}\n"
        f"LOAD_CENTER {centre_lat:.6f} {(lon_min + lon_max) / 2:.6f} "
        f"{max(h_m, w_m):.0f} 2048\n"
        "LAYER_GROUP TERRAIN 1\n",
        encoding="utf-8",
    )


def _deg_to_m(deg: float) -> float:
    """Approximate degrees of latitude to metres."""
    return deg * 111_320.0


def _reflectance_to_uint8(arr: np.ndarray) -> np.ndarray:
    """Scale Sentinel-2 reflectance (0–10000 typical) to uint8 with gamma correction."""
    # Sentinel-2 L2A surface reflectance is scaled by 10000
    arr = arr / 10000.0
    arr = np.clip(arr, 0.0, 1.0)
    # Gamma 0.5 brightens the image to look natural
    arr = np.power(arr, 0.5)
    return (arr * 255).astype(np.uint8)


def make_source(name: str) -> OrthoSource:
    """Return an OrthoSource instance by name ('sentinel2' or 'naip')."""
    if name == "sentinel2":
        return Sentinel2Source()
    if name == "naip":
        return NAIPSource()
    raise ValueError(f"Unknown ortho source: {name!r}. Choose 'sentinel2' or 'naip'.")
