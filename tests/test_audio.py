"""ffmpeg discovery: bundled inside a frozen build, otherwise from PATH."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from daisy2telmi import audio
from daisy2telmi.extractor import AudioSegment


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


def test_a_concat_list_path_escapes_quotes() -> None:
    assert audio._quote(Path("/tmp/it's here.mp3")) == "'/tmp/it'\\''s here.mp3'"


requires_ffmpeg = pytest.mark.skipif(audio.ffmpeg_executable() is None, reason="ffmpeg not installed")


def _clip(tmp_path: Path, name: str, seconds: float) -> Path:
    dest = tmp_path / name
    subprocess.run(
        [
            audio.ffmpeg_executable(),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ar",
            "44100",
            "-ac",
            "1",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(dest),
        ],
        check=True,
    )
    return dest


@requires_ffmpeg
def test_probe_reads_the_stream_header(tmp_path: Path) -> None:
    assert audio.probe(_clip(tmp_path, "a.mp3", 1.0)) == ("mp3", 44100, "mono")


@requires_ffmpeg
def test_whole_clips_are_joined_without_re_encoding(tmp_path: Path, monkeypatch) -> None:
    clips = [_clip(tmp_path, "a.mp3", 1.0), _clip(tmp_path, "b.mp3", 1.5)]
    joined: list[list[Path]] = []
    monkeypatch.setattr(audio, "_copy_concat", lambda paths, dest: joined.append(paths))
    audio.render([AudioSegment(clip) for clip in clips], tmp_path / "out.mp3")
    assert joined == [clips]


@requires_ffmpeg
def test_a_mark_that_stops_at_the_end_of_a_clip_is_not_a_trim(tmp_path: Path, monkeypatch) -> None:
    clip = _clip(tmp_path, "a.mp3", 2.0)
    whole = audio.duration(clip)
    joined: list[list[Path]] = []
    monkeypatch.setattr(audio, "_copy_concat", lambda paths, dest: joined.append(paths))
    audio.render([AudioSegment(clip, begin=0.0, end=whole - 0.1)], tmp_path / "out.mp3")
    assert joined == [[clip]]
    audio.render([AudioSegment(clip, begin=0.0, end=whole - 1.0)], tmp_path / "cut.mp3")
    assert joined == [[clip]]


@requires_ffmpeg
def test_a_trim_inside_a_file_still_goes_through_the_encoder(tmp_path: Path, monkeypatch) -> None:
    clips = [_clip(tmp_path, "a.mp3", 2.0)]
    monkeypatch.setattr(audio, "_copy_concat", lambda paths, dest: pytest.fail("trimmed clip was copied"))
    audio.render([AudioSegment(clips[0], begin=0.5)], tmp_path / "out.mp3")
    assert (tmp_path / "out.mp3").stat().st_size > 0


@requires_ffmpeg
def test_the_joined_file_is_the_two_clips_end_to_end(tmp_path: Path) -> None:
    clips = [_clip(tmp_path, "a.mp3", 1.0), _clip(tmp_path, "b.mp3", 1.5)]
    out = tmp_path / "out.mp3"
    audio.render([AudioSegment(clip) for clip in clips], out)
    assert audio.duration(out) == pytest.approx(2.5, abs=0.2)
    assert not list(tmp_path.glob("*.concat"))
