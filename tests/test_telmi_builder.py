"""JSON builder tests; no audio, no ffmpeg, no network."""

from __future__ import annotations

import struct

import pytest

from daisy2telmi.extractor import Book
from daisy2telmi.telmi_builder import (
    StoryError,
    build_metadata,
    build_nodes,
    placeholder_png,
    story_uuid,
)
from nodes_validator import validate_nodes

SAMPLE = ["s1", "s2", "s3"]


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
    nodes = build_nodes(["s1"])
    assert validate_nodes(nodes) == []
    assert nodes["stages"]["s1"]["ok"]["action"] == "backAction"


def test_start_action_enters_the_first_stage() -> None:
    nodes = build_nodes(SAMPLE)
    assert nodes["startAction"] == {"action": "a0", "index": 0}
    assert nodes["actions"]["a0"] == [{"stage": "s1"}]


def test_chapters_chain_linearly_through_ok_actions() -> None:
    nodes = build_nodes(SAMPLE)
    for first, second in zip(SAMPLE, SAMPLE[1:]):
        following = nodes["stages"][first]["ok"]["action"]
        assert nodes["actions"][following] == [{"stage": second}]


def test_last_chapter_ends_the_story() -> None:
    """The format has no 'finished' node, so the last ok returns to the menu."""
    assert build_nodes(SAMPLE)["stages"]["s3"]["ok"]["action"] == "backAction"


def test_every_scene_allows_autoplay_and_home() -> None:
    for name, stage in build_nodes(SAMPLE)["stages"].items():
        assert stage["control"] == {"ok": True, "home": True, "autoplay": True}
        assert stage["home"] == {"action": "backAction", "index": 0}
        assert stage["audio"] == f"{name}.mp3"
        assert stage["image"] is None


def test_ok_action_keys_are_unique_across_scenes() -> None:
    nodes = build_nodes([f"s{i}" for i in range(1, 8)])
    keys = [stage["ok"]["action"] for stage in nodes["stages"].values()]
    assert len(keys) == len(set(keys))


def test_no_action_is_shared_between_scenes() -> None:
    nodes = build_nodes(SAMPLE)
    used = [a for a in nodes["actions"] if a != "a0"]
    assert len(used) == len(SAMPLE) - 1


def test_empty_chapter_list_is_rejected() -> None:
    with pytest.raises(StoryError):
        build_nodes([])


def test_metadata_contains_the_required_keys() -> None:
    metadata = build_metadata(make_book())
    for key in ("title", "uuid", "image", "version"):
        assert key in metadata
    assert metadata["title"] == "ごんぎつね"
    assert metadata["image"] == "title.png"
    assert metadata["version"] == 2


def test_uuid_is_stable_for_the_same_book() -> None:
    assert story_uuid(make_book()) == story_uuid(make_book())


def test_uuid_differs_between_books() -> None:
    assert story_uuid(make_book()) != story_uuid(make_book(identifier="other"))


def test_metadata_omits_optional_fields_that_are_unknown() -> None:
    metadata = build_metadata(make_book(author=None, narrator=None, publisher=None, language=None))
    assert "category" not in metadata
    assert "age" not in metadata
    assert metadata["description"] == "Converted from DAISY 2.02"


def test_placeholder_png_is_a_valid_640x480_rgb_image() -> None:
    data = placeholder_png()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[12:16] == b"IHDR"
    width, height, depth, color_type = struct.unpack(">IIBB", data[16:26])
    assert (width, height, depth, color_type) == (640, 480, 8, 2)
    assert data.endswith(b"IEND\xaeB`\x82")
