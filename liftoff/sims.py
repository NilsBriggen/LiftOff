"""Detect Microsoft Flight Simulator installs and their Community folders.

On Linux MSFS runs through Steam Proton, so the Windows ``%AppData%`` tree
lives inside a Proton prefix::

    <steam>/steamapps/compatdata/<appid>/pfx/drive_c/users/steamuser/AppData/...

The real Community folder can be relocated by the user; the authoritative
location is the ``InstalledPackagesPath`` entry inside ``UserCfg.opt``. We read
that, translate the Windows path back to Linux, and append ``/Community`` —
falling back to the default next to ``UserCfg.opt`` when translation fails.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

from .config import SimProfile

# Steam AppIDs and their (roaming folder, MS Store package) AppData names.
MSFS_TITLES = [
    ("1250410", "msfs2020", "Microsoft Flight Simulator",
     "Microsoft.FlightSimulator_8wekyb3d8bbwe"),
    ("2537590", "msfs2024", "Microsoft Flight Simulator 2024",
     "Microsoft.Limitless_8wekyb3d8bbwe"),
]

_INSTALLED_PATH_RE = re.compile(r'InstalledPackagesPath\s+"([^"]+)"', re.IGNORECASE)


def steam_roots() -> list[Path]:
    """Candidate Steam base directories that actually exist on this machine."""
    home = Path.home()
    candidates = [
        home / ".steam/steam",
        home / ".steam/root",
        home / ".local/share/Steam",
        home / ".var/app/com.valvesoftware.Steam/data/Steam",  # Flatpak Steam
        home / ".steam/debian-installation",
    ]
    roots: list[Path] = []
    for path in candidates:
        if path.is_dir() and path not in roots:
            roots.append(path)
    return roots


def _library_dirs(root: Path) -> list[Path]:
    """All Steam library 'steamapps' dirs, including extra drives from the VDF."""
    libs = [root / "steamapps"]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            for match in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text("utf-8", "ignore")):
                lib = Path(match.group(1).replace("\\\\", "/")) / "steamapps"
                if lib.is_dir() and lib not in libs:
                    libs.append(lib)
        except OSError:
            pass
    return [lib for lib in libs if lib.is_dir()]


def _prefix_for(appid: str) -> Path | None:
    for root in steam_roots():
        for lib in _library_dirs(root):
            pfx = lib / "compatdata" / appid / "pfx"
            if pfx.is_dir():
                return pfx
    return None


def _win_to_linux(winpath: str, pfx: Path) -> Path | None:
    """Translate a Windows path from a Proton prefix back to a Linux path."""
    winpath = winpath.strip().replace("\\", "/")
    drive = winpath[:2].upper()
    rest = winpath[2:].lstrip("/")
    if drive == "C:":
        return pfx / "drive_c" / rest
    if drive == "Z:":  # Proton maps Z: to the Linux filesystem root
        return Path("/") / rest
    # Other drive letters are user-mounted via dosdevices symlinks.
    dosdev = pfx / "dosdevices" / f"{drive.lower()}"
    if dosdev.exists():
        return (dosdev / rest).resolve()
    return None


def _community_from_usercfg(usercfg: Path, pfx: Path) -> Path | None:
    try:
        text = usercfg.read_text("utf-8", "ignore")
    except OSError:
        return None
    match = _INSTALLED_PATH_RE.search(text)
    if match:
        base = _win_to_linux(match.group(1), pfx)
        if base is not None:
            return base / "Community"
    # Fallback: default layout next to UserCfg.opt (…/<Title>/Packages/Community).
    return usercfg.parent / "Packages" / "Community"


def detect() -> list[SimProfile]:
    """Return a profile for every MSFS Community folder we can locate."""
    profiles: list[SimProfile] = []
    seen: set[str] = set()

    for appid, kind, roaming_name, store_pkg in MSFS_TITLES:
        pfx = _prefix_for(appid)
        if pfx is None:
            continue
        users = pfx / "drive_c" / "users"
        if not users.is_dir():
            continue
        for user_dir in users.iterdir():
            appdata = user_dir / "AppData"
            usercfgs = [
                appdata / "Roaming" / roaming_name / "UserCfg.opt",
                appdata / "Local" / "Packages" / store_pkg / "LocalCache" / "UserCfg.opt",
            ]
            for usercfg in usercfgs:
                if not usercfg.exists():
                    continue
                community = _community_from_usercfg(usercfg, pfx)
                if community is None:
                    continue
                key = str(community)
                if key in seen:
                    continue
                seen.add(key)
                label = roaming_name.replace("Microsoft Flight Simulator", "MSFS").strip()
                profiles.append(
                    SimProfile(
                        id=f"{kind}-{appid}",
                        name=label or roaming_name,
                        community=key,
                        kind=kind,
                        detected=True,
                    )
                )
    return profiles


def make_custom(name: str, community: str) -> SimProfile:
    """Build a user-defined sim profile for any Community-style folder."""
    return SimProfile(
        id=f"custom-{uuid.uuid4().hex[:8]}",
        name=name or "Custom",
        community=str(Path(community).expanduser()),
        kind="custom",
        detected=False,
    )
