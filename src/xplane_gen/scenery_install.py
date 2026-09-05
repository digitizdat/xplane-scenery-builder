"""Install and uninstall generated overlay packs into an X-Plane 12 install.

Copies a generated pack into ``<X-Plane>/Custom Scenery/<name>/`` and maintains
``Custom Scenery/scenery_packs.ini`` so the pack loads at the correct priority.

Overlay packs must sit above the ``SCENERY_PACK *GLOBAL_AIRPORTS*`` marker to
override the default global airports; base meshes go below it.
Reference: https://www.x-plane.com/kb/prioritization-scenery-packs/
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

GLOBAL_AIRPORTS_LINE = "SCENERY_PACK *GLOBAL_AIRPORTS*"
_INI_HEADER = ["I", "1000 Version", "SCENERY", ""]
# Only these subdirectories are scenery content; everything else in a generated
# pack (tile_state.json, review queues, .llm_cache, previews) is skipped.
_CONTENT_SUBDIRS = ("Earth nav data", "orthophoto")


class SceneryInstallError(RuntimeError):
    """Raised for install/uninstall failures (bad path, missing content, etc.)."""


def default_xplane_paths() -> list[Path]:
    """Common X-Plane 12 install locations, most likely first."""
    home = Path.home()
    return [
        home / "Library/Application Support/Steam/steamapps/common/X-Plane 12",
        Path("/Applications/X-Plane 12"),
        home / "X-Plane 12",
    ]


def resolve_xplane_path(override: str | Path | None = None) -> Path:
    """Return an X-Plane install dir that contains a Custom Scenery folder."""
    if override:
        p = Path(override)
        if not (p / "Custom Scenery").is_dir():
            raise SceneryInstallError(f"No 'Custom Scenery' directory under {p}")
        return p
    for cand in default_xplane_paths():
        if (cand / "Custom Scenery").is_dir():
            return cand
    raise SceneryInstallError("X-Plane 12 install not found; pass an explicit path.")


def _validate_pack_name(name: str) -> str:
    """Reject names that are not a single, safe path component."""
    if not name or name in (".", "..") or "/" in name or "\\" in name or name.startswith("."):
        raise SceneryInstallError(f"Invalid pack name: {name!r}")
    return name


def _pack_ref(name: str) -> str:
    return f"Custom Scenery/{name}/"


def _entry_line(name: str) -> str:
    return f"SCENERY_PACK {_pack_ref(name)}"


def _line_pack_path(line: str) -> str | None:
    """Return the pack path of a SCENERY_PACK[_DISABLED] line, else None."""
    s = line.strip()
    for prefix in ("SCENERY_PACK_DISABLED", "SCENERY_PACK"):
        if s.startswith(prefix + " "):
            return s[len(prefix) :].strip()
    return None


def read_ini(ini_path: Path) -> list[str]:
    """Read scenery_packs.ini as lines, or a fresh header if it does not exist."""
    if ini_path.exists():
        return ini_path.read_text(encoding="utf-8").splitlines()
    return list(_INI_HEADER)


def write_ini(ini_path: Path, lines: list[str]) -> None:
    ini_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _first_entry_index(lines: list[str]) -> int:
    """Index of the first pack entry, else the line after the SCENERY header."""
    for i, ln in enumerate(lines):
        if _line_pack_path(ln) is not None:
            return i
    for i, ln in enumerate(lines):
        if ln.strip() == "SCENERY":
            j = i + 1
            while j < len(lines) and lines[j].strip() == "":
                j += 1
            return j
    return len(lines)


def add_entry(lines: list[str], name: str, position: str = "above-global") -> list[str]:
    """Insert a single SCENERY_PACK entry, removing any existing one for name."""
    ref = _pack_ref(name)
    lines = [ln for ln in lines if _line_pack_path(ln) != ref]
    gi = next((i for i, ln in enumerate(lines) if ln.strip() == GLOBAL_AIRPORTS_LINE), None)
    if position == "below-global":
        idx = (gi + 1) if gi is not None else len(lines)
    elif position == "top":
        idx = _first_entry_index(lines)
    else:  # above-global (default)
        idx = gi if gi is not None else _first_entry_index(lines)
    lines.insert(idx, _entry_line(name))
    return lines


def remove_entry(lines: list[str], name: str) -> tuple[list[str], bool]:
    """Remove any entry for name. Returns (new_lines, removed_any)."""
    ref = _pack_ref(name)
    kept = [ln for ln in lines if _line_pack_path(ln) != ref]
    return kept, len(kept) != len(lines)


def install_pack(
    source: str | Path,
    xplane_path: str | Path | None = None,
    name: str | None = None,
    position: str = "above-global",
    force: bool = False,
) -> Path:
    """Copy a generated pack into Custom Scenery and register it in the ini."""
    xp = resolve_xplane_path(xplane_path)
    source = Path(source)
    if not (source / "Earth nav data").is_dir():
        raise SceneryInstallError(f"{source} has no 'Earth nav data' directory")
    name = _validate_pack_name(name or source.name)
    dest = xp / "Custom Scenery" / name
    if dest.exists():
        if not force:
            raise SceneryInstallError(f"{dest} already exists; use force to replace it")
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for sub in _CONTENT_SUBDIRS:
        src = source / sub
        if src.is_dir():
            shutil.copytree(src, dest / sub)
    ini = xp / "Custom Scenery" / "scenery_packs.ini"
    write_ini(ini, add_entry(read_ini(ini), name, position))
    return dest


def uninstall_pack(
    name: str,
    xplane_path: str | Path | None = None,
    delete_files: bool = True,
) -> tuple[bool, bool]:
    """Remove the ini entry and (by default) the pack folder.

    Returns (removed_ini_entry, removed_files). File deletion is bounded to
    ``<X-Plane>/Custom Scenery/<validated name>/``.
    """
    xp = resolve_xplane_path(xplane_path)
    name = _validate_pack_name(name)
    ini = xp / "Custom Scenery" / "scenery_packs.ini"
    removed_line = False
    if ini.exists():
        lines, removed_line = remove_entry(read_ini(ini), name)
        write_ini(ini, lines)
    dest = xp / "Custom Scenery" / name
    removed_files = False
    if delete_files and dest.is_dir():
        shutil.rmtree(dest)
        removed_files = True
    return removed_line, removed_files


# ------------------------------------------------------------------ #
# Inspection: list and validate installed packs                       #
# ------------------------------------------------------------------ #


def _ini_entries(lines: list[str]) -> dict[str, bool]:
    """Map each ``Custom Scenery/<name>/`` ref to enabled (True) / disabled (False).

    Only entries under Custom Scenery are returned (skips *GLOBAL_AIRPORTS* and
    absolute/other refs). The trailing slash is stripped from the name.
    """
    entries: dict[str, bool] = {}
    for ln in lines:
        s = ln.strip()
        enabled = s.startswith("SCENERY_PACK ")
        disabled = s.startswith("SCENERY_PACK_DISABLED ")
        if not (enabled or disabled):
            continue
        ref = _line_pack_path(ln) or ""
        if not ref.startswith("Custom Scenery/"):
            continue
        name = ref[len("Custom Scenery/") :].rstrip("/")
        if name:
            entries[name] = enabled
    return entries


def _newest_content_mtime(pack_dir: Path) -> float | None:
    """Newest file mtime under the pack's scenery content dirs, or None if none."""
    newest: float | None = None
    for sub in _CONTENT_SUBDIRS:
        root = pack_dir / sub
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            if f.is_file():
                m = f.stat().st_mtime
                if newest is None or m > newest:
                    newest = m
    return newest


@dataclass
class PackStatus:
    """Health and freshness of one custom scenery pack."""

    name: str
    in_ini: bool
    enabled: bool
    folder_exists: bool
    has_dsf: bool  # folder has an Earth nav data directory
    stale: bool  # installed content older than the matching build
    build_found: bool  # a matching build dir existed to compare against

    @property
    def healthy(self) -> bool:
        """Registered, enabled, present on disk, and loadable (has DSF)."""
        return self.in_ini and self.enabled and self.folder_exists and self.has_dsf

    @property
    def issues(self) -> list[str]:
        problems: list[str] = []
        if not self.folder_exists:
            problems.append("folder missing (dangling ini entry)")
        elif not self.has_dsf:
            problems.append("no 'Earth nav data' (registered but loads no DSF)")
        if self.folder_exists and not self.in_ini:
            problems.append("not in scenery_packs.ini (orphan folder)")
        if self.in_ini and not self.enabled:
            problems.append("disabled")
        if self.stale:
            problems.append("older than build (stale)")
        return problems


def list_packs(
    xplane_path: str | Path | None = None,
    build_dir: str | Path | None = None,
) -> list[PackStatus]:
    """Return the status of every custom scenery pack (ini entries + folders).

    A pack is included if it appears in scenery_packs.ini and/or exists as a
    folder under Custom Scenery. Freshness is computed against a matching
    ``<build_dir>/<name>/`` directory when one exists.
    """
    xp = resolve_xplane_path(xplane_path)
    cs = xp / "Custom Scenery"
    ini_entries = _ini_entries(read_ini(cs / "scenery_packs.ini"))

    folders = (
        {p.name for p in cs.iterdir() if p.is_dir() and not p.name.startswith(".")}
        if cs.is_dir()
        else set()
    )

    build_root = Path(build_dir) if build_dir is not None else None
    names = sorted(set(ini_entries) | folders)
    statuses: list[PackStatus] = []
    for name in names:
        folder = cs / name
        folder_exists = name in folders
        has_dsf = folder_exists and (folder / "Earth nav data").is_dir()

        stale = False
        build_found = False
        if build_root is not None and folder_exists:
            build_pack = build_root / name
            if build_pack.is_dir():
                build_found = True
                inst_m = _newest_content_mtime(folder)
                build_m = _newest_content_mtime(build_pack)
                if inst_m is not None and build_m is not None and build_m > inst_m:
                    stale = True

        statuses.append(
            PackStatus(
                name=name,
                in_ini=name in ini_entries,
                enabled=ini_entries.get(name, False),
                folder_exists=folder_exists,
                has_dsf=has_dsf,
                stale=stale,
                build_found=build_found,
            )
        )
    return statuses


def validate_packs(
    xplane_path: str | Path | None = None,
    build_dir: str | Path | None = None,
) -> tuple[list[PackStatus], bool]:
    """Return (statuses, ok) where ok is False if any pack is unhealthy or stale."""
    statuses = list_packs(xplane_path, build_dir)
    ok = all(not s.issues for s in statuses)
    return statuses, ok
