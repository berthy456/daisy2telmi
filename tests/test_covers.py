"""The cover a pack does not carry: which number to ask with, and what answers."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from daisy2telmi import covers
from daisy2telmi.extractor import AudioSegment, Book, Chapter

# Values from the Rachel pack: dc:identifier is the DAISY edition's own number,
# dc:source is the print book's ISBN.
DAISY_ID = "FR-ADV-1310715633"
PRINT_ISBN = "979-10-363-6487-7"


def book(**kwargs) -> Book:
    defaults = {
        "title": "Wesh la fée",
        "chapters": (Chapter("Un", (AudioSegment(Path("a.mp3")),)),),
        "identifier": DAISY_ID,
        "source": PRINT_ISBN,
    }
    return Book(**{**defaults, **kwargs})


class Answers:
    """Stand in for the network: record what was asked, reply with what a test wants."""

    def __init__(self, replies: dict[str, bytes] | None = None, fail: bool = False) -> None:
        self.replies = replies or {}
        self.fail = fail
        self.asked: list[str] = []

    def __call__(self, url: str) -> bytes:
        self.asked.append(url)
        if self.fail:
            raise covers.CoverError(f"could not reach {url}")
        for part, body in self.replies.items():
            if part in url:
                return body
        raise AssertionError(f"unexpected request: {url}")


@pytest.fixture()
def offline(monkeypatch) -> Answers:
    answers = Answers()
    monkeypatch.setattr(covers, "_get", answers)
    return answers


def test_the_print_books_isbn_is_the_one_in_dc_source() -> None:
    assert covers.isbn_of(book()) == "9791036364877"


def test_a_daisy_identifier_is_not_taken_for_an_isbn() -> None:
    assert covers.isbn_of(book(source=None)) is None


def test_an_isbn_10_keeps_its_check_letter() -> None:
    assert covers.isbn_of(book(source="0-140-44918-0", identifier=None)) == "0140449180"
    assert covers.isbn_of(book(source="081269018x", identifier=None)) == "081269018X"


def test_an_isbn_points_straight_at_the_cover(offline: Answers) -> None:
    assert covers.cover_url(book()) == "https://covers.openlibrary.org/b/isbn/9791036364877-L.jpg"
    assert offline.asked == [], "an ISBN needs no search"


def test_without_an_isbn_the_title_and_author_are_asked(offline: Answers) -> None:
    offline.replies = {"search.json": json.dumps({"docs": [{"cover_i": 12123878}]}).encode()}
    url = covers.cover_url(book(source=None, author="Rachel Corenblit"))
    query = parse_qs(urlparse(offline.asked[0]).query)
    assert url == "https://covers.openlibrary.org/b/id/12123878-L.jpg"
    assert query["title"] == ["Wesh la fée"]
    assert query["author"] == ["Rachel Corenblit"]


def test_a_work_with_no_cover_is_no_suggestion(offline: Answers) -> None:
    offline.replies = {"search.json": json.dumps({"docs": [{"title": "Wesh la fée"}]}).encode()}
    assert covers.cover_url(book(source=None)) is None


def test_a_book_with_neither_isbn_nor_title_asks_nothing(offline: Answers) -> None:
    assert covers.cover_url(book(source=None, identifier=None, title="")) is None
    assert offline.asked == []


def test_the_one_pixel_answer_is_no_cover(offline: Answers) -> None:
    # Open Library's "we have nothing" reply: a 1x1 GIF.
    offline.replies = {"-L.jpg": b"GIF89a" + b"\0" * 37}
    assert covers.fetch("https://covers.openlibrary.org/b/isbn/1-L.jpg") is None


def test_a_found_cover_lands_in_the_file_the_converter_reads(offline: Answers, tmp_path: Path) -> None:
    offline.replies = {"-L.jpg": b"\xff\xd8\xff" + b"x" * 4000}
    dest = tmp_path / "cover.jpg"
    assert covers.find(book(), dest) == dest
    assert dest.read_bytes().startswith(b"\xff\xd8\xff")


def test_nothing_is_written_when_the_service_has_no_cover(offline: Answers, tmp_path: Path) -> None:
    offline.replies = {"-L.jpg": b"GIF89a" + b"\0" * 37}
    dest = tmp_path / "cover.jpg"
    assert covers.find(book(), dest) is None
    assert not dest.exists()


def test_an_unreachable_service_leaves_nothing_behind(offline: Answers, tmp_path: Path) -> None:
    offline.fail = True
    dest = tmp_path / "cover.jpg"
    assert covers.find(book(), dest) is None
    assert not dest.exists()
