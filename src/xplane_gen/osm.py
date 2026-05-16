"""OSM data fetcher: buildings, land use, and roads via Overpass API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import overpy
from rich.console import Console

console = Console()

# Overpass query template — fetches ways+relations for buildings, landuse, highways
_QUERY = """[out:json][timeout:60];
(
  way["building"]({s},{w},{n},{e});
  relation["building"]({s},{w},{n},{e});
  way["landuse"]({s},{w},{n},{e});
  relation["landuse"]({s},{w},{n},{e});
  way["natural"~"wood|scrub|grassland|wetland|water"]({s},{w},{n},{e});
  way["highway"]({s},{w},{n},{e});
);
out body;
>;
out skel qt;
"""

_OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

_USER_AGENT = "xplane-scenery-builder/0.1 (https://github.com/digitizdat/xplane-scenery-builder)"

_RETRY_DELAYS = [5, 15, 30]  # seconds between retries on a single endpoint


def fetch_tile(
    lat_min: float,
    lon_min: float,
    lat_max: float,
    lon_max: float,
    output_dir: str,
) -> dict[str, Path]:
    """Fetch OSM data for bbox and write buildings/landuse/roads GeoJSON files.

    Returns a dict of {"buildings": Path, "landuse": Path, "roads": Path}.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    console.print(
        f"[cyan]Fetching OSM data for bbox:[/cyan] {lat_min},{lon_min},{lat_max},{lon_max}"
    )
    result = _query_overpass(lat_min, lon_min, lat_max, lon_max)

    buildings = _extract_features(result, _is_building)
    landuse = _extract_features(result, _is_landuse)
    roads = _extract_features(result, _is_road)

    paths: dict[str, Path] = {}
    for name, features in [("buildings", buildings), ("landuse", landuse), ("roads", roads)]:
        path = out / f"{name}.geojson"
        _write_geojson(features, path)
        console.print(f"  [green]{name}:[/green] {len(features)} features → {path}")
        paths[name] = path

    return paths


def _query_overpass(
    lat_min: float, lon_min: float, lat_max: float, lon_max: float
) -> overpy.Result:
    import urllib.request

    query = _QUERY.format(s=lat_min, w=lon_min, n=lat_max, e=lon_max)
    payload = query.encode("utf-8")

    last_exc: Exception = RuntimeError("No Overpass endpoints available")
    for endpoint in _OVERPASS_ENDPOINTS:
        api = overpy.Overpass(url=endpoint)
        for attempt, delay in enumerate([0] + _RETRY_DELAYS):
            if delay:
                console.print(
                    f"[yellow]Rate limited on {endpoint}, retrying in {delay}s "
                    f"(attempt {attempt + 1})…[/yellow]"
                )
                time.sleep(delay)
            try:
                req = urllib.request.Request(
                    endpoint,
                    data=payload,
                    headers={"User-Agent": _USER_AGENT},
                )
                with urllib.request.urlopen(req, timeout=90) as resp:  # nosec B310  # nosemgrep: dynamic-urllib-use-detected
                    body = resp.read()
                return api.parse_json(body)
            except overpy.exception.OverpassTooManyRequests as exc:
                last_exc = exc
                console.print(f"[yellow]Rate limited: {exc}[/yellow]")
            except overpy.exception.OverPyException as exc:
                last_exc = exc
                console.print(f"[yellow]Endpoint {endpoint} failed ({exc}), trying next…[/yellow]")
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                console.print(f"[yellow]Endpoint {endpoint} error ({exc}), trying next…[/yellow]")
                break

    raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_exc}")


# ------------------------------------------------------------------ #
# Feature extraction                                                   #
# ------------------------------------------------------------------ #


def _extract_features(
    result: overpy.Result,
    predicate: Any,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for way in result.ways:
        if not predicate(way.tags):
            continue
        coords = _way_coords(way)
        geom_type = "Polygon" if len(coords) >= 3 and coords[0] == coords[-1] else "LineString"
        if geom_type == "Polygon" and len(coords) < 3:
            continue
        if geom_type == "LineString" and len(coords) < 2:
            continue
        geometry: dict[str, Any] = (
            {"type": "Polygon", "coordinates": [coords]}
            if geom_type == "Polygon"
            else {"type": "LineString", "coordinates": coords}
        )
        features.append(
            {
                "type": "Feature",
                "geometry": geometry,
                "properties": dict(way.tags),
            }
        )
    return features


def _way_coords(way: overpy.Way) -> list[list[float]]:
    return [[float(n.lon), float(n.lat)] for n in way.nodes]


def _is_building(tags: dict[str, str]) -> bool:
    return "building" in tags


def _is_landuse(tags: dict[str, str]) -> bool:
    natural_types = {"wood", "scrub", "grassland", "wetland", "water"}
    return "landuse" in tags or tags.get("natural") in natural_types


def _is_road(tags: dict[str, str]) -> bool:
    return "highway" in tags


def _write_geojson(features: list[dict[str, Any]], path: Path) -> None:
    collection = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(collection, indent=2), encoding="utf-8")
