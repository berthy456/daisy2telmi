"""Write the Telmi story folder: metadata.json, nodes.json, title assets, audios/."""

from __future__ import annotations

import json
import logging
import struct
import uuid
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import audio
from .extractor import Book

log = logging.getLogger(__name__)

TITLE_IMAGE = "title.png"
IMAGE_SIZE = (640, 480)
_BACK_ACTION = "backAction"
_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://wiki.telmi.fr/developments/daisy2telmi")


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


def build_metadata(book: Book) -> dict:
    """`metadata.json`. Only the required keys plus a description are emitted."""
    details = []
    if book.author:
        details.append(f"Author: {book.author}")
    if book.narrator:
        details.append(f"Narrator: {book.narrator}")
    if book.publisher:
        details.append(f"Publisher: {book.publisher}")
    if book.language:
        details.append(f"Language: {book.language}")
    details.append("Converted from DAISY 2.02")

    metadata = {
        "title": book.title,
        "uuid": story_uuid(book),
        "image": TITLE_IMAGE,
        "version": 2,
        "description": " - ".join(details),
    }
    return metadata


def build_nodes(stage_names: Sequence[str]) -> dict:
    """Linear `nodes.json`: one stage per chapter, chained by `ok`, autoplay on.

    The final chapter's `ok` returns to the menu via `backAction`, because the
    Telmi format has no explicit "story finished" node.
    """
    if not stage_names:
        raise StoryError("no chapters to build a story from")

    stages: dict[str, dict] = {}
    actions: dict[str, list[dict]] = {"a0": [{"stage": stage_names[0]}]}

    for index, name in enumerate(stage_names):
        is_last = index == len(stage_names) - 1
        stages[name] = {
            "image": None,
            "audio": f"{name}.mp3",
            "ok": {"action": _BACK_ACTION, "index": 0} if is_last else {"action": f"a{index + 1}", "index": 0},
            "home": {"action": _BACK_ACTION, "index": 0},
            "control": {"ok": True, "home": True, "autoplay": True},
        }
        if not is_last:
            actions[f"a{index + 1}"] = [{"stage": stage_names[index + 1]}]

    return {
        "startAction": {"action": "a0", "index": 0},
        "stages": stages,
        "actions": actions,
    }


def placeholder_png(width: int = IMAGE_SIZE[0], height: int = IMAGE_SIZE[1]) -> bytes:
    """A flat 640x480 PNG, written by hand so the converter needs no image library."""
    background = (26, 30, 42)
    band = (78, 92, 122)
    band_top, band_bottom = height // 2 - 48, height // 2 + 48
    rows = []
    for y in range(height):
        rgb = band if band_top <= y < band_bottom else background
        rows.append(b"\x00" + bytes(rgb) * width)
    raw = b"".join(rows)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def build_story(book: Book, out_dir: Path) -> StoryReport:
    """Render every chapter to `audios/` and write the story's JSON files."""
    if not book.chapters:
        raise StoryError("the pack contains no chapter with audio")

    audios = out_dir / "audios"
    audios.mkdir(parents=True, exist_ok=True)

    stage_names = [f"s{index}" for index in range(1, len(book.chapters) + 1)]
    for name, chapter in zip(stage_names, book.chapters):
        log.info("rendering %s (%d audio clip group(s)) <- %s", name, len(chapter.segments), chapter.title)
        audio.render(chapter.segments, audios / f"{name}.mp3")

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
    (out_dir / "metadata.json").write_text(
        json.dumps(build_metadata(book), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "nodes.json").write_text(
        json.dumps(build_nodes(stage_names), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    return StoryReport(out_dir=out_dir, stages=tuple(stage_names), title_source=title_source)
