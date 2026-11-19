"""Regenerate `web/voices/`: the chapter-card phrases in every language.

A browser tab can play speech but cannot capture it into a file, so the web
converter ships these clips instead of synthesising them. espeak-ng is GPLv3,
the same licence as the project, which is why it is the source and not a
proprietary system voice.

    .venv/bin/python tools/make_web_voices.py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

from daisy2telmi.i18n import LANGUAGES

ROOT = Path(__file__).resolve().parents[1]


def run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


def clip(text: str, voice: str, dest: Path, bitrate: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "speech.wav"
        run(["espeak-ng", "-v", voice, "-s", "150", "-w", str(wav), text])
        run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(wav),
                "-ar",
                "44100",
                "-ac",
                "1",
                "-c:a",
                "libmp3lame",
                "-b:a",
                bitrate,
                str(dest),
            ]
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "web" / "voices")
    parser.add_argument("--max", type=int, default=50, help="highest chapter number to record")
    parser.add_argument("--bitrate", default="32")
    args = parser.parse_args()

    total = 0
    written = 0
    for code, lang in LANGUAGES.items():
        directory = args.out / code
        directory.mkdir(parents=True, exist_ok=True)
        for number in range(1, args.max + 1):
            dest = directory / f"{number:02d}.mp3"
            clip(lang.chapter.format(n=number), lang.espeak, dest, args.bitrate)
            total += dest.stat().st_size
            written += 1
        dest = directory / "next.mp3"
        clip(lang.next_prompt, lang.espeak, dest, args.bitrate)
        total += dest.stat().st_size
        written += 1
        print(f"{code}: {args.max} number(s) + the continue prompt")

    print(f"{written} file(s), {total / 1e6:.2f} MB in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
