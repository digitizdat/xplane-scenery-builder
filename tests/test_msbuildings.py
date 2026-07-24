"""Tests for msbuildings: state mapping, MS-vs-OSM de-dup, and merge idempotency."""

import json
from pathlib import Path

import pytest
from shapely.geometry import Polygon, mapping

from xplane_gen.msbuildings import (
    MsBuildingsError,
    dedup_against_osm,
    merge_into_buildings,
    state_filename,
)


def _square(lon: float, lat: float, size: float = 0.0005) -> Polygon:
    return Polygon(
        [(lon, lat), (lon + size, lat), (lon + size, lat + size), (lon, lat + size), (lon, lat)]
    )


# ── state name -> filename ──────────────────────────────────────────────


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("West Virginia", "WestVirginia"),
        ("New York", "NewYork"),
        ("District of Columbia", "DistrictofColumbia"),
        ("Ohio", "Ohio"),
    ],
)
def test_state_filename(state: str, expected: str) -> None:
    assert state_filename(state) == expected


def test_state_filename_rejects_non_us() -> None:
    with pytest.raises(MsBuildingsError):
        state_filename("Ontario")


# ── de-dup ────────────────────────────────────────────────────────────────


def test_dedup_drops_overlapping_ms() -> None:
    osm = [_square(-79.83, 38.42)]
    ms = [_square(-79.83, 38.42)]  # same location -> duplicate
    assert dedup_against_osm(osm, ms) == []


def test_dedup_keeps_distant_ms() -> None:
    osm = [_square(-79.83, 38.42)]
    far = _square(-79.80, 38.44)  # well outside the tolerance
    kept = dedup_against_osm(osm, [far])
    assert len(kept) == 1


def test_dedup_no_osm_keeps_all() -> None:
    ms = [_square(-79.83, 38.42), _square(-79.80, 38.44)]
    assert len(dedup_against_osm([], ms)) == 2


def test_dedup_mixed() -> None:
    osm = [_square(-79.83, 38.42)]
    ms = [_square(-79.83, 38.42), _square(-79.70, 38.10)]  # one dup, one gap-filler
    assert len(dedup_against_osm(osm, ms)) == 1


# ── merge into buildings.geojson ───────────────────────────────────────────


def _write_buildings(path: Path, polys: list[Polygon]) -> None:
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "geometry": mapping(p), "properties": {"building": "yes"}}
            for p in polys
        ],
    }
    path.write_text(json.dumps(fc), encoding="utf-8")


def test_merge_adds_gap_fillers_and_tags_source(tmp_path: Path) -> None:
    b = tmp_path / "buildings.geojson"
    _write_buildings(b, [_square(-79.83, 38.42)])
    ms = [_square(-79.83, 38.42), _square(-79.70, 38.10)]  # dup + gap-filler

    added, dropped = merge_into_buildings(b, ms)
    assert (added, dropped) == (1, 1)

    fc = json.loads(b.read_text())
    sources = [f["properties"].get("xplane_source") for f in fc["features"]]
    assert sources.count("ms") == 1
    assert len(fc["features"]) == 2  # 1 OSM + 1 MS


def test_merge_is_idempotent(tmp_path: Path) -> None:
    b = tmp_path / "buildings.geojson"
    _write_buildings(b, [_square(-79.83, 38.42)])
    ms = [_square(-79.70, 38.10)]

    merge_into_buildings(b, ms)
    first = json.loads(b.read_text())["features"]
    merge_into_buildings(b, ms)  # re-run must not double the MS features
    second = json.loads(b.read_text())["features"]

    assert len(first) == len(second) == 2
    assert sum(f["properties"].get("xplane_source") == "ms" for f in second) == 1


def test_merge_preserves_osm(tmp_path: Path) -> None:
    b = tmp_path / "buildings.geojson"
    _write_buildings(b, [_square(-79.83, 38.42), _square(-79.82, 38.43)])
    merge_into_buildings(b, [])
    fc = json.loads(b.read_text())
    assert len(fc["features"]) == 2
    assert all(f["properties"].get("xplane_source") != "ms" for f in fc["features"])
