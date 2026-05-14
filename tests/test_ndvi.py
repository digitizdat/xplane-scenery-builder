"""Task 7: Sentinel-2 NDVI → forest density tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from xplane_gen.ndvi import (
    _CLOUD_SCL,
    _ndvi_to_density,
    annotate_forest_density,
)


def _make_ndvi_raster(
    data: np.ndarray,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    tmp_path: Path,
) -> Path:
    h, w = data.shape
    tif = tmp_path / "ndvi.tif"
    with rasterio.open(
        tif,
        "w",
        driver="GTiff",
        height=h,
        width=w,
        count=1,
        dtype=np.float32,
        crs="EPSG:4326",
        transform=from_bounds(lon_min, lat_min, lon_max, lat_max, w, h),
    ) as dst:
        dst.write(data.astype(np.float32), 1)
    return tif


FOREST_FC = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-122.6, 47.6],
                        [-122.5, 47.6],
                        [-122.5, 47.7],
                        [-122.6, 47.7],
                        [-122.6, 47.6],
                    ]
                ],
            },
            "properties": {"label": "tree_cover"},
        }
    ],
}


# ── _ndvi_to_density ──────────────────────────────────────────────────────────


def test_ndvi_to_density_range() -> None:
    assert _ndvi_to_density(0.0) == pytest.approx(0.2)  # below min → clamped
    assert _ndvi_to_density(1.0) == pytest.approx(1.0)  # above max → clamped
    assert 0.2 <= _ndvi_to_density(0.6) <= 1.0


def test_ndvi_to_density_midpoint() -> None:
    mid_ndvi = (0.3 + 0.9) / 2  # 0.6
    mid_density = (0.2 + 1.0) / 2  # 0.6
    assert _ndvi_to_density(mid_ndvi) == pytest.approx(mid_density)


def test_ndvi_to_density_dense_forest() -> None:
    assert _ndvi_to_density(0.75) > 0.6


# ── annotate_forest_density ───────────────────────────────────────────────────


def _mock_fetch_ndvi(dense: bool = True) -> tuple[np.ndarray, object, object]:
    """Return a fake (ndvi_array, transform, crs) tuple."""
    from rasterio.crs import CRS

    val = 0.8 if dense else 0.35
    data = np.full((10, 10), val, dtype=np.float32)
    transform = from_bounds(-123.0, 47.0, -122.0, 48.0, 10, 10)
    return data, transform, CRS.from_epsg(4326)


def test_annotate_adds_ndvi_density(tmp_path: Path) -> None:
    lc = tmp_path / "landcover.geojson"
    lc.write_text(json.dumps(FOREST_FC), encoding="utf-8")

    with patch("xplane_gen.ndvi._fetch_ndvi", return_value=_mock_fetch_ndvi()):
        annotate_forest_density(lc, 47.0, -123.0, 48.0, -122.0)

    fc = json.loads(lc.read_text())
    assert "ndvi_density" in fc["features"][0]["properties"]


def test_annotate_density_in_range(tmp_path: Path) -> None:
    lc = tmp_path / "landcover.geojson"
    lc.write_text(json.dumps(FOREST_FC), encoding="utf-8")

    with patch("xplane_gen.ndvi._fetch_ndvi", return_value=_mock_fetch_ndvi()):
        annotate_forest_density(lc, 47.0, -123.0, 48.0, -122.0)

    fc = json.loads(lc.read_text())
    density = fc["features"][0]["properties"]["ndvi_density"]
    assert 0.0 <= density <= 1.0


def test_annotate_dense_forest_high_density(tmp_path: Path) -> None:
    lc = tmp_path / "landcover.geojson"
    lc.write_text(json.dumps(FOREST_FC), encoding="utf-8")

    with patch("xplane_gen.ndvi._fetch_ndvi", return_value=_mock_fetch_ndvi(dense=True)):
        annotate_forest_density(lc, 47.0, -123.0, 48.0, -122.0)

    fc = json.loads(lc.read_text())
    assert fc["features"][0]["properties"]["ndvi_density"] > 0.6


def test_annotate_no_scene_leaves_default(tmp_path: Path) -> None:
    lc = tmp_path / "landcover.geojson"
    lc.write_text(json.dumps(FOREST_FC), encoding="utf-8")

    with patch("xplane_gen.ndvi._fetch_ndvi", return_value=None):
        annotate_forest_density(lc, 47.0, -123.0, 48.0, -122.0)

    fc = json.loads(lc.read_text())
    # No ndvi_density added when no scene available
    assert "ndvi_density" not in fc["features"][0]["properties"]


def test_annotate_skips_non_vegetated(tmp_path: Path) -> None:
    water_fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-122.6, 47.6],
                            [-122.5, 47.6],
                            [-122.5, 47.7],
                            [-122.6, 47.7],
                            [-122.6, 47.6],
                        ]
                    ],
                },
                "properties": {"label": "water"},
            }
        ],
    }
    lc = tmp_path / "landcover.geojson"
    lc.write_text(json.dumps(water_fc), encoding="utf-8")

    fetch_mock = MagicMock()
    with patch("xplane_gen.ndvi._fetch_ndvi", fetch_mock):
        annotate_forest_density(lc, 47.0, -123.0, 48.0, -122.0)

    fetch_mock.assert_not_called()


def test_cloud_scl_values_excluded() -> None:
    assert 8 in _CLOUD_SCL
    assert 9 in _CLOUD_SCL
    assert 10 in _CLOUD_SCL
    assert 4 not in _CLOUD_SCL  # vegetation — should not be masked
