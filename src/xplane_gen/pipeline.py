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
    "annotate",
    "fetch_ortho",
    "classify",
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
        no_roads: bool = False,
        workers: int = 5,
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
        self.no_roads = no_roads
        self.workers = workers

        # Tile SW corner (integer degrees)
        self.tile_west = int(math.floor(lon_min))
        self.tile_south = int(math.floor(lat_min))

        self.state_file = output_dir / "tile_state.json"
        self._state: dict[str, Any] = self._load_state()

        if regen:
            self._reset_to_cached_data()
        if review_all:
            self._force_stage("review")

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
                # Stop spinner for interactive review stage
                if stage == "review":
                    progress.stop()
                    self._run_stage(stage)
                    console.print(f"[green]  ✓ {stage}[/green]")
                    progress.start()
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

    def _stage_annotate(self) -> None:
        from xplane_gen.ndvi import annotate_forest_density

        lc = self.output_dir / "landcover.geojson"
        if lc.exists():
            console.print("[cyan]Annotating forest density via Sentinel-2 NDVI…[/cyan]")
            annotate_forest_density(lc, self.lat_min, self.lon_min, self.lat_max, self.lon_max)
            console.print("[green]  Forest density annotation complete[/green]")
        else:
            console.print("[dim]  No landcover.geojson — skipping NDVI annotation[/dim]")

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
            workers=self.workers,
        )

    def _stage_classify(self) -> None:
        """Classify buildings, forests, and roads using Bedrock LLM vision."""
        if self.auto:
            return

        import threading
        from concurrent.futures import ThreadPoolExecutor, as_completed

        from xplane_gen.classifier import BedrockClassifier, crop_patch

        classifier = BedrockClassifier(
            output_dir=self.output_dir,
            review_all=self.review_all,
        )
        tile_bbox = (self.lon_min, self.lat_min, self.lon_max, self.lat_max)
        import numpy as np

        dummy = np.zeros((256, 256, 3), dtype=np.uint8)

        def _get_patch(geom: dict[str, Any]) -> np.ndarray:
            coords = geom.get("coordinates", [[]])[0] if geom.get("type") == "Polygon" else []
            if not coords:
                return dummy
            lons = [c[0] for c in coords]
            lats = [c[1] for c in coords]
            bbox = (min(lons), min(lats), max(lons), max(lats))
            patch = crop_patch(self.output_dir, bbox, tile_bbox)
            return patch if patch is not None else dummy

        def _get_road_patch(geom: dict[str, Any]) -> np.ndarray:
            coords = geom.get("coordinates", [])
            if coords and isinstance(coords[0], list):
                flat = coords if isinstance(coords[0][0], (int, float)) else coords[0]
                lons = [c[0] for c in flat]
                lats = [c[1] for c in flat]
                bbox = (min(lons), min(lats), max(lons), max(lats))
                cropped = crop_patch(self.output_dir, bbox, tile_bbox)
                if cropped is not None:
                    return cropped
            return dummy

        # ── Buildings ─────────────────────────────────────────────────
        buildings_path = self.output_dir / "buildings.geojson"
        if buildings_path.exists():
            fc = json.loads(buildings_path.read_text(encoding="utf-8"))
            ambiguous = [
                f
                for f in fc.get("features", [])
                if f.get("properties", {}).get("building") == "yes"
                and "xplane_confidence" not in f.get("properties", {})
            ]
            if ambiguous:
                console.print(
                    f"[cyan]Classifying {len(ambiguous)} buildings ({self.workers} workers)…[/cyan]"
                )
                lock = threading.Lock()
                done = [0]

                def _classify_building(feat: dict[str, Any]) -> None:
                    props = feat.get("properties", {})
                    patch = _get_patch(feat.get("geometry", {}))
                    result = classifier.classify_building(
                        patch, {k: str(v) for k, v in props.items()}
                    )
                    props["xplane_type"] = result["building_type"]
                    props["xplane_stories"] = result.get("stories", 2)
                    props["xplane_roof"] = result.get("roof_type", "gable")
                    props["xplane_material"] = result.get("material", "mixed")
                    props["xplane_height_m"] = result["height_m"]
                    props["xplane_confidence"] = result["confidence"]
                    with lock:
                        done[0] += 1
                        if done[0] % 10 == 0 or done[0] == len(ambiguous):
                            console.print(f"[dim]  buildings {done[0]}/{len(ambiguous)}[/dim]")
                            buildings_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")

                with ThreadPoolExecutor(max_workers=self.workers) as pool:
                    futures = [pool.submit(_classify_building, f) for f in ambiguous]
                    for fut in as_completed(futures):
                        fut.result()  # propagate exceptions
                buildings_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")

        # ── Forests ───────────────────────────────────────────────────
        landcover_path = self.output_dir / "landcover.geojson"
        if landcover_path.exists():
            fc = json.loads(landcover_path.read_text(encoding="utf-8"))
            forests = [
                f
                for f in fc.get("features", [])
                if f.get("properties", {}).get("label") == "tree_cover"
                and "xplane_confidence" not in f.get("properties", {})
            ]
            if forests:
                console.print(
                    f"[cyan]Classifying {len(forests)} forest polygons "
                    f"({self.workers} workers)…[/cyan]"
                )
                lock = threading.Lock()
                done = [0]

                def _classify_forest(feat: dict[str, Any]) -> None:
                    props = feat.get("properties", {})
                    patch = _get_patch(feat.get("geometry", {}))
                    ndvi = float(props.get("ndvi_density", 0.7))
                    result = classifier.classify_forest(
                        patch, props.get("label", "tree_cover"), ndvi
                    )
                    props["xplane_species"] = result["species_mix"]
                    props["xplane_density"] = result["canopy_density"]
                    props["xplane_confidence"] = result["confidence"]
                    with lock:
                        done[0] += 1
                        if done[0] % 10 == 0 or done[0] == len(forests):
                            console.print(f"[dim]  forests {done[0]}/{len(forests)}[/dim]")
                            landcover_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")

                with ThreadPoolExecutor(max_workers=self.workers) as pool:
                    futures = [pool.submit(_classify_forest, f) for f in forests]
                    for fut in as_completed(futures):
                        fut.result()
                landcover_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")

        # ── Roads ─────────────────────────────────────────────────────
        roads_path = self.output_dir / "roads.geojson"
        if roads_path.exists() and not self.no_roads:
            fc = json.loads(roads_path.read_text(encoding="utf-8"))
            roads = [
                f
                for f in fc.get("features", [])
                if "xplane_confidence" not in f.get("properties", {})
            ]
            if roads:
                console.print(
                    f"[cyan]Classifying {len(roads)} road segments ({self.workers} workers)…[/cyan]"
                )
                lock = threading.Lock()
                done = [0]

                def _classify_road(feat: dict[str, Any]) -> None:
                    props = feat.get("properties", {})
                    patch = _get_road_patch(feat.get("geometry", {}))
                    result = classifier.classify_road(patch, {k: str(v) for k, v in props.items()})
                    props["xplane_surface"] = result["surface_type"]
                    props["xplane_lanes"] = result["lane_count"]
                    props["xplane_confidence"] = result["confidence"]
                    with lock:
                        done[0] += 1
                        if done[0] % 10 == 0 or done[0] == len(roads):
                            console.print(f"[dim]  roads {done[0]}/{len(roads)}[/dim]")
                            roads_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")

                with ThreadPoolExecutor(max_workers=self.workers) as pool:
                    futures = [pool.submit(_classify_road, f) for f in roads]
                    for fut in as_completed(futures):
                        fut.result()
                roads_path.write_text(json.dumps(fc, indent=2), encoding="utf-8")

        # ── Summary ───────────────────────────────────────────────────
        if classifier.review_count > 0:
            classifier.flush_review_queue()
            console.print(f"  [yellow]{classifier.review_count} items queued for review[/yellow]")

    def _stage_review(self) -> None:
        """Launch inline interactive review if --review-all or a review queue exists."""
        queue_path = self.output_dir / "review_queue.json"
        if not queue_path.exists():
            if self.review_all:
                console.print(
                    "[dim]  No review_queue.json — LLM classification has not run. "
                    "Review is only available after Bedrock classification.[/dim]"
                )
            return

        import json as _json

        items = _json.loads(queue_path.read_text(encoding="utf-8"))
        if not items:
            return

        count = len(items)
        console.print(f"\n[bold yellow]⚠ {count} item(s) queued for human review.[/bold yellow]")

        if self.auto:
            console.print("[dim]  --auto: accepting LLM suggestions without review[/dim]")
            return

        console.print(
            "  Review now interactively, or quit and run later with:\n"
            f"  [bold]uv run xplane-gen review "
            f"--queue {queue_path} --output {self.output_dir / 'resolved_queue.json'}[/bold]\n"
        )

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
            no_roads=self.no_roads,
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

    _FETCH_STAGES = {"fetch_osm", "fetch_rasters", "fetch_ortho", "annotate"}

    def _reset_to_cached_data(self) -> None:
        """Keep only fetch stages as completed, forcing regeneration from cached data."""
        completed = self._state.get("completed", [])
        self._state["completed"] = [s for s in completed if s in self._FETCH_STAGES]
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        console.print("[cyan]Regenerating from cached data…[/cyan]")

    def _force_stage(self, stage: str) -> None:
        """Remove a stage from completed list so it re-runs."""
        completed = self._state.get("completed", [])
        if stage in completed:
            completed.remove(stage)
            self.state_file.write_text(json.dumps(self._state, indent=2), encoding="utf-8")

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
