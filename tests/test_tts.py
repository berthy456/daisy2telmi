"""Speech engines: which ones are usable, and what they produce."""

from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from daisy2telmi import audio, tts
from daisy2telmi.i18n import LANGUAGES

requires_espeak = pytest.mark.skipif(
    shutil.which("espeak-ng") is None and shutil.which("espeak") is None,
    reason="no espeak-ng on this machine",
)
requires_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def test_the_engine_list_names_the_five_back_ends() -> None:
    assert [engine.name for engine in tts.engines()] == [tts.ESPEAK, tts.SAY, tts.SAPI, tts.COMMAND, tts.CHATTERBOX]


def test_windows_speech_is_only_offered_on_windows(monkeypatch) -> None:
    # pwsh is installed on Linux runners, where System.Speech does not exist;
    # offering it there makes `auto` pick an engine that cannot speak.
    monkeypatch.setattr(tts.sys, "platform", "linux")
    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/pwsh")
    assert not tts.available(tts.SAPI)


def test_off_short_circuits_before_any_lookup() -> None:
    assert tts.resolve("off", LANGUAGES["en"]) == "off"


def test_an_absent_engine_is_refused_rather_than_tried() -> None:
    # Chatterbox answers with its own hint about pip, and has a test of its own.
    absent = next((e.name for e in tts.engines() if not e.found and e.name != tts.CHATTERBOX), None)
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
        tts.synthesize("Chapter 1", "en", Path("/tmp/x.mp3"), engine=tts.COMMAND)


def test_the_chatterbox_helper_is_a_real_file() -> None:
    # The frozen binary has no Python of its own, so the helper it hands to the
    # user's interpreter has to exist on disk rather than live inside the archive.
    assert tts._speak_script().is_file()


def test_chatterbox_is_refused_when_no_python_is_on_the_machine(monkeypatch) -> None:
    monkeypatch.setattr(tts, "_python", lambda python=None: None)
    with pytest.raises(tts.TtsError, match="runs in your own Python"):
        tts.resolve(tts.CHATTERBOX, LANGUAGES["fr"])


def test_chatterbox_points_at_the_install_when_it_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(tts, "_python", lambda python=None: "/usr/bin/python3")
    monkeypatch.setattr(tts, "_has_chatterbox", lambda exe: False)
    with pytest.raises(tts.TtsError, match="pip install chatterbox-tts"):
        tts.resolve(tts.CHATTERBOX, LANGUAGES["fr"])


def test_chatterbox_is_only_offered_when_its_package_is_installed(monkeypatch) -> None:
    tts._chatterbox_cache.clear()
    seen: list[str] = []

    def fake_run(argv, capture_output, text):
        seen.extend(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="False\n", stderr="")

    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    assert not tts.available(tts.CHATTERBOX, "/usr/bin/python3")
    # find_spec only looks the package up; importing chatterbox would pull torch in.
    assert seen[:2] == ["/usr/bin/python3", "-I"] and "find_spec" in " ".join(seen)
    # The options page asks on every relabel, so the answer is kept.
    once = len(seen)
    assert not tts.available(tts.CHATTERBOX, "/usr/bin/python3")
    assert len(seen) == once
    tts._chatterbox_cache.clear()


@requires_ffmpeg
def test_chatterbox_loads_its_model_once_for_the_whole_batch(tmp_path, monkeypatch) -> None:
    manifests: list[dict] = []

    def fake_check(argv, label, env=None):
        manifests.append(json.loads(Path(argv[3]).read_text(encoding="utf-8")))
        for out in manifests[-1]["outs"]:
            with wave.open(out, "wb") as handle:
                handle.setframerate(8000)
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.writeframes(b"\x00\x20" * 8000)

    monkeypatch.setattr(tts, "_check", fake_check)
    monkeypatch.setattr(tts, "_python", lambda python=None: "/usr/bin/python3")
    monkeypatch.setattr(tts, "_has_chatterbox", lambda exe: True)

    dests = [tmp_path / f"c{k}.mp3" for k in range(3)]
    tts.synthesize_all(
        ["un", "deux", "trois"], "fr", dests, engine=tts.CHATTERBOX, python="/opt/models/bin/python", clip="ref.wav"
    )

    assert len(manifests) == 1, "one interpreter process should speak every card"
    assert manifests[0]["phrases"] == ["un", "deux", "trois"]
    assert manifests[0]["lang"] == "fr"
    assert manifests[0]["clip"] == "ref.wav"
    assert len(manifests[0]["outs"]) == 3
    for dest in dests:
        assert dest.is_file() and dest.stat().st_size > 1000


def test_every_phrase_needs_an_output_file() -> None:
    with pytest.raises(tts.TtsError, match="needs an output file"):
        tts.synthesize_all(["un", "deux"], "fr", [Path("/tmp/a.mp3")])
