"""Speech engines: which ones are usable, and what they produce."""

from __future__ import annotations

import shutil
import subprocess

import pytest

from daisy2telmi import audio, tts
from daisy2telmi.i18n import LANGUAGES

requires_espeak = pytest.mark.skipif(
    shutil.which("espeak-ng") is None and shutil.which("espeak") is None,
    reason="no espeak-ng on this machine",
)
requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_the_engine_list_names_the_four_back_ends() -> None:
    assert [engine.name for engine in tts.engines()] == [tts.ESPEAK, tts.SAY, tts.SAPI, tts.COMMAND]


def test_windows_speech_is_only_offered_on_windows(monkeypatch) -> None:
    # pwsh is installed on Linux runners, where System.Speech does not exist;
    # offering it there makes `auto` pick an engine that cannot speak.
    monkeypatch.setattr(tts.sys, "platform", "linux")
    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/pwsh")
    assert not tts.available(tts.SAPI)


def test_off_short_circuits_before_any_lookup() -> None:
    assert tts.resolve("off", LANGUAGES["en"]) == "off"


def test_an_absent_engine_is_refused_rather_than_tried() -> None:
    absent = next((e.name for e in tts.engines() if not e.found), None)
    if absent is None:
        pytest.skip("this machine has every engine")
    with pytest.raises(tts.TtsError, match="not available"):
        tts.resolve(absent, LANGUAGES["en"])


def test_an_unknown_engine_name_is_refused() -> None:
    with pytest.raises(tts.TtsError, match="unknown speech engine"):
        tts.resolve("coqui", LANGUAGES["en"])


@requires_espeak
@requires_ffmpeg
@pytest.mark.parametrize("code", ["en", "fr", "zh", "ar"])
def test_espeak_produces_audio_in_the_telmi_spec(code: str, tmp_path) -> None:
    dest = tmp_path / "card.mp3"
    tts.synthesize(LANGUAGES[code].chapter.format(n=3), code, dest, engine=tts.ESPEAK)

    out = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "csv=p=0",
            str(dest),
        ],
        capture_output=True,
        text=True,
    )
    assert out.stdout.strip() == f"{audio.SAMPLE_RATE},{audio.CHANNELS}"
    assert dest.stat().st_size > 1000


@requires_espeak
def test_espeak_lists_voices_for_a_language() -> None:
    assert tts.voices(tts.ESPEAK, LANGUAGES["fr"])


def test_a_custom_command_needs_a_template() -> None:
    with pytest.raises(tts.TtsError, match="needs --tts-command"):
        tts.synthesize("Chapter 1", "en", __import__("pathlib").Path("/tmp/x.mp3"), engine=tts.COMMAND)
