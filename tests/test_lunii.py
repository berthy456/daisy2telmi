"""The Lunii export: the same story in the shape Lunii's own tools read."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from daisy2telmi.extractor import AudioSegment, Book, Chapter
from daisy2telmi.lunii import LuniiError, build_story_json, write_studio_zip
from daisy2telmi.telmi_builder import build_metadata, build_nodes
from lunii_validator import NODE_SIZE, ni_bytes, validate_studio_zip

PNG = bytes([0x89, 0x50, 0x4E, 0x47]) + b"\x00" * 24
MP3 = b"\xff\xfb\x50\xc0" + b"\x00" * 200


@pytest.fixture()
def story(tmp_path: Path) -> Path:
    """A converted Telmi folder: three parts, their media, and the two JSON files."""
    book = Book(
        title="Wesh la fée",
        chapters=tuple(Chapter(f"Partie {k}", (AudioSegment(tmp_path / f"a{k}.mp3"),)) for k in range(3)),
    )
    directory = tmp_path / "story"
    (directory / "audios").mkdir(parents=True)
    (directory / "images").mkdir(parents=True)
    (directory / "title.mp3").write_bytes(MP3)
    (directory / "title.png").write_bytes(PNG)
    (directory / "cover.png").write_bytes(PNG)
    for k in range(3):
        (directory / "audios" / f"s{k}.mp3").write_bytes(MP3)
        (directory / "audios" / f"c{k}.mp3").write_bytes(MP3)
        (directory / "images" / f"m{k}.png").write_bytes(PNG)

    (directory / "metadata.json").write_text(json.dumps(build_metadata(book)), encoding="utf-8")
    nodes = build_nodes([f"s{k}" for k in range(3)], [f"c{k}.mp3" for k in range(3)])
    (directory / "nodes.json").write_text(json.dumps(nodes), encoding="utf-8")
    return directory


def read(directory: Path) -> tuple[dict, dict]:
    return (
        json.loads((directory / "metadata.json").read_text(encoding="utf-8")),
        json.loads((directory / "nodes.json").read_text(encoding="utf-8")),
    )


def test_the_archive_carries_the_story_a_lunii_reads(tmp_path, story) -> None:
    archive = write_studio_zip(story)
    with zipfile.ZipFile(archive) as zip_file:
        names = zip_file.namelist()
        story_json = json.loads(zip_file.read("story.json").decode("utf-8"))

    assert names[0] == "story.json"
    assert "thumbnail.png" in names
    assert story_json["format"] == "v1"
    assert story_json["title"] == "Wesh la fée"
    # One cover plus the six stages of the Telmi graph.
    assert len(story_json["stageNodes"]) == 7
    assert story_json["stageNodes"][0]["type"] == "cover"
    assert validate_studio_zip(archive) == []


def test_the_two_archives_describe_the_same_story(story) -> None:
    """The Lunii pack is the Telmi pack unfolded backwards: same nodes, same media."""
    metadata, nodes = read(story)
    story_json, assets = build_story_json(metadata, nodes, story)

    media = {p.name for folder in ("audios", "images") for p in (story / folder).iterdir()}
    media |= {"title.mp3", "title.png"}
    assert {source.name for source in assets.values()} == media
    assert story_json["actionNodes"][0]["id"] == "m"
    assert len(story_json["actionNodes"][0]["options"]) == 3


def test_converting_twice_writes_the_same_archive(story) -> None:
    metadata, nodes = read(story)
    first, _ = build_story_json(metadata, nodes, story)
    second, _ = build_story_json(metadata, nodes, story)
    assert first == second


def test_the_device_index_resolves_every_reference(story) -> None:
    """`ni` is 0x200 of header plus 0x2C per node, and its indices have to land."""
    metadata, nodes = read(story)
    story_json, _ = build_story_json(metadata, nodes, story)
    ni = ni_bytes(story_json)

    assert len(ni) == 0x200 + NODE_SIZE * len(story_json["stageNodes"])
    assert int.from_bytes(ni[4:8], "little") == 0x200
    assert int.from_bytes(ni[8:12], "little") == NODE_SIZE
    assert int.from_bytes(ni[12:16], "little") == len(story_json["stageNodes"])
    # The cover's own image and audio are the first two entries of the asset tables.
    assert int.from_bytes(ni[0x200 : 0x204], "little", signed=True) == 0


def test_home_leaves_the_story_the_way_the_device_expects(story) -> None:
    """A lit home with nothing behind it is the firmware's exit; a card keeps it."""
    metadata, nodes = read(story)
    story_json, _ = build_story_json(metadata, nodes, story)
    cards = [node for node in story_json["stageNodes"] if node["name"].startswith("m")]
    assert all(node["controlSettings"]["home"] and node["homeTransition"] is None for node in cards)


def test_night_mode_is_a_flag_on_the_story(story) -> None:
    metadata, nodes = read(story)
    assert build_story_json(metadata, nodes, story)[0]["nightModeAvailable"] is False
    assert build_story_json(metadata, nodes, story, night_mode=True)[0]["nightModeAvailable"] is True


def test_a_story_without_its_title_audio_is_refused(story) -> None:
    (story / "title.mp3").unlink()
    with pytest.raises(LuniiError, match="title.mp3"):
        write_studio_zip(story)


def test_a_folder_that_is_not_a_converted_story_is_refused(tmp_path) -> None:
    with pytest.raises(LuniiError, match="not a converted story"):
        write_studio_zip(tmp_path)
