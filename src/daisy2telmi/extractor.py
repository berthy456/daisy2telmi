"""Parse a DAISY 2.02 pack into chapters and the audio each chapter covers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import unquote

from lxml import etree

from .detector import DaisyPack, DaisyPackError

log = logging.getLogger(__name__)

_HEADING_LEVELS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_MERGE_EPSILON = 0.005


@dataclass(frozen=True)
class AudioSegment:
    """One audio clip: `src`, optionally trimmed to [begin, end) seconds."""

    src: Path
    begin: float | None = None
    end: float | None = None


@dataclass(frozen=True)
class Chapter:
    """One part of the book at the chosen cut level.

    `text` is what the pack's own synced text says at the start of the part, which
    is what a card can show when the part has no title of its own.
    """

    title: str
    segments: tuple[AudioSegment, ...]
    text: str = ""


@dataclass(frozen=True)
class Book:
    title: str
    chapters: tuple[Chapter, ...]
    front_matter: tuple[AudioSegment, ...] = ()
    author: str | None = None
    language: str | None = None
    publisher: str | None = None
    narrator: str | None = None
    identifier: str | None = None


@dataclass
class _TocEntry:
    level: int
    title: str
    target: str
    is_front_matter: bool = False


@dataclass
class _Draft:
    title: str
    segments: list[AudioSegment] = field(default_factory=list)
    text: str = ""


CUT_LEVELS = ("chapter", "paragraph", "sentence")


_PARSER = etree.XMLParser(
    load_dtd=False,
    dtd_validation=False,
    no_network=True,
    resolve_entities=False,
    recover=True,
)


def _localname(element: etree._Element) -> str:
    """Element tag without its namespace; empty for comments and processing instructions."""
    if not isinstance(element.tag, str):
        return ""
    return element.tag.rpartition("}")[2]


def _parse_xml(path: Path) -> etree._Element | None:
    """Parse XML/XHTML without fetching external DTDs, tolerating minor damage."""
    try:
        return etree.parse(str(path), parser=_PARSER).getroot()
    except (etree.XMLSyntaxError, OSError) as exc:
        log.warning("could not parse %s: %s", path, exc)
        return None


def _ncc_meta(root: etree._Element) -> dict[str, str]:
    """Collect `<meta name= content=>` values from an NCC, lowercased by name."""
    out: dict[str, str] = {}
    for meta in root.iter():
        if _localname(meta) != "meta":
            continue
        name = meta.get("name")
        if name and name.lower() not in out:
            out[name.lower()] = (meta.get("content") or "").strip()
    return out


def _opf_meta(root: etree._Element) -> dict[str, str]:
    """Collect Dublin Core fields from a `package.opf` metadata block."""
    out: dict[str, str] = {}
    for element in root.iter():
        name = _localname(element)
        if name in {"title", "language", "creator", "publisher", "identifier", "description"}:
            text = (element.text or "").strip()
            if text and name not in out:
                out[name] = text
    return out


def _npt(value: str | None) -> float | None:
    """Parse a SMIL NPT time such as `npt=12.5`, `npt=0.000s` or `npt=0:01:30.5`."""
    if not value:
        return None
    text = value.strip()
    if text[:3].lower() == "npt":
        text = text[3:].lstrip("=").strip()
    if not text or text.lower() == "indefinite":
        return None
    parts = text.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2].rstrip("s"))
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1].rstrip("s"))
        return float(text.rstrip("s"))
    except ValueError:
        return None


def _merge(segments: list[AudioSegment]) -> list[AudioSegment]:
    """Join neighbouring clips of the same file that play back to back."""
    merged: list[AudioSegment] = []
    for segment in segments:
        previous = merged[-1] if merged else None
        contiguous = (
            previous is not None
            and previous.src == segment.src
            and previous.end is not None
            and segment.begin is not None
            and abs(previous.end - segment.begin) < _MERGE_EPSILON
        )
        if contiguous:
            merged[-1] = AudioSegment(previous.src, previous.begin, segment.end)
        else:
            merged.append(segment)
    return merged


@dataclass
class _Marks:
    """Parsed SMIL and XHTML, kept once per pack so the three cut levels share one read."""

    segments: dict[Path, tuple[AudioSegment, ...]] = field(default_factory=dict)
    parts: dict[Path, tuple[Chapter, ...]] = field(default_factory=dict)
    text: dict[Path, etree._Element | None] = field(default_factory=dict)


def _smil_segments(smil: Path, marks: _Marks) -> tuple[AudioSegment, ...]:
    """Resolve every `<audio>` referenced by a SMIL file, in playback order."""
    if smil in marks.segments:
        return marks.segments[smil]
    root = _parse_xml(smil)
    if root is None:
        marks.segments[smil] = ()
        return ()
    found: list[AudioSegment] = []
    for element in root.iter():
        if _localname(element) != "audio":
            continue
        src = element.get("src")
        if not src:
            continue
        target = (smil.parent / unquote(src)).resolve()
        if not target.is_file():
            log.warning("%s references a missing audio file: %s", smil.name, src)
            continue
        found.append(AudioSegment(target, _npt(element.get("clip-begin")), _npt(element.get("clip-end"))))
    result = tuple(_merge(found))
    marks.segments[smil] = result
    return result


def _text_at(src: str, base: Path, marks: _Marks) -> str:
    """The pack's own words at a `gonxhtml.html#id` anchor, for a card to show."""
    file_part, _, anchor = unquote(src).partition("#")
    if not file_part:
        return ""
    path = (base / file_part).resolve()
    if path not in marks.text:
        marks.text[path] = _parse_xml(path)
    root = marks.text[path]
    if root is None or not anchor:
        return ""
    found = root.xpath(f'//*[@id="{anchor}"]')
    if not found:
        return ""
    return " ".join("".join(found[0].itertext()).split())


def _smil_parts(smil: Path, marks: _Marks) -> tuple[Chapter, ...]:
    """The SMIL's audio clips, each paired with the synced text read over it.

    A DAISY 2.02 audio book marks every `<par>` it synced, so this is where the
    sentence-level cuts come from; a pack that synced nothing gives one part per
    clip with no text.
    """
    if smil in marks.parts:
        return marks.parts[smil]
    root = _parse_xml(smil)
    found: list[Chapter] = []
    if root is not None:
        for element in root.iter():
            if _localname(element) != "audio":
                continue
            src = element.get("src")
            if not src:
                continue
            target = (smil.parent / unquote(src)).resolve()
            if not target.is_file():
                continue
            par = element.getparent()
            while par is not None and _localname(par) != "par":
                par = par.getparent()
            words = ""
            if par is not None:
                text_el = next((c for c in par.iter() if _localname(c) == "text"), None)
                if text_el is not None:
                    words = _text_at(text_el.get("src") or "", smil.parent, marks)
            found.append(
                Chapter(
                    title="",
                    segments=(
                        AudioSegment(target, _npt(element.get("clip-begin")), _npt(element.get("clip-end"))),
                    ),
                    text=words,
                )
            )
    if not found:
        found = [Chapter(title="", segments=(segment,)) for segment in _smil_segments(smil, marks)]
    marks.parts[smil] = tuple(found)
    return marks.parts[smil]


def _split_target(href: str) -> Path | None:
    """Turn an NCC `href` such as `hotl0002.smil#id` into a SMIL path."""
    file_part = unquote(href.split("#", 1)[0]).strip()
    if not file_part or not file_part.lower().endswith(".smil"):
        return None
    return Path(file_part)


def _ncc_entries(root: etree._Element) -> list[_TocEntry]:
    """Read the NCC outline: h1..h6 are TOC items, `class="title"` is front matter."""
    body = next((el for el in root.iter() if _localname(el) == "body"), None)
    if body is None:
        return []
    entries: list[_TocEntry] = []
    for element in body.iter():
        level = _HEADING_LEVELS.get(_localname(element).lower())
        if level is None:
            continue
        classes = (element.get("class") or "").lower().split()
        anchor = next((child for child in element.iter() if _localname(child) == "a"), None)
        href = (anchor.get("href") if anchor is not None else None) or element.get("href") or ""
        label_source = anchor if anchor is not None else element
        title = "".join(label_source.itertext()).strip()
        entries.append(
            _TocEntry(
                level=level,
                title=title,
                target=href,
                is_front_matter="title" in classes,
            )
        )
    return entries


def _ncx_entries(root: etree._Element, level: int = 1) -> list[_TocEntry]:
    """Read a DAISY 2 XML `.ncx` outline as a fallback for packs without an NCC."""
    entries: list[_TocEntry] = []
    for nav_point in root:
        if _localname(nav_point) != "navpoint":
            continue
        declared = nav_point.get("playLevel") or nav_point.get("level")
        current_level = int(declared) if declared and declared.isdigit() else level
        text = next((c for c in nav_point if _localname(c) == "text"), None)
        content = next((c for c in nav_point if _localname(c) == "content"), None)
        title = (text.get("value") or (text.text or "")).strip() if text is not None else ""
        target = content.get("src", "") if content is not None else ""
        if target:
            entries.append(_TocEntry(level=current_level, title=title, target=target))
        entries.extend(_ncx_entries(nav_point, current_level + 1))
    return entries


def _opening_text(parts: tuple[Chapter, ...]) -> str:
    """The first words spoken in a part, skipping a read-out section number."""
    texts = [part.text for part in parts if part.text]
    return next((t for t in texts if len(t) >= 5), texts[0] if texts else "")


def _group(
    entries: list[_TocEntry], pack_root: Path, marks: _Marks, level: str = "chapter"
) -> tuple[list[_Draft], list[AudioSegment]]:
    """Cut the book at `level`: one part per chapter heading, per TOC entry, or per synced mark."""
    chapters: list[_Draft] = []
    front_matter: list[AudioSegment] = []
    chapter_level = min((e.level for e in entries if not e.is_front_matter), default=1)
    for entry in entries:
        smil = _split_target(entry.target)
        if smil is None:
            continue
        resolved = (pack_root / smil).resolve()
        if not resolved.is_file():
            log.warning("TOC entry %r points at a missing SMIL: %s", entry.title, smil)
            continue
        if entry.is_front_matter:
            front_matter.extend(_smil_segments(resolved, marks))
            continue
        parts = _smil_parts(resolved, marks)
        if level == "sentence":
            chapters.extend(_Draft(title="", segments=list(p.segments), text=p.text) for p in parts)
        elif level == "chapter" and entry.level > chapter_level and chapters:
            chapters[-1].segments.extend(_smil_segments(resolved, marks))
        else:
            chapters.append(
                _Draft(
                    title=entry.title or f"Part {len(chapters) + 1}",
                    segments=list(_smil_segments(resolved, marks)),
                    text=_opening_text(parts),
                )
            )
    return chapters, _merge(front_matter)


def extract(pack: DaisyPack, level: str = "chapter") -> Book:
    """Build the part list for a DAISY 2.02 audio pack, cut at `level`.

    `chapter` follows the top TOC headings, `paragraph` every TOC heading, and
    `sentence` every mark the pack itself synced; a pack with no synced text
    gives the same parts at `sentence` as at `paragraph`, only silent cards.
    """
    if level not in CUT_LEVELS:
        raise DaisyPackError(f"unknown cut level: {level}")
    toc = pack.toc_file
    if toc is None:
        raise DaisyPackError("pack has no table of contents")

    root = _parse_xml(toc)
    if root is None:
        raise DaisyPackError(f"could not parse the table of contents: {toc.name}")

    entries = _ncc_entries(root) if toc is pack.ncc else _ncx_entries(root)
    metadata = _ncc_meta(root)

    if pack.opf is not None:
        opf_root = _parse_xml(pack.opf)
        if opf_root is not None:
            for key, value in _opf_meta(opf_root).items():
                metadata.setdefault(f"dc:{key}", value)

    marks = _Marks()
    drafts, front_matter = _group(entries, pack.root, marks, level)
    chapters = tuple(
        Chapter(
            title=d.title or f"Part {index + 1}",
            segments=tuple(_merge(d.segments)),
            text=d.text,
        )
        for index, d in enumerate(drafts)
        if d.segments
    )

    return Book(
        title=metadata.get("dc:title") or pack.root.name,
        chapters=chapters,
        front_matter=tuple(front_matter),
        author=metadata.get("dc:creator") or None,
        language=metadata.get("dc:language") or None,
        publisher=metadata.get("dc:publisher") or None,
        narrator=metadata.get("ncc:narrator") or None,
        identifier=metadata.get("dc:identifier") or None,
    )
