"""Modal screens: install picker, downloads, flightsim.to, sims, settings, help."""

from __future__ import annotations

from pathlib import Path

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DirectoryTree,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Static,
)

from . import fsto
from .config import Config
from .library import human_size
from .sims import detect, make_custom


class ConfirmModal(ModalScreen[bool]):
    """Yes/No confirmation."""

    BINDINGS = [("escape", "dismiss(False)", "Cancel")]

    def __init__(self, question: str, confirm_label: str = "Confirm"):
        super().__init__()
        self.question = question
        self.confirm_label = confirm_label

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Please confirm", classes="dialog-title")
            yield Static(self.question)
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(self.confirm_label, id="ok", variant="error")

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)


class InstallModal(ModalScreen[str | None]):
    """Pick an add-on archive to install, by browsing or pasting a path."""

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, start_dir: Path):
        super().__init__()
        self.start_dir = start_dir if start_dir.is_dir() else Path.home()

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Install add-on from archive", classes="dialog-title")
            yield Input(placeholder="Path to .zip / .rar / .7z …", id="install-path")
            yield DirectoryTree(str(self.start_dir), id="picker-tree")
            yield Static("Pick a file in the tree or paste a path, then Install.", classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Install", id="ok", variant="success")

    @on(DirectoryTree.FileSelected, "#picker-tree")
    def _file(self, event: DirectoryTree.FileSelected) -> None:
        self.query_one("#install-path", Input).value = str(event.path)

    @on(Input.Submitted, "#install-path")
    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        value = self.query_one("#install-path", Input).value.strip()
        if value:
            self.dismiss(value)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)


class DownloadsModal(ModalScreen[str | None]):
    """List recent add-on archives in the Downloads folder for one-key install."""

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, downloads_dir: Path):
        super().__init__()
        self.downloads_dir = downloads_dir
        self.files: list[Path] = []

    def compose(self) -> ComposeResult:
        self.files = fsto.find_downloads(self.downloads_dir)
        with Vertical(classes="dialog"):
            yield Static("Install from Downloads", classes="dialog-title")
            yield Static(f"Watching: {self.downloads_dir}", classes="hint")
            if self.files:
                items = []
                for path in self.files:
                    size = human_size(path.stat().st_size)
                    items.append(
                        ListItem(
                            Static(f"[b]{path.name}[/b]\n[dim]{size}[/dim]"),
                        )
                    )
                yield ListView(*items, id="dl-list")
                yield Static("Enter to install the selected archive.", classes="hint")
            else:
                yield Static(
                    "No .zip / .rar / .7z archives found.\n"
                    "Download an add-on from flightsim.to, then reopen this.",
                    id="dl-list",
                )
            with Horizontal(classes="buttons"):
                yield Button("Close", id="cancel")
                if self.files:
                    yield Button("Install", id="ok", variant="success")

    @on(ListView.Selected, "#dl-list")
    def _selected(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is not None and 0 <= index < len(self.files):
            self.dismiss(str(self.files[index]))

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        try:
            index = self.query_one("#dl-list", ListView).index
        except Exception:
            index = None
        if index is not None and 0 <= index < len(self.files):
            self.dismiss(str(self.files[index]))

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)


class FlightSimToModal(ModalScreen[None]):
    """Discover add-ons on flightsim.to (browser hand-off + optional API search)."""

    BINDINGS = [("escape", "dismiss", "Close")]

    CATEGORIES = [
        ("Liveries", "liveries"),
        ("Aircraft", "aircraft"),
        ("Airports", "scenery"),
        ("Popular", "featured/downloads"),
    ]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.results: list[fsto.RemoteFile] = []

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Browse flightsim.to", classes="dialog-title")
            yield Input(placeholder="Search flightsim.to and press Enter…", id="fsto-search")
            with Horizontal(classes="buttons"):
                for label, _slug in self.CATEGORIES:
                    yield Button(label, id=f"cat-{_slug.replace('/', '-')}")
            if self.client.enabled:
                yield ListView(id="fsto-list")
                yield Static(
                    "API token set: results open on flightsim.to. "
                    "After downloading, press D to install.",
                    classes="hint",
                )
            else:
                yield Static(
                    "Tip: searches open in your browser. Download an add-on, then "
                    "press D in LiftOff to install it from your Downloads folder.\n"
                    "Add a flightsim.to API token in Settings for in-app search.",
                    classes="hint",
                )
            with Horizontal(classes="buttons"):
                yield Button("Close", id="cancel")

    @property
    def client(self) -> fsto.FlightSimToClient:
        return fsto.FlightSimToClient(self.cfg.api_token)

    @on(Input.Submitted, "#fsto-search")
    def _search(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        if not query:
            return
        if self.client.enabled:
            self._api_search(query)
        else:
            fsto.open_in_browser(fsto.search_url(query))
            self.app.notify("Opened flightsim.to search in your browser.")

    def _api_search(self, query: str) -> None:
        try:
            self.results = self.client.search(query)
        except fsto.ApiError as exc:
            self.app.notify(str(exc), severity="error")
            return
        listview = self.query_one("#fsto-list", ListView)
        listview.clear()
        if not self.results:
            self.app.notify("No results.")
            return
        for item in self.results:
            sub = item.author or item.category or ""
            listview.append(ListItem(Static(f"[b]{item.title}[/b]\n[dim]{sub}[/dim]")))

    @on(ListView.Selected, "#fsto-list")
    def _open_result(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is not None and 0 <= index < len(self.results):
            fsto.open_in_browser(self.results[index].url or fsto.BASE_URL)
            self.app.notify("Opened on flightsim.to.")

    @on(Button.Pressed)
    def _button(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "cancel":
            self.dismiss(None)
        elif bid.startswith("cat-"):
            slug = bid[4:].replace("-", "/")
            fsto.open_in_browser(fsto.search_url(category=slug))
            self.app.notify(f"Opened {event.button.label} on flightsim.to.")


class AddFolderModal(ModalScreen[tuple[str, str] | None]):
    """Add a custom Community-style folder as a sim profile."""

    BINDINGS = [("escape", "dismiss", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Add a Community folder", classes="dialog-title")
            yield Input(placeholder="Name (e.g. MSFS 2024)", id="name")
            yield Input(placeholder="Path to the Community folder", id="path")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Add", id="ok", variant="success")

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        name = self.query_one("#name", Input).value.strip()
        path = self.query_one("#path", Input).value.strip()
        if path:
            self.dismiss((name or "Custom", path))

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)


class SimSelectModal(ModalScreen[bool]):
    """Switch the active sim, auto-detect installs, or add a folder."""

    BINDINGS = [("escape", "dismiss(False)", "Close")]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg
        self.changed = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Simulators", classes="dialog-title")
            yield ListView(id="sim-list")
            yield Static("Enter to activate · auto-detect finds Steam/Proton installs.",
                         classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Add folder…", id="add")
                yield Button("Auto-detect", id="detect")

    def on_mount(self) -> None:
        self._refresh()

    def _refresh(self) -> None:
        listview = self.query_one("#sim-list", ListView)
        listview.clear()
        if not self.cfg.sims:
            listview.append(
                ListItem(Static("[dim]No simulators yet — detect or add a folder.[/dim]"))
            )
            return
        for sim in self.cfg.sims:
            mark = "●" if sim.id == self.cfg.active else "○"
            exists = "" if sim.community_path.is_dir() else "  [red](missing)[/red]"
            listview.append(
                ListItem(Static(f"{mark} [b]{sim.name}[/b]{exists}\n[dim]{sim.community}[/dim]"))
            )

    @on(ListView.Selected, "#sim-list")
    def _activate(self, event: ListView.Selected) -> None:
        index = event.list_view.index
        if index is not None and 0 <= index < len(self.cfg.sims):
            self.cfg.active = self.cfg.sims[index].id
            self.cfg.save()
            self.dismiss(True)

    @on(Button.Pressed, "#detect")
    def _detect(self) -> None:
        added = self.cfg.merge_detected(detect())
        self.cfg.save()
        self.changed = True
        self._refresh()
        self.app.notify(f"Detected {added} new install(s)." if added else "No new installs found.")

    @on(Button.Pressed, "#add")
    def _add(self) -> None:
        self.app.push_screen(AddFolderModal(), self._added)

    def _added(self, result: tuple[str, str] | None) -> None:
        if result:
            name, path = result
            self.cfg.add_sim(make_custom(name, path))
            self.cfg.save()
            self.changed = True
            self._refresh()

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(self.changed)


class SettingsModal(ModalScreen[bool]):
    """Edit Downloads folder, API token and removal behaviour."""

    BINDINGS = [("escape", "dismiss(False)", "Cancel")]

    def __init__(self, cfg: Config):
        super().__init__()
        self.cfg = cfg

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Settings", classes="dialog-title")
            yield Label("Downloads folder")
            yield Input(value=str(self.cfg.downloads_path()), id="downloads")
            yield Label("flightsim.to API token (optional — enables in-app search)")
            yield Input(value=self.cfg.api_token, password=True, id="token")
            yield Checkbox("Confirm before removing add-ons", value=self.cfg.confirm_remove,
                           id="confirm")
            yield Static("Removed add-ons go to a recoverable trash store, never deleted outright.",
                         classes="hint")
            with Horizontal(classes="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Save", id="ok", variant="success")

    @on(Button.Pressed, "#ok")
    def _ok(self) -> None:
        self.cfg.downloads_dir = self.query_one("#downloads", Input).value.strip()
        self.cfg.api_token = self.query_one("#token", Input).value.strip()
        self.cfg.confirm_remove = self.query_one("#confirm", Checkbox).value
        self.cfg.save()
        self.dismiss(True)

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)


HELP_TEXT = """\
# LiftOff — keys

| Key | Action |
| --- | --- |
| `/` | Filter add-ons |
| `e` | Enable / disable selected |
| `x` | Remove selected (to trash) |
| `i` | Install from an archive file |
| `d` | Install from Downloads |
| `f` | Browse flightsim.to |
| `s` | Switch / detect simulators |
| `r` | Rescan library |
| `,` | Settings |
| `?` | This help |
| `q` | Quit |

LiftOff manages your Microsoft Flight Simulator **Community** folder.
Enable/disable moves packages to a managed store; nothing is deleted
without going through a recoverable trash.
"""


class HelpModal(ModalScreen[None]):
    BINDINGS = [("escape,q,question_mark", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="dialog"):
            yield Markdown(HELP_TEXT)
            with Horizontal(classes="buttons"):
                yield Button("Close", id="cancel")

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)
