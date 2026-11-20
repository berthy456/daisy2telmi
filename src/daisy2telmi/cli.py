"""Command line entry point: daisy2telmi <daisy-pack> <output-folder>."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

from . import __version__, audio, chapters, covers, images, merlin, settings, tts
from .chapters import ChapterError
from .detector import DaisyPackError, open_pack
from .extractor import CUT_LEVELS, extract
from .i18n import LANGUAGES
from .lunii import LuniiError, write_studio_zip
from .merlin import MerlinError
from .telmi_builder import (
    ANNOUNCE_MODES,
    Announce,
    StoryError,
    build_story,
    story_dir_name,
    story_uuid,
    write_story_zip,
)

log = logging.getLogger("daisy2telmi")

# The players, and the archive each one imports. Telmi and the Flam have a colour
# screen; a plain Lunii shows four grey levels, so its cards are redrawn. The
# Merlin has no screen and no story graph: it takes a card of flat files.
FORMATS = ("telmi", "lunii", "flam", "merlin")
PLAYER = {
    "telmi": "Telmi Sync",
    "lunii": "the Lunii",
    "flam": "the Flam launcher",
    "merlin": "the Merlin story-teller",
}

# The Merlin writes itself, with no official SDK and no way to try a card on the
# machine that made the format, so it is offered but not promised.
BETA = ("merlin",)


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="daisy2telmi",
        description="Convert a DAISY 2.02 audio book pack into a Telmi story folder.",
    )
    parser.add_argument("input", type=Path, help="path to a DAISY pack (.zip or already extracted folder)")
    parser.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="folder to create the story folder in; the story folder gets Telmi's "
        "`<category>_<age>_<title>_<uuid>` name unless this path already has it",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="log every ffmpeg invocation")
    parser.add_argument("-f", "--force", action="store_true", help="write into the output folder even if it is not empty")
    parser.add_argument(
        "--cover",
        metavar="IMAGE",
        type=Path,
        help="draw every chapter card over this picture instead of the placeholder",
    )
    parser.add_argument(
        "--find-cover",
        action="store_true",
        help="ask Open Library for the cover of the print book the pack names in dc:source, "
        "and draw the cards over that instead of the placeholder",
    )
    parser.add_argument(
        "--cover-crop",
        choices=images.CROP_MODES,
        help="how the cover is cropped to fit the chosen player's screens: the middle "
        "(default), the top, or the bottom",
    )
    parser.add_argument(
        "--cover-zoom",
        type=float,
        default=1.0,
        metavar="FACTOR",
        help=f"enlarge the cover by FACTOR (1 to {images.MAX_ZOOM}) before cropping it, so the "
        "frame shows less of it and can be moved sideways as well",
    )
    look = parser.add_argument_group("before converting")
    look.add_argument("--list", action="store_true", help="print the pack's chapters and stop")
    look.add_argument(
        "--cut",
        choices=CUT_LEVELS,
        help="where to cut the book: at its chapters (default), at every paragraph the pack "
        "marks, or at every sentence it synced",
    )
    look.add_argument(
        "--preview",
        metavar="FOLDER",
        type=Path,
        help="write one MP3 per chapter into FOLDER and stop, so each chapter can be listened to",
    )
    look.add_argument(
        "--drop",
        metavar="CHAPTERS",
        help="leave these chapters out of the story, by the numbers --list prints: '2' or '2,4-6'",
    )

    speech = parser.add_argument_group("chapter card speech")
    speech.add_argument(
        "--announce",
        choices=ANNOUNCE_MODES,
        help="what each chapter card says: nothing, the number, the number and the total, "
        "the part's title (alone or with the number), 'chapter N', or the number and a "
        "prompt to continue",
    )
    speech.add_argument(
        "--language",
        choices=sorted(LANGUAGES),
        help="language of the spoken chapter cards",
    )
    speech.add_argument(
        "--autoplay",
        action="store_true",
        help="advance to the next chapter when the card's audio ends, instead of waiting for OK",
    )
    speech.add_argument(
        "--tts",
        choices=tts.ENGINES,
        help="speech engine for the cards: chatterbox (the default) unless it is missing "
        "from --tts-python, in which case the machine's own voice is used",
    )
    speech.add_argument("--tts-voice", help="voice name for the speech engine")
    speech.add_argument("--tts-clip", help="a few seconds of someone speaking, for --tts chatterbox to copy")
    speech.add_argument(
        "--tts-python",
        help="interpreter --tts chatterbox runs in, for a Python where `pip install chatterbox-tts` was done",
    )
    speech.add_argument(
        "--tts-device",
        choices=tts.DEVICES,
        help="what --tts chatterbox runs on: auto (default) takes the fastest device, "
        "mps the Apple GPU, cuda an Nvidia one; Chatterbox otherwise stays on the CPU",
    )
    speech.add_argument(
        "--tts-command",
        help="command template for --tts command, using {text}, {out} and {lang}; "
        "for example 'my-tts {text} {out}' with any Chatterbox-style model behind it",
    )
    parser.add_argument(
        "--format",
        choices=FORMATS,
        help="which player the story is written for: Telmi (default), a Lunii, whose "
        "cards are redrawn in four grey levels, a Flam, or a Merlin story-teller "
        "(beta), whose card holds flat files and a playlist.bin",
    )
    parser.add_argument(
        "--merlin-merge",
        metavar="PLAYLIST",
        type=Path,
        help="with --format merlin, add the story to this playlist.bin read off the card "
        "instead of writing one holding only the story",
    )
    parser.add_argument(
        "--night-mode",
        action=argparse.BooleanOptionalAction,
        help="tell the Lunii the story can be played with its screen off, which is how "
        "it joins the bedtime playlist (--no-night-mode leaves it out); the Telmi "
        "player keeps night mode as a device setting, so this only reaches --format lunii",
    )
    parser.add_argument("--version", action="version", version=f"daisy2telmi {__version__}")
    args = parser.parse_args(argv)
    if args.output is None and not (args.list or args.preview):
        parser.error("an output folder is required unless --list or --preview is given")
    return args


def announce_options(args: argparse.Namespace) -> Announce:
    """Saved settings, overridden by whatever was passed on the command line."""
    saved = settings.load()
    return Announce(
        mode=args.announce or saved["announce"],
        language=args.language or saved["language"],
        autoplay=bool(args.autoplay or saved["autoplay"]),
        engine=args.tts or saved["tts"],
        voice=args.tts_voice or saved["voice"],
        command=args.tts_command or saved["command"],
        python=args.tts_python or saved["python"],
        clip=args.tts_clip or saved["clip"],
        device=args.tts_device or saved["device"],
    )


def cut_level(args: argparse.Namespace) -> str:
    """Saved cut level, overridden by --cut."""
    return args.cut or settings.load()["cut"]


def cover_crop(args: argparse.Namespace) -> str:
    """Saved crop choice, overridden by --cover-crop."""
    return args.cover_crop or settings.load()["cover_crop"]


def output_format(args: argparse.Namespace) -> str:
    """Saved player choice, overridden by --format."""
    return args.format or settings.load()["format"]


def night_mode(args: argparse.Namespace) -> bool:
    """Saved choice, overridden by --night-mode or --no-night-mode."""
    saved = settings.load()["night_mode"]
    return bool(saved if args.night_mode is None else args.night_mode)


def inspect(
    input_path: Path,
    preview_dir: Path | None = None,
    drop: str | None = None,
    cut: str = "chapter",
) -> int:
    """Print what each cut level gives, then the parts at the chosen one."""
    try:
        with open_pack(input_path) as pack:
            log.info("pack root: %s", pack.root)
            books = {level: extract(pack, level) for level in CUT_LEVELS}
            book = books[cut]
            if not book.chapters:
                log.error("no chapter with audio found in %s", input_path)
                return 2
            log.info("%s: %d part(s) at the %s level", book.title, len(book.chapters), cut)
            for row in chapters.describe_levels(books):
                log.info(
                    " %s %-9s %4d part(s), %s each%s",
                    "*" if row.level == cut else " ",
                    row.level,
                    row.parts,
                    chapters.format_seconds(row.each),
                    "" if row.labelled else "  (no synced text to label the cards)",
                )
            if drop:
                book = chapters.drop_chapters(book, chapters.parse_selection(drop))
            rows = chapters.describe(book)
            for row in rows:
                log.info(
                    "  %2d  %s  %s  %d clip(s)%s",
                    row.number,
                    chapters.format_seconds(row.seconds),
                    row.title,
                    row.clips,
                    f"  {row.text[:36]}" if row.text else "",
                )
            if preview_dir is None:
                log.info("to listen to one: --preview FOLDER")
            else:
                audio.require_ffmpeg()
                for row, chapter in zip(rows, book.chapters):
                    log.info("  %s", chapters.render_preview(row, chapter, preview_dir))
    except ChapterError as exc:
        log.error("%s", exc)
        return 2
    except (DaisyPackError, audio.AudioError) as exc:
        log.error("%s", exc)
        return 1
    return 0


def speech(announce: Announce | None) -> Announce | None:
    """The engine this run's cards get, falling back when Chatterbox is not there.

    Chatterbox is the saved default because a card read by a real voice is what the
    player is for, but it is not inside the app: it is a package the user's own
    Python installs. A machine that does not have it keeps its own voice rather
    than losing the story over a card.
    """
    if announce is None or announce.engine != tts.CHATTERBOX:
        return announce
    if tts.available(tts.CHATTERBOX, announce.python):
        return announce
    log.warning(
        "chatterbox is not installed in %s: the machine's own voice will read the cards "
        "(pip install %s there, or pass --tts auto)",
        announce.python or "your Python",
        tts.CHATTERBOX_PACKAGE,
    )
    return replace(announce, engine=tts.AUTO)


def convert(
    input_path: Path,
    output_dir: Path,
    force: bool = False,
    announce: Announce | None = None,
    cover: Path | None = None,
    drop: str | None = None,
    cut: str = "chapter",
    fmt: str = "telmi",
    crop: str = "center",
    night_mode: bool = True,
    find_cover: bool = False,
    zoom: float = 1.0,
    merge: Path | None = None,
) -> int:
    """Convert one pack. Logs through this module's logger so a GUI can follow along."""
    announce = speech(announce)
    try:
        audio.require_ffmpeg()
        if cover is not None and not cover.is_file():
            log.error("no such cover image: %s", cover)
            return 2
        # The looked-up cover has to outlive the lookup: the cards are drawn below.
        with open_pack(input_path) as pack, tempfile.TemporaryDirectory(prefix="daisy2telmi-cover-") as scratch:
            log.info("pack root: %s", pack.root)
            book = extract(pack, cut)
            if not book.chapters:
                log.error("no chapter with audio found in %s", input_path)
                return 2
            log.info(
                "found %d part(s) at the %s level: %s",
                len(book.chapters),
                cut,
                ", ".join(c.title for c in book.chapters),
            )
            if cover is None and find_cover:
                cover = covers.find(book, Path(scratch) / "cover.jpg")
            if drop:
                book = chapters.drop_chapters(book, chapters.parse_selection(drop))
                log.info("dropped %s: converting %d chapter(s)", drop, len(book.chapters))
            for chapter in book.chapters:
                log.debug("  %s -> %s", chapter.title, [str(s.src.name) for s in chapter.segments])
            name = story_dir_name(book.title, story_uuid(book))
            target = output_dir if output_dir.name == name else output_dir / name
            if target.exists() and any(target.iterdir()) and not force:
                log.error("%s is not empty; pass --force to overwrite", target)
                return 2
            target.mkdir(parents=True, exist_ok=True)
            view = images.crop_view(crop, zoom)
            # The Merlin has no story graph to write: its card is made from the
            # Telmi story, so that one is built at Telmi's sizes first.
            player = "telmi" if fmt == "merlin" else fmt
            if fmt == "lunii":
                # The four greys cannot be recovered from the colour cards: their
                # ground is dark and the Lunii wants the other way round. Draw a
                # second set in a scratch folder and build the archive from those.
                with tempfile.TemporaryDirectory(prefix="daisy2telmi-lunii-") as scratch:
                    grey = Path(scratch)
                    report = build_story(book, target, announce, cover, cut, crop, grey, player=fmt, view=view)
                    archive = write_studio_zip(target, image_dir=grey, night_mode=night_mode)
            else:
                report = build_story(book, target, announce, cover, cut, crop, player=player, view=view)
                if fmt == "merlin":
                    log.warning(
                        "the Merlin export is beta: its card format is undocumented, "
                        "so nothing here has been read back off a real device"
                    )
                    card = target.parent / f"{target.name}_merlin"
                    names = merlin.export(target, card, [c.title for c in book.chapters], merge)
                    archive = shutil.make_archive(str(card), "zip", card)
                    log.info("wrote %d card file(s) and a %s to %s", len(names), merlin.PLAYLIST, card)
                else:
                    archive = write_story_zip(target, target.parent)
    except ChapterError as exc:
        log.error("%s", exc)
        return 2
    except (DaisyPackError, StoryError, images.ImageError, audio.AudioError, MerlinError) as exc:
        log.error("%s", exc)
        return 1
    except LuniiError as exc:
        log.error("the Telmi story is written, but the Lunii one is not: %s", exc)
        return 1

    log.info("wrote %d scene(s) to %s", len(report.stages), report.out_dir)
    log.info("zipped for %s import: %s", PLAYER[fmt], archive)
    if fmt == "lunii":
        log.info(
            "night mode: %s",
            "the Lunii may play this story with its screen off"
            if night_mode
            else "not offered, so the Lunii keeps the story out of its bedtime playlist",
        )
    log.info(
        "audio: %s",
        {
            "joined": "joined as the pack's own MP3s, which the player resamples",
            "mixed": f"some scenes joined, the rest written as {audio.SPEC}",
        }.get(report.audio_mode, f"written as {audio.SPEC}"),
    )
    log.info("title.mp3 source: %s", report.title_source)
    log.info("chapter cards: %d spoken, autoplay %s", report.cards, "on" if announce and announce.autoplay else "off")
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        from .gui import run_gui

        return run_gui()
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )
    if args.list or args.preview:
        return inspect(args.input, args.preview, args.drop, cut_level(args))
    return convert(
        args.input,
        args.output,
        args.force,
        announce_options(args),
        args.cover,
        args.drop,
        cut_level(args),
        output_format(args),
        cover_crop(args),
        night_mode(args),
        args.find_cover,
        args.cover_zoom,
        args.merlin_merge,
    )


if __name__ == "__main__":
    raise SystemExit(main())
