"""JSON builder tests; no audio, no ffmpeg, no network."""

from __future__ import annotations

import struct

import pytest

from daisy2telmi import tts
from daisy2telmi.images import card_png, placeholder_png
from daisy2telmi.extractor import Book
from daisy2telmi.telmi_builder import (
    Announce,
    StoryError,
    build_card_audio,
    build_metadata,
    build_nodes,
    build_notes,
    story_dir_name,
    story_uuid,
)
from nodes_validator import validate_nodes

SAMPLE = ["s0", "s1", "s2"]


def make_book(**overrides) -> Book:
    defaults = dict(
        title="ごんぎつね",
        chapters=(),
        front_matter=(),
        author="新美南吉",
        language="ja",
        publisher="ATDO",
        narrator="持田怜香",
        identifier="81353847207-020",
    )
    defaults.update(overrides)
    return Book(**defaults)


def test_nodes_have_no_structural_problems() -> None:
    assert validate_nodes(build_nodes(SAMPLE)) == []


def test_single_chapter_story_is_valid() -> None:
    nodes = build_nodes(["s0"])
    assert validate_nodes(nodes) == []
    assert nodes["stages"]["s0"]["ok"] is None


def test_start_action_enters_the_first_chapter_card() -> None:
    nodes = build_nodes(SAMPLE)
    assert nodes["startAction"] == {"action": "m", "index": 0}


def test_the_menu_lists_every_chapter_card_in_order() -> None:
    nodes = build_nodes(SAMPLE)
    assert nodes["actions"]["m"] == [{"stage": "m0"}, {"stage": "m1"}, {"stage": "m2"}]


def test_a_card_shows_its_image_and_waits_for_ok() -> None:
    """A card has no audio, so autoplay must stay off or the player skips it."""
    card = build_nodes(SAMPLE)["stages"]["m1"]
    assert card == {
        "image": "m1.png",
        "audio": None,
        "ok": {"action": "s1", "index": 0},
        "home": None,
        "control": {"ok": True, "home": True, "autoplay": False},
    }


def test_a_chapter_returns_to_the_next_card() -> None:
    stage = build_nodes(SAMPLE)["stages"]["s1"]
    assert stage["audio"] == "s1.mp3"
    assert stage["image"] is None
    assert stage["ok"] == {"action": "m", "index": 2}
    assert stage["home"] == {"action": "m", "index": 1}
    assert stage["control"] == {"ok": False, "home": True, "autoplay": True}


def test_last_chapter_ends_the_story() -> None:
    """Published packs use a null `ok` to end, not a wrap-around to the menu."""
    assert build_nodes(SAMPLE)["stages"]["s2"]["ok"] is None


def test_empty_chapter_list_is_rejected() -> None:
    with pytest.raises(StoryError):
        build_nodes([])


def test_notes_carry_the_chapter_titles() -> None:
    from daisy2telmi.extractor import Chapter

    book = make_book(chapters=[Chapter("Premier chapitre", ()), Chapter("Second", ())])
    notes = build_notes(book)
    assert notes["m0"] == {"title": "m0", "notes": "Premier chapitre"}
    assert notes["s0"] == {"title": "Premier chapitre", "notes": ""}


def test_metadata_contains_the_required_keys() -> None:
    metadata = build_metadata(make_book())
    for key in ("title", "uuid", "image", "version", "age", "category"):
        assert key in metadata
    assert metadata["title"] == "ごんぎつね"
    assert metadata["image"] == "cover.png"
    assert metadata["version"] == 0
    assert metadata["age"] == 0


def test_uuid_is_stable_for_the_same_book() -> None:
    assert story_uuid(make_book()) == story_uuid(make_book())


def test_uuid_differs_between_books() -> None:
    assert story_uuid(make_book()) != story_uuid(make_book(identifier="other"))


def test_description_lists_the_chapters() -> None:
    from daisy2telmi.extractor import Chapter

    book = make_book(chapters=[Chapter("Gon", ()), Chapter("The hunter", ())])
    description = build_metadata(book)["description"]
    assert "- Gon (1/2)" in description
    assert "- The hunter (2/2)" in description
    assert "Author: 新美南吉" in description


def test_dir_name_matches_a_real_published_story() -> None:
    """Pinned to the folder name Telmi-Sync produced for a published pack."""
    assert story_dir_name("La reine des pirates", "fffffd-19d14f92f57", 0, "") == (
        "_00_La reine des pirates_fffffd-19d14f92f57"
    )


def test_dir_name_strips_accents_and_odd_characters() -> None:
    name = story_dir_name("L'été de l'île", "8f2c-44", 7)
    assert name == "_07_L ete de l ile_8f2c-44"


def test_dir_name_pads_a_single_digit_age_and_caps_the_title() -> None:
    name = story_dir_name("a" * 50, "u", 12)
    assert name.startswith("_12_" + "a" * 32 + "_")


def test_placeholder_png_is_a_valid_640x480_rgb_image() -> None:
    data = placeholder_png()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[12:16] == b"IHDR"
    width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
    assert (width, height, depth, color_type) == (640, 480, 8, 2)
    assert data.endswith(b"IEND\xaeB`\x82")


def test_card_png_is_a_valid_image_that_differs_per_part() -> None:
    for number in (1, 12):
        data = card_png(f"{number}/12")
        width, height = struct.unpack(">II", data[16:24])
        assert (width, height) == (640, 480)
    assert card_png("1/12") != card_png("2/12")


def test_a_card_can_carry_spoken_audio_and_autoplay() -> None:
    nodes = build_nodes(SAMPLE, ["c0.mp3", "c1.mp3", "c2.mp3"], card_autoplay=True)
    assert validate_nodes(nodes) == []
    assert nodes["stages"]["m1"]["audio"] == "c1.mp3"
    assert nodes["stages"]["m1"]["control"]["autoplay"] is True


def test_cards_stay_silent_by_default() -> None:
    nodes = build_nodes(SAMPLE)
    assert all(stage["audio"] is None for name, stage in nodes["stages"].items() if name.startswith("m"))
    assert all(stage["control"]["autoplay"] is False for name, stage in nodes["stages"].items() if name.startswith("m"))


def test_a_card_snippet_is_the_opening_seconds_of_its_part(tmp_path, monkeypatch) -> None:
    from daisy2telmi import audio
    from daisy2telmi.extractor import AudioSegment, Chapter
    from daisy2telmi.telmi_builder import CARD_SNIPPET_SECONDS, build_snippets

    asked: list = []

    def render(segments, dest, limit=None):
        asked.append((dest.name, limit))
        return "cut"

    monkeypatch.setattr(audio, "render", render)
    parts = [Chapter("", (AudioSegment(tmp_path / f"p{k}.mp3"),)) for k in range(3)]
    assert build_snippets(parts, tmp_path) == ["c0.mp3", "c1.mp3", "c2.mp3"]
    assert asked == [(f"c{k}.mp3", CARD_SNIPPET_SECONDS) for k in range(3)]


def test_a_part_shorter_than_the_clip_gives_its_card_the_part_itself(tmp_path, monkeypatch) -> None:
    """Cut to sentences, many parts are under three seconds: a second copy would be pure size."""
    from daisy2telmi import audio
    from daisy2telmi.extractor import AudioSegment, Chapter
    from daisy2telmi.telmi_builder import CARD_SNIPPET_SECONDS, build_snippets

    asked: list = []
    monkeypatch.setattr(audio, "render", lambda segments, dest, limit=None: asked.append(dest.name) or "cut")
    parts = [
        Chapter("", (AudioSegment(tmp_path / "p.mp3", 0.0, CARD_SNIPPET_SECONDS - 1.0),)),
        Chapter("", (AudioSegment(tmp_path / "p.mp3", 0.0, CARD_SNIPPET_SECONDS + 30.0),)),
    ]
    assert build_snippets(parts, tmp_path) == ["s0.mp3", "c1.mp3"]
    assert asked == ["c1.mp3"]


def test_one_failing_snippet_leaves_every_card_silent(tmp_path, monkeypatch) -> None:
    from daisy2telmi import audio
    from daisy2telmi.extractor import AudioSegment, Chapter
    from daisy2telmi.telmi_builder import build_snippets

    def refuse(segments, dest, limit=None):
        raise audio.AudioError("no audio in that range")

    monkeypatch.setattr(audio, "render", refuse)
    parts = [Chapter("", (AudioSegment(tmp_path / "p.mp3"),)) for _ in range(2)]
    assert build_snippets(parts, tmp_path) == [None, None]


def test_the_description_lists_only_the_first_parts() -> None:
    """A book cut to the sentence level has hundreds of them; Telmi-Sync shows this list."""
    from daisy2telmi.extractor import Chapter
    from daisy2telmi.telmi_builder import LISTED_PARTS

    book = make_book(chapters=[Chapter(f"Part {k}", ()) for k in range(LISTED_PARTS + 5)])
    description = build_metadata(book)["description"]
    assert f"- Part {LISTED_PARTS - 1} ({LISTED_PARTS}/{LISTED_PARTS + 5})" in description
    assert "... 5 more" in description
    assert f"Part {LISTED_PARTS}" not in description


def test_an_announcement_phrase_carries_the_chapter_number() -> None:
    assert Announce(language="fr").phrase(3) == "Chapitre 3 Ecouter le chapitre suivant ?"
    assert Announce(mode="chapter", language="nl").phrase(2) == "Hoofdstuk 2"
    assert Announce(mode="off").phrase(1) is None


def test_one_failing_engine_leaves_every_card_silent(tmp_path) -> None:
    absent = next((e.name for e in tts.engines() if not e.found), None)
    if absent is None:
        pytest.skip("this machine has every speech engine")
    cards, spoken = build_card_audio(3, Announce(engine=absent), tmp_path)
    assert cards == [None, None, None]
    assert spoken == 0
