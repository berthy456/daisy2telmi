"""Scene images: placeholders, and a user's cover cropped into Telmi's sizes.

ffmpeg scales, crops and composites; the chapter number is drawn here with a 5x7
font, so the converter needs no image library and no font file. Languages whose
script the font cannot write (Chinese, Arabic) get the number on its own, which
needs no letters to be legible.
"""

from __future__ import annotations

import shutil
import struct
import subprocess
import tempfile
import zlib
from pathlib import Path
from typing import Sequence

from .audio import require_ffmpeg
from .i18n import language

TITLE_IMAGE = "title.png"
COVER_IMAGE = "cover.png"
IMAGE_SIZE = (640, 480)
COVER_SIZE = (512, 512)

BACKGROUND = (26, 30, 42)
BAND = (78, 92, 122)
FOREGROUND = (214, 222, 238)

# 5 columns, 7 rows, "1" is ink. Uppercase only: a card label is a title, and it
# keeps the table to what eight Latin-script languages need.
_LETTERS = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("01110", "00100", "00100", "00100", "00100", "00100", "01110"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "10001", "11011", "10101", "10001", "10001", "10001"),
    "N": ("10001", "10001", "11001", "10101", "10011", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "11011", "10001", "10001"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "Á": ("00100", "00010", "01110", "10001", "11111", "10001", "10001"),
    "É": ("00100", "00010", "11111", "10000", "11110", "10000", "11111"),
    "Í": ("00100", "00010", "01110", "00100", "00100", "00100", "01110"),
    "Ó": ("00100", "00010", "01110", "10001", "10001", "10001", "01110"),
    "Ö": ("00101", "00000", "01110", "10001", "10001", "10001", "01110"),
    "Ü": ("00101", "00000", "10001", "10001", "10001", "10001", "01110"),
    "Ç": ("01110", "10001", "10000", "10000", "10000", "10001", "01110"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
}

_DIGITS = {
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("01110", "10001", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "10001", "01110"),
}

GLYPHS = {**_DIGITS, **_LETTERS}


class ImageError(RuntimeError):
    """Raised when ffmpeg cannot produce a scene image."""


def _png(width: int, height: int, rows: list[bytes], colour_type: int = 2) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, colour_type, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def placeholder_png(width: int = IMAGE_SIZE[0], height: int = IMAGE_SIZE[1]) -> bytes:
    """A flat placeholder, written by hand so the converter needs no image library."""
    band_top, band_bottom = height // 2 - 48, height // 2 + 48
    rows = []
    for y in range(height):
        rgb = BAND if band_top <= y < band_bottom else BACKGROUND
        rows.append(bytes(rgb) * width)
    return _png(width, height, rows)


def glyph_rows(text: str) -> list[str]:
    """The 7 rows of a 5x7 rendering of `text`, one character per column."""
    return [" ".join(GLYPHS[character][y] for character in text) for y in range(7)]


def chapter_png(number: int, width: int = IMAGE_SIZE[0], height: int = IMAGE_SIZE[1]) -> bytes:
    """A placeholder carrying the chapter number, so scenes are tellable apart."""
    glyph = [" ".join(_DIGITS[d][y] for d in str(number)) for y in range(7)]
    scale = min(24, (width * 2 // 3) // len(glyph[0]), (height * 2 // 3) // len(glyph))
    block_width, block_height = len(glyph[0]) * scale, len(glyph) * scale
    left, top = (width - block_width) // 2, (height - block_height) // 2

    canvas = [bytes(BACKGROUND) * width for _ in range(top)]
    for glyph_row in glyph:
        strip = b"".join(
            bytes(FOREGROUND if ink == "1" else BACKGROUND) * scale for ink in glyph_row
        )
        canvas += [bytes(BACKGROUND) * left + strip + bytes(BACKGROUND) * (width - left - block_width)] * scale
    canvas += [bytes(BACKGROUND) * width for _ in range(height - top - block_height)]
    return _png(width, height, canvas)


def card_label(language_code: str, number: int, total: int) -> str:
    """The words drawn on a chapter card, in the story's language.

    The font is Latin, so Chinese and Arabic cards carry the number alone: it is
    the part that has to be read, and the spoken card already says the word.
    """
    label = f"{language(language_code).card.upper()} {number}/{total}"
    if all(character in GLYPHS for character in label):
        return label
    return f"{number}/{total}"


def label_png(text: str, max_width: int = IMAGE_SIZE[0]) -> bytes:
    """`text` in white with a black border, on a transparent canvas."""
    glyph = glyph_rows(text)
    scale = max(4, min(24, (max_width * 4 // 5) // len(glyph[0])))
    border = max(1, scale // 6)
    pad = border * 2
    columns, rows = len(glyph[0]), len(glyph)

    def ink(x: int, y: int) -> bool:
        return 0 <= x < columns and 0 <= y < rows and glyph[y][x] == "1"

    def touched(x: int, y: int) -> bool:
        return any(
            ink(x + dx, y + dy)
            for dx in range(-border, border + 1)
            for dy in range(-border, border + 1)
        )

    width, height = columns * scale + 2 * pad, rows * scale + 2 * pad
    canvas = []
    for y in range(height):
        row = bytearray()
        for x in range(width):
            cell_x, cell_y = (x - pad) // scale, (y - pad) // scale
            if 0 <= cell_x < columns and 0 <= cell_y < rows:
                colour = (255, 255, 255, 255) if ink(cell_x, cell_y) else (
                    (0, 0, 0, 255) if touched(cell_x, cell_y) else (0, 0, 0, 0)
                )
            else:
                colour = (0, 0, 0, 0)
            row += bytes(colour)
        canvas.append(bytes(row))
    return _png(width, height, canvas, colour_type=6)


def _run(args: list[str], description: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise ImageError(f"{description}: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'ffmpeg failed'}")


def _crop(ffmpeg: str, source: Path, size: tuple[int, int], dest: Path) -> None:
    width, height = size
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(source),
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
            "-frames:v",
            "1",
            str(dest),
        ],
        f"could not crop {source.name} to {width}x{height}",
    )


def _overlay(ffmpeg: str, base: Path, overlay: Path, dest: Path) -> None:
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(base),
            "-i",
            str(overlay),
            "-filter_complex",
            "overlay=(W-w)/2:(H-h)/2",
            "-frames:v",
            "1",
            str(dest),
        ],
        f"could not draw on {dest.name}",
    )


def write_cover(source: Path, out_dir: Path, labels: Sequence[str]) -> None:
    """`title.png`, `cover.png` and one numbered card per label, all from `source`."""
    ffmpeg = require_ffmpeg()
    images = out_dir / "images"
    images.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="daisy2telmi-") as tmp:
        scratch = Path(tmp)
        base = scratch / "base.png"
        square = scratch / "square.png"
        _crop(ffmpeg, source, IMAGE_SIZE, base)
        _crop(ffmpeg, source, COVER_SIZE, square)

        for index, label in enumerate(labels):
            text = scratch / f"label{index}.png"
            text.write_bytes(label_png(label))
            _overlay(ffmpeg, base, text, images / f"m{index}.png")

        shutil.copyfile(base, out_dir / TITLE_IMAGE)
        shutil.copyfile(square, out_dir / COVER_IMAGE)
