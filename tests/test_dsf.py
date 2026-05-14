"""Task 1: DSFTool spike tests."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from shapely.geometry import LinearRing

from xplane_gen.dsf import (
    DsfWriter,
    ExclusionZone,
    ForestFeature,
    _dsf_path,
    _ensure_ccw,
)


def make_writer() -> DsfWriter:
    w = DsfWriter(tile_west=-123, tile_south=47)
    w.add_forest(
        ForestFeature(
            resource="lib/g8/trees_decid_cld_wet.for",
            density=0.8,
            coords=[(-122.6, 47.6), (-122.5, 47.6), (-122.5, 47.7), (-122.6, 47.7), (-122.6, 47.6)],
        )
    )
    w.add_exclusion(ExclusionZone("for", -123, 47, -122, 48))
    return w


def test_dsf_path() -> None:
    p = _dsf_path(Path("/out"), 47, -123)
    assert p == Path("/out/Earth nav data/+47-123/+47-123.dsf")


def test_render_contains_required_properties() -> None:
    text = make_writer()._render()
    assert "sim/overlay 1" in text
    assert "sim/west -123" in text
    assert "sim/south 47" in text
    assert "lib/g8/trees_decid_cld_wet.for" in text
    assert "sim/exclude_for" in text


def test_render_polygon_winding() -> None:
    """Outer ring coords must be CCW in rendered output."""
    cw_coords = [(-122.6, 47.7), (-122.5, 47.7), (-122.5, 47.6), (-122.6, 47.6), (-122.6, 47.7)]
    w = DsfWriter(tile_west=-123, tile_south=47)
    w.add_forest(ForestFeature("lib/g8/trees_decid_cld_wet.for", 0.5, cw_coords))
    w._render()
    ccw = _ensure_ccw(cw_coords)
    assert LinearRing(ccw).is_ccw


def test_ensure_ccw_already_ccw() -> None:
    ccw = [(-122.6, 47.6), (-122.5, 47.6), (-122.5, 47.7), (-122.6, 47.7), (-122.6, 47.6)]
    assert _ensure_ccw(ccw) == ccw


def test_ensure_ccw_flips_cw() -> None:
    cw = [(-122.6, 47.7), (-122.5, 47.7), (-122.5, 47.6), (-122.6, 47.6), (-122.6, 47.7)]
    assert LinearRing(_ensure_ccw(cw)).is_ccw


def test_compile_calls_dsftool(tmp_path: Path) -> None:
    writer = make_writer()
    fake_dsf = tmp_path / "Earth nav data" / "+47-123" / "+47-123.dsf"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        fake_dsf.parent.mkdir(parents=True, exist_ok=True)
        fake_dsf.write_bytes(b"XPLNEDSF")
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("xplane_gen.dsf.subprocess.run", side_effect=fake_run) as mock_run:
        result = writer.compile(tmp_path, dsftool=Path("/fake/DSFTool"))

    assert mock_run.called
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "/fake/DSFTool"
    assert "--text2dsf" in cmd
    assert result == fake_dsf


def test_compile_raises_on_dsftool_failure(tmp_path: Path) -> None:
    writer = make_writer()
    mock_result = MagicMock()
    mock_result.returncode = 1
    mock_result.stderr = "bad input"

    with (
        patch("xplane_gen.dsf.subprocess.run", return_value=mock_result),
        pytest.raises(RuntimeError, match="DSFTool failed"),
    ):
        writer.compile(tmp_path, dsftool=Path("/fake/DSFTool"))


def test_output_folder_structure(tmp_path: Path) -> None:
    writer = make_writer()
    fake_dsf = tmp_path / "Earth nav data" / "+47-123" / "+47-123.dsf"

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        fake_dsf.parent.mkdir(parents=True, exist_ok=True)
        fake_dsf.write_bytes(b"XPLNEDSF")
        m = MagicMock()
        m.returncode = 0
        return m

    with patch("xplane_gen.dsf.subprocess.run", side_effect=fake_run):
        dsf_path = writer.compile(tmp_path, dsftool=Path("/fake/DSFTool"))

    assert dsf_path.parent.name == "+47-123"
    assert dsf_path.parent.parent.name == "Earth nav data"
    assert dsf_path.stat().st_size > 0
