"""Persistent configuration and XDG paths for LiftOff.

Everything lives under the standard XDG locations so the tool stays portable
and leaves no mess: config in ``~/.config/liftoff`` and managed data (the
disabled/trash stores) in ``~/.local/share/liftoff``.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "liftoff"


def _xdg(env: str, default: str) -> Path:
    value = os.environ.get(env)
    return Path(value).expanduser() if value else Path.home() / default


def config_dir() -> Path:
    return _xdg("XDG_CONFIG_HOME", ".config") / APP_NAME


def data_dir() -> Path:
    return _xdg("XDG_DATA_HOME", ".local/share") / APP_NAME


def config_file() -> Path:
    return config_dir() / "config.json"


def default_downloads_dir() -> Path:
    """Best-effort guess of the user's Downloads folder."""
    env = os.environ.get("XDG_DOWNLOAD_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / "Downloads"


@dataclass
class SimProfile:
    """A managed simulator install pointing at one Community folder."""

    id: str
    name: str
    community: str
    kind: str = "msfs"  # msfs2020 | msfs2024 | xplane | custom
    detected: bool = False

    @property
    def community_path(self) -> Path:
        return Path(self.community).expanduser()


@dataclass
class Config:
    sims: list[SimProfile] = field(default_factory=list)
    active: str | None = None
    downloads_dir: str = ""
    api_token: str = ""
    confirm_remove: bool = True

    # ------------------------------------------------------------------ load
    @classmethod
    def load(cls) -> Config:
        path = config_file()
        if not path.exists():
            return cls()
        try:
            raw = json.loads(path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        sims = [SimProfile(**s) for s in raw.get("sims", []) if "id" in s and "community" in s]
        return cls(
            sims=sims,
            active=raw.get("active"),
            downloads_dir=raw.get("downloads_dir", ""),
            api_token=raw.get("api_token", ""),
            confirm_remove=bool(raw.get("confirm_remove", True)),
        )

    # ------------------------------------------------------------------ save
    def save(self) -> None:
        path = config_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "sims": [asdict(s) for s in self.sims],
            "active": self.active,
            "downloads_dir": self.downloads_dir,
            "api_token": self.api_token,
            "confirm_remove": self.confirm_remove,
        }
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), "utf-8")
        tmp.replace(path)

    # --------------------------------------------------------------- helpers
    def get_sim(self, sim_id: str | None) -> SimProfile | None:
        return next((s for s in self.sims if s.id == sim_id), None)

    def active_sim(self) -> SimProfile | None:
        return self.get_sim(self.active) or (self.sims[0] if self.sims else None)

    def add_sim(self, sim: SimProfile) -> None:
        """Add or replace a sim profile (matched by id), keeping it unique."""
        self.sims = [s for s in self.sims if s.id != sim.id]
        self.sims.append(sim)
        if self.active is None:
            self.active = sim.id

    def merge_detected(self, detected: list[SimProfile]) -> int:
        """Add freshly detected sims that we don't already track. Returns count."""
        known = {s.community for s in self.sims}
        added = 0
        for sim in detected:
            if sim.community not in known:
                self.add_sim(sim)
                known.add(sim.community)
                added += 1
        return added

    def downloads_path(self) -> Path:
        if self.downloads_dir:
            return Path(self.downloads_dir).expanduser()
        return default_downloads_dir()

    def disabled_store(self, sim_id: str) -> Path:
        return data_dir() / "disabled" / sim_id

    def trash_store(self, sim_id: str) -> Path:
        return data_dir() / "trash" / sim_id
