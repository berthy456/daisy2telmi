"""Looking at chapters before converting them: the listing, the selection, the drop."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from daisy2telmi import audio, chapters
from daisy2telmi.extractor import AudioSegment, Book, Chapter

LENGTHS = {"a.mp3": 30.0, "b.mp3": 12.5, "c.mp3": 7.197}


def book() -> Book:
    def chapter(title: str, *names: str) -> Chapter:
        return Chapter(title, tuple(AudioSegment(Path(n)) for n in names))

    return Book(
        title="Test book",
        chapters=(chapter("One", "a.mp3", "b.mp3"), chapter("Two", "b.mp3"), chapter("Three", "c.mp3")),
        front_matter=(AudioSegment(Path("c.mp3")),),
        identifier="urn:test",
    )


@pytest.fixture()
def measured(monkeypatch) -> None:
    monkeypatch.setattr(audio, "duration", lambda src: LENGTHS.get(str(src)))


def test_the_listing_adds_up_the_clips_of_a_chapter(measured) -> None:
    rows = chapters.describe(book())
    assert [(r.number, r.title, r.clips) for r in rows] == [(1, "One", 2), (2, "Two", 1), (3, "Three", 1)]
    assert rows[0].seconds == pytest.approx(42.5)
    assert chapters.format_seconds(rows[0].seconds) == "0:42"


def test_a_trimmed_clip_counts_only_its_kept_part(measured) -> None:
    trimmed = Book(
        title="Trimmed",
        chapters=(Chapter("One", (AudioSegment(Path("a.mp3"), begin=5.0, end=20.0),)),),
    )
    assert chapters.describe(trimmed)[0].seconds == pytest.approx(15.0)


def test_an_unreadable_length_stays_a_question_mark(measured) -> None:
    rows = chapters.describe(Book(title="?", chapters=(Chapter("One", (AudioSegment(Path("zz.mp3")),)),)))
    assert rows[0].seconds is None
    assert chapters.format_seconds(None) == "?"
    assert chapters.describe(book(), with_durations=False)[0].seconds is None


def test_a_selection_reads_numbers_and_ranges() -> None:
    assert chapters.parse_selection("2") == [2]
    assert chapters.parse_selection("2,4-6") == [2, 4, 5, 6]
    assert chapters.parse_selection(" 3 ; 1-2 ") == [1, 2, 3]
    assert chapters.parse_selection("5 5") == [5]


@pytest.mark.parametrize("spec", ["", "  ", "one", "4-2", "2-", "-2", "2,,3x"])
def test_a_selection_that_is_not_a_list_of_numbers_is_refused(spec: str) -> None:
    with pytest.raises(chapters.ChapterError):
        chapters.parse_selection(spec)


def test_dropping_renumbers_the_rest(measured) -> None:
    kept = chapters.drop_chapters(book(), chapters.parse_selection("2"))
    assert [c.title for c in kept.chapters] == ["One", "Three"]
    assert kept.front_matter == book().front_matter
    assert kept.title == "Test book"


def test_a_number_outside_the_book_is_refused(measured) -> None:
    with pytest.raises(chapters.ChapterError, match="has 3 chapter"):
        chapters.drop_chapters(book(), [3, 4])


def test_dropping_every_chapter_is_refused(measured) -> None:
    with pytest.raises(chapters.ChapterError, match="leaves nothing"):
        chapters.drop_chapters(book(), [1, 2, 3])


def test_preview_files_sort_in_chapter_order() -> None:
    rows = chapters.describe(book(), with_durations=False)
    assert [chapters.preview_name(r) for r in rows] == ["01 One.mp3", "02 Two.mp3", "03 Three.mp3"]
    odd = chapters.ChapterInfo(9, "Chapitre l'épée <x>", None, 1)
    assert chapters.preview_name(odd) == "09 Chapitre lépée x.mp3"


def test_rendering_a_preview_writes_one_file_per_chapter(tmp_path: Path, monkeypatch) -> None:
    written: list[Path] = []
    monkeypatch.setattr(audio, "render", lambda segments, dest: written.append(Path(dest)))
    rows = chapters.describe(book(), with_durations=False)
    paths = [
        chapters.render_preview(row, chapter, tmp_path / "listen")
        for row, chapter in zip(rows, book().chapters)
    ]
    assert [p.name for p in paths] == ["01 One.mp3", "02 Two.mp3", "03 Three.mp3"]
    assert all(p.parent == tmp_path / "listen" for p in paths)
    assert len(written) == 3


def test_opening_a_preview_hands_the_file_to_the_desktop(monkeypatch) -> None:
    started: list[list[str]] = []
    monkeypatch.setattr(chapters.sys, "platform", "darwin")
    monkeypatch.setattr(subprocess, "Popen", lambda args: started.append(list(args)))
    chapters.open_preview(Path("/tmp/01 One.mp3"))
    assert started == [["open", "/tmp/01 One.mp3"]]

    started.clear()
    monkeypatch.setattr(chapters.sys, "platform", "linux")
    chapters.open_preview(Path("/tmp/01 One.mp3"))
    assert started == [["xdg-open", "/tmp/01 One.mp3"]]
