"""DSFTool CLI wrapper and DSF text-format writer."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess  # nosec B404 — subprocess used only to invoke DSFTool with a fixed arg list; no shell, no user input
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from shapely.geometry import LinearRing


def find_dsftool() -> Path:
    """Locate DSFTool binary. Checks PATH, then common install locations."""
    if path := shutil.which("DSFTool"):
        return Path(path)
    candidates = [
        Path.home() / "bin" / "DSFTool",
        Path("/usr/local/bin/DSFTool"),
        Path(__file__).parent.parent.parent / "tools" / "DSFTool",
    ]
    for c in candidates:
        if c.exists():
            return c
    raise FileNotFoundError(
        "DSFTool not found. Install xptools and ensure DSFTool is on PATH.\n"
        "Build from source: https://github.com/X-Plane/xptools\n"
        "Or place binary at tools/DSFTool relative to project root."
    )


Coord = tuple[float, float]  # (lon, lat)


@dataclass
class ForestFeature:
    resource: str
    density: float
    coords: list[Coord]


@dataclass
class FacadeFeature:
    resource: str
    height: float
    coords: list[Coord]


@dataclass
class ExclusionZone:
    kind: Literal["obj", "fac", "for", "net", "pol"]
    west: float
    south: float
    east: float
    north: float


@dataclass
class DrapedPolygon:
    resource: str  # path to .pol file
    coords: list[tuple[float, float, float, float]]  # (lon, lat, s, t) per vertex


@dataclass
class DsfWriter:
    """Builds a DSF overlay text file and compiles it with DSFTool."""

    tile_west: int
    tile_south: int
    forests: list[ForestFeature] = field(default_factory=list)
    facades: list[FacadeFeature] = field(default_factory=list)
    draped: list[DrapedPolygon] = field(default_factory=list)
    exclusions: list[ExclusionZone] = field(default_factory=list)

    def add_forest(self, feature: ForestFeature) -> None:
        self.forests.append(feature)

    def add_draped(self, polygon: DrapedPolygon) -> None:
        self.draped.append(polygon)

    def add_facade(self, feature: FacadeFeature) -> None:
        self.facades.append(feature)

    def add_exclusion(self, zone: ExclusionZone) -> None:
        self.exclusions.append(zone)

    def compile(self, output_dir: Path, dsftool: Path | None = None) -> Path:
        """Write text DSF and compile to binary. Returns path to .dsf file."""
        tool = dsftool or find_dsftool()
        text = self._render()

        dsf_path = _dsf_path(output_dir, self.tile_south, self.tile_west)
        dsf_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            tmp_path = tmp.name

        try:
            result = subprocess.run(  # nosec B603 — args are [dsftool_path, flag, tmp_file, out_file]; no shell, no user-controlled input
                [str(tool), "--text2dsf", tmp_path, str(dsf_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                raise RuntimeError(
                    f"DSFTool failed (exit {result.returncode}):\n{result.stderr or result.stdout}"
                )
        finally:
            os.unlink(tmp_path)

        return dsf_path

    def _render(self) -> str:
        lines: list[str] = [
            "A",
            "800",
            "DSF2TEXT",
            "",
            f"PROPERTY sim/west {self.tile_west}",
            f"PROPERTY sim/east {self.tile_west + 1}",
            f"PROPERTY sim/south {self.tile_south}",
            f"PROPERTY sim/north {self.tile_south + 1}",
            "PROPERTY sim/planet earth",
            "PROPERTY sim/overlay 1",
            "PROPERTY sim/require_facade 1/0",
            "PROPERTY sim/require_object 1/0",
        ]

        for ex in self.exclusions:
            lines.append(
                f"PROPERTY sim/exclude_{ex.kind} {ex.west}/{ex.south}/{ex.east}/{ex.north}"
            )

        lines.append("")

        forest_resources = list(dict.fromkeys(f.resource for f in self.forests))
        facade_resources = list(dict.fromkeys(f.resource for f in self.facades))
        draped_resources = list(dict.fromkeys(d.resource for d in self.draped))

        for r in forest_resources:
            lines.append(f"POLYGON_DEF {r}")
        for r in facade_resources:
            lines.append(f"POLYGON_DEF {r}")
        for r in draped_resources:
            lines.append(f"POLYGON_DEF {r}")

        lines.append("")

        for feat in self.forests:
            idx = forest_resources.index(feat.resource)
            coords = _ensure_ccw(feat.coords)
            lines += [
                f"BEGIN_POLYGON {idx} {int(feat.density * 255)} 2",
                "BEGIN_WINDING",
                *[f"POLYGON_POINT {lon:.7f} {lat:.7f}" for lon, lat in coords],
                "END_WINDING",
                "END_POLYGON",
            ]

        for facade in self.facades:
            idx = len(forest_resources) + facade_resources.index(facade.resource)
            coords = _ensure_ccw(facade.coords)
            lines += [
                f"BEGIN_POLYGON {idx} {int(facade.height)} 2",
                "BEGIN_WINDING",
                *[f"POLYGON_POINT {lon:.7f} {lat:.7f}" for lon, lat in coords],
                "END_WINDING",
                "END_POLYGON",
            ]

        base_idx = len(forest_resources) + len(facade_resources)
        for dp in self.draped:
            idx = base_idx + draped_resources.index(dp.resource)
            lines += [
                f"BEGIN_POLYGON {idx} 0 4",
                "BEGIN_WINDING",
                *[
                    f"POLYGON_POINT {lon:.7f} {lat:.7f} {s:.6f} {t:.6f}"
                    for lon, lat, s, t in dp.coords
                ],
                "END_WINDING",
                "END_POLYGON",
            ]

        lines.append("")
        return "\n".join(lines)


def _dsf_path(output_dir: Path, lat: int, lon: int) -> Path:
    # X-Plane groups DSF tiles in 10°×10° parent folders (SW corner rounded to nearest 10°)
    parent_lat = (lat // 10) * 10
    parent_lon = (lon // 10) * 10
    folder = f"{parent_lat:+03d}{parent_lon:+04d}"
    filename = f"{lat:+03d}{lon:+04d}.dsf"
    return output_dir / "Earth nav data" / folder / filename


def _ensure_ccw(coords: list[Coord]) -> list[Coord]:
    """Return coords in counter-clockwise winding order."""
    ring = LinearRing(coords)
    if not ring.is_ccw:
        return list(reversed(coords))
    return coords


# ------------------------------------------------------------------ #
# High-level overlay builder                                           #
# ------------------------------------------------------------------ #


def build_overlay(
    tile_west: int,
    tile_south: int,
    buildings_geojson: Path | None,
    landcover_geojson: Path | None,
    output_dir: Path,
    dsftool: Path | None = None,
    dry_run: bool = False,
) -> Path:
    """Build a DSF overlay from classified GeoJSON files.

    Reads buildings and landcover GeoJSON, maps features through the asset
    catalog, writes exclusion zones for all placed content, and compiles
    to binary DSF via DSFTool.

    Returns the path to the compiled .dsf (or the text file in dry_run mode).
    """
    from xplane_gen.catalog import AssetCatalog

    catalog = AssetCatalog()
    writer = DsfWriter(tile_west=tile_west, tile_south=tile_south)

    # Tile bbox for exclusion zones
    west, south = float(tile_west), float(tile_south)
    east, north = west + 1.0, south + 1.0
    tile_centre_lat = south + 0.5

    has_forests = False

    # ── landcover → forest features ──────────────────────────────────
    if landcover_geojson and landcover_geojson.exists():
        fc: dict[str, Any] = json.loads(landcover_geojson.read_text(encoding="utf-8"))
        for feat in fc.get("features", []):
            props = feat.get("properties", {})
            label: str = props.get("label", "")
            density: float = float(props.get("ndvi_density", 0.7))
            geom = feat.get("geometry", {})
            coords = _geom_to_coords(geom)
            if not coords or not label:
                continue
            # Skip classes that shouldn't render as tree polygons
            if label in {"built_up", "bare", "snow_ice", "water", "cropland", "grassland"}:
                continue
            for_path = catalog.get_forest(label, tile_centre_lat, west + 0.5)
            if not for_path:
                continue
            writer.add_forest(ForestFeature(resource=for_path, density=density, coords=coords))
            has_forests = True

    # ── buildings → facade features ──────────────────────────────────
    if buildings_geojson and buildings_geojson.exists():
        from xplane_gen.buildings import building_exclusion_zones, buildings_to_facades

        facades = buildings_to_facades(buildings_geojson, catalog, tile_centre_lat, west + 0.5)
        for f in facades:
            writer.add_facade(f)
        if facades:
            for ex in building_exclusion_zones(tile_west, tile_south):
                writer.add_exclusion(ex)

    # ── forest exclusion zone ─────────────────────────────────────────
    if has_forests:
        writer.add_exclusion(ExclusionZone("for", west, south, east, north))

    # ── orthophoto draped polygons ────────────────────────────────────
    ortho_dir = output_dir / "orthophoto"
    if ortho_dir.exists():
        for pol_file in sorted(ortho_dir.glob("*.pol")):
            # Parse LOAD_CENTER from .pol to get tile bounds
            pol_text = pol_file.read_text(encoding="utf-8")
            for line in pol_text.splitlines():
                if line.startswith("LOAD_CENTER"):
                    parts = line.split()
                    if len(parts) >= 5:
                        clat, clon = float(parts[1]), float(parts[2])
                        h_m, w_m = float(parts[3]), float(parts[4])
                        h_deg = h_m / 111_320.0
                        w_deg = w_m / (111_320.0 * math.cos(math.radians(clat)))
                        # Corner coordinates with UV mapping
                        s_lon = clon - w_deg / 2
                        n_lon = clon + w_deg / 2
                        s_lat = clat - h_deg / 2
                        n_lat = clat + h_deg / 2
                        # Relative path from scenery root to .pol
                        rel_pol = f"orthophoto/{pol_file.name}"
                        writer.add_draped(DrapedPolygon(
                            resource=rel_pol,
                            coords=[
                                (s_lon, s_lat, 0.0, 0.0),
                                (n_lon, s_lat, 1.0, 0.0),
                                (n_lon, n_lat, 1.0, 1.0),
                                (s_lon, n_lat, 0.0, 1.0),
                            ],
                        ))
                    break

    if dry_run:
        text_path = output_dir / "overlay_preview.txt"
        output_dir.mkdir(parents=True, exist_ok=True)
        text_path.write_text(writer._render(), encoding="utf-8")
        return text_path

    # Fall back to dry-run if DSFTool is not installed
    try:
        return writer.compile(output_dir, dsftool=dsftool)
    except FileNotFoundError as exc:
        from rich.console import Console as _Console

        _Console().print(
            f"[yellow]Warning: {exc}\nWriting text preview instead (--dry-run mode).[/yellow]"
        )
        text_path = output_dir / "overlay_preview.txt"
        text_path.write_text(writer._render(), encoding="utf-8")
        return text_path


def _geom_to_coords(geom: dict[str, Any]) -> list[Coord]:
    """Extract outer ring coords from a GeoJSON Polygon or first polygon of MultiPolygon."""
    gtype = geom.get("type")
    if gtype == "Polygon":
        rings = geom.get("coordinates", [])
        if rings:
            return [(float(c[0]), float(c[1])) for c in rings[0]]
    elif gtype == "MultiPolygon":
        polys = geom.get("coordinates", [])
        if polys and polys[0]:
            return [(float(c[0]), float(c[1])) for c in polys[0][0]]
    return []


def _building_height(props: dict[str, Any]) -> float:
    """Extract building height from OSM tags with fallback heuristics."""
    if h := props.get("height"):
        try:
            return float(str(h).replace("m", "").strip())
        except ValueError:
            pass
    if lvl := props.get("building:levels"):
        try:
            return float(lvl) * 3.5
        except ValueError:
            pass
    heuristics: dict[str, float] = {
        "residential": 7.0,
        "house": 7.0,
        "apartments": 12.0,
        "commercial": 15.0,
        "office": 20.0,
        "industrial": 10.0,
        "warehouse": 8.0,
        "religious": 12.0,
        "church": 12.0,
    }
    btype = str(props.get("building", "generic"))
    return heuristics.get(btype, 8.0)


def _polygon_area_m2(coords: list[Coord]) -> float:
    """Approximate polygon area in m² using the shoelace formula with degree→metre conversion."""
    if len(coords) < 3:
        return 0.0
    # Average latitude for metre-per-degree conversion
    avg_lat = sum(c[1] for c in coords) / len(coords)
    m_per_deg_lat = 111_320.0
    m_per_deg_lon = 111_320.0 * math.cos(math.radians(avg_lat))

    # Shoelace in projected coordinates
    area = 0.0
    n = len(coords)
    for i in range(n):
        x1 = coords[i][0] * m_per_deg_lon
        y1 = coords[i][1] * m_per_deg_lat
        x2 = coords[(i + 1) % n][0] * m_per_deg_lon
        y2 = coords[(i + 1) % n][1] * m_per_deg_lat
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0
