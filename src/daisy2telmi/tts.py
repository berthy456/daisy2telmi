"""Turn a short phrase into an MP3 using whatever speech engine the machine has.

Every supported engine writes a lossless or near-lossless file into a temp
directory; ffmpeg then brings it to the Telmi audio spec, so the announcement
sits in the same `audios/` folder as the chapters and needs no special handling
in the player.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from . import audio
from .i18n import Language, language

log = logging.getLogger(__name__)

AUTO = "auto"
OFF = "off"
ESPEAK = "espeak"
SAY = "say"
SAPI = "sapi"
COMMAND = "command"

ENGINES = (AUTO, ESPEAK, SAY, SAPI, COMMAND, OFF)

SPEAKING_RATE = 150  # words per minute, espeak-ng's unit


class TtsError(RuntimeError):
    """Raised when no engine can produce the audio."""


@dataclass(frozen=True)
class Engine:
    name: str
    label: str
    found: bool


def _which(name: str) -> str | None:
    bundled = audio.bundled_executable(name)
    return str(bundled) if bundled else shutil.which(name)


def _espeak_env() -> dict[str, str]:
    """Point a bundled espeak-ng at the language data sitting next to it.

    Without this the binary finds no voices and says nothing at all, which looks
    like a working engine that produces silence.
    """
    env = dict(os.environ)
    bundled = audio.bundled_executable("espeak-ng")
    if bundled is None:
        return env
    data = Path(sys._MEIPASS) / "espeak-ng-data" if hasattr(sys, "_MEIPASS") else bundled.parent / "espeak-ng-data"
    if data.is_dir():
        env["ESPEAK_DATA_PATH"] = str(data)
    if sys.platform != "darwin":
        # The copied binary still names its libraries by their build-machine
        # paths; the loader looks next to the binary instead. macOS gets the same
        # effect from @loader_path rewrites at build time.
        env["LD_LIBRARY_PATH"] = os.pathsep.join([str(bundled.parent), env.get("LD_LIBRARY_PATH", "")]).rstrip(
            os.pathsep
        )
    return env


def available(name: str) -> bool:
    if name == ESPEAK:
        return _which("espeak-ng") or _which("espeak")
    if name == SAY:
        return sys.platform == "darwin" and _which("say")
    if name == SAPI:
        return _which("powershell") or _which("pwsh")
    if name == COMMAND:
        return True
    return False


def engines() -> list[Engine]:
    labels = {
        ESPEAK: "espeak-ng",
        SAY: "macOS say",
        SAPI: "Windows speech",
        COMMAND: "custom command",
    }
    return [Engine(name, labels[name], bool(available(name))) for name in (ESPEAK, SAY, SAPI, COMMAND)]


def resolve(engine: str, lang: Language) -> str:
    """Pick an engine. `auto` prefers espeak-ng: it covers all ten languages."""
    if engine in (AUTO, OFF):
        if engine == OFF:
            return OFF
        for name in (ESPEAK, SAY, SAPI):
            if available(name):
                return name
        raise TtsError(
            "no speech engine found. Install espeak-ng "
            "(macOS: brew install espeak-ng, Debian/Ubuntu: apt install espeak-ng) "
            "or pass --tts command."
        )
    if engine not in ENGINES:
        raise TtsError(f"unknown speech engine {engine!r}; choose from {', '.join(ENGINES)}")
    if engine != COMMAND and not available(engine):
        raise TtsError(f"{engine} is not available on this machine")
    return engine


def voices(engine: str, lang: Language) -> list[str]:
    """Voices the engine offers for `lang`, for the options page to list."""
    if engine == ESPEAK and (exe := _which("espeak-ng") or _which("espeak")):
        return _lines(exe, ["--voices=" + lang.espeak], _espeak_env(), skip_header=True)
    if engine == SAY and (exe := _which("say")):
        result = subprocess.run([exe, "-v", "?"], capture_output=True, text=True)
        wanted = lang.locale.replace("-", "_")
        return [
            line.split()[0]
            for line in result.stdout.splitlines()
            if len(line.split()) > 1
            and (line.split()[1] == wanted or line.split()[1].split("_")[0] == lang.code)
        ]
    if engine == SAPI and (exe := _which("powershell") or _which("pwsh")):
        script = (
            "[System.Speech.Synthesis.SpeechSynthesizer]::new().GetInstalledVoices() |"
            " ForEach-Object { $_.VoiceInfo.Name + \"`t\" + $_.VoiceInfo.Culture.Name }"
        )
        result = _run_powershell(exe, script)
        return [line.split("\t")[0] for line in result.splitlines() if lang.code in line.lower()]
    return []


def _lines(exe: str, args: list[str], env: dict[str, str] | None = None, skip_header: bool = False) -> list[str]:
    result = subprocess.run([exe, *args], capture_output=True, text=True, env=env)
    rows = result.stdout.splitlines()[1:] if skip_header else result.stdout.splitlines()
    names = []
    for row in rows:
        columns = row.split()
        if len(columns) >= 4:
            names.append(columns[3])
    return names


def _run_powershell(exe: str, script: str) -> str:
    # -EncodedCommand keeps non-ASCII phrases (Arabic, Chinese) intact and avoids quoting.
    payload = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-EncodedCommand", payload],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise TtsError(f"speech command failed: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def _render(engine: str, phrase: str, lang: Language, voice: str | None, command: str | None, out: Path) -> None:
    if engine == ESPEAK:
        exe = _which("espeak-ng") or _which("espeak")
        voice_name = voice or lang.espeak
        _check(
            [exe, "-v", voice_name, "-s", str(SPEAKING_RATE), "-w", str(out), phrase],
            "espeak-ng",
            _espeak_env(),
        )
    elif engine == SAY:
        # Without a matching voice, say reads foreign text with the default one
        # and mangles it, so pick one for the language rather than trusting -v.
        voice = voice or (voices(SAY, lang) or [None])[0]
        args = ["-r", str(SPEAKING_RATE)]
        if voice:
            args += ["-v", voice]
        elif lang.code != "en":
            log.warning("no %s voice installed for `say`; the default voice will read it", lang.name)
        _check(["say", *args, "-o", str(out), phrase], "say")
    elif engine == SAPI:
        exe = _which("powershell") or _which("pwsh")
        select = f"$s.SelectVoice('{voice}');" if voice else ""
        script = (
            "Add-Type -AssemblyName System.Speech;"
            "$s=[System.Speech.Synthesis.SpeechSynthesizer]::new();"
            f"{select}"
            f"$s.Rate=0;$s.SetOutputToWaveFile('{out}');$s.Speak('{phrase}');$s.Dispose();"
        )
        _run_powershell(exe, script)
    elif engine == COMMAND:
        if not command:
            raise TtsError("--tts command needs --tts-command with {text}, {out} and {lang} placeholders")
        import shlex

        argv = [
            part.format(text=phrase, out=str(out), lang=lang.code, locale=lang.locale, voice=voice or "")
            for part in shlex.split(command)
        ]
        _check(argv, "custom speech command")
    else:
        raise TtsError(f"cannot speak with engine {engine!r}")


def _check(argv: list[str], label: str, env: dict[str, str] | None = None) -> None:
    log.debug("running: %s", " ".join(argv))
    result = subprocess.run(argv, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise TtsError(f"{label} failed: {detail[-1] if detail else 'exit ' + str(result.returncode)}")


def synthesize(
    phrase: str,
    lang_code: str,
    dest: Path,
    engine: str = AUTO,
    voice: str | None = None,
    command: str | None = None,
) -> None:
    """Speak `phrase` into `dest` as an MP3 in the Telmi audio spec."""
    lang = language(lang_code)
    chosen = resolve(engine, lang)
    if chosen == OFF:
        raise TtsError("speech is switched off")

    suffix = ".aiff" if chosen == SAY else ".wav"
    with tempfile.TemporaryDirectory(prefix="daisy2telmi-tts-") as tmp:
        raw = Path(tmp) / f"speech{suffix}"
        _render(chosen, phrase, lang, voice, command, raw)
        if not raw.is_file() or raw.stat().st_size == 0:
            raise TtsError(f"{chosen} produced no audio for {phrase!r}")
        audio.convert_to_spec(raw, dest)
    log.debug("speech via %s: %r -> %s", chosen, phrase, dest.name)
