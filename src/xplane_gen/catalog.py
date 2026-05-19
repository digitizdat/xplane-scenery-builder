"""Asset catalog: scores facades by physical attributes, maps forests by climate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()

_CATALOG_PATH = Path(__file__).parent.parent.parent / "assets" / "catalog.yaml"
_FACADE_ATTRS_PATH = Path(__file__).parent.parent.parent / "assets" / "facade_attributes.yaml"

# Size bucket thresholds in m²
_SMALL = 200.0
_LARGE = 1000.0

# Simplified Köppen zone boundaries (lat → zone)
_KOPPEN_LAT_ZONES: list[tuple[float, float, str]] = [
    (-90.0, -66.5, "polar"),
    (66.5, 90.0, "polar"),
    (-23.5, 23.5, "tropical"),
    (-35.0, -23.5, "arid"),
    (23.5, 35.0, "arid"),
    (-50.0, -35.0, "temperate"),
    (35.0, 50.0, "temperate"),
    (-66.5, -50.0, "continental"),
    (50.0, 66.5, "continental"),
]


class AssetCatalog:
    def __init__(
        self,
        catalog_path: Path = _CATALOG_PATH,
        facade_attrs_path: Path = _FACADE_ATTRS_PATH,
    ) -> None:
        with catalog_path.open(encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f)
        self._defaults: dict[str, str] = data["facade_defaults"]
        self._forests: dict[str, dict[str, str]] = data["forests"]

        # Load facade physical attributes
        self._facade_attrs: dict[str, dict[str, Any]] = {}
        if facade_attrs_path.exists():
            with facade_attrs_path.open(encoding="utf-8") as f:
                self._facade_attrs = yaml.safe_load(f) or {}

    def get_facade(
        self,
        building_type: str,  # noqa: ARG002 — kept for API compat
        footprint_area_m2: float,
        lat: float,  # noqa: ARG002
        lon: float,  # noqa: ARG002
        stories: int | None = None,
        material: str | None = None,
        wall_color: str | None = None,
        window_density: str | None = None,
        roof_type: str | None = None,
    ) -> str:
        """Select the best-matching facade based on physical attributes.

        Falls back to size-based default when no attributes or no facade_attrs.
        """
        if not self._facade_attrs or (stories is None and material is None):
            return self._defaults[_size_bucket(footprint_area_m2)]

        best_path = ""
        best_score = -1.0

        for fac_path, attrs in self._facade_attrs.items():
            if not attrs:
                continue
            score = _score_facade(attrs, stories, material, wall_color, window_density, roof_type)
            if score > best_score:
                best_score = score
                best_path = fac_path

        if best_path:
            return best_path
        return self._defaults[_size_bucket(footprint_area_m2)]

    def get_forest(self, esa_label: str, lat: float, lon: float) -> str:  # noqa: ARG002
        zone = self.get_climate_zone(lat)
        forests = self._forests.get(esa_label)
        if forests is None:
            return self._forests["tree_cover"][zone]
        return forests[zone]

    def get_climate_zone(self, lat: float) -> str:
        for lat_min, lat_max, zone in _KOPPEN_LAT_ZONES:
            if lat_min <= lat < lat_max:
                return zone
        return "temperate"

    def validate_catalog(self, xplane_path: Path) -> None:
        """Check that all virtual paths resolve in X-Plane's library system."""
        lib_root = xplane_path / "Resources" / "default scenery"
        exports = _parse_library_exports(lib_root)

        ok = True
        for size, vpath in self._defaults.items():
            found = vpath in exports
            status = "✓" if found else "✗"
            if not found:
                ok = False
            console.print(f"  [{status}] defaults/{size}: {vpath}")
        for label, zones in self._forests.items():
            for zone, vpath in zones.items():
                found = vpath in exports
                status = "✓" if found else "✗"
                if not found:
                    ok = False
                console.print(f"  [{status}] forests/{label}/{zone}: {vpath}")
        # Check facade_attributes entries
        missing = 0
        for vpath in self._facade_attrs:
            if vpath not in exports:
                missing += 1
        if missing:
            console.print(
                f"  [yellow]{missing}/{len(self._facade_attrs)} "
                f"facade_attributes entries not in library[/yellow]"
            )
        if ok and missing == 0:
            console.print("[green]All catalog entries validated.[/green]")
        elif ok:
            console.print(
                "[yellow]Core catalog OK; some facade_attributes may vary by version.[/yellow]"
            )
        else:
            console.print(
                "[yellow]Some entries not found — paths may differ by X-Plane version.[/yellow]"
            )


def _score_facade(
    attrs: dict[str, Any],
    stories: int | None,
    material: str | None,
    wall_color: str | None,
    window_density: str | None,
    roof_type: str | None,
) -> float:
    """Score a facade's attributes against desired building attributes.

    Higher score = better match. Stories fit is weighted heaviest.
    """
    score = 0.0

    # Stories fit (weight: 3) — must be within facade's range
    if stories is not None:
        fac_min = attrs.get("stories_min", 1)
        fac_max = attrs.get("stories_max", 60)
        if fac_min <= stories <= fac_max:
            # Prefer facades whose range is tighter around the target
            range_size = fac_max - fac_min + 1
            score += 3.0 / max(1, range_size / 5)
        else:
            # Hard penalty for out-of-range
            score -= 5.0

    # Material match (weight: 2)
    if material:
        if attrs.get("wall_material") == material:
            score += 2.0
        elif attrs.get("wall_material") == "mixed":
            score += 0.5

    # Wall color (weight: 1)
    if wall_color and attrs.get("wall_color") == wall_color:
        score += 1.0

    # Window density (weight: 1.5)
    if window_density and attrs.get("window_density") == window_density:
        score += 1.5

    # Roof type (weight: 0.5)
    if roof_type and attrs.get("roof_type") == roof_type:
        score += 0.5

    return score


def _parse_library_exports(lib_root: Path) -> set[str]:
    """Parse all library.txt files and return the set of exported virtual paths."""
    exports: set[str] = set()
    for lib_txt in lib_root.rglob("library.txt"):
        for line in lib_txt.read_text(encoding="utf-8", errors="ignore").splitlines():
            if not line.startswith("EXPORT"):
                continue
            parts = line.split()
            for part in parts[1:]:
                if "/" in part and (part.endswith(".for") or part.endswith(".fac")):
                    exports.add(part)
                    break
    return exports


def _size_bucket(area_m2: float) -> str:
    if area_m2 < _SMALL:
        return "small"
    if area_m2 <= _LARGE:
        return "medium"
    return "large"
