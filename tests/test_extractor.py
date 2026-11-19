"""Extractor tests against a synthetic pack that mirrors the gon-ruby-mp3 layout."""

from __future__ import annotations

from pathlib import Path

import pytest

from daisy2telmi.detector import DaisyPackError, detect
from daisy2telmi.extractor import _npt, extract

NCC = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <meta name="dc:title" content="Sample"/>
    <meta name="dc:creator" content="Author"/>
    <meta name="dc:language" content="fr"/>
    <meta name="ncc:narrator" content="Reader"/>
  </head>
  <body>
    <h1 class="title" id="t"><a href="a.smil#t">Sample</a></h1>
    <h1 id="c1"><a href="b.smil#c1">Un</a></h1>
    <span class="page-normal" id="p"><a href="b.smil#pg">1</a></span>
    <h2 id="c11"><a href="c.smil#c11">1-1</a></h2>
    <h1 id="c2"><a href="d.smil#c2">Deux</a></h1>
    <h2 id="c21"><a href="e.smil#c21">2-1</a></h2>
  </body>
</html>
"""


def smil(*clips: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<smil><body><seq>\n'
        + "\n".join(f"<par><audio {clip}/></par>" for clip in clips)
        + "\n</seq></body></smil>\n"
    )


@pytest.fixture()
def book(tmp_path: Path):
    root = tmp_path / "pack"
    root.mkdir()
    (root / "ncc.html").write_text(NCC, encoding="utf-8")
    # Two back-to-back clips of one file: they should collapse into a single range.
    (root / "a.smil").write_text(smil('src="front.mp3"'), encoding="utf-8")
    (root / "b.smil").write_text(
        smil('src="one.mp3" clip-begin="npt=0.000s" clip-end="npt=10.000s"',
             'src="one.mp3" clip-begin="npt=10.000s" clip-end="npt=20.000s"'),
        encoding="utf-8",
    )
    (root / "c.smil").write_text(smil('src="sub.mp3"'), encoding="utf-8")
    (root / "d.smil").write_text(smil('src="two.mp3"'), encoding="utf-8")
    (root / "e.smil").write_text(smil('src="gone.mp3"'), encoding="utf-8")
    for name in ("front.mp3", "one.mp3", "sub.mp3", "two.mp3"):
        (root / name).write_bytes(b"\xff\xfb")
    pack = detect(tmp_path)
    assert pack is not None
    return extract(pack)


def test_metadata_comes_from_the_ncc(book) -> None:
    assert (book.title, book.author, book.language, book.narrator) == ("Sample", "Author", "fr", "Reader")


def test_top_level_headings_open_chapters(book) -> None:
    assert [c.title for c in book.chapters] == ["Un", "Deux"]


def test_sub_headings_are_folded_into_their_chapter(book) -> None:
    assert [s.src.name for s in book.chapters[0].segments] == ["one.mp3", "sub.mp3"]


def test_back_to_back_clips_of_one_file_merge_into_one_range(book) -> None:
    segment = book.chapters[0].segments[0]
    assert (segment.begin, segment.end) == (0.0, 20.0)


def test_front_matter_is_kept_apart_from_the_chapters(book) -> None:
    assert [s.src.name for s in book.front_matter] == ["front.mp3"]


def test_page_anchors_are_not_treated_as_chapters(book) -> None:
    assert len(book.chapters) == 2


def test_missing_audio_is_dropped_without_failing_the_pack(book) -> None:
    assert [s.src.name for s in book.chapters[1].segments] == ["two.mp3"]


def test_a_pack_whose_top_level_is_h2_splits_on_h2(tmp_path: Path) -> None:
    """Some producers start their outline at h2; the shallowest level opens chapters."""
    root = tmp_path / "pack"
    root.mkdir()
    (root / "ncc.html").write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><head><title>T</title></head><body>
  <h1 class="title" id="t"><a href="a.smil#t">Book</a></h1>
  <h2 id="c1"><a href="b.smil#c1">Un</a></h2>
  <h3 id="c11"><a href="c.smil#c11">1-1</a></h3>
  <h2 id="c2"><a href="d.smil#c2">Deux</a></h2>
</body></html>
""",
        encoding="utf-8",
    )
    for name in ("a", "b", "c", "d"):
        (root / f"{name}.smil").write_text(smil(f'src="{name}.mp3"'), encoding="utf-8")
        (root / f"{name}.mp3").write_bytes(b"\xff\xfb")
    pack = detect(tmp_path)
    assert pack is not None
    book = extract(pack)
    assert [c.title for c in book.chapters] == ["Un", "Deux"]
    assert [s.src.name for s in book.chapters[0].segments] == ["b.mp3", "c.mp3"]
    assert [s.src.name for s in book.chapters[1].segments] == ["d.mp3"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("npt=0.000s", 0.0),
        ("npt=12.5", 12.5),
        ("npt=0:01:30.5", 90.5),
        ("npt=1:00:00", 3600.0),
        ("npt=indefinite", None),
        (None, None),
        ("npt=", None),
    ],
)
def test_npt_parsing(raw, expected) -> None:
    assert _npt(raw) == expected


SYNCED_NCC = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><meta name="dc:title" content="Sample"/></head>
  <body>
    <h1 id="c1"><a href="b.smil#c1">Un</a></h1>
    <h2 id="c11"><a href="c.smil#c11">1-1</a></h2>
    <h1 id="c2"><a href="d.smil#c2">Deux</a></h1>
  </body>
</html>
"""

LYRICS = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body>
  <p id="s1">Le loup sortit de la foret.</p>
  <p id="s2">Il cherchait de quoi manger.</p>
  <p id="s3">Un agneau buvait a la riviere.</p>
</body></html>
"""


def synced(*pairs: tuple[str, str, str, str]) -> str:
    """SMIL whose every par pairs one clip with the line read over it."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<smil><body><seq>\n'
        + "\n".join(
            f'<par><text src="text.html#{word}"/><audio src="{audio}"'
            f' clip-begin="npt={begin}s" clip-end="npt={end}s"/></par>'
            for word, audio, begin, end in pairs
        )
        + "\n</seq></body></smil>\n"
    )


@pytest.fixture()
def marked(tmp_path: Path):
    """A pack that synced its text: the source of all three cut levels."""
    root = tmp_path / "pack"
    root.mkdir()
    (root / "ncc.html").write_text(SYNCED_NCC, encoding="utf-8")
    (root / "text.html").write_text(LYRICS, encoding="utf-8")
    (root / "b.smil").write_text(
        synced(("s1", "one.mp3", "0", "10"), ("s2", "one.mp3", "10", "20")), encoding="utf-8"
    )
    (root / "c.smil").write_text(synced(("s3", "sub.mp3", "0", "5")), encoding="utf-8")
    (root / "d.smil").write_text(synced(("s1", "two.mp3", "0", "8")), encoding="utf-8")
    for name in ("one.mp3", "sub.mp3", "two.mp3"):
        (root / name).write_bytes(b"\xff\xfb")
    pack = detect(tmp_path)
    assert pack is not None
    return pack


def test_the_chapter_card_shows_the_first_line_read_over_it(marked) -> None:
    book = extract(marked, "chapter")
    assert [c.text for c in book.chapters] == [
        "Le loup sortit de la foret.",
        "Le loup sortit de la foret.",
    ]


def test_the_paragraph_level_cuts_on_every_heading_the_pack_marks(marked) -> None:
    book = extract(marked, "paragraph")
    assert [c.title for c in book.chapters] == ["Un", "1-1", "Deux"]
    assert [s.src.name for s in book.chapters[0].segments] == ["one.mp3"]
    assert book.chapters[1].text == "Un agneau buvait a la riviere."


def test_the_sentence_level_gives_one_part_per_synced_clip(marked) -> None:
    book = extract(marked, "sentence")
    assert [(c.title, c.text) for c in book.chapters] == [
        ("Part 1", "Le loup sortit de la foret."),
        ("Part 2", "Il cherchait de quoi manger."),
        ("Part 3", "Un agneau buvait a la riviere."),
        ("Part 4", "Le loup sortit de la foret."),
    ]
    assert [(s.begin, s.end) for s in book.chapters[1].segments] == [(10.0, 20.0)]


def test_an_unknown_cut_level_is_refused(marked) -> None:
    with pytest.raises(DaisyPackError, match="unknown cut level"):
        extract(marked, "verse")
