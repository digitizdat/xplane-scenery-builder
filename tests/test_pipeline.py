"""Task 8: End-to-end CLI and tile state machine tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from xplane_gen.pipeline import STAGES, TileProcessor


def _make_processor(tmp_path: Path, **kwargs: object) -> TileProcessor:
    return TileProcessor(47.0, -123.0, 48.0, -122.0, tmp_path, **kwargs)


# ── state machine ─────────────────────────────────────────────────────────────


def test_state_file_written_after_each_stage(tmp_path: Path) -> None:
    proc = _make_processor(tmp_path)
    proc._mark_done("fetch_osm")
    state = json.loads((tmp_path / "tile_state.json").read_text())
    assert "fetch_osm" in state["completed"]


def test_completed_stage_detected(tmp_path: Path) -> None:
    proc = _make_processor(tmp_path)
    proc._mark_done("fetch_osm")
    assert proc._completed("fetch_osm")
    assert not proc._completed("fetch_rasters")


def test_state_persists_across_instances(tmp_path: Path) -> None:
    proc1 = _make_processor(tmp_path)
    proc1._mark_done("fetch_osm")

    proc2 = _make_processor(tmp_path)
    assert proc2._completed("fetch_osm")
    assert not proc2._completed("fetch_rasters")


def test_tile_sw_corner(tmp_path: Path) -> None:
    proc = TileProcessor(47.6, -122.4, 48.6, -121.4, tmp_path)
    assert proc.tile_west == -123
    assert proc.tile_south == 47


# ── run() skips completed stages ─────────────────────────────────────────────


def test_run_skips_completed_stages(tmp_path: Path) -> None:
    proc = _make_processor(tmp_path)
    # Pre-mark all stages done
    for stage in STAGES:
        proc._mark_done(stage)

    called_stages: list[str] = []
    original = proc._run_stage

    def tracking_run_stage(stage: str) -> None:
        called_stages.append(stage)
        original(stage)

    proc._run_stage = tracking_run_stage  # type: ignore[method-assign]

    with (
        patch.object(proc, "_stage_fetch_osm"),
        patch.object(proc, "_stage_fetch_rasters"),
        patch.object(proc, "_stage_classify"),
        patch.object(proc, "_stage_write_dsf"),
        patch.object(proc, "_stage_validate"),
    ):
        proc.run()

    assert called_stages == []


def test_run_executes_all_stages_fresh(tmp_path: Path) -> None:
    proc = _make_processor(tmp_path)
    executed: list[str] = []

    for stage in STAGES[:-1]:
        mock = MagicMock(side_effect=lambda s=stage: executed.append(s))
        setattr(proc, f"_stage_{stage}", mock)

    proc.run()
    assert executed == STAGES[:-1]


# ── dry_run ───────────────────────────────────────────────────────────────────


def test_dry_run_does_not_compile_dsf(tmp_path: Path) -> None:
    proc = _make_processor(tmp_path, dry_run=True)

    with (
        patch.object(proc, "_stage_fetch_osm"),
        patch.object(proc, "_stage_fetch_rasters"),
        patch.object(proc, "_stage_classify"),
        patch("xplane_gen.dsf.build_overlay") as mock_build,
        patch.object(proc, "_stage_validate"),
    ):
        mock_build.return_value = tmp_path / "overlay_preview.txt"
        proc.run()

    mock_build.assert_called_once()
    _, kwargs = mock_build.call_args
    assert kwargs.get("dry_run") is True


# ── validation stage ──────────────────────────────────────────────────────────


def test_validate_stage_runs_without_error(tmp_path: Path) -> None:
    proc = _make_processor(tmp_path)
    # Write a valid polygon GeoJSON
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [-122.6, 47.6],
                            [-122.5, 47.6],
                            [-122.5, 47.7],
                            [-122.6, 47.7],
                            [-122.6, 47.6],
                        ]
                    ],
                },
                "properties": {},
            }
        ],
    }
    (tmp_path / "buildings.geojson").write_text(json.dumps(fc), encoding="utf-8")
    proc._stage_validate()  # should not raise
