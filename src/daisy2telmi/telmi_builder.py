"""Write the Telmi story folder: metadata.json, nodes.json, notes.json, title assets, audios/, images/."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from . import audio, images, tts
from .extractor import AudioSegment, Book, Chapter
from .i18n import language

log = logging.getLogger(__name__)

CARD_SNIPPET_SECONDS = 3.0
# A book cut to the sentence level has hundreds of parts; Telmi-Sync shows this
# list, so it stops short rather than filling the story's description.
LISTED_PARTS = 30

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

class StoryError(RuntimeError):
    """Raised when a story cannot be produced."""


@dataclass(frozen=True)
class StoryReport:
    out_dir: Path
    stages: tuple[str, ...]
    title_source: str
    cards: int = 0
    audio_mode: str = "encoded"


@dataclass(frozen=True)
class Announce:
    """What each chapter card says, and whether the story advances by itself.

    `prompt` is the default because the player stops at the end of a chapter:
    the card has to say which chapter is next and that OK starts it.
    """

    mode: str = "prompt"
    language: str = "en"
    autoplay: bool = False
    engine: str = tts.AUTO
    voice: str | None = None
    command: str | None = None
    python: str | None = None
    clip: str | None = None
    device: str = tts.AUTO

    def phrase(self, number: int) -> str | None:
        if self.mode == "off":
            return None
        lang = language(self.language)
        chapter = lang.chapter.format(n=number)
        return f"{chapter} {lang.next_prompt}" if self.mode == "prompt" else chapter


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
        "image": images.COVER_IMAGE,
        "category": "",
        "version": 0,
        "age": 0,
    }
    shown = book.chapters[:LISTED_PARTS]
    details = [f"{chapter.title} ({index + 1}/{len(book.chapters)})" for index, chapter in enumerate(shown)]
    if len(book.chapters) > len(shown):
        details.append(f"... {len(book.chapters) - len(shown)} more")
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


def build_nodes(
    chapter_names: Sequence[str],
    card_audio: Sequence[str | None] | None = None,
    card_autoplay: bool = False,
) -> dict:
    """Chapter-menu `nodes.json`, mirroring Telmi-Sync's own audio-list generator.

    `m<k>` is a menu card naming chapter k, `s<k>` the chapter audio.
    `ok` on the last chapter is null: the published packs use null, not a
    wrap-around, to end a story.

    A card plays its `audio` as soon as it is drawn, whether or not autoplay is
    on (`readStage` calls `audio_play` for any defined audio); autoplay only
    decides whether the player waits for OK afterwards.
    """
    if not chapter_names:
        raise StoryError("no chapters to build a story from")

    if card_audio is None:
        card_audio = [None] * len(chapter_names)

    stages: dict[str, dict] = {}
    actions: dict[str, list[dict]] = {"m": [{"stage": f"m{k}"} for k in range(len(chapter_names))]}

    for k in range(len(chapter_names)):
        stages[f"m{k}"] = {
            "image": f"m{k}.png",
            "audio": card_audio[k],
            "ok": {"action": f"s{k}", "index": 0},
            "home": None,
            "control": {"ok": True, "home": True, "autoplay": card_autoplay},
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


def build_card_audio(
    count: int, announce: Announce, audios: Path
) -> tuple[list[str | None], bool]:
    """Speak one announcement per card. A failure silences them all: the same
    engine would fail again, and a silent card is still a valid story."""
    phrases = {k: announce.phrase(k + 1) for k in range(count)}
    spoken = [k for k, phrase in phrases.items() if phrase is not None]
    if not spoken:
        return [None] * count, 0
    try:
        tts.synthesize_all(
            [phrases[k] for k in spoken],
            announce.language,
            [audios / f"c{k}.mp3" for k in spoken],
            engine=announce.engine,
            voice=announce.voice,
            command=announce.command,
            python=announce.python,
            clip=announce.clip,
            device=announce.device,
        )
    except (tts.TtsError, audio.AudioError) as exc:
        log.warning("chapter cards stay silent: %s", exc)
        return [None] * count, 0
    cards: list[str | None] = [None] * count
    for k in spoken:
        cards[k] = f"c{k}.mp3"
    return cards, len(spoken)


def _span(segments: Sequence[AudioSegment]) -> float | None:
    """Seconds the segments cover, or None when the pack left a range open."""
    total = 0.0
    for segment in segments:
        if segment.begin is None or segment.end is None:
            return None
        total += segment.end - segment.begin
    return total


def build_snippets(chapters: Sequence[Chapter], audios: Path) -> list[str | None]:
    """The first seconds of each part, so a card can be told apart by ear.

    A book cut to the sentence level has hundreds of parts, and no word in any
    language would say which one a card is; its own opening sound does. A part
    shorter than the clip gets no second copy: its card plays the part.
    """
    cards: list[str | None] = []
    for k, chapter in enumerate(chapters):
        span = _span(chapter.segments)
        if span is not None and span <= CARD_SNIPPET_SECONDS:
            cards.append(f"s{k}.mp3")
            continue
        name = f"c{k}.mp3"
        try:
            audio.render(chapter.segments, audios / name, limit=CARD_SNIPPET_SECONDS)
        except audio.AudioError as exc:
            log.warning("cards stay silent: %s", exc)
            return [None] * len(chapters)
        cards.append(name)
    return cards


def build_story(
    book: Book,
    out_dir: Path,
    announce: Announce | None = None,
    cover: Path | None = None,
    cut: str = "chapter",
    crop: str = "center",
    lunii_dir: Path | None = None,
    player: str = "telmi",
) -> StoryReport:
    """Render every chapter to `audios/` and write the story's JSON files and images.

    `cover` is the user's picture: it becomes the title image, the cover and the
    background of every card, which carries the chapter number and the total.
    `crop` says which band of it survives the three different aspect ratios.
    `player` decides the size every picture is drawn at.

    `lunii_dir` gets the same pictures drawn again for a greyscale Lunii screen:
    a plain player has four grey levels and no colour panel, so its set is drawn
    light-on-dark the other way round and flattened to those four levels.
    """
    if not book.chapters:
        raise StoryError("the pack contains no chapter with audio")

    audios = out_dir / "audios"
    scene = out_dir / "images"
    audios.mkdir(parents=True, exist_ok=True)
    scene.mkdir(parents=True, exist_ok=True)

    count = len(book.chapters)
    chapter_names = [f"s{k}" for k in range(count)]
    modes = set()
    for name, index, chapter in zip(chapter_names, range(count), book.chapters):
        log.info("rendering %s (%d audio clip group(s)) <- %s", name, len(chapter.segments), chapter.title)
        modes.add(audio.render(chapter.segments, audios / f"{name}.mp3"))

    cards = [None] * count
    spoken = 0
    if announce is not None and announce.mode != "off":
        if cut == "chapter":
            log.info("speaking %d chapter card(s) in %s", count, language(announce.language).name)
            cards, spoken = build_card_audio(count, announce, audios)
        else:
            log.info("playing the first %.0f s of each of the %d part(s) on its card", CARD_SNIPPET_SECONDS, count)
            cards = build_snippets(book.chapters, audios)
            spoken = len(cards)

    # The player plays title.mp3 when the story is selected, so the pack's own
    # spoken title belongs there rather than in a second stage inside the story.
    title_path = out_dir / "title.mp3"
    if book.front_matter:
        log.info("rendering title.mp3 from the pack's front matter")
        modes.add(audio.render(book.front_matter, title_path))
        title_source = "front matter"
    else:
        log.info("pack has no front-matter audio; writing 1s of silence as title.mp3")
        audio.render_silence(title_path, 1.0)
        title_source = "generated silence"

    code = announce.language if announce is not None else "en"
    labels = [images.card_label(code, k + 1, count, cut == "chapter") for k in range(count)]
    texts = [chapter.text for chapter in book.chapters]

    def draw(target: Path, style: str) -> None:
        """The title image, the cover and every card, at one player's sizes."""
        scene, cover_size = images.screen(player)
        if cover is not None:
            images.write_cover(cover, target, labels, texts, crop, style, scene, cover_size)
            return
        (target / "images").mkdir(parents=True, exist_ok=True)
        for index, text in enumerate(texts):
            (target / "images" / f"m{index}.png").write_bytes(
                images.card_png(labels[index], text, *scene, style=style)
            )
        (target / images.TITLE_IMAGE).write_bytes(images.placeholder_png(*scene, style=style))
        (target / images.COVER_IMAGE).write_bytes(images.placeholder_png(*cover_size, style=style))

    log.info("drawing %d card(s)%s", count, "" if cover is None else f" from the cover {cover.name}")
    draw(out_dir, "colour")
    if lunii_dir is not None:
        log.info("drawing the same %d card(s) in four greys for the Lunii", count)
        draw(lunii_dir, "bw")

    metadata = build_metadata(book)
    (out_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (out_dir / "nodes.json").write_text(
        json.dumps(
            build_nodes(chapter_names, cards, announce.autoplay if announce else False),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (out_dir / "notes.json").write_text(
        json.dumps(build_notes(book), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    audio_mode = modes.pop() if len(modes) == 1 else "mixed"
    return StoryReport(
        out_dir=out_dir,
        stages=tuple(chapter_names),
        title_source=title_source,
        cards=spoken,
        audio_mode=audio_mode,
    )


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
