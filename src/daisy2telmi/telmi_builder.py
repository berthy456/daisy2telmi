"""Write the Telmi story folder: metadata.json, nodes.json, notes.json, title assets, audios/, images/."""

from __future__ import annotations

import json
import logging
import re
import struct
import unicodedata
import uuid
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import audio
from .extractor import Book

log = logging.getLogger(__name__)

TITLE_IMAGE = "title.png"
COVER_IMAGE = "cover.png"
IMAGE_SIZE = (640, 480)
COVER_SIZE = (512, 512)
_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://wiki.telmi.fr/developments/daisy2telmi")

# Telmi-Sync's readStoryMetadata() deletes any story folder missing one of these.
REQUIRED_ENTRIES = (
    "audios",
    "images",
    "metadata.json",
    "nodes.json",
    "title.mp3",
    "title.png",
)

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


class StoryError(RuntimeError):
    """Raised when a story cannot be produced."""


@dataclass(frozen=True)
class StoryReport:
    out_dir: Path
    stages: tuple[str, ...]
    title_source: str


def story_uuid(book: Book) -> str:
    """Stable per book, so re-converting the same pack yields the same story id."""
    seed = book.identifier or f"{book.title}|{book.author or ''}|{len(book.chapters)}"
    return str(uuid.uuid5(_UUID_NAMESPACE, seed))


def normalize_file_name(value: str) -> str:
    """Telmi-Sync's stringNormalizeFileName: strip accents, collapse odd characters to spaces."""
    decomposed = unicodedata.normalize("NFD", value)
    stripped = "".join(c for c in decomposed if not 0x300 <= ord(c) <= 0x36F)
    return re.sub(r"[^a-zA-Z0-9\-.]+", " ", stripped)


def slugify(value: str) -> str:
    """Telmi-Sync's stringSlugify."""
    decomposed = unicodedata.normalize("NFD", value)
    stripped = "".join(c for c in decomposed if not 0x300 <= ord(c) <= 0x36F)
    return re.sub(r"[^a-z0-9]+", "-", stripped.lower())


def story_dir_name(title: str, story_id: str, age: int = 0, category: str = "") -> str:
    """Telmi-Sync's `generateDirNameStory`: `<category>_<age>_<title>_<uuid>`."""
    return (
        f"{normalize_file_name(category)[:32]}_"
        f"{('0' if age < 10 else '') + str(age)}_"
        f"{normalize_file_name(title)[:32]}_"
        f"{slugify(story_id)[:36]}"
    )


def build_metadata(book: Book) -> dict:
    """`metadata.json`, using the keys Telmi-Sync reads."""
    metadata = {
        "title": book.title,
        "uuid": story_uuid(book),
        "image": COVER_IMAGE,
        "category": "",
        "version": 0,
        "age": 0,
    }
    details = [
        f"{chapter.title} ({index + 1}/{len(book.chapters)})"
        for index, chapter in enumerate(book.chapters)
    ]
    credits = [
        f"{label}: {value}"
        for label, value in (
            ("Author", book.author),
            ("Narrator", book.narrator),
            ("Publisher", book.publisher),
            ("Language", book.language),
        )
        if value
    ]
    description = "\n".join(f"- {line}" for line in details)
    if credits:
        description = " - ".join(credits) + "\n" + description
    metadata["description"] = description
    return metadata


def build_nodes(chapter_names: Sequence[str]) -> dict:
    """Chapter-menu `nodes.json`, mirroring Telmi-Sync's own audio-list generator.

    `m<k>` is a silent menu card naming chapter k, `s<k>` the chapter audio.
    `ok` on the last chapter is null: the published packs use null, not a
    wrap-around, to end a story.
    """
    if not chapter_names:
        raise StoryError("no chapters to build a story from")

    stages: dict[str, dict] = {}
    actions: dict[str, list[dict]] = {"m": [{"stage": f"m{k}"} for k in range(len(chapter_names))]}

    for k in range(len(chapter_names)):
        stages[f"m{k}"] = {
            "image": f"m{k}.png",
            "audio": None,
            "ok": {"action": f"s{k}", "index": 0},
            "home": None,
            "control": {"ok": True, "home": True, "autoplay": False},
        }
        stages[f"s{k}"] = {
            "image": None,
            "audio": f"{chapter_names[k]}.mp3",
            "ok": None if k == len(chapter_names) - 1 else {"action": "m", "index": k + 1},
            "home": {"action": "m", "index": k},
            "control": {"ok": False, "home": True, "autoplay": True},
        }
        actions[f"s{k}"] = [{"stage": f"s{k}"}]

    return {"startAction": {"action": "m", "index": 0}, "stages": stages, "actions": actions}


def build_notes(book: Book) -> dict:
    """`notes.json`: the chapter titles, in the slots Telmi-Sync's Studio reads."""
    notes: dict[str, dict] = {}
    for k, chapter in enumerate(book.chapters):
        notes[f"m{k}"] = {"title": f"m{k}", "notes": chapter.title}
        notes[f"s{k}"] = {"title": chapter.title, "notes": ""}
    return notes


def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rows)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def placeholder_png(width: int = IMAGE_SIZE[0], height: int = IMAGE_SIZE[1]) -> bytes:
    """A flat placeholder, written by hand so the converter needs no image library."""
    background = (26, 30, 42)
    band = (78, 92, 122)
    band_top, band_bottom = height // 2 - 48, height // 2 + 48
    rows = []
    for y in range(height):
        rgb = band if band_top <= y < band_bottom else background
        rows.append(bytes(rgb) * width)
    return _png(width, height, rows)


def chapter_png(number: int, width: int = IMAGE_SIZE[0], height: int = IMAGE_SIZE[1]) -> bytes:
    """A placeholder carrying the chapter number, so scenes are tellable apart."""
    background = (26, 30, 42)
    foreground = (214, 222, 238)
    glyph = [" ".join(_DIGITS[d][y] for d in str(number)) for y in range(7)]
    scale = min(24, (width * 2 // 3) // len(glyph[0]), (height * 2 // 3) // len(glyph))
    block_width, block_height = len(glyph[0]) * scale, len(glyph) * scale
    left, top = (width - block_width) // 2, (height - block_height) // 2

    canvas = [bytes(background) * width for _ in range(top)]
    for glyph_row in glyph:
        strip = b"".join(
            bytes(foreground if ink == "1" else background) * scale for ink in glyph_row
        )
        canvas += [bytes(background) * left + strip + bytes(background) * (width - left - block_width)] * scale
    canvas += [bytes(background) * width for _ in range(height - top - block_height)]
    return _png(width, height, canvas)


def build_story(book: Book, out_dir: Path) -> StoryReport:
    """Render every chapter to `audios/` and write the story's JSON files and images."""
    if not book.chapters:
        raise StoryError("the pack contains no chapter with audio")

    audios = out_dir / "audios"
    images = out_dir / "images"
    audios.mkdir(parents=True, exist_ok=True)
    images.mkdir(parents=True, exist_ok=True)

    chapter_names = [f"s{k}" for k in range(len(book.chapters))]
    for name, index, chapter in zip(chapter_names, range(len(book.chapters)), book.chapters):
        log.info("rendering %s (%d audio clip group(s)) <- %s", name, len(chapter.segments), chapter.title)
        audio.render(chapter.segments, audios / f"{name}.mp3")
        (images / f"m{index}.png").write_bytes(chapter_png(index + 1))

    # The player plays title.mp3 when the story is selected, so the pack's own
    # spoken title belongs there rather than in a second stage inside the story.
    title_path = out_dir / "title.mp3"
    if book.front_matter:
        log.info("rendering title.mp3 from the pack's front matter")
        audio.render(book.front_matter, title_path)
        title_source = "front matter"
    else:
        log.info("pack has no front-matter audio; writing 1s of silence as title.mp3")
        audio.render_silence(title_path, 1.0)
        title_source = "generated silence"

    (out_dir / TITLE_IMAGE).write_bytes(placeholder_png())
    (out_dir / COVER_IMAGE).write_bytes(placeholder_png(*COVER_SIZE))

    metadata = build_metadata(book)
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "nodes.json").write_text(
        json.dumps(build_nodes(chapter_names), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "notes.json").write_text(
        json.dumps(build_notes(book), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return StoryReport(out_dir=out_dir, stages=tuple(chapter_names), title_source=title_source)


def write_story_zip(story_dir: Path, parent: Path) -> Path:
    """Package the story folder for Telmi-Sync's zip import.

    `findDirectory` in ConvertZip.js counts the Telmi marker files per zip
    directory and needs exactly four, so the folder goes in nested one level
    rather than unpacked at the archive root.
    """
    zip_path = parent / f"{story_dir.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in sorted(story_dir.rglob("*")):
            if entry.is_file():
                archive.write(entry, f"{story_dir.name}/{entry.relative_to(story_dir)}")
    return zip_path
