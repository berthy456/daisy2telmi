"""The AppImage layout, checked without appimagetool or squashfs."""

from __future__ import annotations

import importlib.util
import os
import stat
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "make_appimage", Path(__file__).resolve().parents[1] / "tools" / "make_appimage.py"
)
make_appimage = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_appimage)
build_appdir = make_appimage.build_appdir


def make_binary(tmp_path: Path) -> Path:
    binary = tmp_path / "daisy2telmi"
    binary.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary


def test_the_appdir_has_the_layout_appimagetool_expects(tmp_path: Path) -> None:
    binary = make_binary(tmp_path)
    appdir = build_appdir(binary, tmp_path / "AppDir")

    assert (appdir / "AppRun").is_file()
    assert (appdir / "usr" / "bin" / "daisy2telmi").is_file()
    assert (appdir / "daisy2telmi.desktop").is_file()


def test_apprun_and_the_binary_are_executable(tmp_path: Path) -> None:
    binary = make_binary(tmp_path)
    appdir = build_appdir(binary, tmp_path / "AppDir")

    for name in ("AppRun", "usr/bin/daisy2telmi"):
        mode = (appdir / name).stat().st_mode
        assert mode & stat.S_IXUSR, f"{name} is not executable"
    if os.name == "posix":
        assert "usr/bin/daisy2telmi" in (appdir / "AppRun").read_text(encoding="utf-8")


def test_the_desktop_file_points_at_the_binary(tmp_path: Path) -> None:
    appdir = build_appdir(make_binary(tmp_path), tmp_path / "AppDir")
    assert "Exec=daisy2telmi" in (appdir / "daisy2telmi.desktop").read_text(encoding="utf-8")


def test_rebuilding_replaces_the_previous_appdir(tmp_path: Path) -> None:
    build_appdir(make_binary(tmp_path), tmp_path / "AppDir")
    (tmp_path / "AppDir" / "stale.txt").write_text("old", encoding="utf-8")
    appdir = build_appdir(make_binary(tmp_path), tmp_path / "AppDir")
    assert not (appdir / "stale.txt").exists()
