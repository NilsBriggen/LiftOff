"""Headless smoke tests for the Textual UI using Textual's test pilot."""

from __future__ import annotations

import json

import pytest

from liftoff.app import LiftOffApp
from liftoff.config import Config, SimProfile


def _make_pkg(parent, name, title, ctype="LIVERY"):
    pkg = parent / name
    pkg.mkdir(parents=True)
    (pkg / "manifest.json").write_text(
        json.dumps({"title": title, "creator": "ACME", "content_type": ctype,
                    "package_version": "1.2.3"})
    )
    (pkg / "layout.json").write_text("{}")
    return pkg


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    community = tmp_path / "Community"
    _make_pkg(community, "b-livery", "Boeing Livery", "LIVERY")
    _make_pkg(community, "a-airport", "Cool Airport", "SCENERY")
    cfg = Config()
    cfg.add_sim(SimProfile(id="msfs", name="MSFS 2024", community=str(community), kind="msfs2024"))
    cfg.save()
    return community


async def test_app_lists_addons(configured):
    app = LiftOffApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        # Wait for the background scan worker to finish populating.
        await app.workers.wait_for_complete()
        await pilot.pause()
        from textual.widgets import DataTable

        table = app.query_one("#table", DataTable)
        assert table.row_count == 2
        assert len(app.addons) == 2


async def test_filter_narrows_rows(configured):
    app = LiftOffApp()
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        app.query_one("#search").value = "airport"
        await pilot.pause()
        from textual.widgets import DataTable

        table = app.query_one("#table", DataTable)
        assert table.row_count == 1
        assert app.filtered[0].display_title == "Cool Airport"


async def test_toggle_disables_addon(configured):
    app = LiftOffApp()
    async with app.run_test() as pilot:
        await app.workers.wait_for_complete()
        await pilot.pause()
        # Cursor starts on the first row (a-airport, sorted by name).
        first = app.filtered[0]
        assert first.enabled
        await pilot.press("e")
        await app.workers.wait_for_complete()
        await pilot.pause()
        await app.workers.wait_for_complete()
        await pilot.pause()
        states = {a.name: a.enabled for a in app.addons}
        assert states[first.name] is False
