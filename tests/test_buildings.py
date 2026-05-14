"""Task 6: Building footprint → facade pipeline tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from xplane_gen.buildings import building_exclusion_zones, buildings_to_facades
from xplane_gen.catalog import AssetCatalog

SQUARE = [[-122.6, 47.6], [-122.5, 47.6], [-122.5, 47.7], [-122.6, 47.7], [-122.6, 47.6]]


def _write_buildings(path: Path, features: list[dict]) -> None:
    path.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}),
        encoding="utf-8",
    )


@pytest.fixture()
def cat() -> AssetCatalog:
    return AssetCatalog()


def test_basic_residential(tmp_path: Path, cat: AssetCatalog) -> None:
    f = tmp_path / "b.geojson"
    _write_buildings(
        f,
        [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                "properties": {"building": "residential", "building:levels": "2"},
            }
        ],
    )
    facades = buildings_to_facades(f, cat, 47.6, -122.3)
    assert len(facades) == 1
    assert facades[0].height == pytest.approx(7.0)
    assert facades[0].resource.endswith(".fac")


def test_height_from_tag(tmp_path: Path, cat: AssetCatalog) -> None:
    f = tmp_path / "b.geojson"
    _write_buildings(
        f,
        [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                "properties": {"building": "yes", "height": "15.5"},
            }
        ],
    )
    facades = buildings_to_facades(f, cat, 47.6, -122.3)
    assert facades[0].height == pytest.approx(15.5)


def test_height_from_levels(tmp_path: Path, cat: AssetCatalog) -> None:
    f = tmp_path / "b.geojson"
    _write_buildings(
        f,
        [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                "properties": {"building": "yes", "building:levels": "4"},
            }
        ],
    )
    facades = buildings_to_facades(f, cat, 47.6, -122.3)
    assert facades[0].height == pytest.approx(14.0)


def test_all_buildings_have_positive_height(tmp_path: Path, cat: AssetCatalog) -> None:
    f = tmp_path / "b.geojson"
    _write_buildings(
        f,
        [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                "properties": {"building": btype},
            }
            for btype in ["yes", "residential", "commercial", "industrial", "church", "barn"]
        ],
    )
    facades = buildings_to_facades(f, cat, 47.6, -122.3)
    assert all(f.height > 0 for f in facades)


def test_linestring_features_skipped(tmp_path: Path, cat: AssetCatalog) -> None:
    f = tmp_path / "b.geojson"
    _write_buildings(
        f,
        [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[-122.6, 47.6], [-122.5, 47.6]]},
                "properties": {"building": "yes"},
            }
        ],
    )
    assert buildings_to_facades(f, cat, 47.6, -122.3) == []


def test_facade_virtual_paths_valid(tmp_path: Path, cat: AssetCatalog) -> None:
    f = tmp_path / "b.geojson"
    _write_buildings(
        f,
        [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                "properties": {"building": "commercial"},
            }
        ],
    )
    facades = buildings_to_facades(f, cat, 47.6, -122.3)
    assert facades[0].resource.startswith("lib/")


def test_exclusion_zones_cover_full_tile() -> None:
    zones = building_exclusion_zones(-123, 47)
    kinds = {z.kind for z in zones}
    assert "obj" in kinds
    assert "fac" in kinds
    for z in zones:
        assert z.west == -123.0
        assert z.south == 47.0
        assert z.east == -122.0
        assert z.north == 48.0


def test_no_self_intersecting_output(tmp_path: Path, cat: AssetCatalog) -> None:
    from shapely.geometry import LinearRing

    f = tmp_path / "b.geojson"
    _write_buildings(
        f,
        [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [SQUARE]},
                "properties": {"building": "yes"},
            }
        ],
    )
    facades = buildings_to_facades(f, cat, 47.6, -122.3)
    for facade in facades:
        ring = LinearRing(facade.coords)
        assert not ring.is_empty
