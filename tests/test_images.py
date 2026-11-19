"""The drawn scene images: the font table, the card labels, and the cover pass."""

from __future__ import annotations

import shutil
import struct
import subprocess
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


def test_the_card_layer_is_white_ink_on_a_transparent_canvas() -> None:
    width, height, colour = png_header(images.card_layer_png("2/6", "the second of six parts"))
    assert colour == 6, "RGBA, so ffmpeg can overlay it"
    assert (width, height) == images.IMAGE_SIZE


def test_a_card_shows_the_opening_words_in_three_lines() -> None:
    lines = images.card_words("the second of six parts, and the words keep going past the line")
    assert len(lines) == images.CARD_LINES
    assert lines[0].startswith("THE SECOND")
    assert all(len(line) * images.CARD_SCALE * 6 <= images.IMAGE_SIZE[0] for line in lines)
    assert images.card_words("one two") == ["ONE TWO"]


def test_words_the_font_cannot_write_leave_the_card_without_lines() -> None:
    assert images.card_words("これは、私（わたし）が小さいときに") == []
    assert images.card_words("") == []


def test_a_part_below_chapter_level_is_numbered_without_a_word() -> None:
    assert images.card_label("fr", 7, 213, word=False) == "7/213"


def test_the_placeholder_and_the_card_are_the_sizes_telmi_wants() -> None:
    assert png_header(images.placeholder_png())[:2] == (640, 480)
    assert png_header(images.placeholder_png(*images.COVER_SIZE))[:2] == (512, 512)
    assert png_header(images.card_png("7/9"))[:2] == (640, 480)
    assert png_header(images.flat_png())[:2] == (640, 480)


@NO_FFMPEG
def test_write_cover_crops_the_picture_and_numbers_every_card(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    # A picture with detail in it, so a card's real size shows up.
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=800x600,format=rgb24", "-frames:v", "1", str(source),
        ],
        check=True,
    )
    out = tmp_path / "story"

    images.write_cover(
        source,
        out,
        [images.card_label("en", k + 1, 3) for k in range(3)],
        ["", "", ""],
    )

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
    # A book cut to the sentence level has hundreds of cards, so one must stay small.
    assert len(first) < 20_000


@NO_FFMPEG
def test_write_cover_reports_an_image_ffmpeg_cannot_read(tmp_path: Path) -> None:
    broken = tmp_path / "broken.png"
    broken.write_bytes(b"not a png")
    with pytest.raises(images.ImageError, match="could not crop"):
        images.write_cover(broken, tmp_path / "story", [images.card_label("en", 1, 1)], [""])
