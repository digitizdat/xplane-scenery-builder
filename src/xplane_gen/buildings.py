"""Building footprint → facade pipeline.

Converts OSM building GeoJSON features into FacadeFeature placements
ready for DsfWriter, with heights from OSM tags or type heuristics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, shape
from shapely.geometry.base import BaseGeometry
from shapely.validation import make_valid

from xplane_gen.catalog import AssetCatalog
from xplane_gen.dsf import ExclusionZone, FacadeFeature, _building_height


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

        rings = geom.get("coordinates") or []
        if not rings or len(rings[0]) < 4:
            continue

        # Validate and repair geometry, then emit the repaired outer ring so
        # self-intersecting or mis-wound OSM footprints reach X-Plane as a
        # clean simple polygon (see RENDER-001).
        shp = make_valid(shape(geom))
        if shp.is_empty:
            continue
        coords = _exterior_coords(shp)
        if len(coords) < 3:
            continue

        btype: str = str(props.get("building", "generic"))
        height = _building_height(props)
        area = float(shp.area * _m2_per_deg2(tile_centre_lat))
        fac_path = catalog.get_facade(
            btype,
            area,
            tile_centre_lat,
            tile_centre_lon,
            stories=props.get("xplane_stories"),
            material=props.get("xplane_material"),
            wall_color=props.get("xplane_wall_color"),
            window_density=props.get("xplane_window_density"),
            roof_type=props.get("xplane_roof"),
        )

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


def _exterior_coords(geom: BaseGeometry) -> list[tuple[float, float]]:
    """Return the outer ring of a repaired geometry as (lon, lat) tuples.

    ``make_valid`` can turn a self-intersecting footprint into a MultiPolygon
    or GeometryCollection; pick the largest Polygon so a single simple outer
    ring is emitted.
    """
    if isinstance(geom, Polygon):
        polys = [geom]
    elif isinstance(geom, (MultiPolygon, GeometryCollection)):
        polys = [g for g in geom.geoms if isinstance(g, Polygon)]
    else:
        polys = []
    if not polys:
        return []
    largest = max(polys, key=lambda p: p.area)
    return [(float(c[0]), float(c[1])) for c in largest.exterior.coords]


def _m2_per_deg2(lat: float) -> float:
    """Approximate m² per square degree at given latitude."""
    import math

    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(lat))
    return m_per_deg_lat * m_per_deg_lon
