"""The LiftOff Textual application: library view, actions and workers."""

from __future__ import annotations

from pathlib import Path

from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Input, Static

from .config import Config
from .install import InstallError, install_archive, remove, set_enabled
from .library import Addon, human_size, scan
from .screens import (
    ConfirmModal,
    DownloadsModal,
    FlightSimToModal,
    HelpModal,
    InstallModal,
    SettingsModal,
    SimSelectModal,
)


def _liftoff_theme():
    """A cohesive sky-blue / runway-amber dark theme."""
    from textual.theme import Theme

    return Theme(
        name="liftoff",
        primary="#4aa3ff",
        secondary="#7bdcff",
        accent="#ff8c42",
        foreground="#dce6f2",
        background="#0b1622",
        surface="#0f1d2e",
        panel="#13263b",
        success="#3ddc84",
        warning="#ffb454",
        error="#ff5c66",
        dark=True,
    )


class LiftOffApp(App):
    CSS_PATH = "styles.tcss"
    TITLE = "LiftOff"
    SUB_TITLE = "Flight Simulator mod manager"

    BINDINGS = [
        Binding("slash", "focus_search", "Filter"),
        Binding("e", "toggle_enable", "On/Off"),
        Binding("x", "remove", "Remove"),
        Binding("i", "install", "Install"),
        Binding("d", "downloads", "Downloads"),
        Binding("f", "flightsimto", "flightsim.to"),
        Binding("s", "sims", "Sims"),
        Binding("r", "rescan", "Rescan", show=False),
        Binding("comma", "settings", "Settings", show=False),
        Binding("question_mark", "help", "Help"),
        Binding("q", "quit", "Quit"),
        Binding("escape", "unfocus_search", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.cfg = Config.load()
        self.addons: list[Addon] = []
        self.filtered: list[Addon] = []
        self._sel = -1

    # ----------------------------------------------------------------- layout
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="topbar")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Input(placeholder="Filter add-ons…  ( / to focus )", id="search")
                yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="details"):
                yield Static(id="details-body")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.register_theme(_liftoff_theme())
            self.theme = "liftoff"
        except Exception:
            pass
        table = self.query_one("#table", DataTable)
        table.add_column(" ", width=1, key="state")
        table.add_column("Name", key="name")
        table.add_column("Creator", key="creator")
        table.add_column("Type", width=9, key="type")
        table.add_column("Ver", width=8, key="ver")
        table.add_column("Size", width=9, key="size")
        table.focus()  # keyboard actions work immediately; "/" jumps to the filter
        self._render_details(None)
        self.first_run()

    # ------------------------------------------------------------- top + detail
    def _render_topbar(self, note: str = "") -> None:
        sim = self.cfg.active_sim()
        bar = self.query_one("#topbar", Static)
        if note:
            bar.update(Text.from_markup(f"[b]🚀 LiftOff[/b]   [dim]{note}[/dim]"))
            return
        if not sim:
            bar.update(Text.from_markup(
                "[b]🚀 LiftOff[/b]   [#ff8c42]No simulator[/#ff8c42] — press "
                "[b]s[/b] to auto-detect or add a Community folder"
            ))
            return
        enabled = sum(a.enabled for a in self.addons)
        bar.update(Text.from_markup(
            f"[b]🚀 LiftOff[/b]   [#7bdcff]{sim.name}[/#7bdcff] "
            f"[dim]▸ {sim.community}[/dim]   "
            f"[#3ddc84]{enabled} on[/#3ddc84] · {len(self.addons)} total"
        ))

    def _render_details(self, addon: Addon | None) -> None:
        body = self.query_one("#details-body", Static)
        if addon is None:
            body.update(Text.from_markup(
                "[b #ff8c42]Welcome to LiftOff[/b #ff8c42]\n\n"
                "A fast manager for your Microsoft Flight Simulator\n"
                "[b]Community[/b] folder.\n\n"
                "• [b]i[/b] install an add-on archive\n"
                "• [b]d[/b] install from your Downloads\n"
                "• [b]f[/b] browse flightsim.to\n"
                "• [b]e[/b] enable / disable · [b]x[/b] remove\n"
                "• [b]s[/b] choose your simulator\n\n"
                "[dim]Select an add-on to see its details.[/dim]"
            ))
            return
        state = "[#3ddc84]Enabled[/#3ddc84]" if addon.enabled else "[#ffb454]Disabled[/#ffb454]"
        rows = [
            f"[b #ff8c42]{addon.display_title}[/b #ff8c42]",
            f"[dim]{addon.name}[/dim]",
            "",
            f"[b]Creator[/b]   {addon.creator or '—'}",
            f"[b]Type[/b]      {addon.type_label}",
            f"[b]Version[/b]   {addon.version or '—'}",
            f"[b]Min sim[/b]   {addon.min_game_version or '—'}",
            f"[b]Size[/b]      {human_size(addon.size_bytes)}",
            f"[b]State[/b]     {state}",
            "",
            f"[dim]{addon.path}[/dim]",
        ]
        body.update(Text.from_markup("\n".join(rows)))

    # ----------------------------------------------------------------- scanning
    def first_run(self) -> None:
        self._render_topbar("Loading…")
        self._scan_worker(detect_if_empty=True)

    def action_rescan(self) -> None:
        self.refresh_library()

    def refresh_library(self) -> None:
        self._render_topbar("Scanning…")
        self._scan_worker(detect_if_empty=False)

    @work(thread=True, exclusive=True, group="scan")
    def _scan_worker(self, detect_if_empty: bool) -> None:
        if detect_if_empty and not self.cfg.sims:
            from .sims import detect

            if self.cfg.merge_detected(detect()):
                self.cfg.save()
        sim = self.cfg.active_sim()
        if not sim:
            self.call_from_thread(self._apply_scan, [])
            return
        addons = scan(sim.community_path, self.cfg.disabled_store(sim.id), with_size=True)
        self.call_from_thread(self._apply_scan, addons)

    def _apply_scan(self, addons: list[Addon]) -> None:
        self.addons = addons
        self._apply_filter(self.query_one("#search", Input).value)
        self._render_topbar()

    # ------------------------------------------------------------------ filter
    @on(Input.Changed, "#search")
    def _on_filter(self, event: Input.Changed) -> None:
        self._apply_filter(event.value)

    def _apply_filter(self, query: str) -> None:
        q = query.strip().lower()
        if q:
            self.filtered = [
                a for a in self.addons
                if q in a.display_title.lower()
                or q in a.creator.lower()
                or q in a.type_label.lower()
                or q in a.name.lower()
            ]
        else:
            self.filtered = list(self.addons)
        self._populate_table()

    def _populate_table(self) -> None:
        table = self.query_one("#table", DataTable)
        table.clear()
        for i, a in enumerate(self.filtered):
            dot = Text("●", style="#3ddc84") if a.enabled else Text("○", style="#54627a")
            name = Text(a.display_title, style="" if a.enabled else "#8aa0b8")
            table.add_row(
                dot, name, a.creator or "—", a.type_label, a.version or "—",
                human_size(a.size_bytes), key=str(i),
            )
        if self.filtered:
            self._sel = 0
            table.move_cursor(row=0)
            self._render_details(self.filtered[0])
        else:
            self._sel = -1
            self._render_details(None)

    @on(DataTable.RowHighlighted, "#table")
    def _on_highlight(self, event: DataTable.RowHighlighted) -> None:
        try:
            self._sel = int(event.row_key.value)
        except (TypeError, ValueError):
            self._sel = -1
        self._render_details(self.current_addon())

    def current_addon(self) -> Addon | None:
        if 0 <= self._sel < len(self.filtered):
            return self.filtered[self._sel]
        return None

    # ----------------------------------------------------------------- actions
    def action_focus_search(self) -> None:
        self.query_one("#search", Input).focus()

    def action_unfocus_search(self) -> None:
        self.query_one("#table", DataTable).focus()

    def _require_sim(self) -> bool:
        if self.cfg.active_sim() is None:
            self.notify("No simulator selected. Press 's' to detect or add one.",
                        severity="warning")
            return False
        return True

    def action_toggle_enable(self) -> None:
        addon = self.current_addon()
        if addon is None or not self._require_sim():
            return
        self._toggle_worker(addon.path, not addon.enabled)

    @work(thread=True, exclusive=True, group="mutate")
    def _toggle_worker(self, path: Path, enable: bool) -> None:
        sim = self.cfg.active_sim()
        try:
            set_enabled(path, enable, sim.community_path, self.cfg.disabled_store(sim.id))
        except InstallError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")
            return
        self.call_from_thread(
            self.notify, f"{'Enabled' if enable else 'Disabled'} {path.name}."
        )
        self.call_from_thread(self.refresh_library)

    def action_remove(self) -> None:
        addon = self.current_addon()
        if addon is None or not self._require_sim():
            return
        if self.cfg.confirm_remove:
            question = (
                f"Remove '{addon.display_title}'?\n"
                "It moves to trash and can be restored."
            )
            self.push_screen(
                ConfirmModal(question, confirm_label="Remove"),
                lambda ok: self._remove_worker(addon.path) if ok else None,
            )
        else:
            self._remove_worker(addon.path)

    @work(thread=True, exclusive=True, group="mutate")
    def _remove_worker(self, path: Path) -> None:
        sim = self.cfg.active_sim()
        remove(path, self.cfg.trash_store(sim.id))
        self.call_from_thread(self.notify, f"Removed {path.name} (in trash).")
        self.call_from_thread(self.refresh_library)

    def action_install(self) -> None:
        if not self._require_sim():
            return
        self.push_screen(InstallModal(self.cfg.downloads_path()), self._install_path)

    def action_downloads(self) -> None:
        if not self._require_sim():
            return
        self.push_screen(DownloadsModal(self.cfg.downloads_path()), self._install_path)

    def _install_path(self, path: str | None) -> None:
        if path:
            self._render_topbar("Installing…")
            self._install_worker(path)

    @work(thread=True, exclusive=True, group="install")
    def _install_worker(self, archive: str) -> None:
        sim = self.cfg.active_sim()
        try:
            result = install_archive(Path(archive), sim.community_path,
                                     self.cfg.trash_store(sim.id))
        except InstallError as exc:
            self.call_from_thread(self.notify, str(exc), severity="error")
            self.call_from_thread(self.refresh_library)
            return
        msg = "Installed " + ", ".join(result.installed)
        for warning in result.warnings:
            msg += f"\n{warning}"
        self.call_from_thread(self.notify, msg)
        self.call_from_thread(self.refresh_library)

    def action_flightsimto(self) -> None:
        self.push_screen(FlightSimToModal(self.cfg))

    def action_sims(self) -> None:
        self.push_screen(SimSelectModal(self.cfg), self._sims_done)

    def _sims_done(self, changed: bool | None) -> None:
        if changed:
            self.refresh_library()

    def action_settings(self) -> None:
        self.push_screen(SettingsModal(self.cfg), lambda _ok: None)

    def action_help(self) -> None:
        self.push_screen(HelpModal())


def run() -> int:
    LiftOffApp().run()
    return 0
