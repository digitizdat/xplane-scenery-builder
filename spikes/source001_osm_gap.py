"""Spike: quantify the OSM building-coverage gap for the Green Bank tile.

Backlog: SOURCE-001. Status: spike (throwaway measurement).

Question
--------
Q1. How many real buildings is OSM missing for the Green Bank bbox, estimated
    against Microsoft US Building Footprints (ODbL-1.0, same ML corpus as the
    Planetary Computer ms-buildings release)? Report raw counts, total footprint
    area, and spatial recall (fraction of MS buildings with an OSM building
    nearby, tolerant of the OSM-vs-imagery offset from ALIGN-001).
A1. Green Bank bbox (2026-07-24): OSM 167 buildings vs MS 652 (~4x more).
    Footprint area OSM 51,506 m^2 vs MS 121,465 m^2. Only 138/652 MS buildings
    have an OSM building within 15 m => ~79% estimated OSM miss rate. Confirms
    the missing buildings are an OSM source-coverage gap, not a render issue.
    MS-vs-OSM systematic offset is negligible: median (dx,dy)=(+0.3,-0.5) m,
    magnitude 0.6 m (per-pair median 1.8 m = shape-draw differences; p90 25.7 m
    is match noise, not a global shift). So MS footprints need no alignment
    step and can be placed as-is, same as OSM.

Reference is ML-derived (its own errors, <1% false-positive per MS), so numbers
are an estimate, not ground truth.

Note: an earlier attempt used the Planetary Computer delta/quadkey dataset, but
the Azure/delta read and the quadkey->tile convention were fragile; the per-state
GeoJSON here is the same corpus and far simpler.

Run: uv run --with geopandas --with pyogrio python spikes/source001_osm_gap.py
"""

from __future__ import annotations

import math
import urllib.request
from pathlib import Path

import geopandas as gpd

REPO = Path(__file__).resolve().parent.parent
OSM = REPO / "green_bank" / "buildings.geojson"
BBOX = (-79.9, 38.4, -79.8, 38.45)  # w, s, e, n
WV_URL = (
    "https://minedbuildings.z5.web.core.windows.net/legacy/usbuildings-v2/"
    "WestVirginia.geojson.zip"
)
CACHE = Path("/tmp/WestVirginia.geojson.zip")  # nosec B108 — cache for a public file
UTM17N = 32617  # metric CRS for West Virginia
MATCH_M = 15.0  # centroid tolerance to absorb OSM-vs-imagery offset (ALIGN-001)
MEASURE_M = 40.0  # generous radius for offset measurement (avoid censoring the offset)


def _offset(ms: gpd.GeoDataFrame, osm: gpd.GeoDataFrame) -> None:
    """Median MS->OSM centroid displacement (systematic offset) and spread."""
    import statistics

    ms_c = ms.geometry.centroid
    osm_c = osm.geometry.centroid
    pairs = gpd.sjoin_nearest(
        gpd.GeoDataFrame(geometry=ms_c, crs=ms.crs),
        gpd.GeoDataFrame(geometry=osm_c, crs=osm.crs),
        max_distance=MEASURE_M,
        how="inner",
        distance_col="dist",
    )
    if pairs.empty:
        print("offset: no MS/OSM pairs within measurement radius")
        return
    dxs, dys, mags = [], [], []
    osm_c = osm_c.reset_index(drop=True)
    for ms_idx, row in pairs.iterrows():
        oc = osm_c.iloc[int(row["index_right"])]
        mc = ms_c.loc[ms_idx]
        dxs.append(mc.x - oc.x)
        dys.append(mc.y - oc.y)
        mags.append(float(row["dist"]))
    med_dx, med_dy = statistics.median(dxs), statistics.median(dys)
    med_mag = math.hypot(med_dx, med_dy)
    print(f"MS<->OSM pairs (<= {MEASURE_M:.0f} m):  {len(dxs)}")
    print(f"systematic offset (median dx,dy): ({med_dx:+.1f}, {med_dy:+.1f}) m  |{med_mag:.1f}| m")
    print(f"per-pair distance median / p90:   {statistics.median(mags):.1f} / "
          f"{sorted(mags)[int(0.9 * len(mags)) - 1]:.1f} m")


def main() -> int:
    if not CACHE.exists():
        print(f"downloading {WV_URL} ...")
        urllib.request.urlretrieve(WV_URL, CACHE)  # nosec B310 — fixed public HTTPS URL
    print(f"reading MS footprints within bbox from {CACHE.name}")

    ms = gpd.read_file(f"zip://{CACHE}", bbox=BBOX).to_crs(UTM17N)
    osm = gpd.read_file(OSM, bbox=BBOX)
    osm = osm[osm.geometry.type == "Polygon"].to_crs(UTM17N)

    osm_area = float(osm.area.sum())
    ms_area = float(ms.area.sum())

    # spatial recall: MS buildings with an OSM building within MATCH_M
    matched = gpd.sjoin_nearest(ms, osm, max_distance=MATCH_M, how="inner")
    matched_ms = matched.index.nunique()

    print(f"OSM buildings in bbox:        {len(osm)}")
    print(f"MS buildings in bbox:         {len(ms)}")
    print(f"OSM total footprint area:     {osm_area:,.0f} m^2")
    print(f"MS total footprint area:      {ms_area:,.0f} m^2")
    if len(ms):
        print(f"MS buildings covered by OSM:  {matched_ms}/{len(ms)} = {matched_ms / len(ms):.0%}")
        print(f"Estimated OSM miss rate:      {1 - matched_ms / len(ms):.0%}")
    _offset(ms, osm)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
