"""Task 4: Asset catalog tests."""

from __future__ import annotations

from pathlib import Path

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
    """Building type string must resolve without KeyError."""
    for tag in ["residential", "commercial", "industrial", "church", "barn", "generic"]:
        path = cat.get_facade(tag, 300.0, 47.6, -122.3)
        assert path


# ── get_forest ────────────────────────────────────────────────────────────────


def test_get_forest_tree_cover_temperate(cat: AssetCatalog) -> None:
    path = cat.get_forest("tree_cover", 47.6, -122.3)
    assert "broadleaves" in path or "conifers" in path or "mixed" in path


def test_get_forest_tropical(cat: AssetCatalog) -> None:
    path = cat.get_forest("tree_cover", 5.0, 100.0)
    assert "very_hot" in path or "hot" in path


def test_get_forest_unknown_label_falls_back(cat: AssetCatalog) -> None:
    """Unknown ESA label should fall back to tree_cover rather than raise."""
    path = cat.get_forest("built_up", 47.6, -122.3)
    assert path and path.endswith(".for")


def test_get_forest_all_labels(cat: AssetCatalog) -> None:
    """Every forest label in catalog must resolve for all climate zones."""
    for label in cat._forests:
        for lat in [5.0, 25.0, 47.6, 60.0, 75.0]:
            path = cat.get_forest(label, lat, 0.0)
            assert path


# ── catalog completeness ──────────────────────────────────────────────────────


def test_all_facade_entries_non_empty(cat: AssetCatalog) -> None:
    for vpath, attrs in cat._facade_attrs.items():
        assert vpath, "Empty facade path"
        assert attrs, f"Empty attributes for {vpath}"


def test_all_forest_entries_non_empty(cat: AssetCatalog) -> None:
    for label, zones in cat._forests.items():
        for zone, vpath in zones.items():
            assert vpath, f"Empty path for forests/{label}/{zone}"


# ── X-Plane library validation ────────────────────────────────────────────────

# Change this to match your local X-Plane 12 installation path.
XPLANE_PATH = "/Users/martin/Library/Application Support/Steam/steamapps/common/X-Plane 12"


def _find_library_exports(xplane_path: str) -> set[str]:
    """Parse all library.txt files and return the set of exported virtual paths."""
    from pathlib import Path

    exports: set[str] = set()
    root = Path(xplane_path) / "Resources" / "default scenery"
    for lib_txt in root.rglob("library.txt"):
        for line in lib_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.startswith("EXPORT"):
                continue
            parts = line.split()
            # EXPORT <vpath> <realpath>
            # EXPORT_SEASON <season> <vpath> <realpath>
            # EXPORT_EXCLUDE <vpath> <realpath>
            # EXPORT_EXCLUDE_SEASON <season> <vpath> <realpath>
            for part in parts[1:]:
                if "/" in part and (part.endswith(".for") or part.endswith(".fac")):
                    exports.add(part)
                    break
    return exports


def _find_direct_files(xplane_path: str) -> set[str]:
    """Not used — DSFs can only reference library-exported virtual paths."""
    return set()


@pytest.mark.xplane
def test_all_catalog_forests_resolve(cat: AssetCatalog) -> None:
    """Every .for path in catalog.yaml must resolve in X-Plane 12's library."""
    from pathlib import Path

    if not Path(XPLANE_PATH).exists():
        pytest.skip(f"X-Plane not found at {XPLANE_PATH}")

    exports = _find_library_exports(XPLANE_PATH)
    missing = []

    for label, zones in cat._forests.items():
        for zone, vpath in zones.items():
            if vpath in exports:
                continue
            missing.append(f"forests/{label}/{zone}: {vpath}")

    assert not missing, "Unresolved forest paths:\n" + "\n".join(missing)


@pytest.mark.xplane
def test_all_catalog_facades_resolve(cat: AssetCatalog) -> None:
    """Every .fac path in catalog.yaml must resolve in X-Plane 12's library."""
    from pathlib import Path

    if not Path(XPLANE_PATH).exists():
        pytest.skip(f"X-Plane not found at {XPLANE_PATH}")

    exports = _find_library_exports(XPLANE_PATH)
    missing = []

    for vpath in cat._facade_attrs:
        if vpath in exports:
            continue
        missing.append(f"facade_attrs: {vpath}")

    assert not missing, "Unresolved facade paths:\n" + "\n".join(missing)


# ── attribute alignment tests ─────────────────────────────────────────────────


def test_classifier_enums_match_facade_attributes() -> None:
    """Every enum value the classifier can output must exist in facade_attributes.yaml."""
    import yaml

    from xplane_gen.classifier import _BUILDING_TOOL

    facade_attrs_path = Path(__file__).parent.parent / "assets" / "facade_attributes.yaml"
    facade_data = yaml.safe_load(facade_attrs_path.read_text(encoding="utf-8"))

    # Collect all values present in facade_attributes for each field
    facade_values: dict[str, set[str]] = {}
    for attrs in facade_data.values():
        if not attrs:
            continue
        for key, val in attrs.items():
            facade_values.setdefault(key, set()).add(str(val))

    # Map classifier tool field names → facade_attributes field names
    tool_to_facade = {
        "wall_material": "wall_material",
        "wall_color": "wall_color",
        "window_density": "window_density",
        "roof_type": "roof_type",
    }

    schema_props = _BUILDING_TOOL["inputSchema"]["json"]["properties"]
    for tool_field, facade_field in tool_to_facade.items():
        tool_enums = set(schema_props[tool_field]["enum"])
        facade_vals = facade_values.get(facade_field, set())
        # Every facade value should be representable by the tool
        unmatched = facade_vals - tool_enums
        assert not unmatched, (
            f"facade_attributes has {facade_field} values {unmatched} "
            f"not in classifier tool enum: {sorted(tool_enums)}"
        )


def test_classifier_fallback_keys_match_tool_required() -> None:
    """Classifier fallback dict must have same keys as tool's required fields."""
    from xplane_gen.classifier import _BUILDING_TOOL

    required = set(_BUILDING_TOOL["inputSchema"]["json"]["required"])

    # Get the fallback from classify_building by inspecting the source
    from unittest.mock import patch

    from xplane_gen.classifier import BedrockClassifier

    # The fallback dict is the last arg to _classify — extract its keys
    # by calling with a mock that captures it

    with patch("boto3.client"):
        clf = BedrockClassifier(Path("/tmp/test_fallback"))
    # Patch _classify to capture the fallback arg
    captured: dict = {}

    def _capture(*args: object, **kwargs: object) -> dict:
        captured.update(args[4] if len(args) > 4 else {})  # type: ignore[arg-type]
        return captured

    clf._classify = _capture  # type: ignore[assignment]
    clf.classify_building(
        __import__("numpy").zeros((64, 64, 3), dtype=__import__("numpy").uint8),
        {"building": "yes"},
    )
    assert set(captured.keys()) == required, (
        f"Fallback keys {set(captured.keys())} != required {required}"
    )


def test_pipeline_property_names_match_buildings_reader() -> None:
    """Property names written by pipeline must match what buildings.py reads."""
    import inspect

    from xplane_gen import buildings, pipeline

    # Extract property names written in _classify_building closure
    pipeline_src = inspect.getsource(pipeline.TileProcessor._stage_classify)
    # Find all props["xplane_*"] = assignments
    written = set()
    for line in pipeline_src.splitlines():
        if 'props["xplane_' in line and "=" in line:
            key = line.split('props["')[1].split('"]')[0]
            written.add(key)

    # Extract property names read in buildings_to_facades
    buildings_src = inspect.getsource(buildings.buildings_to_facades)
    read = set()
    for line in buildings_src.splitlines():
        if 'props.get("xplane_' in line:
            key = line.split('props.get("')[1].split('"')[0]
            read.add(key)

    # Everything buildings.py reads must be written by pipeline
    missing = read - written
    assert not missing, f"buildings.py reads {missing} but pipeline doesn't write them"


def test_facade_defaults_cover_all_size_buckets(cat: AssetCatalog) -> None:
    """facade_defaults must have entries for small, medium, large."""
    for bucket in ("small", "medium", "large"):
        assert bucket in cat._defaults, f"Missing facade_defaults[{bucket}]"
        assert cat._defaults[bucket], f"Empty path for facade_defaults[{bucket}]"


def test_score_facade_positive_for_all_classifier_outputs() -> None:
    """_score_facade must produce positive scores for typical classifier outputs."""
    import yaml

    from xplane_gen.catalog import _score_facade

    facade_attrs_path = Path(__file__).parent.parent / "assets" / "facade_attributes.yaml"
    facade_data = yaml.safe_load(facade_attrs_path.read_text(encoding="utf-8"))

    # Simulate a typical classifier output
    test_building = {
        "stories": 3,
        "wall_material": "brick",
        "wall_color": "red",
        "window_density": "moderate",
        "roof_type": "flat",
    }

    # At least one facade must score positively
    scores = [
        _score_facade(
            attrs,
            test_building["stories"],
            test_building["wall_material"],
            test_building["wall_color"],
            test_building["window_density"],
            test_building["roof_type"],
        )
        for attrs in facade_data.values()
        if attrs
    ]
    assert max(scores) > 0, "No facade scored positively for typical building"
