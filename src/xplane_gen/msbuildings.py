"""Microsoft US Building Footprints as a supplementary building source (SOURCE-001).

Fetches Microsoft's open (ODbL) US building footprints for a bbox and merges them
into the OSM building set, filling coverage gaps (rural OSM is very incomplete).
MS footprints are placed as-is: the measured MS-vs-OSM systematic offset is
sub-metre (spikes/source001_osm_gap.py), so no alignment step is applied.

US-only for now (per-state files). Reads a bbox subset with pyogrio (bundled GDAL,
no geopandas); de-dup uses shapely. Both OSM and MS are ODbL, so mixing is
license-compatible; attribute output to both.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from rich.console import Console
from shapely import STRtree, from_wkb
from shapely.geometry import MultiPolygon, Polygon, mapping

console = Console()

_BASE_URL = "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2"
_CACHE_DIR = Path.home() / ".cache" / "xplane-gen" / "msbuildings"
_DEDUP_TOL_M = 2.0  # MS footprint dropped if within this of an OSM building (offset is ~0.6 m)

# US states + DC. MS filename = state name without spaces (West Virginia -> WestVirginia).
_US_STATES = frozenset(
    {
        "Alabama",
        "Alaska",
        "Arizona",
        "Arkansas",
        "California",
        "Colorado",
        "Connecticut",
        "Delaware",
        "District of Columbia",
        "Florida",
        "Georgia",
        "Hawaii",
        "Idaho",
        "Illinois",
        "Indiana",
        "Iowa",
        "Kansas",
        "Kentucky",
        "Louisiana",
        "Maine",
        "Maryland",
        "Massachusetts",
        "Michigan",
        "Minnesota",
        "Mississippi",
        "Missouri",
        "Montana",
        "Nebraska",
        "Nevada",
        "New Hampshire",
        "New Jersey",
        "New Mexico",
        "New York",
        "North Carolina",
        "North Dakota",
        "Ohio",
        "Oklahoma",
        "Oregon",
        "Pennsylvania",
        "Rhode Island",
        "South Carolina",
        "South Dakota",
        "Tennessee",
        "Texas",
        "Utah",
        "Vermont",
        "Virginia",
        "Washington",
        "West Virginia",
        "Wisconsin",
        "Wyoming",
    }
)


class MsBuildingsError(RuntimeError):
    """Raised when MS footprints cannot be resolved or fetched for a bbox."""


def state_filename(state: str) -> str:
    """Map a US state name to its Microsoft footprints filename stem."""
    if state not in _US_STATES:
        raise MsBuildingsError(f"Not a supported US state: {state!r} (MS footprints are US-only)")
    return state.replace(" ", "")


def reverse_geocode_state(lat: float, lon: float) -> str:
    """Return the US state name containing (lat, lon) via Nominatim reverse geocoding."""
    url = f"https://nominatim.openstreetmap.org/reverse?lat={lat}&lon={lon}&format=json"
    req = urllib.request.Request(url, headers={"User-Agent": "xplane-scenery-builder/1.0"})
    # nosemgrep: dynamic-urllib-use-detected
    with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310 — fixed Nominatim host
        data = json.loads(resp.read())
    state = data.get("address", {}).get("state")
    if not state:
        raise MsBuildingsError(f"Could not determine US state for ({lat}, {lon})")
    return str(state)


def download_state(filename: str) -> Path:
    """Download (and cache) a state's MS footprints zip. Returns the local path."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    dest = _CACHE_DIR / f"{filename}.geojson.zip"
    if dest.exists():
        return dest
    url = f"{_BASE_URL}/{urllib.parse.quote(filename)}.geojson.zip"
    console.print(f"[cyan]Downloading MS footprints: {url}[/cyan]")
    urllib.request.urlretrieve(url, dest)  # nosec B310 — fixed public HTTPS host
    return dest


def read_ms_polygons(
    zip_path: Path, filename: str, bbox: tuple[float, float, float, float]
) -> list[Polygon]:
    """Read MS footprints within bbox (w, s, e, n) as shapely Polygons.

    Uses pyogrio's low-level reader (bundled GDAL, no geopandas). MultiPolygons
    are reduced to their largest part so downstream facade placement (which
    handles single Polygons) gets a simple outer ring.
    """
    from pyogrio.raw import read  # local import: heavy, optional dependency

    vsi = f"/vsizip/{zip_path}/{filename}.geojson"
    result = read(vsi, columns=[], bbox=bbox, read_geometry=True)
    wkb_geoms = result[2]
    polys: list[Polygon] = []
    for wkb in wkb_geoms:
        if wkb is None:
            continue
        geom = from_wkb(bytes(wkb))
        if isinstance(geom, Polygon):
            polys.append(geom)
        elif isinstance(geom, MultiPolygon) and not geom.is_empty:
            polys.append(max(geom.geoms, key=lambda p: p.area))
    return polys


def dedup_against_osm(
    osm_polys: list[Polygon], ms_polys: list[Polygon], tol_m: float = _DEDUP_TOL_M
) -> list[Polygon]:
    """Return MS polygons that do NOT duplicate an OSM building (OSM wins).

    A MS polygon is a duplicate if, buffered by tol_m, it intersects any OSM
    footprint. Buffer absorbs the small MS-vs-OSM offset and slight shape
    differences without merging genuinely separate neighbours.
    """
    if not osm_polys:
        return list(ms_polys)
    tol_deg = tol_m / 111_320.0
    tree = STRtree(osm_polys)
    kept: list[Polygon] = []
    for g in ms_polys:
        probe = g.buffer(tol_deg)
        candidates = tree.query(probe)
        if any(probe.intersects(osm_polys[i]) for i in candidates):
            continue
        kept.append(g)
    return kept


def _polygons_from_features(features: list[dict[str, Any]]) -> list[Polygon]:
    polys: list[Polygon] = []
    for feat in features:
        geom = feat.get("geometry", {})
        if geom.get("type") != "Polygon":
            continue
        rings = geom.get("coordinates") or []
        if rings and len(rings[0]) >= 4:
            polys.append(Polygon(rings[0]))
    return polys


def merge_into_buildings(
    buildings_path: Path, ms_polys: list[Polygon], tol_m: float = _DEDUP_TOL_M
) -> tuple[int, int]:
    """Merge de-duplicated MS polygons into buildings.geojson (OSM stays authoritative).

    Idempotent: existing MS-sourced features (xplane_source == "ms") are dropped
    first, so re-running rebuilds the union from the OSM features plus fresh MS.
    Returns (added, dropped_as_duplicate).
    """
    fc: dict[str, Any] = json.loads(buildings_path.read_text(encoding="utf-8"))
    osm_features = [
        f for f in fc.get("features", []) if f.get("properties", {}).get("xplane_source") != "ms"
    ]
    osm_polys = _polygons_from_features(osm_features)
    kept = dedup_against_osm(osm_polys, ms_polys, tol_m)

    ms_features = [
        {
            "type": "Feature",
            "geometry": mapping(g),
            "properties": {"building": "yes", "xplane_source": "ms"},
        }
        for g in kept
    ]
    fc["features"] = osm_features + ms_features
    buildings_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")
    return len(kept), len(ms_polys) - len(kept)


def supplement_with_ms(
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    output_dir: Path,
    tol_m: float = _DEDUP_TOL_M,
) -> tuple[int, int]:
    """Fetch MS footprints for the bbox and merge them into buildings.geojson.

    Returns (added, dropped_as_duplicate). No-op-safe: raises MsBuildingsError if
    the area is outside the supported US coverage.
    """
    buildings_path = output_dir / "buildings.geojson"
    if not buildings_path.exists():
        raise MsBuildingsError(f"{buildings_path} not found; run fetch_osm first")

    lat_c, lon_c = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
    state = reverse_geocode_state(lat_c, lon_c)
    filename = state_filename(state)
    zip_path = download_state(filename)
    ms_polys = read_ms_polygons(zip_path, filename, (lon_min, lat_min, lon_max, lat_max))
    console.print(f"[cyan]MS footprints in bbox ({state}): {len(ms_polys)}[/cyan]")
    added, dropped = merge_into_buildings(buildings_path, ms_polys, tol_m)
    console.print(
        f"[green]  merged {added} MS buildings ({dropped} de-duplicated against OSM)[/green]"
    )
    return added, dropped
