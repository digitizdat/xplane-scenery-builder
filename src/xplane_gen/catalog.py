"""Asset catalog: maps building type + climate zone → .fac/.for virtual paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from rich.console import Console

console = Console()

_CATALOG_PATH = Path(__file__).parent.parent.parent / "assets" / "catalog.yaml"

# Size bucket thresholds in m²
_SMALL = 200.0
_LARGE = 1000.0

# Simplified Köppen zone boundaries (lat/lon → zone string)
# Ordered from most specific to least; first match wins.
# Format: (lat_min, lat_max, zone)
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

# OSM building tag → catalog building_type
_OSM_BUILDING_TYPE: dict[str, str] = {
    "house": "residential",
    "residential": "residential",
    "apartments": "residential",
    "detached": "residential",
    "terrace": "residential",
    "retail": "commercial",
    "commercial": "commercial",
    "office": "commercial",
    "supermarket": "commercial",
    "shop": "commercial",
    "industrial": "industrial",
    "warehouse": "industrial",
    "factory": "industrial",
    "church": "religious",
    "cathedral": "religious",
    "mosque": "religious",
    "temple": "religious",
    "synagogue": "religious",
    "barn": "agricultural",
    "farm": "agricultural",
    "greenhouse": "agricultural",
}


class AssetCatalog:
    def __init__(self, catalog_path: Path = _CATALOG_PATH) -> None:
        with catalog_path.open(encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f)
        self._facades: dict[str, dict[str, str]] = data["facades"]
        self._forests: dict[str, dict[str, str]] = data["forests"]

    def get_facade(
        self,
        building_type: str,
        footprint_area_m2: float,
        lat: float,
        lon: float,  # noqa: ARG002 — reserved for future regional refinement
    ) -> str:
        btype = _OSM_BUILDING_TYPE.get(building_type, "generic")
        bucket = _size_bucket(footprint_area_m2)
        return self._facades[btype][bucket]

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
        """Check that all virtual paths exist under xplane_path/Resources/default scenery/."""
        lib_root = xplane_path / "Resources" / "default scenery"
        ok = True
        for btype, sizes in self._facades.items():
            for size, vpath in sizes.items():
                full = lib_root / vpath
                status = "✓" if full.exists() else "✗"
                if not full.exists():
                    ok = False
                console.print(f"  [{status}] facades/{btype}/{size}: {vpath}")
        for label, zones in self._forests.items():
            for zone, vpath in zones.items():
                full = lib_root / vpath
                status = "✓" if full.exists() else "✗"
                if not full.exists():
                    ok = False
                console.print(f"  [{status}] forests/{label}/{zone}: {vpath}")
        if ok:
            console.print("[green]All catalog entries validated.[/green]")
        else:
            console.print(
                "[yellow]Some entries not found — paths may differ by X-Plane version.[/yellow]"
            )


def _size_bucket(area_m2: float) -> str:
    if area_m2 < _SMALL:
        return "small"
    if area_m2 <= _LARGE:
        return "medium"
    return "large"
