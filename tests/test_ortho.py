"""Tests for ortho.py: tile grid math, .pol generation, fetch_ortho_tiles."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from xplane_gen.ortho import (
    _tile_grid,
    _write_pol,
    fetch_ortho_tiles,
    make_source,
)

# ------------------------------------------------------------------ #
# _tile_grid                                                           #
# ------------------------------------------------------------------ #


def test_tile_grid_single_tile() -> None:
    # bbox smaller than tile size → exactly one tile
    tiles = _tile_grid(38.40, -79.90, 38.41, -79.89, tile_deg=0.02)
    assert len(tiles) == 1
    row, col, lat_min, lon_min, lat_max, lon_max = tiles[0]
    assert row == 0 and col == 0
    assert lat_min == pytest.approx(38.40)
    assert lon_min == pytest.approx(-79.90)
    assert lat_max == pytest.approx(38.41)
    assert lon_max == pytest.approx(-79.89)


def test_tile_grid_multiple_tiles() -> None:
    # 0.05° bbox with 0.02° tiles → 3×3 = 9 tiles (ceil(0.05/0.02) = 3)
    tiles = _tile_grid(38.40, -79.90, 38.45, -79.85, tile_deg=0.02)
    assert len(tiles) == 9
    rows = {t[0] for t in tiles}
    cols = {t[1] for t in tiles}
    assert rows == {0, 1, 2}
    assert cols == {0, 1, 2}


def test_tile_grid_clamps_to_bbox() -> None:
    # Last tile should not exceed bbox boundary
    tiles = _tile_grid(38.40, -79.90, 38.45, -79.85, tile_deg=0.02)
    last = tiles[-1]
    _, _, _, _, lat_max, lon_max = last
    assert lat_max <= 38.45 + 1e-9
    assert lon_max <= -79.85 + 1e-9


def test_tile_grid_covers_full_bbox() -> None:
    # Union of all tiles should cover the full bbox
    tiles = _tile_grid(38.40, -79.90, 38.45, -79.85, tile_deg=0.02)
    assert min(t[2] for t in tiles) == pytest.approx(38.40)
    assert min(t[3] for t in tiles) == pytest.approx(-79.90)
    assert max(t[4] for t in tiles) == pytest.approx(38.45)
    assert max(t[5] for t in tiles) == pytest.approx(-79.85)


# ------------------------------------------------------------------ #
# _write_pol                                                           #
# ------------------------------------------------------------------ #


def test_write_pol_creates_file(tmp_path: Path) -> None:
    pol = tmp_path / "tile.pol"
    _write_pol(pol, "tile.png", 38.40, -79.90, 38.42, -79.88)
    assert pol.exists()


def test_write_pol_content(tmp_path: Path) -> None:
    pol = tmp_path / "tile.pol"
    _write_pol(pol, "tile.png", 38.40, -79.90, 38.42, -79.88)
    text = pol.read_text()
    assert "DRAPED_POLYGON" in text
    assert "TEXTURE_NOWRAP tile.png" in text
    assert "LOAD_CENTER" in text
    assert "LAYER_GROUP TERRAIN 1" in text
    assert "38.41" in text


# ------------------------------------------------------------------ #
# fetch_ortho_tiles                                                    #
# ------------------------------------------------------------------ #


def _make_rgb(h: int = 4, w: int = 4) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def test_fetch_ortho_tiles_writes_png_and_pol(tmp_path: Path) -> None:
    source = MagicMock()
    source.fetch_rgb.return_value = _make_rgb()

    pols = fetch_ortho_tiles(38.40, -79.90, 38.41, -79.89, str(tmp_path), source)

    assert len(pols) == 1
    pol = pols[0]
    assert pol.exists()
    assert pol.suffix == ".pol"
    assert pol.with_suffix(".png").exists()


def test_fetch_ortho_tiles_skips_missing_imagery(tmp_path: Path) -> None:
    source = MagicMock()
    source.fetch_rgb.return_value = None  # no imagery available

    pols = fetch_ortho_tiles(38.40, -79.90, 38.41, -79.89, str(tmp_path), source)

    assert pols == []


def test_fetch_ortho_tiles_resumes_existing(tmp_path: Path) -> None:
    # Pre-create the .pol file — source should not be called again
    out = tmp_path / "orthophoto"
    out.mkdir()
    pol = out / "000_000.pol"
    pol.write_text("existing")

    source = MagicMock()
    pols = fetch_ortho_tiles(38.40, -79.90, 38.41, -79.89, str(tmp_path), source)

    source.fetch_rgb.assert_not_called()
    assert pols == [pol]


def test_fetch_ortho_tiles_multiple_tiles(tmp_path: Path) -> None:
    source = MagicMock()
    source.fetch_rgb.return_value = _make_rgb()

    pols = fetch_ortho_tiles(38.40, -79.90, 38.45, -79.85, str(tmp_path), source)

    assert len(pols) == 9
    assert source.fetch_rgb.call_count == 9


# ------------------------------------------------------------------ #
# make_source                                                          #
# ------------------------------------------------------------------ #


def test_make_source_sentinel2() -> None:
    from xplane_gen.ortho import Sentinel2Source

    assert isinstance(make_source("sentinel2"), Sentinel2Source)


def test_make_source_naip() -> None:
    from xplane_gen.ortho import NAIPSource

    assert isinstance(make_source("naip"), NAIPSource)


def test_make_source_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown ortho source"):
        make_source("landsat")
