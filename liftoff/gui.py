"""LiftOff desktop GUI (PySide6 / Qt).

A small, fast, native window over the same engine the TUI uses. Long operations
run on a Qt thread pool so the UI never blocks.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    QObject,
    QRunnable,
    QSortFilterProxyModel,
    Qt,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QColor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableView,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .config import Config
from .gui_dialogs import DownloadsDialog, FlightSimToDialog, SettingsDialog, SimsDialog
from .install import InstallError, install_archive, remove, set_enabled
from .library import Addon, human_size, scan
from .theme import (
    GREEN,
    QSS,
    TXT_MUTED,
    TYPE_COLORS,
    TYPE_MISC,
    WELCOME as _WELCOME,
    addon_html as _theme_addon_html,
)

COLUMNS = ["", "Name", "Creator", "Type", "Ver", "Size"]
_ROOT = QModelIndex()  # the (invalid) root index used as a parent default


class AddonTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self._rows: list[Addon] = []

    def set_rows(self, rows: list[Addon]) -> None:
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def addon_at(self, row: int) -> Addon | None:
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def rowCount(self, parent=_ROOT) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=_ROOT) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        addon = self._rows[index.row()]
        col = index.column()
        if role == Qt.DisplayRole:
            return [
                "●" if addon.enabled else "○",
                addon.display_title,
                addon.creator or "—",
                addon.type_label,
                addon.version or "—",
                human_size(addon.size_bytes),
            ][col]
        if role == Qt.UserRole:  # stable sort keys
            return [
                addon.enabled,
                addon.display_title.lower(),
                addon.creator.lower(),
                addon.type_label.lower(),
                addon.version.lower(),
                addon.size_bytes if addon.size_bytes is not None else -1,
            ][col]
        if role == Qt.ForegroundRole:
            if col == 0:
                return QColor(GREEN) if addon.enabled else QColor("#5a6675")
            if not addon.enabled:
                return QColor(TXT_MUTED)
            if col == 3:  # color-coded add-on type
                return QColor(TYPE_COLORS.get(addon.type_label, TYPE_MISC))
        if role == Qt.TextAlignmentRole and col == 0:
            return int(Qt.AlignCenter)
        return None


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = _Signals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.fn())
        except InstallError as exc:
            self.signals.failed.emit(str(exc))
        except Exception as exc:  # never crash the UI thread
            self.signals.failed.emit(f"Unexpected error: {exc}")


def _addon_html(addon: Addon | None) -> str:
    if addon is None:
        return _WELCOME
    return _theme_addon_html(addon, human_size)


class LiftOffWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config.load()
        self.addons: list[Addon] = []
        self._selected_name: str | None = None
        self.pool = QThreadPool.globalInstance()

        self.setWindowTitle("LiftOff — Flight Simulator mod manager")
        self.resize(1080, 680)
        self._build_ui()
        self._install_shortcuts()
        self._reload_sims_combo()
        self._rescan()

    # --------------------------------------------------------------- build UI
    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_topbar())

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Filter add-ons…   ( / )")
        self.search.textChanged.connect(self._filter)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self._build_table())
        splitter.addWidget(left)

        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        self.details.setHtml(_WELCOME)
        splitter.addWidget(self.details)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([640, 380])

        body_layout.addWidget(splitter, 1)  # the table/details fill the window
        body_layout.addWidget(self._build_actions())
        root.addWidget(body)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")
        self.table.setFocus()

    def _build_topbar(self) -> QFrame:
        top = QFrame()
        top.setObjectName("topbar")
        top.setFixedHeight(54)
        layout = QHBoxLayout(top)
        layout.setContentsMargins(16, 0, 16, 0)
        brand = QLabel("🚀 LiftOff")
        brand.setObjectName("brand")
        self.sim_combo = QComboBox()
        self.sim_combo.setMinimumWidth(160)
        self.sim_combo.currentIndexChanged.connect(self._sim_changed)
        sims_btn = QPushButton("Sims…")
        sims_btn.clicked.connect(self._sims)
        self.path_label = QLabel("")
        self.path_label.setObjectName("path")
        self.counts_label = QLabel("")
        self.counts_label.setObjectName("counts")

        layout.addWidget(brand)
        layout.addSpacing(18)
        layout.addWidget(QLabel("Sim:"))
        layout.addWidget(self.sim_combo)
        layout.addWidget(sims_btn)
        layout.addSpacing(16)
        layout.addWidget(self.path_label, 1)
        layout.addWidget(self.counts_label)
        return top

    def _build_table(self) -> QTableView:
        self.model = AddonTableModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setSortRole(Qt.UserRole)
        self.proxy.setFilterKeyColumn(-1)
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(30)
        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 30)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for col in (2, 3, 4, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        self.table.selectionModel().currentRowChanged.connect(self._selection_changed)
        return self.table

    def _build_actions(self) -> QWidget:
        bar = QWidget()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(0, 10, 0, 0)

        install_btn = QPushButton("Install…")
        install_btn.setObjectName("primary")
        install_btn.clicked.connect(self._install)
        downloads_btn = QPushButton("Downloads")
        downloads_btn.clicked.connect(self._downloads)
        fsto_btn = QPushButton("flightsim.to")
        fsto_btn.clicked.connect(self._flightsimto)

        self.toggle_btn = QPushButton("Enable / Disable")
        self.toggle_btn.clicked.connect(self._toggle)
        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("danger")
        remove_btn.clicked.connect(self._remove)
        rescan_btn = QPushButton("Rescan")
        rescan_btn.clicked.connect(self._rescan)
        settings_btn = QPushButton("Settings")
        settings_btn.clicked.connect(self._settings)

        for widget in (install_btn, downloads_btn, fsto_btn):
            layout.addWidget(widget)
        layout.addStretch(1)
        for widget in (self.toggle_btn, remove_btn, rescan_btn, settings_btn):
            layout.addWidget(widget)
        return bar

    def _install_shortcuts(self) -> None:
        for seq, fn in [
            ("/", self._focus_search), ("e", self._toggle), ("x", self._remove),
            ("Delete", self._remove), ("i", self._install), ("d", self._downloads),
            ("f", self._flightsimto), ("s", self._sims), ("r", self._rescan),
            ("F5", self._rescan), ("Ctrl+,", self._settings),
        ]:
            QShortcut(QKeySequence(seq), self).activated.connect(fn)

    # ----------------------------------------------------------------- workers
    def _run_task(self, fn, on_done) -> None:
        task = _Task(fn)
        task.signals.done.connect(on_done)
        task.signals.failed.connect(self._task_failed)
        self.pool.start(task)

    def _task_failed(self, message: str) -> None:
        self.statusBar().showMessage(message, 8000)
        QMessageBox.warning(self, "LiftOff", message)

    # ------------------------------------------------------------------- scan
    def _rescan(self) -> None:
        sim = self.cfg.active_sim()
        self.statusBar().showMessage("Scanning…")
        if sim is None:
            self._apply_scan([])
            return
        community = sim.community_path
        disabled = self.cfg.disabled_store(sim.id)
        self._run_task(lambda: scan(community, disabled, True), self._apply_scan)

    def reload_now(self) -> None:
        """Synchronous scan + apply (used by tests and headless rendering)."""
        sim = self.cfg.active_sim()
        addons = scan(sim.community_path, self.cfg.disabled_store(sim.id), True) if sim else []
        self._apply_scan(addons)

    def _apply_scan(self, addons: list[Addon]) -> None:
        self.addons = addons
        self.model.set_rows(addons)
        self.proxy.sort(1, Qt.AscendingOrder)
        self._update_topbar()
        self._restore_selection()
        self.statusBar().showMessage(f"{len(addons)} add-on(s)", 4000)

    def _restore_selection(self) -> None:
        if self.proxy.rowCount() == 0:
            self.details.setHtml(_WELCOME)
            return
        target = 0
        if self._selected_name:
            for row in range(self.proxy.rowCount()):
                src = self.proxy.mapToSource(self.proxy.index(row, 0))
                addon = self.model.addon_at(src.row())
                if addon and addon.name == self._selected_name:
                    target = row
                    break
        self.table.selectRow(target)

    # -------------------------------------------------------------- selection
    def _selection_changed(self, *_args) -> None:
        addon = self._current_addon()
        if addon is not None:
            self._selected_name = addon.name
        self.details.setHtml(_addon_html(addon))

    def _current_addon(self) -> Addon | None:
        index = self.table.currentIndex()
        if not index.isValid():
            return None
        return self.model.addon_at(self.proxy.mapToSource(index).row())

    # ----------------------------------------------------------------- topbar
    def _reload_sims_combo(self) -> None:
        self.sim_combo.blockSignals(True)
        self.sim_combo.clear()
        for sim in self.cfg.sims:
            self.sim_combo.addItem(sim.name, sim.id)
        if self.cfg.sims:
            self.sim_combo.setCurrentIndex(max(0, self.sim_combo.findData(self.cfg.active)))
        self.sim_combo.blockSignals(False)

    def _sim_changed(self, _index: int) -> None:
        sim_id = self.sim_combo.currentData()
        if sim_id and sim_id != self.cfg.active:
            self.cfg.active = sim_id
            self.cfg.save()
            self._rescan()

    def _update_topbar(self) -> None:
        sim = self.cfg.active_sim()
        if sim is None:
            self.path_label.setText("No simulator — click Sims… to auto-detect or add a folder")
            self.counts_label.setText("")
            return
        self.path_label.setText(sim.community)
        enabled = sum(a.enabled for a in self.addons)
        self.counts_label.setText(f"{enabled} on · {len(self.addons)} total")

    # ----------------------------------------------------------------- actions
    def _require_sim(self) -> bool:
        if self.cfg.active_sim() is None:
            QMessageBox.information(self, "No simulator",
                                    "Add a simulator first via Sims….")
            return False
        return True

    def _focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def _filter(self, text: str) -> None:
        self.proxy.setFilterFixedString(text.strip())

    def _toggle(self) -> None:
        addon = self._current_addon()
        if addon is None or not self._require_sim():
            return
        sim = self.cfg.active_sim()
        self._run_task(
            lambda: set_enabled(addon.path, not addon.enabled, sim.community_path,
                                self.cfg.disabled_store(sim.id)),
            lambda _r: self._rescan(),
        )

    def _remove(self) -> None:
        addon = self._current_addon()
        if addon is None or not self._require_sim():
            return
        if self.cfg.confirm_remove:
            answer = QMessageBox.question(
                self, "Remove add-on",
                f"Remove '{addon.display_title}'?\nIt moves to trash and can be restored.",
            )
            if answer != QMessageBox.Yes:
                return
        sim = self.cfg.active_sim()
        self._run_task(
            lambda: remove(addon.path, self.cfg.trash_store(sim.id)),
            lambda _r: self._rescan(),
        )

    def _install(self) -> None:
        if not self._require_sim():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose add-on archive", str(self.cfg.downloads_path()),
            "Add-on archives (*.zip *.rar *.7z);;All files (*)",
        )
        if path:
            self._install_path(path)

    def _install_path(self, path: str) -> None:
        sim = self.cfg.active_sim()
        self.statusBar().showMessage(f"Installing {Path(path).name}…")
        self._run_task(
            lambda: install_archive(Path(path), sim.community_path, self.cfg.trash_store(sim.id)),
            self._install_done,
        )

    def _install_done(self, result) -> None:
        self.statusBar().showMessage("Installed " + ", ".join(result.installed), 6000)
        self._rescan()

    def _downloads(self) -> None:
        if not self._require_sim():
            return
        dlg = DownloadsDialog(self.cfg.downloads_path(), self)
        if dlg.exec() and dlg.result_value:
            self._install_path(dlg.result_value)

    def _flightsimto(self) -> None:
        FlightSimToDialog(self.cfg, self).exec()

    def _sims(self) -> None:
        dlg = SimsDialog(self.cfg, self)
        dlg.exec()
        if dlg.changed:
            self._reload_sims_combo()
            self._rescan()

    def _settings(self) -> None:
        SettingsDialog(self.cfg, self).exec()


def run_gui() -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName("LiftOff")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    window = LiftOffWindow()
    window.show()
    return app.exec()
