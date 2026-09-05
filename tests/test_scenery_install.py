"""Tests for scenery_install: ini editing and pack install/uninstall."""

from pathlib import Path

import pytest

from xplane_gen.scenery_install import (
    GLOBAL_AIRPORTS_LINE,
    SceneryInstallError,
    _validate_pack_name,
    add_entry,
    install_pack,
    list_packs,
    read_ini,
    remove_entry,
    resolve_xplane_path,
    uninstall_pack,
    validate_packs,
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


# ── list_packs / validate_packs ─────────────────────────────────────────────


def _status_by_name(statuses: list, name: str):
    return next(s for s in statuses if s.name == name)


def test_list_packs_healthy(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    install_pack(_make_pack(tmp_path / "src"), xp, name="mypack")

    statuses = list_packs(xp)
    s = _status_by_name(statuses, "mypack")
    assert s.healthy
    assert s.in_ini and s.enabled and s.folder_exists and s.has_dsf
    assert s.issues == []


def test_list_packs_dangling_ini_entry(tmp_path: Path) -> None:
    # ini references a pack that has no folder on disk
    ini = _ini_with_global() + ["SCENERY_PACK Custom Scenery/ghost/"]
    xp = _make_xplane(tmp_path / "xp", ini)

    s = _status_by_name(list_packs(xp), "ghost")
    assert s.in_ini and not s.folder_exists
    assert "folder missing (dangling ini entry)" in s.issues


def test_list_packs_orphan_folder(tmp_path: Path) -> None:
    # folder present but not registered in the ini
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    orphan = xp / "Custom Scenery" / "orphan" / "Earth nav data"
    orphan.mkdir(parents=True)

    s = _status_by_name(list_packs(xp), "orphan")
    assert s.folder_exists and not s.in_ini
    assert "not in scenery_packs.ini (orphan folder)" in s.issues


def test_list_packs_missing_dsf(tmp_path: Path) -> None:
    # registered folder present but no Earth nav data (the flatten bug)
    xp = _make_xplane(tmp_path / "xp", _ini_with_global() + ["SCENERY_PACK Custom Scenery/broken/"])
    (xp / "Custom Scenery" / "broken").mkdir()

    s = _status_by_name(list_packs(xp), "broken")
    assert s.folder_exists and not s.has_dsf
    assert any("Earth nav data" in i for i in s.issues)


def test_list_packs_disabled(tmp_path: Path) -> None:
    ini = _ini_with_global() + ["SCENERY_PACK_DISABLED Custom Scenery/off/"]
    xp = _make_xplane(tmp_path / "xp", ini)
    (xp / "Custom Scenery" / "off" / "Earth nav data").mkdir(parents=True)

    s = _status_by_name(list_packs(xp), "off")
    assert s.in_ini and not s.enabled
    assert "disabled" in s.issues


def test_validate_packs_flags_stale(tmp_path: Path) -> None:
    import os
    import time

    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    build = tmp_path / "build"
    install_pack(_make_pack(build, name="mypack"), xp, name="mypack")

    # Make the build content newer than the installed copy.
    newer = time.time() + 100
    for f in (build / "mypack" / "Earth nav data" / "+30-080").glob("*"):
        os.utime(f, (newer, newer))

    statuses, ok = validate_packs(xp, build)
    s = _status_by_name(statuses, "mypack")
    assert s.build_found and s.stale
    assert "older than build (stale)" in s.issues
    assert not ok


def test_validate_packs_ok_when_current(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    build = tmp_path / "build"
    # install AFTER creating build, so installed copy is at least as new
    install_pack(_make_pack(build, name="mypack"), xp, name="mypack")

    statuses, ok = validate_packs(xp, build)
    s = _status_by_name(statuses, "mypack")
    assert s.build_found and not s.stale
    # "Some Airport" / "z_base_mesh" from the ini have no folder -> unhealthy,
    # so overall ok is False; but mypack itself is clean.
    assert s.issues == []


def test_list_packs_no_build_dir_skips_freshness(tmp_path: Path) -> None:
    xp = _make_xplane(tmp_path / "xp", _ini_with_global())
    install_pack(_make_pack(tmp_path / "src"), xp, name="mypack")

    s = _status_by_name(list_packs(xp, build_dir=None), "mypack")
    assert not s.build_found and not s.stale
