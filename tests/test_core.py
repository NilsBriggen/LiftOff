"""Tests for the LiftOff engine: install, library, sims detection and config."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from liftoff import install, library, sims
from liftoff.config import Config, SimProfile


# --------------------------------------------------------------------- helpers
def make_package(parent: Path, name: str, title: str = "", ctype: str = "LIVERY") -> Path:
    pkg = parent / name
    pkg.mkdir(parents=True)
    (pkg / "manifest.json").write_text(
        json.dumps(
            {
                "title": title or name,
                "creator": "Tester",
                "content_type": ctype,
                "package_version": "1.0.0",
            }
        )
    )
    (pkg / "layout.json").write_text("{}")
    (pkg / "data.bin").write_bytes(b"x" * 1024)
    return pkg


def zip_dir(src: Path, archive: Path) -> Path:
    with zipfile.ZipFile(archive, "w") as zf:
        for path in src.rglob("*"):
            zf.write(path, path.relative_to(src.parent))
    return archive


# ---------------------------------------------------------------------- library
def test_scan_reads_manifest(tmp_path):
    community = tmp_path / "Community"
    make_package(community, "cool-livery", title="Cool Livery", ctype="LIVERY")
    addons = library.scan(community, with_size=True)
    assert len(addons) == 1
    a = addons[0]
    assert a.display_title == "Cool Livery"
    assert a.type_label == "Livery"
    assert a.creator == "Tester"
    assert a.enabled and a.size_bytes and a.size_bytes >= 1024


def test_scan_includes_disabled(tmp_path):
    community = tmp_path / "Community"
    disabled = tmp_path / "disabled"
    make_package(community, "enabled-one")
    make_package(disabled, "disabled-one")
    addons = library.scan(community, disabled)
    states = {a.name: a.enabled for a in addons}
    assert states == {"enabled-one": True, "disabled-one": False}


def test_human_size():
    assert library.human_size(None) == "…"
    assert library.human_size(512) == "512 B"
    assert library.human_size(2048) == "2.0 KB"


# ---------------------------------------------------------------------- install
def test_find_packages_nested_and_multi(tmp_path):
    root = tmp_path / "extract"
    make_package(root / "wrapper", "pkg-a")
    make_package(root / "wrapper", "pkg-b")
    found = install.find_packages(root)
    names = sorted(p.name for p in found)
    assert names == ["pkg-a", "pkg-b"]


def test_install_archive_with_wrapper(tmp_path):
    src = tmp_path / "src"
    make_package(src, "livery-pkg", title="Livery")
    archive = zip_dir(src / "livery-pkg", tmp_path / "livery.zip")
    community = tmp_path / "Community"
    result = install.install_archive(archive, community)
    assert result.installed == ["livery-pkg"]
    assert (community / "livery-pkg" / "manifest.json").exists()


def test_install_archive_manifest_at_root(tmp_path):
    # Archive whose root *is* the package (manifest.json at top level).
    pkgroot = tmp_path / "build"
    pkgroot.mkdir()
    (pkgroot / "manifest.json").write_text(json.dumps({"title": "Root Pkg"}))
    (pkgroot / "layout.json").write_text("{}")
    archive = tmp_path / "rootpkg.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(pkgroot / "manifest.json", "manifest.json")
        zf.write(pkgroot / "layout.json", "layout.json")
    community = tmp_path / "Community"
    result = install.install_archive(archive, community)
    assert result.installed == ["rootpkg"]
    assert (community / "rootpkg" / "manifest.json").exists()


def test_install_rejects_non_package(tmp_path):
    archive = tmp_path / "junk.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "nothing useful here")
    with pytest.raises(install.InstallError):
        install.install_archive(archive, tmp_path / "Community")


def test_install_overwrite_backs_up_to_trash(tmp_path):
    community = tmp_path / "Community"
    trash = tmp_path / "trash"
    make_package(community, "dup", title="Old")
    src = tmp_path / "src"
    make_package(src, "dup", title="New")
    archive = zip_dir(src / "dup", tmp_path / "dup.zip")
    result = install.install_archive(archive, community, trash)
    assert result.installed == ["dup"]
    new_manifest = json.loads((community / "dup" / "manifest.json").read_text())
    assert new_manifest["title"] == "New"
    assert any(trash.iterdir())  # old copy preserved


def test_enable_disable_roundtrip(tmp_path):
    community = tmp_path / "Community"
    disabled = tmp_path / "disabled"
    pkg = make_package(community, "tog")
    moved = install.set_enabled(pkg, False, community, disabled)
    assert moved.parent == disabled and not pkg.exists()
    back = install.set_enabled(moved, True, community, disabled)
    assert back.parent == community


def test_remove_moves_to_trash(tmp_path):
    community = tmp_path / "Community"
    trash = tmp_path / "trash"
    pkg = make_package(community, "gone")
    install.remove(pkg, trash)
    assert not pkg.exists()
    assert any(trash.iterdir())


# --------------------------------------------------------------- sims detection
def test_detect_msfs_via_usercfg(tmp_path, monkeypatch):
    # Fake a Steam Proton prefix for MSFS 2020 with a relocated Community folder.
    steam = tmp_path / ".steam" / "steam"
    pfx = steam / "steamapps" / "compatdata" / "1250410" / "pfx"
    roaming = pfx / "drive_c" / "users" / "steamuser" / "AppData" / "Roaming"
    msfs = roaming / "Microsoft Flight Simulator"
    msfs.mkdir(parents=True)
    real_packages = pfx / "drive_c" / "MSFS-Packages"
    (real_packages / "Community").mkdir(parents=True)
    (msfs / "UserCfg.opt").write_text('InstalledPackagesPath "C:\\\\MSFS-Packages"\n')

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    found = sims.detect()
    assert len(found) == 1
    assert found[0].kind == "msfs2020"
    assert found[0].community_path == real_packages / "Community"
    assert found[0].community_path.is_dir()


def test_detect_msfs_default_fallback(tmp_path, monkeypatch):
    # No InstalledPackagesPath override -> default Packages/Community next to cfg.
    steam = tmp_path / ".local" / "share" / "Steam"
    pfx = steam / "steamapps" / "compatdata" / "2537590" / "pfx"
    roaming = pfx / "drive_c" / "users" / "steamuser" / "AppData" / "Roaming"
    msfs = roaming / "Microsoft Flight Simulator 2024"
    (msfs / "Packages" / "Community").mkdir(parents=True)
    (msfs / "UserCfg.opt").write_text("SomeOtherSetting 1\n")

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    found = sims.detect()
    assert len(found) == 1
    assert found[0].kind == "msfs2024"
    assert found[0].community_path == msfs / "Packages" / "Community"


# ------------------------------------------------------------------------ config
def test_config_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    cfg = Config()
    cfg.add_sim(SimProfile(id="s1", name="MSFS", community=str(tmp_path / "Community")))
    cfg.api_token = "secret"
    cfg.save()
    again = Config.load()
    assert again.active == "s1"
    assert again.api_token == "secret"
    assert again.active_sim().name == "MSFS"


def test_merge_detected_dedupes(tmp_path):
    cfg = Config()
    cfg.add_sim(SimProfile(id="a", name="A", community="/x/Community"))
    added = cfg.merge_detected(
        [
            SimProfile(id="b", name="B", community="/x/Community"),  # dup path
            SimProfile(id="c", name="C", community="/y/Community"),  # new
        ]
    )
    assert added == 1
    assert len(cfg.sims) == 2
