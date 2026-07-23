"""Tests for scenery_install: ini editing and pack install/uninstall."""

from pathlib import Path

import pytest

from xplane_gen.scenery_install import (
    GLOBAL_AIRPORTS_LINE,
    SceneryInstallError,
    _validate_pack_name,
    add_entry,
    install_pack,
    read_ini,
    remove_entry,
    resolve_xplane_path,
    uninstall_pack,
)


def _ini_with_global() -> list[str]:
    return [
        "I",
        "1000 Version",
        "SCENERY",
        "",
        "SCENERY_PACK Custom Scenery/Some Airport/",
        GLOBAL_AIRPORTS_LINE,
        "SCENERY_PACK Custom Scenery/z_base_mesh/",
    ]


def _make_xplane(tmp_path: Path, ini_lines: list[str] | None = None) -> Path:
    cs = tmp_path / "Custom Scenery"
    cs.mkdir(parents=True)
    if ini_lines is not None:
        (cs / "scenery_packs.ini").write_text("\n".join(ini_lines) + "\n", encoding="utf-8")
    return tmp_path


def _make_pack(tmp_path: Path, name: str = "mypack", with_ortho: bool = True) -> Path:
    pack = tmp_path / name
    dsf_dir = pack / "Earth nav data" / "+30-080"
    dsf_dir.mkdir(parents=True)
    (dsf_dir / "+38-080.dsf").write_bytes(b"XPLNEDSF")
    if with_ortho:
        (pack / "orthophoto").mkdir()
        (pack / "orthophoto" / "000_000.pol").write_text("A\n850\nDRAPED_POLYGON\n")
    # pipeline artifacts that must NOT be copied
    (pack / "tile_state.json").write_text("{}")
    (pack / ".llm_cache").mkdir()
    return pack


# ── ini editing ──────────────────────────────────────────────────────────


def test_add_entry_above_global() -> None:
    lines = add_entry(_ini_with_global(), "mypack", "above-global")
    gi = lines.index(GLOBAL_AIRPORTS_LINE)
    assert lines[gi - 1] == "SCENERY_PACK Custom Scenery/mypack/"


def test_add_entry_below_global() -> None:
    lines = add_entry(_ini_with_global(), "mypack", "below-global")
    gi = lines.index(GLOBAL_AIRPORTS_LINE)
    assert lines[gi + 1] == "SCENERY_PACK Custom Scenery/mypack/"


def test_add_entry_dedupes_existing() -> None:
    lines = add_entry(_ini_with_global(), "mypack")
    lines = add_entry(lines, "mypack")
    assert sum(1 for ln in lines if ln == "SCENERY_PACK Custom Scenery/mypack/") == 1


def test_add_entry_no_global_marker_goes_to_top() -> None:
    base = ["I", "1000 Version", "SCENERY", "", "SCENERY_PACK Custom Scenery/A/"]
    lines = add_entry(base, "mypack", "above-global")
    assert lines[4] == "SCENERY_PACK Custom Scenery/mypack/"


def test_remove_entry() -> None:
    lines, removed = remove_entry(_ini_with_global(), "Some Airport")
    assert removed
    assert all("Some Airport" not in ln for ln in lines)


def test_remove_entry_absent() -> None:
    _, removed = remove_entry(_ini_with_global(), "does-not-exist")
    assert not removed


def test_entry_path_matches_exactly_not_suffix() -> None:
    # "KCRW" must not match "z_KCRW"
    base = ["I", "1000 Version", "SCENERY", "", "SCENERY_PACK Custom Scenery/z_KCRW/"]
    _, removed = remove_entry(base, "KCRW")
    assert not removed


# ── path + name validation ─────────────────────────────────────────────────


def test_resolve_xplane_path_override(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path)
    assert resolve_xplane_path(xp) == xp


def test_resolve_xplane_path_rejects_missing_custom_scenery(tmp_path: Path) -> None:
    with pytest.raises(SceneryInstallError):
        resolve_xplane_path(tmp_path)


@pytest.mark.parametrize("bad", ["", ".", "..", "a/b", "a\\b", ".hidden"])
def test_validate_pack_name_rejects_bad(bad: str) -> None:
    with pytest.raises(SceneryInstallError):
        _validate_pack_name(bad)


@pytest.mark.parametrize("bad", [".", "..", "a/b", "a\\b", ".hidden"])
def test_install_rejects_bad_name(tmp_path: Path, bad: str) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    pack = _make_pack(tmp_path / "src")
    with pytest.raises(SceneryInstallError):
        install_pack(pack, xp, name=bad)


# ── install ─────────────────────────────────────────────────────────────────


def test_install_copies_content_and_skips_artifacts(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    pack = _make_pack(tmp_path / "src")
    dest = install_pack(pack, xp, name="mypack")
    assert (dest / "Earth nav data" / "+30-080" / "+38-080.dsf").exists()
    assert (dest / "orthophoto" / "000_000.pol").exists()
    assert not (dest / "tile_state.json").exists()
    assert not (dest / ".llm_cache").exists()
    ini = read_ini(xp / "Custom Scenery" / "scenery_packs.ini")
    gi = ini.index(GLOBAL_AIRPORTS_LINE)
    assert ini[gi - 1] == "SCENERY_PACK Custom Scenery/mypack/"


def test_install_refuses_pack_without_earth_nav_data(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    bad_pack = tmp_path / "bad"
    bad_pack.mkdir()
    with pytest.raises(SceneryInstallError):
        install_pack(bad_pack, xp, name="bad")


def test_install_refuses_existing_without_force(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    pack = _make_pack(tmp_path / "src")
    install_pack(pack, xp, name="mypack")
    with pytest.raises(SceneryInstallError):
        install_pack(pack, xp, name="mypack")


def test_install_force_replaces(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    pack = _make_pack(tmp_path / "src")
    install_pack(pack, xp, name="mypack")
    dest = install_pack(pack, xp, name="mypack", force=True)
    assert (dest / "Earth nav data" / "+30-080" / "+38-080.dsf").exists()
    ini = read_ini(xp / "Custom Scenery" / "scenery_packs.ini")
    assert sum(1 for ln in ini if ln == "SCENERY_PACK Custom Scenery/mypack/") == 1


# ── uninstall ────────────────────────────────────────────────────────────────


def test_uninstall_removes_files_and_entry(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    pack = _make_pack(tmp_path / "src")
    install_pack(pack, xp, name="mypack")
    removed_line, removed_files = uninstall_pack("mypack", xp, delete_files=True)
    assert removed_line and removed_files
    assert not (xp / "Custom Scenery" / "mypack").exists()
    ini = read_ini(xp / "Custom Scenery" / "scenery_packs.ini")
    assert all("mypack" not in ln for ln in ini)


def test_uninstall_keep_files(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    pack = _make_pack(tmp_path / "src")
    install_pack(pack, xp, name="mypack")
    removed_line, removed_files = uninstall_pack("mypack", xp, delete_files=False)
    assert removed_line and not removed_files
    assert (xp / "Custom Scenery" / "mypack").exists()
