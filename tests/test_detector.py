"""Detector tests against synthetic packs; no network, no ffmpeg."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from daisy2telmi.detector import DaisyPackError, detect, open_pack

NCC = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
  <head>
    <title>Test</title>
    <meta name="dc:title" content="Test Book"/>
    <meta name="dc:format" content="Daisy 2.02"/>
  </head>
  <body>
    <h1 class="title" id="t1"><a href="a.smil#t1">Front</a></h1>
    <h1 id="c1"><a href="b.smil#c1">One</a></h1>
  </body>
</html>
"""

NCX = """<?xml version="1.0" encoding="utf-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2002/ncx/">
  <head><meta name="dc:title" content="Ncx Book"/></head>
  <navMap>
    <navPoint id="n1" playLevel="1"><text>One</text><content src="a.smil#n1"/></navPoint>
  </navMap>
</ncx>
"""

OPF = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2006/01/opf" unique-identifier="uid">
  <metadata><dc:title xmlns:dc="http://purl.org/dc/elements/1.1/">Opf Book</dc:title></metadata>
</package>
"""


def write_pack(root: Path, *, ncc: bool = True, opf: bool = False, ncx: bool = False) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    if ncc:
        (root / "ncc.html").write_text(NCC, encoding="utf-8")
    if opf:
        (root / "package.opf").write_text(OPF, encoding="utf-8")
    if ncx:
        (root / "book.ncx").write_text(NCX, encoding="utf-8")
    return root


def test_folder_with_ncc_is_detected(tmp_path: Path) -> None:
    pack = detect(write_pack(tmp_path / "book", opf=True))
    assert pack is not None
    assert pack.ncc is not None and pack.ncc.name == "ncc.html"
    assert pack.opf is not None and pack.opf.name == "package.opf"


def test_ncc_alone_is_enough_without_an_opf(tmp_path: Path) -> None:
    """The gon-ruby-mp3 fixture ships no package.opf at all."""
    pack = detect(write_pack(tmp_path / "book"))
    assert pack is not None
    assert pack.opf is None


def test_ncx_only_pack_is_detected(tmp_path: Path) -> None:
    pack = detect(write_pack(tmp_path / "book", ncc=False, ncx=True))
    assert pack is not None
    assert pack.toc_file is not None and pack.toc_file.name == "book.ncx"


def test_opf_without_a_toc_is_not_a_pack(tmp_path: Path) -> None:
    assert detect(write_pack(tmp_path / "book", ncc=False, opf=True)) is None


def test_random_folder_is_not_a_pack(tmp_path: Path) -> None:
    (tmp_path / "stuff").mkdir()
    (tmp_path / "stuff" / "readme.txt").write_text("hello", encoding="utf-8")
    assert detect(tmp_path / "stuff") is None


def test_pack_nested_one_level_below_the_search_root(tmp_path: Path) -> None:
    """Archives usually unpack into a single top-level folder."""
    write_pack(tmp_path / "gon-ruby-mp3")
    pack = detect(tmp_path)
    assert pack is not None
    assert pack.root.name == "gon-ruby-mp3"


def test_open_pack_reads_a_zip(tmp_path: Path) -> None:
    source = tmp_path / "book"
    write_pack(source, opf=True)
    archive = tmp_path / "book.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for file in sorted(source.rglob("*")):
            zf.write(file, file.relative_to(source))
    with open_pack(archive) as pack:
        assert pack.ncc is not None and pack.ncc.is_file()
        assert (pack.root / "ncc.html").read_text(encoding="utf-8").startswith("<?xml")


def test_open_pack_rejects_a_traversal_archive(tmp_path: Path) -> None:
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("../ncc.html", NCC)
    with pytest.raises(DaisyPackError, match="escapes"):
        with open_pack(archive):
            pass


def test_open_pack_skips_macos_resource_forks(tmp_path: Path) -> None:
    archive = tmp_path / "book.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("book/ncc.html", NCC)
        zf.writestr("__MACOSX/book/._ncc.html", "junk")
        zf.writestr("book/._ncc.html", "junk")
    with open_pack(archive) as pack:
        assert pack.root is not None
        assert not any(p.name.startswith("._") for p in pack.root.iterdir())


def test_open_pack_rejects_a_missing_path(tmp_path: Path) -> None:
    with pytest.raises(DaisyPackError):
        with open_pack(tmp_path / "nope.zip"):
            pass


def test_open_pack_rejects_a_non_zip_file(tmp_path: Path) -> None:
    (tmp_path / "plain.zip").write_text("not an archive", encoding="utf-8")
    with pytest.raises(DaisyPackError, match="readable"):
        with open_pack(tmp_path / "plain.zip"):
            pass
