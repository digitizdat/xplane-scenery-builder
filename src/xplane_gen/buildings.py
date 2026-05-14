"""Building footprint → facade pipeline.

Converts OSM building GeoJSON features into FacadeFeature placements
ready for DsfWriter, with heights from OSM tags or type heuristics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import shape
from shapely.validation import make_valid

from xplane_gen.catalog import AssetCatalog
from xplane_gen.dsf import ExclusionZone, FacadeFeature, _building_height, _geom_to_coords


def buildings_to_facades(
    buildings_geojson: Path,
    catalog: AssetCatalog,
    tile_centre_lat: float,
    tile_centre_lon: float,
) -> list[FacadeFeature]:
    """Read OSM buildings GeoJSON and return a list of FacadeFeature placements."""
    fc: dict[str, Any] = json.loads(buildings_geojson.read_text(encoding="utf-8"))
    features: list[FacadeFeature] = []

    for feat in fc.get("features", []):
        props: dict[str, Any] = feat.get("properties", {})
        geom = feat.get("geometry", {})

        if geom.get("type") != "Polygon":
            continue

        coords = _geom_to_coords(geom)
        if len(coords) < 3:
            continue

        # Validate and repair geometry
        shp = make_valid(shape(geom))
        if shp.is_empty:
            continue

        btype: str = str(props.get("building", "generic"))
        height = _building_height(props)
        area = float(shp.area * _m2_per_deg2(tile_centre_lat))
        fac_path = catalog.get_facade(btype, area, tile_centre_lat, tile_centre_lon)

        features.append(FacadeFeature(resource=fac_path, height=height, coords=coords))

    return features


def building_exclusion_zones(tile_west: int, tile_south: int) -> list[ExclusionZone]:
    """Return obj + fac exclusion zones covering the full tile."""
    w, s = float(tile_west), float(tile_south)
    e, n = w + 1.0, s + 1.0
    return [
        ExclusionZone("obj", w, s, e, n),
        ExclusionZone("fac", w, s, e, n),
    ]


def _m2_per_deg2(lat: float) -> float:
    """Approximate m² per square degree at given latitude."""
    import math

    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    return m_per_deg_lat * m_per_deg_lon
