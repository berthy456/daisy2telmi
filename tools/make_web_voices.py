"""Regenerate `web/voices/`: the chapter-card phrases in every language.

A browser tab can play speech but cannot capture it into a file, so the web
converter ships these clips instead of synthesising them.

    .venv/bin/python tools/make_web_voices.py
    .venv/bin/python tools/make_web_voices.py --engine chatterbox --python /usr/bin/python3

espeak-ng is the default because it is GPLv3 like the project and needs no
download. Chatterbox gives a real voice instead of a robotic one, but it runs in
a Python of your own (`pip install chatterbox-tts`) and takes a couple of minutes
per language on a CPU. Both are levelled to the same loudness, so switching
engine does not change how loud the cards sound next to the story.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from daisy2telmi import tts
from daisy2telmi.i18n import LANGUAGES

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


def rows(lang, max_number: int) -> list[tuple[str, str]]:
    """The phrases one language needs, with the file name each one becomes."""
    every = [(lang.chapter.format(n=n), f"{n:02d}.mp3") for n in range(1, max_number + 1)]
    return every + [(lang.next_prompt, "next.mp3")]


def encode(raw: Path, dest: Path, bitrate: str) -> None:
    """One clip to the web page's size: mono, small, and levelled like a card."""
    run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(raw),
            "-ar",
            "44100",
            "-ac",
            "1",
            "-af",
            tts.card_loudness(None),
            "-c:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            str(dest),
        ]
    )


def speak_espeak(phrases: list[str], voice: str, raws: list[Path]) -> None:
    for phrase, raw in zip(phrases, raws):
        run(["espeak-ng", "-v", voice, "-s", str(tts.SPEAKING_RATE), "-w", str(raw), phrase])


def speak_chatterbox(phrases: list[str], lang, raws: list[Path], folder: Path, python, device: str) -> None:
    """One process for the whole language: loading the model costs more than
    speaking a chapter number, and it would otherwise happen 51 times."""
    manifest = folder / "manifest.json"
    manifest.write_text(
        json.dumps({"phrases": phrases, "outs": [str(raw) for raw in raws], "lang": lang.code, "device": device}),
        encoding="utf-8",
    )
    result = subprocess.run(
        [python, "-I", str(tts._speak_script()), str(manifest)], capture_output=True, text=True
    )
    if result.returncode:
        raise SystemExit(f"chatterbox failed: {(result.stderr or result.stdout).strip()}")
    print(f"  {result.stdout.strip().splitlines()[0]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "voices")
    parser.add_argument("--max", type=int, default=50, help="highest chapter number to record")
    parser.add_argument("--bitrate", default="32")
    parser.add_argument("--engine", choices=(tts.ESPEAK, tts.CHATTERBOX), default=tts.ESPEAK)
    parser.add_argument("--python", default=None, help="interpreter --engine chatterbox runs in")
    parser.add_argument("--device", choices=tts.DEVICES, default=tts.AUTO)
    args = parser.parse_args()

    python = tts._python(args.python) if args.engine == tts.CHATTERBOX else None
    if args.engine == tts.CHATTERBOX and not python:
        raise SystemExit("chatterbox runs in your own Python: pass --python")

    total = 0
    written = 0
    for code, lang in LANGUAGES.items():
        directory = args.out / code
        directory.mkdir(parents=True, exist_ok=True)
        wanted = rows(lang, args.max)
        with tempfile.TemporaryDirectory(prefix="daisy2telmi-voices-") as tmp:
            folder = Path(tmp)
            raws = [folder / f"speech{k}.wav" for k in range(len(wanted))]
            phrases = [phrase for phrase, _ in wanted]
            if args.engine == tts.CHATTERBOX:
                speak_chatterbox(phrases, lang, raws, folder, python, args.device)
            else:
                speak_espeak(phrases, lang.espeak, raws)
            for (phrase, name), raw in zip(wanted, raws):
                dest = directory / name
                encode(raw, dest, args.bitrate)
                total += dest.stat().st_size
                written += 1
        print(f"{code}: {args.max} number(s) + the continue prompt")

    print(f"{written} file(s), {total / 1e6:.2f} MB in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
