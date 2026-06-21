"""Scan a Community folder and read add-on metadata from ``manifest.json``."""

from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

# Friendly labels for the content_type field used by MSFS manifests.
_CONTENT_LABELS = {
    "AIRCRAFT": "Aircraft",
    "LIVERY": "Livery",
    "SCENERY": "Scenery",
    "MISC": "Misc",
    "INSTRUMENTS": "Instruments",
    "SOUND": "Sound",
}


@dataclass
class Addon:
    name: str  # the package folder name
    path: Path
    enabled: bool = True
    title: str = ""
    creator: str = ""
    content_type: str = ""
    version: str = ""
    min_game_version: str = ""
    size_bytes: int | None = None  # None until computed (lazy)

    @property
    def display_title(self) -> str:
        return self.title or self.name

    @property
    def type_label(self) -> str:
        return _CONTENT_LABELS.get(self.content_type.upper(), self.content_type or "—")


def _read_json(path: Path) -> dict:
    try:
        # MSFS manifests are sometimes saved with a UTF-8 BOM.
        return json.loads(path.read_text("utf-8-sig", "ignore"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {}


def parse_manifest(pkg_dir: Path) -> dict:
    return _read_json(pkg_dir / "manifest.json")


def is_package(path: Path) -> bool:
    """A package folder contains a manifest.json or a layout.json."""
    return path.is_dir() and ((path / "manifest.json").exists() or (path / "layout.json").exists())


def dir_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += os.lstat(os.path.join(root, name)).st_size
            except OSError:
                pass
    return total


def _manifest_size(manifest: dict) -> int | None:
    """MSFS manifests carry total_package_size — use it to avoid a disk walk."""
    value = manifest.get("total_package_size")
    if value in (None, ""):
        return None
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _addon_from_dir(path: Path, enabled: bool, with_size: bool) -> Addon:
    manifest = parse_manifest(path)
    size: int | None = None
    if with_size:
        size = _manifest_size(manifest)
        if size is None:
            size = dir_size(path)  # fallback: walk the package
    return Addon(
        name=path.name,
        path=path,
        enabled=enabled,
        title=str(manifest.get("title", "")).strip(),
        creator=str(manifest.get("creator", "")).strip(),
        content_type=str(manifest.get("content_type", "")).strip(),
        version=str(manifest.get("package_version", "")).strip(),
        min_game_version=str(manifest.get("minimum_game_version", "")).strip(),
        size_bytes=size,
    )


def scan(
    community: Path, disabled_store: Path | None = None, with_size: bool = False
) -> list[Addon]:
    """List enabled add-ons in *community* plus disabled ones in *disabled_store*."""
    entries: list[tuple[Path, bool]] = []
    if community.is_dir():
        for child in sorted(community.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir() and not child.name.startswith("."):
                entries.append((child, True))
    if disabled_store and disabled_store.is_dir():
        for child in sorted(disabled_store.iterdir(), key=lambda p: p.name.lower()):
            if child.is_dir():
                entries.append((child, False))
    if not entries:
        return []
    if with_size and len(entries) > 1:
        # Sizing may need to walk dirs (I/O bound) — fan out across threads.
        with ThreadPoolExecutor(max_workers=min(8, len(entries))) as pool:
            return list(pool.map(lambda e: _addon_from_dir(e[0], e[1], True), entries))
    return [_addon_from_dir(path, enabled, with_size) for path, enabled in entries]


def human_size(num: int | None) -> str:
    if num is None:
        return "…"
    size = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"
