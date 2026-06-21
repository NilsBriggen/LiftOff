"""Command-line entry point.

Running ``liftoff`` with no arguments launches the graphical UI (``--tui`` for
the terminal UI instead). A few headless subcommands make the same engine
scriptable and easy to test.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .config import Config
from .install import InstallError, install_archive
from .library import human_size, scan
from .sims import detect


def _resolve_community(cfg: Config, override: str | None) -> Path | None:
    if override:
        return Path(override).expanduser()
    sim = cfg.active_sim()
    return sim.community_path if sim else None


def cmd_detect(_args: argparse.Namespace) -> int:
    found = detect()
    if not found:
        print("No Microsoft Flight Simulator install detected.")
        print("Add one in the app (press 's') or pass --community to other commands.")
        return 1
    for sim in found:
        marker = "✓" if sim.community_path.is_dir() else "·"
        print(f"{marker} {sim.name}  [{sim.kind}]\n    {sim.community}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    cfg = Config.load()
    community = _resolve_community(cfg, args.community)
    if community is None:
        print("No active sim. Run 'liftoff detect' or pass --community PATH.", file=sys.stderr)
        return 2
    sim = cfg.active_sim()
    disabled = cfg.disabled_store(sim.id) if sim else None
    addons = scan(community, disabled, with_size=args.size)
    if not addons:
        print(f"No add-ons found in {community}")
        return 0
    for a in addons:
        state = "on " if a.enabled else "off"
        size = f"  {human_size(a.size_bytes)}" if args.size else ""
        print(f"[{state}] {a.display_title}  ({a.type_label}){size}")
    print(f"\n{len(addons)} add-on(s) · {sum(a.enabled for a in addons)} enabled")
    return 0


def cmd_install(args: argparse.Namespace) -> int:
    cfg = Config.load()
    community = _resolve_community(cfg, args.community)
    if community is None:
        print("No active sim. Run 'liftoff detect' or pass --community PATH.", file=sys.stderr)
        return 2
    sim = cfg.active_sim()
    trash = cfg.trash_store(sim.id) if sim else None
    rc = 0
    for archive in args.archives:
        try:
            result = install_archive(Path(archive), community, trash)
            for name in result.installed:
                print(f"installed: {name}")
            for warning in result.warnings:
                print(f"note: {warning}")
        except InstallError as exc:
            print(f"error: {exc}", file=sys.stderr)
            rc = 1
    return rc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="liftoff",
        description="LiftOff — a fast Linux mod manager for Microsoft Flight Simulator.",
    )
    parser.add_argument("--version", action="version", version=f"LiftOff {__version__}")
    ui = parser.add_mutually_exclusive_group()
    ui.add_argument("--gui", action="store_true", help="force the graphical UI (default)")
    ui.add_argument("--tui", action="store_true", help="force the terminal UI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("detect", help="detect MSFS installs and Community folders")

    p_list = sub.add_parser("list", help="list installed add-ons")
    p_list.add_argument("--community", help="Community folder to use")
    p_list.add_argument("--size", action="store_true", help="compute on-disk sizes")

    p_install = sub.add_parser("install", help="install add-on archive(s)")
    p_install.add_argument("archives", nargs="+", help="zip/rar/7z files to install")
    p_install.add_argument("--community", help="Community folder to install into")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "detect":
        return cmd_detect(args)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "install":
        return cmd_install(args)
    return _launch_ui(args)


def _has_display() -> bool:
    return bool(
        os.environ.get("DISPLAY")
        or os.environ.get("WAYLAND_DISPLAY")
        or os.environ.get("QT_QPA_PLATFORM")
    )


def _launch_ui(args: argparse.Namespace) -> int:
    """Launch the GUI on a desktop, the TUI on a headless box or on request."""
    def tui() -> int:
        from .app import run

        return run()

    if args.tui or (not args.gui and not _has_display()):
        return tui()
    try:
        from .gui import run_gui
    except Exception as exc:  # PySide6 missing or no Qt platform libs
        print(f"GUI unavailable ({exc}); falling back to the terminal UI.", file=sys.stderr)
        return tui()
    return run_gui()


if __name__ == "__main__":
    raise SystemExit(main())
