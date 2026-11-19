"""Look at a pack's chapters before converting them: list them, listen to one, drop the rest.

A DAISY table of contents says what a chapter is called, not what is in it. The
front matter, an interview or a duplicated ending only become obvious on hearing
them, so the chapter numbers printed here, shown in the window and accepted by
`--drop` are the same everywhere.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Sequence

from . import audio
from .extractor import Book, Chapter

log = logging.getLogger(__name__)


class ChapterError(RuntimeError):
    """Raised when a chapter selection does not name the pack's chapters."""


@dataclass(frozen=True)
class ChapterInfo:
    number: int
    title: str
    seconds: float | None
    clips: int
    text: str = ""


def describe(book: Book, with_durations: bool = True) -> list[ChapterInfo]:
    """One row per chapter. `seconds` is None when ffmpeg cannot read a source file."""
    rows: list[ChapterInfo] = []
    for number, chapter in enumerate(book.chapters, start=1):
        total = chapter_seconds(chapter) if with_durations else None
        rows.append(ChapterInfo(number, chapter.title, total, len(chapter.segments), chapter.text))
    return rows


@dataclass(frozen=True)
class LevelInfo:
    level: str
    parts: int
    each: float | None
    labelled: bool


def chapter_seconds(chapter: Chapter) -> float | None:
    """How long one part plays, or None when ffmpeg cannot read one of its clips."""
    total = 0.0
    for segment in chapter.segments:
        seconds = audio.duration(segment.src)
        if seconds is None:
            return None
        if segment.end is not None:
            seconds = min(seconds, segment.end)
        total += max(0.0, seconds - (segment.begin or 0.0))
    return total


def describe_levels(books: dict[str, Book]) -> list[LevelInfo]:
    """One row per cut level: how many parts it gives, their average length, and
    whether the pack's own synced text can put words on the cards."""
    rows: list[LevelInfo] = []
    for level, book in books.items():
        totals = [chapter_seconds(chapter) for chapter in book.chapters]
        each = None if None in totals else sum(t for t in totals if t) / max(1, len(totals))
        rows.append(
            LevelInfo(level, len(book.chapters), each, any(chapter.text for chapter in book.chapters))
        )
    return rows


def format_seconds(seconds: float | None) -> str:
    """`183.4` -> `3:03`; a length ffmpeg could not read stays a question mark."""
    if seconds is None:
        return "?"
    minutes, rest = divmod(int(seconds), 60)
    return f"{minutes}:{rest:02d}"


def parse_selection(spec: str) -> list[int]:
    """`"2, 4-6"` -> `[2, 4, 5, 6]`. Chapter numbers are 1-based, as printed."""
    numbers: set[int] = set()
    for part in re.split(r"[,\s;]+", spec.strip()):
        if not part:
            continue
        bounds = re.fullmatch(r"(\d+)(?:-(\d+))?", part)
        if bounds is None:
            raise ChapterError(f"not a chapter number or a range: {part}")
        start = int(bounds.group(1))
        end = int(bounds.group(2) or start)
        if end < start:
            raise ChapterError(f"chapter range counts backwards: {part}")
        numbers.update(range(start, end + 1))
    if not numbers:
        raise ChapterError("no chapter number in that selection")
    return sorted(numbers)


def drop_chapters(book: Book, numbers: Sequence[int]) -> Book:
    """A copy of `book` without those 1-based chapter numbers."""
    dropped = set(numbers)
    unknown = sorted(n for n in dropped if not 1 <= n <= len(book.chapters))
    if unknown:
        raise ChapterError(
            f"{book.title} has {len(book.chapters)} chapter(s), so there is no chapter "
            f"{', '.join(str(n) for n in unknown)}"
        )
    kept = tuple(chapter for number, chapter in enumerate(book.chapters, start=1) if number not in dropped)
    if not kept:
        raise ChapterError("dropping those chapters leaves nothing to convert")
    return replace(book, chapters=kept)


def preview_name(info: ChapterInfo) -> str:
    """A file name a music player sorts in chapter order."""
    title = re.sub(r"[^\w\- ]+", "", info.title, flags=re.UNICODE).strip()
    return f"{info.number:02d} {(title or 'chapter')[:40]}.mp3"


def render_preview(info: ChapterInfo, chapter: Chapter, out_dir: Path) -> Path:
    """One chapter's audio on its own, so it can be listened to on its own."""
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / preview_name(info)
    log.info("previewing chapter %d: %s", info.number, chapter.title)
    audio.render(chapter.segments, dest)
    return dest


def _ffplay() -> str | None:
    bundled = audio.bundled_executable("ffplay")
    return str(bundled) if bundled else shutil.which("ffplay")


def open_preview(path: Path) -> None:
    """Hand the rendered chapter to a player the machine already has.

    The desktop's own opener is tried first because it is the player the user
    chose for MP3s; a bare window manager has none, and ffmpeg is a dependency
    already, so it can play the file itself.
    """
    if sys.platform == "win32":
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as exc:
            raise ChapterError(f"could not open {path.name}: {exc}")
        return
    players = [["open" if sys.platform == "darwin" else "xdg-open", str(path)]]
    play = _ffplay()
    if play:
        players.append([play, "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)])
    for argv in players:
        try:
            subprocess.Popen(argv)
            return
        except OSError:
            continue
    raise ChapterError(f"no player on this machine: play {path} yourself")
