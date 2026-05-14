"""Task 1 & 5: DsfWriter and build_overlay tests."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from shapely.geometry import LinearRing

from xplane_gen.dsf import (
    DsfWriter,
    ExclusionZone,
    ForestFeature,
    _building_height,
    _dsf_path,
    _ensure_ccw,
    _geom_to_coords,
    _polygon_area_m2,
    build_overlay,
)


def make_writer() -> DsfWriter:
    w = DsfWriter(tile_west=-123, tile_south=47)
    w.add_forest(
        ForestFeature(
            resource="lib/g8/trees_decid_cld_wet.for",
            density=0.8,
            coords=[(-122.6, 47.6), (-122.5, 47.6), (-122.5, 47.7), (-122.6, 47.7), (-122.6, 47.6)],
        )
    )
    w.add_exclusion(ExclusionZone("for", -123, 47, -122, 48))
    return w


def test_dsf_path() -> None:
    p = _dsf_path(Path("/out"), 47, -123)
    assert p == Path("/out/Earth nav data/+47-123/+47-123.dsf")


def test_render_contains_required_properties() -> None:
    text = make_writer()._render()
    assert "sim/overlay 1" in text
    assert "sim/west -123" in text
    assert "sim/south 47" in text
    assert "lib/g8/trees_decid_cld_wet.for" in text
    assert "sim/exclude_for" in text


def test_render_polygon_winding() -> None:
    """Outer ring coords must be CCW in rendered output."""
    cw_coords = [(-122.6, 47.7), (-122.5, 47.7), (-122.5, 47.6), (-122.6, 47.6), (-122.6, 47.7)]
    w = DsfWriter(tile_west=-123, tile_south=47)
    w.add_forest(ForestFeature("lib/g8/trees_decid_cld_wet.for", 0.5, cw_coords))
    w._render()
    ccw = _ensure_ccw(cw_coords)
    assert LinearRing(ccw).is_ccw


def test_ensure_ccw_already_ccw() -> None:
    ccw = [(-122.6, 47.6), (-122.5, 47.6), (-122.5, 47.7), (-122.6, 47.7), (-122.6, 47.6)]
    assert _ensure_ccw(ccw) == ccw


def test_ensure_ccw_flips_cw() -> None:
    cw = [(-122.6, 47.7), (-122.5, 47.7), (-122.5, 47.6), (-122.6, 47.6), (-122.6, 47.7)]
    assert LinearRing(_ensure_ccw(cw)).is_ccw


def test_compile_calls_dsftool(tmp_path: Path) -> None:
    writer = make_writer()
    fake_dsf = tmp_path / "Earth nav data" / "+47-123" / "+47-123.dsf"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        fake_dsf.parent.mkdir(parents=True, exist_ok=True)
        fake_dsf.write_bytes(b"XPLNEDSF")
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("xplane_gen.dsf.subprocess.run", side_effect=fake_run) as mock_run:
        result = writer.compile(tmp_path, dsftool=Path("/fake/DSFTool"))

    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/fake/DSFTool"
    assert "--text2dsf" in cmd
    assert result == fake_dsf


def test_compile_raises_on_dsftool_failure(tmp_path: Path) -> None:
    writer = make_writer()
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "bad input"

    with (
        patch("xplane_gen.dsf.subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="DSFTool failed"),
    ):
        writer.compile(tmp_path, dsftool=Path("/fake/DSFTool"))


def test_output_folder_structure(tmp_path: Path) -> None:
    writer = make_writer()
    fake_dsf = tmp_path / "Earth nav data" / "+47-123" / "+47-123.dsf"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        fake_dsf.parent.mkdir(parents=True, exist_ok=True)
        fake_dsf.write_bytes(b"XPLNEDSF")
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("xplane_gen.dsf.subprocess.run", side_effect=fake_run):
        dsf_path = writer.compile(tmp_path, dsftool=Path("/fake/DSFTool"))

    assert dsf_path.parent.name == "+47-123"
    assert dsf_path.parent.parent.name == "Earth nav data"
    assert dsf_path.stat().st_size > 0


SQUARE_GEOJSON = {
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
            "properties": {"building": "residential", "building:levels": "2"},
        }
    ],
}

FOREST_GEOJSON = {
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
            "properties": {"label": "tree_cover", "ndvi_density": 0.8},
        }
    ],
}


def test_build_overlay_dry_run_produces_text(tmp_path: Path) -> None:
    buildings = tmp_path / "buildings.geojson"
    landcover = tmp_path / "landcover.geojson"
    buildings.write_text(json.dumps(SQUARE_GEOJSON), encoding="utf-8")
    landcover.write_text(json.dumps(FOREST_GEOJSON), encoding="utf-8")

    result = build_overlay(-123, 47, buildings, landcover, tmp_path, dry_run=True)

    assert result.suffix == ".txt"
    text = result.read_text()
    assert "sim/overlay 1" in text
    assert "sim/exclude_obj" in text
    assert "sim/exclude_for" in text


def test_build_overlay_facade_exclusion_zones(tmp_path: Path) -> None:
    buildings = tmp_path / "buildings.geojson"
    buildings.write_text(json.dumps(SQUARE_GEOJSON), encoding="utf-8")

    result = build_overlay(-123, 47, buildings, None, tmp_path, dry_run=True)
    text = result.read_text()

    assert "sim/exclude_obj" in text
    assert "sim/exclude_fac" in text
    assert "sim/exclude_for" not in text


def test_build_overlay_forest_only(tmp_path: Path) -> None:
    landcover = tmp_path / "landcover.geojson"
    landcover.write_text(json.dumps(FOREST_GEOJSON), encoding="utf-8")

    result = build_overlay(-123, 47, None, landcover, tmp_path, dry_run=True)
    text = result.read_text()

    assert "sim/exclude_for" in text
    assert "sim/exclude_obj" not in text


def test_build_overlay_skips_non_vegetated(tmp_path: Path) -> None:
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
                            [-122.6, 47.6],
                        ]
                    ],
                },
                "properties": {"label": "water"},
            }
        ],
    }
    landcover = tmp_path / "landcover.geojson"
    landcover.write_text(json.dumps(water_fc), encoding="utf-8")

    result = build_overlay(-123, 47, None, landcover, tmp_path, dry_run=True)
    text = result.read_text()
    assert "POLYGON_DEF" not in text


def test_building_height_from_height_tag() -> None:
    assert _building_height({"height": "12.5"}) == 12.5
    assert _building_height({"height": "10m"}) == 10.0


def test_building_height_from_levels() -> None:
    assert _building_height({"building:levels": "3"}) == pytest.approx(10.5)


def test_building_height_heuristic() -> None:
    assert _building_height({"building": "residential"}) == 7.0
    assert _building_height({"building": "unknown"}) == 8.0


def test_polygon_area_m2_reasonable() -> None:
    # ~0.1° × 0.1° square near Seattle ≈ 78 km² → ~78e6 m²... actually ~78 km²
    # 0.1° lat ≈ 11,132 m; 0.1° lon at 47.6° ≈ 7,530 m → area ≈ 83.8e6 m²
    coords = [(-122.6, 47.6), (-122.5, 47.6), (-122.5, 47.7), (-122.6, 47.7)]
    area = _polygon_area_m2(coords)
    assert 70e6 < area < 100e6


def test_geom_to_coords_polygon() -> None:
    geom = {"type": "Polygon", "coordinates": [[[1.0, 2.0], [3.0, 4.0], [1.0, 2.0]]]}
    coords = _geom_to_coords(geom)
    assert coords == [(1.0, 2.0), (3.0, 4.0), (1.0, 2.0)]


def test_geom_to_coords_multipolygon() -> None:
    geom = {
        "type": "MultiPolygon",
        "coordinates": [[[[1.0, 2.0], [3.0, 4.0], [1.0, 2.0]]]],
    }
    coords = _geom_to_coords(geom)
    assert coords[0] == (1.0, 2.0)
