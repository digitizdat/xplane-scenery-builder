"""Task 2: OSM data fetcher tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xplane_gen.osm import _is_building, _is_landuse, _is_road, fetch_tile


def _make_node(lon: float, lat: float) -> MagicMock:
    n = MagicMock()
    n.lon = lon
    n.lat = lat
    return n


def _make_way(tags: dict[str, str], coords: list[tuple[float, float]]) -> MagicMock:
    way = MagicMock()
    way.tags = tags
    way.nodes = [_make_node(lon, lat) for lon, lat in coords]
    return way


def _make_result(ways: list[MagicMock]) -> MagicMock:
    result = MagicMock()
    result.ways = ways
    return result


SQUARE = [(-122.5, 47.5), (-122.4, 47.5), (-122.4, 47.6), (-122.5, 47.6), (-122.5, 47.5)]


@pytest.fixture()
def mock_result() -> MagicMock:
    return _make_result(
        [
            _make_way({"building": "yes", "building:levels": "3"}, SQUARE),
            _make_way({"landuse": "forest"}, SQUARE),
            _make_way({"highway": "residential"}, [(-122.5, 47.5), (-122.4, 47.5)]),
            _make_way({"natural": "wood"}, SQUARE),
        ]
    )


def test_fetch_tile_writes_three_files(tmp_path: Path, mock_result: MagicMock) -> None:
    with patch("xplane_gen.osm._query_overpass", return_value=mock_result):
        paths = fetch_tile(47.5, -122.5, 47.6, -122.4, str(tmp_path))

    assert set(paths.keys()) == {"buildings", "landuse", "roads"}
    for p in paths.values():
        assert p.exists()


def test_buildings_geojson_valid(tmp_path: Path, mock_result: MagicMock) -> None:
    with patch("xplane_gen.osm._query_overpass", return_value=mock_result):
        paths = fetch_tile(47.5, -122.5, 47.6, -122.4, str(tmp_path))

    fc = json.loads(paths["buildings"].read_text())
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) == 1
    feat = fc["features"][0]
    assert feat["geometry"]["type"] == "Polygon"
    assert feat["properties"]["building"] == "yes"


def test_landuse_includes_natural_wood(tmp_path: Path, mock_result: MagicMock) -> None:
    with patch("xplane_gen.osm._query_overpass", return_value=mock_result):
        paths = fetch_tile(47.5, -122.5, 47.6, -122.4, str(tmp_path))

    fc = json.loads(paths["landuse"].read_text())
    # landuse=forest + natural=wood = 2 features
    assert len(fc["features"]) == 2


def test_roads_linestring(tmp_path: Path, mock_result: MagicMock) -> None:
    with patch("xplane_gen.osm._query_overpass", return_value=mock_result):
        paths = fetch_tile(47.5, -122.5, 47.6, -122.4, str(tmp_path))

    fc = json.loads(paths["roads"].read_text())
    assert len(fc["features"]) == 1
    assert fc["features"][0]["geometry"]["type"] == "LineString"


def test_tags_preserved(tmp_path: Path, mock_result: MagicMock) -> None:
    with patch("xplane_gen.osm._query_overpass", return_value=mock_result):
        paths = fetch_tile(47.5, -122.5, 47.6, -122.4, str(tmp_path))

    fc = json.loads(paths["buildings"].read_text())
    assert fc["features"][0]["properties"]["building:levels"] == "3"


def test_predicates() -> None:
    assert _is_building({"building": "yes"})
    assert not _is_building({"landuse": "forest"})
    assert _is_landuse({"landuse": "forest"})
    assert _is_landuse({"natural": "wood"})
    assert not _is_landuse({"building": "yes"})
    assert _is_road({"highway": "residential"})
    assert not _is_road({"building": "yes"})


def test_retry_on_overpass_error(tmp_path: Path) -> None:
    import overpy

    good_result = _make_result([_make_way({"building": "yes"}, SQUARE)])
    call_count = 0

    def flaky_query(query: str) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise overpy.exception.OverPyException()
        return good_result

    with (
        patch("xplane_gen.osm.time.sleep"),
        patch("overpy.Overpass.query", side_effect=flaky_query),
    ):
        paths = fetch_tile(47.5, -122.5, 47.6, -122.4, str(tmp_path))

    assert call_count == 2
    fc = json.loads(paths["buildings"].read_text())
    assert len(fc["features"]) == 1
