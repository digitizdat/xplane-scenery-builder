"""Task 3: ESA WorldCover land classifier tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from xplane_gen.landcover import (
    _ESA_CLASSES,
    _find_worldcover_tile,
    _vectorise,
    classify_tile,
)


def _make_mock_raster(
    data: np.ndarray,
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    tmp_path: Path,
) -> Path:
    """Write a tiny GeoTIFF with the given data array."""
    height, width = data.shape
    transform = from_bounds(lon_min, lat_min, lon_max, lat_max, width, height)
    tif = tmp_path / "worldcover.tif"
    with rasterio.open(
        tif,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=1,
        dtype=np.uint8,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(data.astype(np.uint8), 1)
    return tif


@pytest.fixture()
def simple_raster(tmp_path: Path) -> Path:
    """4×4 raster: top half tree_cover (10), bottom half cropland (40)."""
    data = np.array(
        [[10, 10, 10, 10], [10, 10, 10, 10], [40, 40, 40, 40], [40, 40, 40, 40]],
        dtype=np.uint8,
    )
    return _make_mock_raster(data, 47.0, -123.0, 48.0, -122.0, tmp_path)


def test_find_worldcover_tile_naming() -> None:
    path = _find_worldcover_tile(47.0, -122.5, 48.0, -121.5)
    assert "N45W123" in path
    assert path.endswith(".tif")


def test_find_worldcover_tile_southern_hemisphere() -> None:
    path = _find_worldcover_tile(-10.0, 30.0, -9.0, 31.0)
    assert "S12E030" in path


def test_vectorise_produces_features(simple_raster: Path) -> None:
    features = _vectorise(str(simple_raster), 47.0, -123.0, 48.0, -122.0)
    labels = {f["properties"]["label"] for f in features}
    assert "tree_cover" in labels
    assert "cropland" in labels


def test_vectorise_no_unknown_classes(simple_raster: Path) -> None:
    features = _vectorise(str(simple_raster), 47.0, -123.0, 48.0, -122.0)
    for f in features:
        assert f["properties"]["esa_class"] in _ESA_CLASSES


def test_vectorise_polygon_vertex_count(simple_raster: Path) -> None:
    features = _vectorise(str(simple_raster), 47.0, -123.0, 48.0, -122.0)
    for f in features:
        geom = f["geometry"]
        if geom["type"] == "Polygon":
            for ring in geom["coordinates"]:
                assert len(ring) <= 500


def test_classify_tile_writes_geojson(simple_raster: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    with patch("xplane_gen.landcover._find_worldcover_tile", return_value=str(simple_raster)):
        path = classify_tile(47.0, -123.0, 48.0, -122.0, str(out))

    assert path.exists()
    fc = json.loads(path.read_text())
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) > 0


def test_classify_tile_coverage(simple_raster: Path, tmp_path: Path) -> None:
    """Output polygons should cover the full tile area (>95%)."""
    from shapely.geometry import box, shape

    out = tmp_path / "out"
    with patch("xplane_gen.landcover._find_worldcover_tile", return_value=str(simple_raster)):
        path = classify_tile(47.0, -123.0, 48.0, -122.0, str(out))

    fc = json.loads(path.read_text())
    tile_area = box(-123.0, 47.0, -122.0, 48.0).area
    covered = sum(shape(f["geometry"]).area for f in fc["features"])
    assert covered / tile_area > 0.95


def test_all_esa_classes_have_mapping() -> None:
    for code, (label, _) in _ESA_CLASSES.items():
        assert isinstance(code, int)
        assert label
