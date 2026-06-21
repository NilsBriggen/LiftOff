"""Ensure every modal screen composes and mounts without error."""

from __future__ import annotations

import json

import pytest
from textual.screen import ModalScreen

from liftoff.app import LiftOffApp
from liftoff.config import Config, SimProfile


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    community = tmp_path / "Community"
    pkg = community / "demo"
    pkg.mkdir(parents=True)
    (pkg / "manifest.json").write_text(json.dumps({"title": "Demo", "content_type": "LIVERY"}))
    cfg = Config()
    cfg.add_sim(SimProfile(id="msfs", name="MSFS", community=str(community)))
    cfg.save()
    return community


@pytest.mark.parametrize("key", ["i", "d", "f", "s", "comma", "question_mark"])
async def test_each_modal_opens(configured, key):
    app = LiftOffApp()
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        assert isinstance(app.screen, ModalScreen)
        await pilot.press("escape")
        await pilot.pause()
        # Back to the main screen.
        assert not isinstance(app.screen, ModalScreen)
