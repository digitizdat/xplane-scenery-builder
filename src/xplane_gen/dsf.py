"""DSFTool CLI wrapper and DSF text-format writer."""

from __future__ import annotations

import os
import shutil
import subprocess  # nosec B404 — subprocess used only to invoke DSFTool with a fixed arg list; no shell, no user input
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

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
class DsfWriter:
    """Builds a DSF overlay text file and compiles it with DSFTool."""

    tile_west: int
    tile_south: int
    forests: list[ForestFeature] = field(default_factory=list)
    facades: list[FacadeFeature] = field(default_factory=list)
    exclusions: list[ExclusionZone] = field(default_factory=list)

    def add_forest(self, feature: ForestFeature) -> None:
        self.forests.append(feature)

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
        ]

        for ex in self.exclusions:
            lines.append(
                f"PROPERTY sim/exclude_{ex.kind} {ex.west}/{ex.south}/{ex.east}/{ex.north}"
            )

        lines.append("")

        forest_resources = list(dict.fromkeys(f.resource for f in self.forests))
        facade_resources = list(dict.fromkeys(f.resource for f in self.facades))

        for r in forest_resources:
            lines.append(f"POLYGON_DEF {r}")
        for r in facade_resources:
            lines.append(f"POLYGON_DEF {r}")

        lines.append("")

        for feat in self.forests:
            idx = forest_resources.index(feat.resource)
            coords = _ensure_ccw(feat.coords)
            lines += [
                f"BEGIN_POLYGON {idx} {feat.density:.4f} 2",
                "BEGIN_WINDING",
                *[f"POLYGON_POINT {lon:.7f} {lat:.7f}" for lon, lat in coords],
                "END_WINDING",
                "END_POLYGON",
            ]

        for facade in self.facades:
            idx = len(forest_resources) + facade_resources.index(facade.resource)
            coords = _ensure_ccw(facade.coords)
            lines += [
                f"BEGIN_POLYGON {idx} {facade.height:.2f} 2",
                "BEGIN_WINDING",
                *[f"POLYGON_POINT {lon:.7f} {lat:.7f}" for lon, lat in coords],
                "END_WINDING",
                "END_POLYGON",
            ]

        lines.append("")
        return "\n".join(lines)


def _dsf_path(output_dir: Path, lat: int, lon: int) -> Path:
    folder = f"{lat:+03d}{lon:+04d}"
    filename = f"{lat:+03d}{lon:+04d}.dsf"
    return output_dir / "Earth nav data" / folder / filename


def _ensure_ccw(coords: list[Coord]) -> list[Coord]:
    """Return coords in counter-clockwise winding order."""
    ring = LinearRing(coords)
    if not ring.is_ccw:
        return list(reversed(coords))
    return coords
