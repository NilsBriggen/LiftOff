"""Install add-ons from archives or folders and toggle/remove them safely.

A flightsim.to download may wrap the package in any number of ways: the
package at the archive root, inside a versioned folder, inside a ``Community``
folder, or several packages side by side. We locate every ``manifest.json`` and
treat its parent directory as a package root, ignoring nested ones.

Speed:

* Extraction prefers native C extractors — ``bsdtar``/``unzip`` or the
  ``libarchive`` shared library — and only falls back to Python's ``zipfile``.
* Archives are staged on the *same filesystem* as the Community folder, so
  installing is an atomic ``rename`` instead of copying gigabytes twice.

Enable/disable and remove are non-destructive: disabled packages move to a
managed store and removed packages move to a trash store, both reversible.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}

# libarchive's extract_file works against the current directory, so serialise
# the brief chdir it needs. Everything else in LiftOff uses absolute paths.
_CHDIR_LOCK = threading.Lock()


class InstallError(Exception):
    """A user-facing installation problem."""


@dataclass
class InstallResult:
    installed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.installed)


# --------------------------------------------------------------------- extract
def _run(cmd: list[str]) -> bool:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except (OSError, ValueError):
        return False
    return proc.returncode == 0


def _have(tool: str) -> bool:
    return shutil.which(tool) is not None


def _libarchive_extract(archive: Path, dest: Path) -> bool:
    try:
        import libarchive  # ctypes wrapper over the C libarchive
    except Exception:
        return False
    try:
        with _CHDIR_LOCK:
            cwd = os.getcwd()
            os.chdir(dest)
            try:
                libarchive.extract_file(str(archive))
            finally:
                os.chdir(cwd)
        return True
    except Exception:
        return False


def _zipfile_extract(archive: Path, dest: Path) -> bool:
    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(dest)
        return True
    except (zipfile.BadZipFile, OSError):
        return False


def _bsdtar(archive: Path, dest: Path) -> bool:
    return _have("bsdtar") and _run(["bsdtar", "-xf", str(archive), "-C", str(dest)])


def _strategies(suffix: str):
    """Ordered extractors for a suffix: native C first, Python last."""
    bsdtar = _bsdtar
    if suffix == ".zip":
        return [
            bsdtar,
            lambda a, d: _have("unzip") and _run(["unzip", "-o", "-q", str(a), "-d", str(d)]),
            _libarchive_extract,
            _zipfile_extract,
        ]
    if suffix == ".7z":
        return [
            bsdtar,
            _libarchive_extract,
            lambda a, d: _have("7z") and _run(["7z", "x", "-y", f"-o{d}", str(a)]),
            lambda a, d: _have("7za") and _run(["7za", "x", "-y", f"-o{d}", str(a)]),
        ]
    if suffix == ".rar":
        return [
            bsdtar,
            _libarchive_extract,
            lambda a, d: _have("unar") and _run(["unar", "-f", "-o", str(d), str(a)]),
            lambda a, d: _have("unrar") and _run(["unrar", "x", "-o+", str(a), f"{d}/"]),
        ]
    return [bsdtar, _libarchive_extract]


def _clear(path: Path) -> None:
    for child in path.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)


def _extract(archive: Path, dest: Path) -> None:
    suffix = archive.suffix.lower()
    strategies = _strategies(suffix)
    for extract in strategies:
        _clear(dest)
        if extract(archive, dest):
            return
    _clear(dest)
    if suffix == ".zip":
        raise InstallError(f"Could not extract {archive.name} (corrupt archive?).")
    raise InstallError(
        f"Could not extract {archive.name}. Install libarchive, 7z or unar "
        f"for {suffix} support (e.g. 'sudo apt install libarchive-tools p7zip-full')."
    )


# ---------------------------------------------------------------- find packages
def find_packages(root: Path) -> list[Path]:
    """Return top-level package roots (dirs holding manifest.json/layout.json)."""
    markers: list[Path] = []
    for marker_name in ("manifest.json", "layout.json"):
        markers += [p.parent for p in root.rglob(marker_name)]
    unique = sorted(set(markers), key=lambda p: len(p.parts))
    roots: list[Path] = []
    for cand in unique:
        if not any(cand != r and _is_within(cand, r) for r in roots):
            roots.append(cand)
    return roots


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


# -------------------------------------------------------------- moving in place
def _move(src: Path, dst: Path) -> None:
    try:
        os.replace(src, dst)  # atomic when src and dst share a filesystem
    except OSError:
        shutil.move(str(src), str(dst))  # cross-device: copy + delete


def _place(src: Path, community: Path, trash: Path | None) -> str:
    community.mkdir(parents=True, exist_ok=True)
    target = community / src.name
    if target.exists():
        if trash is not None:
            _to_trash(target, trash)
        else:
            shutil.rmtree(target, ignore_errors=True)
    _move(src, target)
    return src.name


def _staging(community: Path) -> Path:
    """A temp dir on the same filesystem as Community, so moves are renames."""
    parent = community.parent
    base = str(parent) if parent.is_dir() and os.access(parent, os.W_OK) else None
    return Path(tempfile.mkdtemp(prefix=".liftoff-", dir=base))


# ------------------------------------------------------------------ public ops
def install_archive(
    archive: Path, community: Path, trash: Path | None = None
) -> InstallResult:
    archive = Path(archive).expanduser()
    if not archive.is_file():
        raise InstallError(f"File not found: {archive}")
    if archive.suffix.lower() not in ARCHIVE_SUFFIXES:
        raise InstallError(f"Unsupported file type: {archive.suffix or archive.name}")

    staging = _staging(community)
    try:
        _extract(archive, staging)
        return _install_from_tree(staging, community, trash, fallback_name=archive.stem)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def install_folder(folder: Path, community: Path, trash: Path | None = None) -> InstallResult:
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        raise InstallError(f"Folder not found: {folder}")
    return _install_from_tree(folder, community, trash, fallback_name=folder.name)


def _install_from_tree(
    tree: Path, community: Path, trash: Path | None, fallback_name: str
) -> InstallResult:
    result = InstallResult()
    packages = find_packages(tree)
    if not packages:
        raise InstallError(
            "No add-on (manifest.json) found inside. "
            "This may not be an MSFS package, or it is wrapped in an unexpected way."
        )
    for pkg in packages:
        if pkg == tree:
            # Manifest sits at the archive root: wrap it in a sensibly named dir.
            staged = tree.parent / _safe_name(fallback_name)
            _move(tree, staged)
            result.installed.append(_place(staged, community, trash))
        else:
            result.installed.append(_place(pkg, community, trash))
    if len(result.installed) > 1:
        result.warnings.append(f"Installed {len(result.installed)} packages from one archive.")
    return result


def set_enabled(addon_path: Path, enabled: bool, community: Path, disabled_store: Path) -> Path:
    """Move a package between the Community folder and the disabled store."""
    community.mkdir(parents=True, exist_ok=True)
    disabled_store.mkdir(parents=True, exist_ok=True)
    dest_dir = community if enabled else disabled_store
    target = dest_dir / addon_path.name
    if target.resolve() == addon_path.resolve():
        return addon_path
    if target.exists():
        raise InstallError(f"'{addon_path.name}' already exists in the destination.")
    _move(addon_path, target)
    return target


def remove(addon_path: Path, trash: Path | None) -> None:
    """Delete a package, moving it to the trash store first when one is given."""
    if trash is not None:
        _to_trash(addon_path, trash)
    else:
        shutil.rmtree(addon_path, ignore_errors=True)


def _to_trash(path: Path, trash: Path) -> None:
    trash.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = trash / f"{stamp}-{path.name}"
    i = 1
    while dest.exists():
        dest = trash / f"{stamp}-{i}-{path.name}"
        i += 1
    _move(path, dest)


def _safe_name(name: str) -> str:
    cleaned = "".join(c for c in name if c.isalnum() or c in " ._-").strip()
    return cleaned or "addon"
