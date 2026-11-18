"""The drawn scene images: the font table, the card labels, and the cover pass."""

from __future__ import annotations

import shutil
import struct
from pathlib import Path

import pytest

from daisy2telmi import images
from daisy2telmi.i18n import LANGUAGES

NO_FFMPEG = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")


def png_header(data: bytes) -> tuple[int, int, int]:
    width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
    assert depth == 8
    return width, height, colour


def test_every_glyph_is_five_by_seven() -> None:
    for character, glyph in images.GLYPHS.items():
        assert len(glyph) == 7, character
        assert all(len(row) == 5 and set(row) <= {"0", "1"} for row in glyph), character


def test_the_font_covers_every_card_word_it_claims() -> None:
    for code, language in LANGUAGES.items():
        drawn = images.card_label(code, 3, 12)
        assert all(character in images.GLYPHS for character in drawn), (code, drawn)


def test_the_card_word_is_written_in_the_story_language() -> None:
    assert images.card_label("en", 2, 23) == "CHAPTER 2/23"
    assert images.card_label("fr", 2, 23) == "CHAPITRE 2/23"
    assert images.card_label("tr", 2, 23) == "BÖLÜM 2/23"
    assert images.card_label("nl", 9, 9) == "HOOFDSTUK 9/9"


def test_scripts_the_font_lacks_fall_back_to_the_number() -> None:
    for code in ("zh", "ar"):
        assert images.card_label(code, 4, 23) == "4/23"


def test_glyph_rows_put_the_characters_side_by_side() -> None:
    rows = images.glyph_rows("10")
    assert len(rows) == 7
    assert all(len(row) == 11 for row in rows)  # two 5-wide glyphs and a gap
    assert rows[0] == "00100 01110"


def test_the_label_is_white_ink_on_a_transparent_canvas() -> None:
    width, height, colour = png_header(images.label_png("2/6"))
    assert colour == 6, "RGBA, so ffmpeg can overlay it"
    assert (width, height) == (17 * 24 + 16, 7 * 24 + 16)  # three glyphs at the largest scale
    # A longer label shrinks its scale instead of running off the card.
    wide, tall = png_header(images.label_png("HOOFDSTUK 12/120"))[:2]
    assert wide <= images.IMAGE_SIZE[0] * 4 // 5
    assert tall < height


def test_the_placeholder_and_the_card_are_the_sizes_telmi_wants() -> None:
    assert png_header(images.placeholder_png())[:2] == (640, 480)
    assert png_header(images.placeholder_png(*images.COVER_SIZE))[:2] == (512, 512)
    assert png_header(images.chapter_png(7))[:2] == (640, 480)


@NO_FFMPEG
def test_write_cover_crops_the_picture_and_numbers_every_card(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(images.placeholder_png(300, 200))
    out = tmp_path / "story"

    images.write_cover(source, out, [images.card_label("en", k + 1, 3) for k in range(3)])

    assert png_header((out / images.TITLE_IMAGE).read_bytes())[:2] == (640, 480)
    assert png_header((out / images.COVER_IMAGE).read_bytes())[:2] == (512, 512)
    cards = sorted(p.name for p in (out / "images").glob("*.png"))
    assert cards == ["m0.png", "m1.png", "m2.png"]
    for name in cards:
        assert png_header((out / "images" / name).read_bytes())[:2] == (640, 480)
    # The label is what separates the cards; identical cards mean the overlay failed.
    first = (out / "images/m0.png").read_bytes()
    second = (out / "images/m1.png").read_bytes()
    assert first != second


@NO_FFMPEG
def test_write_cover_reports_an_image_ffmpeg_cannot_read(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    with pytest.raises(images.ImageError, match="could not crop"):
        images.write_cover(broken, tmp_path / "story", [images.card_label("en", 1, 1)])
