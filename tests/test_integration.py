"""End-to-end conversion of the real gon-ruby-mp3 DAISY 2.02 pack."""

from __future__ import annotations

import json
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

from daisy2telmi import audio, images
from daisy2telmi.cli import FORMATS, main
from daisy2telmi.detector import open_pack
from daisy2telmi.extractor import extract
from daisy2telmi.telmi_builder import story_dir_name
from lunii_validator import validate_studio_zip
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
            "stream=codec_name,sample_rate,channels,bit_rate:format=duration",
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


def _clip_count() -> int:
    with open_pack(PACK) as pack:
        return sum(len(chapter.segments) for chapter in extract(pack).chapters)


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
    # Joined clips keep their container's own padding, so the book can come out a
    # tolerance per clip longer than the marks declare. Nothing may be shorter.
    slack = audio.WHOLE_CLIP_TOLERANCE * _clip_count()
    assert scenes + title >= TOTAL_SECONDS - 0.5
    assert scenes + title <= TOTAL_SECONDS + slack
    assert title == pytest.approx(FRONT_MATTER_SECONDS, abs=audio.WHOLE_CLIP_TOLERANCE + 0.2)


@requires_pack
@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_audio_is_an_mp3_the_player_can_decode(story: Path) -> None:
    """Whole clips are joined as the pack wrote them; the player resamples to 44100 Hz."""
    for path in [story / "title.mp3", *(story / "audios").glob("s*.mp3")]:
        info = probe(path)
        assert info["codec_name"] == "mp3", path
        assert float(info["sample_rate"]) == 22050.0, path
        assert info["channels"] == "1", path
        assert 24_000 <= float(info["bit_rate"]) <= 320_000, path
    for path in (story / "audios").glob("c*.mp3"):
        assert float(probe(path)["sample_rate"]) == 44100.0, path


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


@requires_pack
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_listing_needs_no_output_folder(tmp_path: Path) -> None:
    assert main(["--list", str(PACK)]) == 0
    assert list(tmp_path.iterdir()) == []


def test_an_output_folder_is_still_required_to_convert() -> None:
    with pytest.raises(SystemExit) as stop:
        main([str(PACK)])
    assert stop.value.code == 2


def test_a_crop_outside_the_three_bands_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as stop:
        main([str(PACK), str(tmp_path / "out"), "--cover-crop", "middle"])
    assert stop.value.code == 2


@requires_pack
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_each_cover_crop_draws_a_different_pack(tmp_path: Path) -> None:
    cover = tmp_path / "tall.png"
    # Detail across the whole height, so no two bands of it are the same picture.
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc2=size=300x900,format=rgb24", "-frames:v", "1", str(cover),
        ],
        check=True,
    )
    titles = {}
    for mode in images.CROP_MODES:
        out = tmp_path / mode
        assert main([str(PACK), str(out), "--cover", str(cover), "--cover-crop", mode]) == 0
        folder = next(entry for entry in out.iterdir() if entry.is_dir())
        titles[mode] = (folder / images.TITLE_IMAGE).read_bytes()
    assert len(set(titles.values())) == 3, "each band has to land somewhere else in the pack"


@requires_pack
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_a_preview_writes_one_playable_file_per_chapter(tmp_path: Path) -> None:
    listen = tmp_path / "listen"
    assert main(["--preview", str(listen), str(PACK)]) == 0
    files = sorted(p.name for p in listen.glob("*.mp3"))
    assert len(files) == EXPECTED_CHAPTERS
    assert files[0].startswith("01 ") and files[-1].startswith("06 ")
    assert float(probe(listen / files[0])["duration"]) > 60


@requires_pack
def test_dropping_chapters_leaves_a_valid_shorter_story(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(PACK), str(out), "--drop", "1,4-6"]) == 0
    story = next(entry for entry in out.iterdir() if entry.is_dir())
    assert validate_story_dir(story) == []
    assert len(list((story / "audios").glob("s*.mp3"))) == 2
    nodes = json.loads((story / "nodes.json").read_text(encoding="utf-8"))
    assert sorted(k for k in nodes["stages"] if k.startswith("s")) == ["s0", "s1"]
    notes = json.loads((story / "notes.json").read_text(encoding="utf-8"))
    assert [notes[f"m{k}"]["notes"] for k in (0, 1)] == ["二", "三"]


@requires_pack
def test_a_chapter_selection_that_does_not_fit_is_refused_early(tmp_path: Path) -> None:
    out = tmp_path / "out"
    for spec in ("7", "1-6", "two"):
        assert main([str(PACK), str(out), "--drop", spec]) == 2, spec
    assert not out.exists()


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


def _greys(png: Path) -> set[int]:
    """The grey levels one picture holds."""
    raw = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(png),
         "-vf", "format=gray", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True,
        capture_output=True,
    ).stdout
    return set(raw)


@requires_pack
def test_the_lunii_format_writes_an_archive_lunii_imports(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    out = tmp_path / "out"
    assert main([str(PACK), str(out), "--format", "lunii"]) == 0
    story = next(entry for entry in out.iterdir() if entry.is_dir())
    archive = out / f"{story.name}-lunii.zip"
    assert archive.is_file(), f"no Lunii archive beside {story}"
    assert validate_studio_zip(archive) == []


@requires_pack
def test_the_lunii_format_draws_every_picture_in_four_greys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    out = tmp_path / "out"
    assert main([str(PACK), str(out), "--format", "lunii"]) == 0
    story = next(entry for entry in out.iterdir() if entry.is_dir())

    with zipfile.ZipFile(out / f"{story.name}-lunii.zip") as packed:
        pictures = [name for name in packed.namelist() if name.endswith(".png")]
        assert pictures, "a Lunii story carries its cards"
        for name in pictures:
            picture = tmp_path / "assets" / name
            picture.parent.mkdir(parents=True, exist_ok=True)
            picture.write_bytes(packed.read(name))
            levels = _greys(picture)
            assert len(levels) <= 4, f"{name} holds {sorted(levels)}"
            assert max(levels) == 255, f"{name} is not drawn light on dark"

    assert (story / "title.png").read_bytes() != (tmp_path / "assets" / "thumbnail.png").read_bytes(), (
        "the story folder keeps its colour pictures"
    )


def _png_size(path: Path) -> tuple[int, int]:
    return struct.unpack(">II", path.read_bytes()[16:24])


@requires_pack
def test_each_format_draws_at_its_own_screen(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    for player in FORMATS:
        out = tmp_path / f"out-{player}"
        assert main([str(PACK), str(out), "--format", player]) == 0
        story = next(entry for entry in out.iterdir() if entry.is_dir())
        scene, cover_size = images.screen(player)
        assert _png_size(story / "title.png") == scene, player
        assert _png_size(story / "cover.png") == cover_size, player
        assert _png_size(next((story / "images").glob("m*.png"))) == scene, player


@requires_pack
def test_no_lunii_archive_is_written_unless_asked(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    out = tmp_path / "out"
    assert main([str(PACK), str(out)]) == 0
    assert not list(out.glob("*-lunii.zip"))


@requires_pack
def test_force_reuses_an_existing_output_folder(tmp_path: Path) -> None:
    out = tmp_path / "out"
    assert main([str(PACK), str(out)]) == 0
    assert main([str(PACK), str(out), "--force"]) == 0
    story_folder = next(entry for entry in out.iterdir() if entry.is_dir())
    audios = story_folder / "audios"
    assert len(list(audios.glob("s*.mp3"))) == EXPECTED_CHAPTERS
    assert len(list(audios.glob("c*.mp3"))) == EXPECTED_CHAPTERS
