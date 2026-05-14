"""Task 4: Asset catalog tests."""

from __future__ import annotations

import pytest

from xplane_gen.catalog import AssetCatalog, _size_bucket


@pytest.fixture()
def cat() -> AssetCatalog:
    return AssetCatalog()


# ── size bucket ──────────────────────────────────────────────────────────────


def test_size_bucket_small() -> None:
    assert _size_bucket(50.0) == "small"


def test_size_bucket_medium() -> None:
    assert _size_bucket(500.0) == "medium"


def test_size_bucket_large() -> None:
    assert _size_bucket(2000.0) == "large"


def test_size_bucket_boundaries() -> None:
    assert _size_bucket(199.9) == "small"
    assert _size_bucket(200.0) == "medium"
    assert _size_bucket(1000.0) == "medium"
    assert _size_bucket(1000.1) == "large"


# ── climate zone ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "lat,expected",
    [
        (0.0, "tropical"),
        (51.5, "continental"),  # London — above 50° in lat-band model
        (47.6, "temperate"),  # Seattle
        (60.0, "continental"),  # Helsinki
        (75.0, "polar"),  # Arctic
        (-75.0, "polar"),  # Antarctic
        (25.0, "arid"),  # Riyadh
        (-30.0, "arid"),  # Southern hemisphere arid
    ],
)
def test_climate_zone(cat: AssetCatalog, lat: float, expected: str) -> None:
    assert cat.get_climate_zone(lat) == expected


# ── get_facade ────────────────────────────────────────────────────────────────


def test_get_facade_known_type(cat: AssetCatalog) -> None:
    path = cat.get_facade("residential", 150.0, 47.6, -122.3)
    assert path.startswith("lib/")
    assert path.endswith(".fac")


def test_get_facade_unknown_type_falls_back_to_generic(cat: AssetCatalog) -> None:
    path = cat.get_facade("unknown_building_type", 500.0, 47.6, -122.3)
    assert "generic" in path


def test_get_facade_all_osm_types(cat: AssetCatalog) -> None:
    """Every OSM building tag must resolve without KeyError."""
    from xplane_gen.catalog import _OSM_BUILDING_TYPE

    for tag in _OSM_BUILDING_TYPE:
        path = cat.get_facade(tag, 300.0, 47.6, -122.3)
        assert path


# ── get_forest ────────────────────────────────────────────────────────────────


def test_get_forest_tree_cover_temperate(cat: AssetCatalog) -> None:
    path = cat.get_forest("tree_cover", 47.6, -122.3)
    assert "decid" in path or "evgr" in path or "tropical" in path


def test_get_forest_tropical(cat: AssetCatalog) -> None:
    path = cat.get_forest("tree_cover", 5.0, 100.0)
    assert "tropical" in path


def test_get_forest_unknown_label_falls_back(cat: AssetCatalog) -> None:
    """Unknown ESA label should fall back to tree_cover rather than raise."""
    path = cat.get_forest("built_up", 47.6, -122.3)
    assert path.startswith("lib/")


def test_get_forest_all_labels(cat: AssetCatalog) -> None:
    """Every forest label in catalog must resolve for all climate zones."""
    for label in cat._forests:
        for lat in [5.0, 25.0, 47.6, 60.0, 75.0]:
            path = cat.get_forest(label, lat, 0.0)
            assert path


# ── catalog completeness ──────────────────────────────────────────────────────


def test_all_facade_entries_non_empty(cat: AssetCatalog) -> None:
    for btype, sizes in cat._facades.items():
        for size, vpath in sizes.items():
            assert vpath, f"Empty path for facades/{btype}/{size}"


def test_all_forest_entries_non_empty(cat: AssetCatalog) -> None:
    for label, zones in cat._forests.items():
        for zone, vpath in zones.items():
            assert vpath, f"Empty path for forests/{label}/{zone}"
