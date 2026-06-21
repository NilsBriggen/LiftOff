"""Offscreen tests for the Qt GUI: model, filtering and view wiring.

These run headless via the Qt 'offscreen' platform plugin (set in conftest).
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from liftoff.config import Config, SimProfile  # noqa: E402
from liftoff.gui import LiftOffWindow  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    community = tmp_path / "Community"
    for name, title, ctype in [
        ("b-livery", "Boeing Livery", "LIVERY"),
        ("a-airport", "Cool Airport", "SCENERY"),
        ("c-aircraft", "Nice Aircraft", "AIRCRAFT"),
    ]:
        pkg = community / name
        pkg.mkdir(parents=True)
        (pkg / "manifest.json").write_text(
            json.dumps({"title": title, "creator": "ACME", "content_type": ctype,
                        "package_version": "1.0.0", "total_package_size": "1048576"})
        )
    cfg = Config()
    cfg.add_sim(SimProfile(id="msfs", name="MSFS 2024", community=str(community), kind="msfs2024"))
    cfg.save()
    return community


def test_window_lists_addons(qapp, configured):
    win = LiftOffWindow()
    win.reload_now()
    assert win.model.rowCount() == 3
    assert win.proxy.rowCount() == 3
    assert "3 total" in win.counts_label.text()


def test_filter_narrows_proxy(qapp, configured):
    win = LiftOffWindow()
    win.reload_now()
    win.search.setText("airport")
    assert win.proxy.rowCount() == 1
    src = win.proxy.mapToSource(win.proxy.index(0, 0))
    assert win.model.addon_at(src.row()).display_title == "Cool Airport"


def test_selection_updates_details(qapp, configured):
    win = LiftOffWindow()
    win.reload_now()
    win.table.selectRow(0)
    addon = win._current_addon()
    assert addon is not None
    assert addon.display_title in win.details.toHtml()


def test_size_from_manifest_renders(qapp, configured):
    win = LiftOffWindow()
    win.reload_now()
    # 1 MiB total_package_size -> shown as "1.0 MB", no disk walk needed.
    win.table.selectRow(0)
    assert "1.0 MB" in win.details.toHtml()
