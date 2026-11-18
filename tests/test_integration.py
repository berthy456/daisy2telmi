"""End-to-end conversion of the real gon-ruby-mp3 DAISY 2.02 pack."""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from daisy2telmi import images
from daisy2telmi.cli import main
from daisy2telmi.telmi_builder import story_dir_name
from nodes_validator import validate_story_dir, validate_story_zip

_PACK_CANDIDATES = (
    Path(__file__).resolve().parents[1] / "gon-ruby-mp3.zip",
    Path("~/daisy/gon-ruby-mp3.zip").expanduser(),
)
PACK = next((p for p in _PACK_CANDIDATES if p.exists()), _PACK_CANDIDATES[-1])
requires_pack = pytest.mark.skipif(not PACK.exists(), reason=f"test pack missing: {PACK}")

# Declared by ncc.html (ncc:totalTime 00:22:56) and er_book_info.xml.
TOTAL_SECONDS = 1376.645
FRONT_MATTER_SECONDS = 7.197
EXPECTED_CHAPTERS = 6


@pytest.fixture(scope="module")
def story(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("story")
    assert main([str(PACK), str(out)]) == 0
    folders = [entry for entry in out.iterdir() if entry.is_dir()]
    assert len(folders) == 1, f"expected one story folder, got {[f.name for f in folders]}"
    return folders[0]


def probe(path: Path) -> dict[str, str]:
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels,bit_rate:format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=0",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.strip().splitlines())


@requires_pack
def test_the_folder_passes_telmis_own_import_checks(story: Path) -> None:
    """The six entries Telmi-Sync requires, plus every referenced media file."""
    assert validate_story_dir(story) == []


@requires_pack
def test_the_zip_passes_telmis_zip_import_checks(story: Path) -> None:
    zip_path = story.with_name(story.name + ".zip")
    assert zip_path.is_file(), f"no zip next to {story}"
    assert validate_story_zip(zip_path) == []
    with zipfile.ZipFile(zip_path) as archive:
        entries = archive.namelist()
    assert all(name.startswith(f"{story.name}/") for name in entries)
    assert f"{story.name}/nodes.json" in entries


@requires_pack
def test_the_story_folder_uses_telmis_naming(story: Path) -> None:
    metadata = json.loads((story / "metadata.json").read_text(encoding="utf-8"))
    assert story.name == story_dir_name(metadata["title"], metadata["uuid"])


@requires_pack
def test_metadata_json_is_complete(story: Path) -> None:
    metadata = json.loads((story / "metadata.json").read_text(encoding="utf-8"))
    assert metadata["title"] == "ごんぎつね"
    assert metadata["image"] == "cover.png"
    assert metadata["uuid"]


@requires_pack
def test_nodes_json_has_one_chapter_per_top_level_chapter(story: Path) -> None:
    nodes = json.loads((story / "nodes.json").read_text(encoding="utf-8"))
    assert [name for name in nodes["stages"] if name.startswith("s")] == [
        f"s{k}" for k in range(EXPECTED_CHAPTERS)
    ]


@requires_pack
def test_every_chapter_has_a_card_image(story: Path) -> None:
    for k in range(EXPECTED_CHAPTERS):
        image = story / "images" / f"m{k}.png"
        assert image.is_file(), f"missing {image}"
        assert image.stat().st_size > 1000


@requires_pack
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_no_audio_is_dropped_from_the_book(story: Path) -> None:
    nodes = json.loads((story / "nodes.json").read_text(encoding="utf-8"))
    scenes = sum(
        float(probe(story / "audios" / stage["audio"])["duration"])
        for name, stage in nodes["stages"].items()
        if name.startswith("s")
    )
    title = float(probe(story / "title.mp3")["duration"])
    assert scenes + title == pytest.approx(TOTAL_SECONDS, abs=0.5)
    assert title == pytest.approx(FRONT_MATTER_SECONDS, abs=0.2)


@requires_pack
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_audio_meets_the_telmi_spec(story: Path) -> None:
    files = [story / "title.mp3", *(story / "audios").glob("*.mp3")]
    for path in files:
        info = probe(path)
        assert float(info["sample_rate"]) == 44100.0, path
        assert info["channels"] == "1", path
        assert 64_000 <= float(info["bit_rate"]) <= 192_000, path


@requires_pack
def test_an_already_extracted_folder_is_accepted(tmp_path: Path) -> None:
    unpacked = tmp_path / "unpacked"
    with zipfile.ZipFile(PACK) as archive:
        archive.extractall(unpacked)
    out = tmp_path / "out"
    assert main([str(unpacked), str(out)]) == 0
    story_folders = [entry for entry in out.iterdir() if entry.is_dir()]
    assert len(story_folders) == 1
    assert validate_story_dir(story_folders[0]) == []


@requires_pack
def test_an_existing_story_folder_is_refused_without_force(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(PACK), str(out)]) == 0
    (out / "keep.txt").write_text("do not clobber", encoding="utf-8")
    assert main([str(PACK), str(out)]) == 2
    assert (out / "keep.txt").read_text(encoding="utf-8") == "do not clobber"


def test_a_non_daisy_folder_fails_cleanly(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty), str(tmp_path / "out")]) == 1
    assert not (tmp_path / "out").exists()


def test_a_corrupt_table_of_contents_fails_cleanly(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "ncc.html").write_text("", encoding="utf-8")
    assert main([str(root), str(tmp_path / "out")]) == 1


@requires_pack
def test_a_missing_cover_is_refused_before_the_audio_runs(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(PACK), str(out), "--cover", str(tmp_path / "nope.png")]) == 2
    assert not out.exists()


@requires_pack
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_a_cover_replaces_every_generated_image(tmp_path: Path, story: Path) -> None:
    cover = tmp_path / "cover.png"
    cover.write_bytes(images.placeholder_png(300, 200))
    out = tmp_path / "out"
    assert main([str(PACK), str(out), "--cover", str(cover), "--language", "fr"]) == 0

    covered = next(entry for entry in out.iterdir() if entry.is_dir())
    assert validate_story_dir(covered) == []
    for name in (images.TITLE_IMAGE, images.COVER_IMAGE):
        assert (covered / name).read_bytes() != (story / name).read_bytes()
    cards = [covered / "images" / f"m{index}.png" for index in range(EXPECTED_CHAPTERS)]
    assert all(card.read_bytes() != (story / "images" / card.name).read_bytes() for card in cards)
    # The number is the only thing separating two cards drawn from one picture.
    assert cards[0].read_bytes() != cards[1].read_bytes()


MINIMAL_PACK = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><meta name="dc:title" content="No Front Matter"/></head>
  <body><h1 id="c1"><a href="a.smil#c1">One</a></h1></body>
</html>
"""


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_a_pack_without_front_matter_gets_a_silent_title(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "ncc.html").write_text(MINIMAL_PACK, encoding="utf-8")
    (root / "a.smil").write_text('<smil><body><audio src="one.mp3"/></body></smil>', encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=f=440", "-t", "2",
         "-c:a", "libmp3lame", str(root / "one.mp3")],
        check=True,
    )
    out = tmp_path / "out"
    assert main([str(root), str(out)]) == 0
    story = next(entry for entry in out.iterdir() if entry.is_dir())
    assert float(probe(story / "title.mp3")["duration"]) == pytest.approx(1.0, abs=0.2)
    assert float(probe(story / "audios" / "s0.mp3")["duration"]) == pytest.approx(2.0, abs=0.2)


@requires_pack
def test_force_reuses_an_existing_output_folder(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(PACK), str(out)]) == 0
    assert main([str(PACK), str(out), "--force"]) == 0
    story_folder = next(entry for entry in out.iterdir() if entry.is_dir())
    audios = story_folder / "audios"
    assert len(list(audios.glob("s*.mp3"))) == EXPECTED_CHAPTERS
    assert len(list(audios.glob("c*.mp3"))) == EXPECTED_CHAPTERS
