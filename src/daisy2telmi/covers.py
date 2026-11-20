"""The cover a DAISY audio pack does not carry.

A 2.02 pack has no image, but its metadata names the print book it was read
from: `dc:source` holds that book's ISBN. Open Library answers for it with no
key and with `Access-Control-Allow-Origin: *`, so the web page can ask the same
question the app asks. isbndb.com answers it too, but only for a paid key.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .extractor import Book

log = logging.getLogger("daisy2telmi")

# The app and the web page ask the same service; saying who asks is what keeps
# the request welcome.
USER_AGENT = "daisy2telmi (+https://github.com/berthy456/daisy2telmi)"
TIMEOUT = 12.0
# Open Library answers a cover it does not have with a 1x1 GIF of 43 bytes.
PLACEHOLDER_BYTES = 200


class CoverError(Exception):
    """The lookup could not be made, as opposed to made and answered with nothing."""


def isbn_of(book: Book) -> str | None:
    """The ISBN of the print book the pack was read from.

    DAISY puts it in `dc:source`. `dc:identifier` is the DAISY edition's own
    number (`FR-ADV-1310715633`), which no cover service knows, so it is only
    taken when it happens to be an ISBN.
    """
    for value in (book.source, book.identifier):
        # Digits, spaces and hyphens, and an X only as the last character: a DAISY
        # id such as `FR-ADV-1310715633` has letters in the middle and is not one.
        text = (value or "").strip().upper().removeprefix("URN:ISBN:")
        if not re.fullmatch(r"[0-9][0-9 -]*[0-9X]", text):
            continue
        digits = text.replace(" ", "").replace("-", "")
        if len(digits) == 13 and digits.isdigit():
            return digits
        if len(digits) == 10 and digits[:9].isdigit():
            return digits
    return None


def cover_url(book: Book) -> str | None:
    """Where Open Library keeps this book's cover, or None when there is nothing to ask."""
    isbn = isbn_of(book)
    if isbn:
        return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"
    if book.title:
        return _search(book.title, book.author)
    return None


def _search(title: str, author: str | None) -> str | None:
    """No ISBN in the pack: ask by title and author, and take the first work with a cover."""
    params = {"title": title, "limit": "5", "fields": "cover_i"}
    if author:
        params["author"] = author
    body = _get(f"https://openlibrary.org/search.json?{urllib.parse.urlencode(params)}")
    try:
        docs = json.loads(body)["docs"]
    except (ValueError, KeyError, TypeError) as exc:
        raise CoverError(f"Open Library answered an unreadable search: {exc}") from exc
    for doc in docs:
        cover = doc.get("cover_i")
        if cover:
            return f"https://covers.openlibrary.org/b/id/{int(cover)}-L.jpg"
    return None


def fetch(url: str) -> bytes:
    """The picture at `url`, or None when the service has none for it."""
    body = _get(url)
    return body if len(body) > PLACEHOLDER_BYTES else None


def find(book: Book, dest: Path) -> Path | None:
    """Look the cover up and put it in `dest`, or leave nothing behind.

    The answer is written rather than kept in memory because the rest of the
    converter takes a cover as a file, like the one a user picks.
    """
    url = cover_url(book)
    if url is None:
        return None
    log.info("looking for a cover at %s", url)
    try:
        body = fetch(url)
    except CoverError as exc:
        log.warning("%s", exc)
        return None
    if body is None:
        log.info("Open Library has no cover for this book")
        return None
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return dest


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise CoverError(f"could not reach {url}: {exc}") from exc
