"""Install add-ons from archives or folders and toggle/remove them safely.

A flightsim.to download may wrap the package in any number of ways: the
package at the archive root, inside a versioned folder, inside a ``Community``
folder, or several packages side by side. We locate every ``manifest.json`` and
treat its parent directory as a package root, ignoring nested ones.

Enable/disable and remove are non-destructive: disabled packages move to a
managed store and removed packages move to a trash store, both reversible.
"""

from __future__ import annotations

import shutil
import tempfile
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ARCHIVE_SUFFIXES = {".zip", ".rar", ".7z"}


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
def _extract(archive: Path, dest: Path) -> None:
    suffix = archive.suffix.lower()
    if suffix == ".zip":
        try:
            with zipfile.ZipFile(archive) as zf:
                zf.extractall(dest)
        except zipfile.BadZipFile as exc:
            raise InstallError(f"Not a valid zip archive: {archive.name}") from exc
        return
    # rar / 7z need an external tool; use whatever the user has installed.
    tool = _external_extractor()
    if tool is None:
        raise InstallError(
            f"{suffix} archives need 7z, unar or unrar installed. "
            f"Install one (e.g. 'sudo apt install p7zip-full') or extract {archive.name} manually."
        )
    import subprocess

    cmd = tool + [str(archive)]
    proc = subprocess.run(cmd, cwd=dest, capture_output=True, text=True)
    if proc.returncode != 0:
        raise InstallError(f"Failed to extract {archive.name}: {proc.stderr.strip()[:200]}")


def _external_extractor() -> list[str] | None:
    if shutil.which("7z"):
        return ["7z", "x", "-y"]
    if shutil.which("7za"):
        return ["7za", "x", "-y"]
    if shutil.which("unar"):
        return ["unar", "-f", "-o", "."]
    if shutil.which("unrar"):
        return ["unrar", "x", "-o+"]
    return None


# ---------------------------------------------------------------- find packages
def find_packages(root: Path) -> list[Path]:
    """Return top-level package roots (dirs holding manifest.json/layout.json)."""
    markers: list[Path] = []
    for marker_name in ("manifest.json", "layout.json"):
        markers += [p.parent for p in root.rglob(marker_name)]
    # Deduplicate and drop any directory nested inside another candidate.
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


def _place(src: Path, community: Path, trash: Path | None) -> str:
    """Move package dir *src* into *community*, backing up any existing copy."""
    community.mkdir(parents=True, exist_ok=True)
    target = community / src.name
    if target.exists():
        if trash is not None:
            _to_trash(target, trash)
        else:
            shutil.rmtree(target, ignore_errors=True)
    shutil.move(str(src), str(target))
    return src.name


# ------------------------------------------------------------------ public ops
def install_archive(
    archive: Path, community: Path, trash: Path | None = None
) -> InstallResult:
    archive = Path(archive).expanduser()
    if not archive.is_file():
        raise InstallError(f"File not found: {archive}")
    if archive.suffix.lower() not in ARCHIVE_SUFFIXES:
        raise InstallError(f"Unsupported file type: {archive.suffix or archive.name}")

    result = InstallResult()
    with tempfile.TemporaryDirectory(prefix="liftoff-") as tmp:
        tmpdir = Path(tmp)
        _extract(archive, tmpdir)
        result = _install_from_tree(tmpdir, community, trash, fallback_name=archive.stem)
    return result


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
            shutil.move(str(tree), str(staged))
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
    shutil.move(str(addon_path), str(target))
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
    shutil.move(str(path), str(dest))


def _safe_name(name: str) -> str:
    cleaned = "".join(c for c in name if c.isalnum() or c in " ._-").strip()
    return cleaned or "addon"
