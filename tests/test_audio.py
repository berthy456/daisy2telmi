"""ffmpeg discovery: bundled inside a frozen build, otherwise from PATH."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from daisy2telmi import audio


@pytest.fixture()
def fake_bundle(tmp_path: Path, monkeypatch) -> Path:
    exe_dir = tmp_path / "app"
    exe_dir.mkdir()
    name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    (exe_dir / name).write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "daisy2telmi"), raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    return exe_dir


def test_no_bundle_lookup_outside_a_frozen_build(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert audio.bundled_ffmpeg() is None


def test_bundled_ffmpeg_is_found_next_to_the_executable(fake_bundle: Path) -> None:
    assert audio.bundled_ffmpeg() == fake_bundle / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")


def test_bundled_ffmpeg_wins_over_path(fake_bundle: Path, monkeypatch) -> None:
    found = audio.ffmpeg_executable()
    assert found is not None and Path(found).parent == fake_bundle


def test_falls_back_to_path_when_nothing_is_bundled(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "daisy2telmi"), raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)
    monkeypatch.setattr(audio.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert audio.ffmpeg_executable() == "/usr/bin/ffmpeg"


def test_render_rejects_an_empty_segment_list(tmp_path: Path) -> None:
    with pytest.raises(audio.AudioError):
        audio.render([], tmp_path / "out.mp3")
