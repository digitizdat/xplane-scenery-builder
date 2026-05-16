"""End-to-end tile generation pipeline with resumable stage state machine."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from shapely.geometry import LinearRing, shape
from shapely.validation import make_valid

console = Console()

STAGES = [
    "fetch_osm",
    "fetch_rasters",
    "classify",
    "fetch_ortho",
    "review",
    "write_dsf",
    "validate",
    "done",
]


class TileProcessor:
    def __init__(
        self,
        lat_min: float,
        lon_min: float,
        lat_max: float,
        lon_max: float,
        output_dir: Path,
        dry_run: bool = False,
        auto: bool = False,
        dsftool: Path | None = None,
        ortho_source: str | None = None,
        regen: bool = False,
        review_all: bool = False,
    ) -> None:
        self.lat_min = lat_min
        self.lon_min = lon_min
        self.lat_max = lat_max
        self.lon_max = lon_max
        self.output_dir = output_dir
        self.dry_run = dry_run
        self.auto = auto
        self.dsftool = dsftool
        self.ortho_source = ortho_source
        self.review_all = review_all

        # Tile SW corner (integer degrees)
        self.tile_west = int(math.floor(lon_min))
        self.tile_south = int(math.floor(lat_min))

        self.state_file = output_dir / "tile_state.json"
        self._state: dict[str, Any] = self._load_state()

        if regen:
            self._reset_to_cached_data()

    # ------------------------------------------------------------------ #
    # Public                                                               #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        output_dir = self.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            for stage in STAGES[:-1]:  # skip sentinel "done"
                if self._completed(stage):
                    console.print(f"[dim]  ✓ {stage} (cached)[/dim]")
                    continue
                task = progress.add_task(f"[cyan]{stage}[/cyan]…", total=None)
                self._run_stage(stage)
                progress.remove_task(task)
                console.print(f"[green]  ✓ {stage}[/green]")

        self._mark_done("done")
        console.print("[bold green]Tile complete.[/bold green]")

    # ------------------------------------------------------------------ #
    # Stage dispatch                                                       #
    # ------------------------------------------------------------------ #

    def _run_stage(self, stage: str) -> None:
        getattr(self, f"_stage_{stage}")()
        self._mark_done(stage)

    def _stage_fetch_osm(self) -> None:
        from xplane_gen.osm import fetch_tile

        fetch_tile(
            self.lat_min,
            self.lon_min,
            self.lat_max,
            self.lon_max,
            str(self.output_dir),
        )

    def _stage_fetch_rasters(self) -> None:
        from xplane_gen.landcover import classify_tile

        classify_tile(
            self.lat_min,
            self.lon_min,
            self.lat_max,
            self.lon_max,
            str(self.output_dir),
        )

    def _stage_classify(self) -> None:
        from xplane_gen.ndvi import annotate_forest_density

        lc = self.output_dir / "landcover.geojson"
        if lc.exists():
            annotate_forest_density(lc, self.lat_min, self.lon_min, self.lat_max, self.lon_max)

    def _stage_fetch_ortho(self) -> None:
        if self.ortho_source is None:
            return
        from xplane_gen.ortho import fetch_ortho_tiles, make_source

        fetch_ortho_tiles(
            self.lat_min,
            self.lon_min,
            self.lat_max,
            self.lon_max,
            str(self.output_dir),
            make_source(self.ortho_source),
        )

    def _stage_review(self) -> None:
        """Launch inline interactive review if --review-all or a review queue exists."""
        queue_path = self.output_dir / "review_queue.json"
        if not queue_path.exists():
            return
        if self.auto:
            console.print("[dim]  --auto: skipping human review[/dim]")
            return

        from xplane_gen.review import run_review

        resolved_path = self.output_dir / "resolved_queue.json"
        run_review(str(queue_path), str(resolved_path))

    def _stage_write_dsf(self) -> None:
        from xplane_gen.dsf import build_overlay

        buildings = self.output_dir / "buildings.geojson"
        landcover = self.output_dir / "landcover.geojson"
        build_overlay(
            self.tile_west,
            self.tile_south,
            buildings if buildings.exists() else None,
            landcover if landcover.exists() else None,
            self.output_dir,
            dsftool=self.dsftool,
            dry_run=self.dry_run,
        )

    def _stage_validate(self) -> None:
        """Validate polygon winding, self-intersections, and object count."""
        issues: list[str] = []
        count = 0

        for geojson in self.output_dir.glob("*.geojson"):
            fc: dict[str, Any] = json.loads(geojson.read_text(encoding="utf-8"))
            for feat in fc.get("features", []):
                geom_dict = feat.get("geometry", {})
                if geom_dict.get("type") != "Polygon":
                    continue
                count += 1
                geom = make_valid(shape(geom_dict))
                if geom.is_empty:
                    issues.append(f"Empty geometry in {geojson.name}")
                    continue
                coords = geom_dict.get("coordinates", [[]])[0]
                if coords and not LinearRing(coords).is_ccw:
                    issues.append(f"CW winding in {geojson.name}")

        if count > 3000:
            console.print(
                f"[yellow]Warning: {count} objects may impact X-Plane performance.[/yellow]"
            )
        for issue in issues:
            console.print(f"[yellow]Validation: {issue}[/yellow]")

    # ------------------------------------------------------------------ #
    # State persistence                                                    #
    # ------------------------------------------------------------------ #

    _FETCH_STAGES = {"fetch_osm", "fetch_rasters", "fetch_ortho"}

    def _reset_to_cached_data(self) -> None:
        """Keep only fetch stages as completed, forcing regeneration from cached data."""
        completed = self._state.get("completed", [])
        self._state["completed"] = [s for s in completed if s in self._FETCH_STAGES]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        console.print("[cyan]Regenerating from cached data…[/cyan]")

    def _load_state(self) -> dict[str, Any]:
        if self.state_file.exists():
            data: dict[str, Any] = json.loads(self.state_file.read_text(encoding="utf-8"))
            return data
        return {"completed": []}

    def _completed(self, stage: str) -> bool:
        return stage in self._state.get("completed", [])

    def _mark_done(self, stage: str) -> None:
        completed: list[str] = self._state.setdefault("completed", [])
        if stage not in completed:
            completed.append(stage)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
