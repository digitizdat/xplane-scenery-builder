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
        patch.object(proc, "_stage_annotate"),
        patch.object(proc, "_stage_fetch_ortho"),
        patch.object(proc, "_stage_classify"),
        patch.object(proc, "_stage_review"),
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
        patch.object(proc, "_stage_annotate"),
        patch.object(proc, "_stage_fetch_ortho"),
        patch.object(proc, "_stage_classify"),
        patch.object(proc, "_stage_review"),
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


# ── reclassify ────────────────────────────────────────────────────────────────


def test_reclassify_clears_results_keeps_source_and_reruns(tmp_path: Path) -> None:
    # A classified building tagged as an MS gap-filler, plus prior queues + state.
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
                "properties": {
                    "building": "yes",
                    "xplane_source": "ms",
                    "xplane_confidence": 0.4,
                    "xplane_stories": 2,
                },
            }
        ],
    }
    (tmp_path / "buildings.geojson").write_text(json.dumps(fc), encoding="utf-8")
    (tmp_path / "review_queue.json").write_text("[]", encoding="utf-8")
    (tmp_path / "resolved_queue.json").write_text("[]", encoding="utf-8")
    for stage in STAGES:
        _make_processor(tmp_path)._mark_done(stage)

    _make_processor(tmp_path, reclassify=True)

    props = json.loads((tmp_path / "buildings.geojson").read_text())["features"][0]["properties"]
    assert props.get("xplane_source") == "ms"  # provenance preserved
    assert "xplane_confidence" not in props  # result cleared
    assert "xplane_stories" not in props
    assert not (tmp_path / "review_queue.json").exists()
    assert not (tmp_path / "resolved_queue.json").exists()

    state = json.loads((tmp_path / "tile_state.json").read_text())["completed"]
    for stage in ("classify", "review", "write_dsf", "validate"):
        assert stage not in state
    assert "fetch_osm" in state  # fetch/ortho data preserved
