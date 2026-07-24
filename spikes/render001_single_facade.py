"""Spike: RENDER-001 step-1 diagnostic — force one permissive facade.

Backlog: RENDER-001. Status: spike (throwaway prototype, not shipped).

Question this spike is built to answer
--------------------------------------
Q1. Is per-building facade *selection* (wall-width incompatibility) the primary
    cause of "many but not all" buildings rendering? If every building is placed
    with a single maximally-permissive facade and they all then render in-sim,
    the geometry reaches X-Plane fine and the fault is in selection, not the
    pipeline. If some still fail, another factor (height, footprint) remains.
A1. Confirmed in X-Plane 12 (2026-07-23). With every building forced onto the
    permissive facade and the green_bank ortho draped underneath as reference,
    buildings render across the tile. Geometry reaches X-Plane intact and the
    pipeline delivers the footprints, so the "many but not all" drop is caused
    by per-building facade *selection* (wall-width incompatibility in
    catalog._score_facade), not the pipeline or geometry.
    lib/buildings/facades/generic/high_universal_01.fac (RING 1, walls 0-200 m)
    works as a permissive fallback.

Method
------
Build facade placements from green_bank/buildings.geojson through the real
buildings_to_facades path (so it exercises the 2a/2b geometry fixes), override
every facade resource to one permissive facade, and drape the existing
green_bank ortho tiles underneath as a ground reference. The chosen facade,
lib/buildings/facades/generic/high_universal_01.fac, is RING 1 with walls
covering 0-200 m at all headings, so any footprint segment matches. Buildings
sit on the real imagery so their presence and placement can be checked against
the satellite ground.

Run: python3 spikes/render001_single_facade.py
Then copy the printed pack folder into X-Plane 12 'Custom Scenery/' and fly over
Green Bank, WV (~38.43, -79.83). Compare rendered buildings against 167 expected.
"""

from __future__ import annotations

import math
import shutil
import sys
from pathlib import Path

# Allow running from the repo root without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from xplane_gen.buildings import buildings_to_facades  # noqa: E402
from xplane_gen.catalog import AssetCatalog  # noqa: E402
from xplane_gen.dsf import DrapedPolygon, DsfWriter, FacadeFeature, find_dsftool  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
BUILDINGS = REPO / "green_bank" / "buildings.geojson"
ORTHO_SRC = REPO / "green_bank" / "orthophoto"
OUT = REPO / "green_bank_render001_diag"
PERMISSIVE_FACADE = "lib/buildings/facades/generic/high_universal_01.fac"
TILE_WEST, TILE_SOUTH = -80, 38
TILE_CENTRE_LAT, TILE_CENTRE_LON = 38.43, -79.83


def _add_ortho(writer: DsfWriter) -> int:
    """Drape the green_bank ortho tiles as a ground reference (from build_overlay)."""
    if not ORTHO_SRC.is_dir():
        return 0
    n = 0
    for pol_file in sorted(ORTHO_SRC.glob("*.pol")):
        clat = clon = w_m = h_m = 0.0
        for line in pol_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("SCALE"):
                _, w_m_s, h_m_s = line.split()[:3]
                w_m, h_m = float(w_m_s), float(h_m_s)
            elif line.startswith("LOAD_CENTER"):
                _, clat_s, clon_s = line.split()[:3]
                clat, clon = float(clat_s), float(clon_s)
        if w_m <= 0 or h_m <= 0:
            continue
        h_deg = h_m / 111_320.0
        w_deg = w_m / (111_320.0 * math.cos(math.radians(clat)))
        s_lon, n_lon = clon - w_deg / 2, clon + w_deg / 2
        s_lat, n_lat = clat - h_deg / 2, clat + h_deg / 2
        writer.add_draped(
            DrapedPolygon(
                resource=f"orthophoto/{pol_file.name}",
                coords=[
                    (s_lon, s_lat, 0.0, 0.0),
                    (n_lon, s_lat, 1.0, 0.0),
                    (n_lon, n_lat, 1.0, 1.0),
                    (s_lon, n_lat, 0.0, 1.0),
                ],
            )
        )
        n += 1
    return n


def main() -> int:
    if not BUILDINGS.exists():
        print(f"missing {BUILDINGS}", file=sys.stderr)
        return 1

    catalog = AssetCatalog()
    facades = buildings_to_facades(BUILDINGS, catalog, TILE_CENTRE_LAT, TILE_CENTRE_LON)
    print(f"buildings -> facades: {len(facades)}")

    writer = DsfWriter(tile_west=TILE_WEST, tile_south=TILE_SOUTH)
    for f in facades:
        writer.add_facade(
            FacadeFeature(resource=PERMISSIVE_FACADE, height=f.height, coords=f.coords)
        )
    n_ortho = _add_ortho(writer)
    print(f"ortho tiles draped as ground reference: {n_ortho}")

    dsftool = find_dsftool()
    dsf_path = writer.compile(OUT, dsftool=dsftool)
    # Copy the ortho textures alongside the DSF so the .pol references resolve.
    if n_ortho:
        dest_ortho = OUT / "orthophoto"
        if dest_ortho.exists():
            shutil.rmtree(dest_ortho)
        shutil.copytree(ORTHO_SRC, dest_ortho)
    print(f"compiled: {dsf_path}")
    print(f"\nInstall: uv run xplane-gen install --pack '{OUT}' --name green_bank_diag --force")
    print("Then fly over Green Bank, WV (~38.43, -79.83) and compare buildings to the imagery.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
