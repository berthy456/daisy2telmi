"""The drawn scene images: the font table, the card labels, and the cover pass."""

from __future__ import annotations

import shutil
import struct
import subprocess
from pathlib import Path

import pytest

from daisy2telmi import images
from daisy2telmi.cli import FORMATS
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


def test_each_player_draws_at_its_own_screen() -> None:
    assert images.screen("telmi") == ((640, 480), (512, 512))
    assert images.screen("lunii") == ((320, 240), (320, 240))
    assert images.screen("flam") == ((320, 212), (104, 136))
    assert set(images.SCREENS) == set(FORMATS)


def test_a_smaller_card_shrinks_everything_around_it() -> None:
    """The font is a fixed 5x7 grid, so the card's furniture scales with its screen."""
    assert images._layout(640) == (24, (160, 120), 4, 6)
    assert images._layout(320) == (12, (80, 60), 2, 3)


def test_a_smaller_card_holds_the_same_words() -> None:
    sentence = "the second of six parts, and the words keep going past the line"
    assert images.card_words(sentence, 320, 2) == images.card_words(sentence)


def test_the_lettering_of_every_card_stays_inside_its_screen() -> None:
    for player, (scene, _) in images.SCREENS.items():
        margin, thumb, scale, number_scale = images._layout(scene[0])
        lines = images.card_words("the second of six parts, and the words keep going", scene[0], scale)
        bottom = margin + thumb[1] + margin + (len(lines) - 1) * scale * 9 + 7 * scale
        assert bottom <= scene[1], player
        number = images.glyph_rows("213/213")
        assert margin + len(number[0]) * number_scale <= scene[0], player


def test_the_crop_preview_keeps_the_players_ratio() -> None:
    assert images.preview_size("telmi") == (160, 120)
    assert images.preview_size("lunii") == (160, 120)
    assert images.preview_size("flam") == (160, 106)


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


BANDS = {"top": "red", "center": "green", "bottom": "blue"}


def _tall_cover(tmp_path: Path) -> Path:
    """Red over green over blue, 300x900: a crop's band is then its colour."""
    source = tmp_path / "bands.png"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "color=red:s=300x300",
            "-f", "lavfi", "-i", "color=lime:s=300x300",
            "-f", "lavfi", "-i", "color=blue:s=300x300",
            "-filter_complex", "vstack=inputs=3", "-frames:v", "1", str(source),
        ],
        check=True,
    )
    return source


def _colour(png: Path) -> tuple[int, int, int]:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(png),
         "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    return struct.unpack("BBB", result.stdout[:3])


def _band(png: Path) -> str:
    """The channel that dominates a picture: ffmpeg moves a flat colour by a
    couple of units, so the loudest channel is what a crop can be checked on."""
    return max(zip(_colour(png), ("red", "green", "blue")))[1]


@NO_FFMPEG
def test_each_crop_keeps_the_band_it_names(tmp_path: Path) -> None:
    source = _tall_cover(tmp_path)
    for mode, band in BANDS.items():
        out = tmp_path / f"{mode}.png"
        images._crop("ffmpeg", source, images.IMAGE_SIZE, out, mode)
        assert _band(out) == band, mode


@NO_FFMPEG
def test_the_crop_choice_reaches_every_image_write_cover_draws(tmp_path: Path) -> None:
    source = _tall_cover(tmp_path)
    high = tmp_path / "high"
    low = tmp_path / "low"
    images.write_cover(source, high, ["1/1"], [""], "top")
    images.write_cover(source, low, ["1/1"], [""], "bottom")
    for name in (images.TITLE_IMAGE, images.COVER_IMAGE):
        assert _band(high / name) == BANDS["top"], name
        assert _band(low / name) == BANDS["bottom"], name
    # The card's thumbnail follows the same band, so it is the choice that changes it.
    assert (high / "images/m0.png").read_bytes() != (low / "images/m0.png").read_bytes()


@NO_FFMPEG
def test_crop_previews_shows_every_band_small(tmp_path: Path) -> None:
    previews = images.crop_previews(_tall_cover(tmp_path))
    assert list(previews) == list(images.CROP_MODES)
    for mode, png in previews.items():
        assert png_header(png)[:2] == images.PREVIEW_SIZE, mode
    saved = tmp_path / "preview.png"
    for mode, png in previews.items():
        saved.write_bytes(png)
        assert _band(saved) == BANDS[mode], mode
