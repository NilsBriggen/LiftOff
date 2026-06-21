"""Qt dialogs for LiftOff: settings, simulators, downloads and flightsim.to."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import fsto
from .config import Config
from .library import human_size
from .sims import detect, make_custom


def _browse_dir(parent: QWidget, line: QLineEdit) -> None:
    start = line.text() or str(Path.home())
    chosen = QFileDialog.getExistingDirectory(parent, "Choose folder", start)
    if chosen:
        line.setText(chosen)


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)

        form = QFormLayout()
        self.downloads = QLineEdit(str(cfg.downloads_path()))
        dl_row = QHBoxLayout()
        dl_row.addWidget(self.downloads)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: _browse_dir(self, self.downloads))
        dl_row.addWidget(browse)
        dl_wrap = QWidget()
        dl_wrap.setLayout(dl_row)
        form.addRow("Downloads folder", dl_wrap)

        self.token = QLineEdit(cfg.api_token)
        self.token.setEchoMode(QLineEdit.Password)
        self.token.setPlaceholderText("optional — enables in-app flightsim.to search")
        form.addRow("flightsim.to API token", self.token)

        self.confirm = QCheckBox("Confirm before removing add-ons")
        self.confirm.setChecked(cfg.confirm_remove)
        form.addRow("", self.confirm)

        note = QLabel("Removed add-ons go to a recoverable trash store, never deleted outright.")
        note.setObjectName("hint")
        note.setWordWrap(True)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(note)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self.cfg.downloads_dir = self.downloads.text().strip()
        self.cfg.api_token = self.token.text().strip()
        self.cfg.confirm_remove = self.confirm.isChecked()
        self.cfg.save()
        self.accept()


class AddFolderDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Add a Community folder")
        self.setMinimumWidth(560)
        self.result_value: tuple[str, str] | None = None

        form = QFormLayout()
        self.name = QLineEdit()
        self.name.setPlaceholderText("e.g. MSFS 2024")
        form.addRow("Name", self.name)

        self.path = QLineEdit()
        self.path.setPlaceholderText("path to the Community folder")
        row = QHBoxLayout()
        row.addWidget(self.path)
        browse = QPushButton("Browse…")
        browse.clicked.connect(lambda: _browse_dir(self, self.path))
        row.addWidget(browse)
        wrap = QWidget()
        wrap.setLayout(row)
        form.addRow("Folder", wrap)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._ok)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _ok(self) -> None:
        path = self.path.text().strip()
        if path:
            self.result_value = (self.name.text().strip() or "Custom", path)
            self.accept()


class SimsDialog(QDialog):
    def __init__(self, cfg: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.changed = False
        self.setWindowTitle("Simulators")
        self.setMinimumSize(620, 380)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._activate())

        detect_btn = QPushButton("Auto-detect")
        detect_btn.clicked.connect(self._detect)
        add_btn = QPushButton("Add folder…")
        add_btn.clicked.connect(self._add)
        activate_btn = QPushButton("Activate")
        activate_btn.setObjectName("primary")
        activate_btn.clicked.connect(self._activate)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)

        row = QHBoxLayout()
        row.addWidget(detect_btn)
        row.addWidget(add_btn)
        row.addStretch(1)
        row.addWidget(activate_btn)
        row.addWidget(close_btn)

        hint = QLabel("Double-click a simulator to make it active. "
                      "Auto-detect scans Steam/Proton installs.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.list)
        layout.addWidget(hint)
        layout.addLayout(row)
        self._refresh()

    def _refresh(self) -> None:
        self.list.clear()
        for sim in self.cfg.sims:
            mark = "●" if sim.id == self.cfg.active else "○"
            missing = "" if sim.community_path.is_dir() else "   (folder missing)"
            item = QListWidgetItem(f"{mark}  {sim.name}{missing}\n      {sim.community}")
            item.setData(Qt.UserRole, sim.id)
            self.list.addItem(item)

    def _selected_id(self) -> str | None:
        item = self.list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _activate(self) -> None:
        sim_id = self._selected_id()
        if sim_id:
            self.cfg.active = sim_id
            self.cfg.save()
            self.changed = True
            self.accept()

    def _detect(self) -> None:
        added = self.cfg.merge_detected(detect())
        self.cfg.save()
        self.changed = self.changed or bool(added)
        self._refresh()
        QMessageBox.information(
            self, "Auto-detect",
            f"Detected {added} new install(s)." if added else "No new installs found.",
        )

    def _add(self) -> None:
        dlg = AddFolderDialog(self)
        if dlg.exec() and dlg.result_value:
            name, path = dlg.result_value
            self.cfg.add_sim(make_custom(name, path))
            self.cfg.save()
            self.changed = True
            self._refresh()


class DownloadsDialog(QDialog):
    def __init__(self, downloads_dir: Path, parent: QWidget | None = None):
        super().__init__(parent)
        self.downloads_dir = downloads_dir
        self.result_value: str | None = None
        self.setWindowTitle("Install from Downloads")
        self.setMinimumSize(620, 400)

        self.files = fsto.find_downloads(downloads_dir)
        self.list = QListWidget()
        for path in self.files:
            size = human_size(path.stat().st_size)
            item = QListWidgetItem(f"{path.name}\n      {size}")
            item.setData(Qt.UserRole, str(path))
            self.list.addItem(item)
        if not self.files:
            self.list.addItem(QListWidgetItem(
                "No .zip / .rar / .7z archives found.\n"
                "Download an add-on from flightsim.to, then reopen this."))
        self.list.itemDoubleClicked.connect(lambda _i: self._install())

        header = QLabel(f"Watching: {downloads_dir}")
        header.setObjectName("hint")

        install_btn = QPushButton("Install")
        install_btn.setObjectName("primary")
        install_btn.setEnabled(bool(self.files))
        install_btn.clicked.connect(self._install)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(install_btn)
        row.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(header)
        layout.addWidget(self.list)
        layout.addLayout(row)

    def _install(self) -> None:
        item = self.list.currentItem()
        if item and item.data(Qt.UserRole):
            self.result_value = item.data(Qt.UserRole)
            self.accept()


class FlightSimToDialog(QDialog):
    CATEGORIES = [("Liveries", "liveries"), ("Aircraft", "aircraft"),
                  ("Airports", "scenery"), ("Popular", "featured/downloads")]

    def __init__(self, cfg: Config, parent: QWidget | None = None):
        super().__init__(parent)
        self.cfg = cfg
        self.results: list[fsto.RemoteFile] = []
        self.setWindowTitle("Browse flightsim.to")
        self.setMinimumSize(640, 460)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search flightsim.to and press Enter…")
        self.search.returnPressed.connect(self._search)

        cats = QHBoxLayout()
        for label, slug in self.CATEGORIES:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _c=False, s=slug, ll=label: self._open_category(s, ll))
            cats.addWidget(btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search)
        layout.addLayout(cats)

        self.results_list = QListWidget()
        self.results_list.itemDoubleClicked.connect(self._open_result)
        if self.client.enabled:
            layout.addWidget(self.results_list)
            tip = QLabel("Results open on flightsim.to. After downloading, "
                         "use Downloads to install.")
        else:
            tip = QLabel("Searches open in your browser. Download an add-on, then click "
                         "Downloads to install it.\n"
                         "Add an API token in Settings for in-app search.")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        layout.addLayout(row)

    @property
    def client(self) -> fsto.FlightSimToClient:
        return fsto.FlightSimToClient(self.cfg.api_token)

    def _search(self) -> None:
        query = self.search.text().strip()
        if not query:
            return
        if not self.client.enabled:
            fsto.open_in_browser(fsto.search_url(query))
            return
        try:
            self.results = self.client.search(query)
        except fsto.ApiError as exc:
            QMessageBox.warning(self, "flightsim.to", str(exc))
            return
        self.results_list.clear()
        for item in self.results:
            sub = item.author or item.category or ""
            self.results_list.addItem(QListWidgetItem(f"{item.title}\n      {sub}"))
        if not self.results:
            self.results_list.addItem(QListWidgetItem("No results."))

    def _open_result(self) -> None:
        row = self.results_list.currentRow()
        if 0 <= row < len(self.results):
            fsto.open_in_browser(self.results[row].url or fsto.BASE_URL)

    def _open_category(self, slug: str, _label: str) -> None:
        fsto.open_in_browser(fsto.search_url(category=slug))
