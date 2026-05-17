"""Place name → bounding box lookup via OpenStreetMap Nominatim."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request


def placename_to_bbox(placename: str) -> tuple[float, float, float, float]:
    """Geocode a place name and return (lat_min, lon_min, lat_max, lon_max).

    Uses the Nominatim free geocoding API (no key required).
    Raises ValueError if the place cannot be found.
    """
    url = (
        "https://nominatim.openstreetmap.org/search?"
        f"q={urllib.parse.quote(placename)}&format=json&limit=1"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "xplane-scenery-builder/1.0"})
    # nosemgrep: dynamic-urllib-use-detected
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
        data = json.loads(resp.read())

    if not data:
        raise ValueError(f"Place not found: {placename!r}")

    # Nominatim returns boundingbox as [south, north, west, east] (strings)
    bb = data[0]["boundingbox"]
    lat_min, lat_max, lon_min, lon_max = float(bb[0]), float(bb[1]), float(bb[2]), float(bb[3])
    return lat_min, lon_min, lat_max, lon_max
