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

# A Lunii that is not a Flam has no colour panel: four greys, and the light end of
# them, so its cards are drawn the other way round — white ground, black ink.
LUNII_STYLES = ("colour", "bw")

_GREY_LEVELS = (0, 96, 192, 255)
_GREY_CUTS = (40, 110, 185)

_PALETTE = {
    "colour": {"background": BACKGROUND, "band": BAND, "ink": (255, 255, 255), "border": (0, 0, 0)},
    "bw": {"background": (255, 255, 255), "band": _GREY_LEVELS[2], "ink": (0, 0, 0), "border": (255, 255, 255)},
}

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


def placeholder_png(width: int = IMAGE_SIZE[0], height: int = IMAGE_SIZE[1], style: str = "colour") -> bytes:
    """A flat placeholder, written by hand so the converter needs no image library."""
    palette = _PALETTE[style]
    band_top, band_bottom = height // 2 - 48, height // 2 + 48
    rows = []
    for y in range(height):
        rgb = palette["band"] if band_top <= y < band_bottom else palette["background"]
        rows.append(bytes(rgb) * width)
    return _png(width, height, rows)


def glyph_rows(text: str) -> list[str]:
    """The 7 rows of a 5x7 rendering of `text`, one character per column."""
    return [" ".join(GLYPHS[character][y] for character in text) for y in range(7)]


MARGIN = 24
CARD_LINES = 3
CARD_WORDS = 20
CARD_SCALE = 4
NUMBER_SCALE = 6
CARD_THUMB = (160, 120)


def _drawable(text: str) -> str:
    """`text` upper cased with every character the built-in font lacks turned into a space."""
    return "".join(character if character in GLYPHS else " " for character in text.upper())


def card_words(text: str, width: int = IMAGE_SIZE[0], scale: int = CARD_SCALE) -> list[str]:
    """The opening words of a part, as up to three lines the card can show.

    The built-in font is 5x7 Latin, so a part whose words it cannot write gets no
    lines at all: the number and the spoken snippet still place the listener.
    """
    words = _drawable(text).split()[:CARD_WORDS]
    if not words:
        return []
    columns = (width - 2 * MARGIN) // (scale * 6)
    lines: list[str] = []
    for word in words:
        if lines and len(lines[-1]) + 1 + len(word) <= columns:
            lines[-1] = f"{lines[-1]} {word}"
        elif len(lines) < CARD_LINES:
            lines.append(word)
        else:
            break
    return [line[:columns] for line in lines]


def _stamp(ink: list[bytearray], left: int, top: int, glyph: list[str], scale: int, border: int) -> None:
    """Mark a 5x7 `glyph` into `ink`: 1 for the outline, 2 for the letter itself."""
    for pass_number, value in ((1, 1), (2, 2)):
        for y, row in enumerate(glyph):
            for x, cell in enumerate(row):
                if cell != "1":
                    continue
                grow = border if pass_number == 1 else 0
                for py in range(top + y * scale - grow, top + (y + 1) * scale + grow):
                    if 0 <= py < len(ink):
                        line = ink[py]
                        for px in range(left + x * scale - grow, left + (x + 1) * scale + grow):
                            if 0 <= px < len(line):
                                line[px] = value


def _card_grid(label: str, lines: list[str], width: int, height: int) -> list[bytearray]:
    """One card's lettering: the number top right, its opening words under the thumbnail."""
    ink = [bytearray(width) for _ in range(height)]
    number = glyph_rows(label)
    _stamp(ink, width - MARGIN - len(number[0]) * NUMBER_SCALE, MARGIN, number, NUMBER_SCALE, 1)
    top = MARGIN + CARD_THUMB[1] + MARGIN
    for offset, line in enumerate(lines):
        glyph = glyph_rows(line)
        _stamp(ink, MARGIN, top + offset * CARD_SCALE * 9, glyph, CARD_SCALE, 1)
    return ink


def _grid_png(ink: list[bytearray], base: tuple[int, int, int] | None, style: str = "colour") -> bytes:
    """Colour a card's lettering grid: over `base` for a whole card, transparent for an overlay."""
    palette = _PALETTE[style]
    letter, border = bytes(palette["ink"]), bytes(palette["border"])
    width, height = len(ink[0]), len(ink)
    rows = []
    for line in ink:
        row = bytearray()
        for cell in line:
            if cell == 2:
                row += letter + (b"" if base is not None else b"\xff")
            elif cell == 1:
                row += border + (b"" if base is not None else b"\xff")
            elif base is not None:
                row += bytes(base)
            else:
                row += b"\x00\x00\x00\x00"
        rows.append(bytes(row))
    return _png(width, height, rows, colour_type=6 if base is None else 2)


def card_png(
    label: str,
    text: str = "",
    width: int = IMAGE_SIZE[0],
    height: int = IMAGE_SIZE[1],
    style: str = "colour",
) -> bytes:
    """A card on its own: the part number, and the words it opens with when we can draw them."""
    return _grid_png(_card_grid(label, card_words(text), width, height), _PALETTE[style]["background"], style)


def card_layer_png(
    label: str,
    text: str = "",
    width: int = IMAGE_SIZE[0],
    height: int = IMAGE_SIZE[1],
    style: str = "colour",
) -> bytes:
    """The same lettering on a transparent canvas, to lay over a cropped cover."""
    return _grid_png(_card_grid(label, card_words(text), width, height), None, style)


def card_label(language_code: str, number: int, total: int, word: bool = True) -> str:
    """The words drawn on a card, in the story's language.

    The font is Latin, so Chinese and Arabic cards carry the number alone: it is
    the part that has to be read, and the spoken card already says the word.
    A part cut below chapter level gets the number alone as well, because none
    of the words we have would be the right one for it.
    """
    label = f"{number}/{total}" if not word else f"{language(language_code).card.upper()} {number}/{total}"
    if all(character in GLYPHS for character in label):
        return label
    return f"{number}/{total}"


def flat_png(width: int = IMAGE_SIZE[0], height: int = IMAGE_SIZE[1], style: str = "colour") -> bytes:
    """A plain card background, before the cover thumbnail and the lettering go on it."""
    return _png(width, height, [bytes(_PALETTE[style]["background"]) * width] * height)


def _run(args: list[str], description: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise ImageError(f"{description}: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'ffmpeg failed'}")


# A tall cover loses its title to a centre-crop, so which band survives is the
# user's call.
CROP_MODES = ("top", "center", "bottom")

# `ih-oh`, not the shorter `ih-h`: ffmpeg 9 dropped the crop filter's w/h aliases.
_CROP_OFFSET = {"top": ":0:0", "center": "", "bottom": ":0:ih-oh"}


def _grey_chain() -> str:
    """Flatten a picture to the four Lunii greys.

    The cuts sit towards the light end, so only a genuinely dark pixel turns
    black, and the blur before them keeps large areas flat instead of dithered.
    """
    steps = str(_GREY_LEVELS[-1])
    for cut, level in reversed(list(zip(_GREY_CUTS, _GREY_LEVELS))):
        steps = f"if(lt(val,{cut}),{level},{steps})"
    return f"format=gray,eq=contrast=1.6,gblur=sigma=1,lutyuv=y='{steps}',format=rgb24"


def _crop(ffmpeg: str, source: Path, size: tuple[int, int], dest: Path, mode: str = "center") -> None:
    width, height = size
    chain = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}{_CROP_OFFSET[mode]}"
    )
    _run(
        [ffmpeg, "-y", "-i", str(source), "-vf", chain, "-frames:v", "1", str(dest)],
        f"could not crop {source.name} to {width}x{height}",
    )


def _flatten(ffmpeg: str, png: Path) -> None:
    """Reduce one finished picture in place, so it holds no grey the screen lacks."""
    flat = png.with_suffix(".flat.png")
    _run(
        [ffmpeg, "-y", "-i", str(png), "-vf", _grey_chain(), "-frames:v", "1", str(flat)],
        f"could not flatten {png.name} to four greys",
    )
    flat.replace(png)


PREVIEW_SIZE = (160, 120)


def crop_previews(source: Path, size: tuple[int, int] = PREVIEW_SIZE) -> dict[str, bytes]:
    """Every crop band of `source`, small, so the choice can be made by eye."""
    ffmpeg = require_ffmpeg()
    previews: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="daisy2telmi-") as tmp:
        out = Path(tmp) / "preview.png"
        for mode in CROP_MODES:
            _crop(ffmpeg, source, size, out, mode)
            previews[mode] = out.read_bytes()
    return previews


def _overlay(ffmpeg: str, base: Path, overlay: Path, dest: Path, x: int, y: int) -> None:
    _run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(base),
            "-i",
            str(overlay),
            "-filter_complex",
            f"overlay={x}:{y}",
            "-frames:v",
            "1",
            str(dest),
        ],
        f"could not draw on {dest.name}",
    )


def write_cover(
    source: Path,
    out_dir: Path,
    labels: Sequence[str],
    texts: Sequence[str],
    crop: str = "center",
    style: str = "colour",
) -> None:
    """`title.png`, `cover.png` and one card per part, all from `source`.

    `style` is the screen the pack is drawn for: `bw` flattens the picture to the
    four Lunii greys and turns the card inside out, white ground and black ink.

    A card is a plain background with a small thumbnail of the cover, not the
    cover blown up behind the words: a book cut to the sentence level has
    hundreds of cards, and the thumbnail keeps one near 11 KB instead of 60 KB.
    """
    ffmpeg = require_ffmpeg()
    images = out_dir / "images"
    images.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="daisy2telmi-") as tmp:
        scratch = Path(tmp)
        base = scratch / "base.png"
        square = scratch / "square.png"
        thumb = scratch / "thumb.png"
        plain = scratch / "plain.png"
        card_base = scratch / "card.png"
        _crop(ffmpeg, source, IMAGE_SIZE, base, crop)
        _crop(ffmpeg, source, COVER_SIZE, square, crop)
        _crop(ffmpeg, source, CARD_THUMB, thumb, crop)
        plain.write_bytes(flat_png(style=style))
        _overlay(ffmpeg, plain, thumb, card_base, MARGIN, MARGIN)

        for index, (label, text) in enumerate(zip(labels, texts)):
            layer = scratch / f"layer{index}.png"
            layer.write_bytes(card_layer_png(label, text, style=style))
            _overlay(ffmpeg, card_base, layer, images / f"m{index}.png", 0, 0)
            if style == "bw":
                # Flattened last, once the compositing is done, so a card cannot
                # pick up a fifth grey where two layers meet.
                _flatten(ffmpeg, images / f"m{index}.png")
        if style == "bw":
            _flatten(ffmpeg, base)
            _flatten(ffmpeg, square)

        shutil.copyfile(base, out_dir / TITLE_IMAGE)
        shutil.copyfile(square, out_dir / COVER_IMAGE)
