"""Command line entry point: daisy2telmi <daisy-pack> <output-folder>."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__, audio, chapters, images, settings, tts
from .chapters import ChapterError
from .detector import DaisyPackError, open_pack
from .extractor import CUT_LEVELS, extract
from .i18n import LANGUAGES
from .telmi_builder import (
    Announce,
    StoryError,
    build_story,
    story_dir_name,
    story_uuid,
    write_story_zip,
)

log = logging.getLogger("daisy2telmi")


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
        choices=("off", "chapter", "prompt"),
        help="what each chapter card says: nothing, the chapter number, or the number and a prompt to continue",
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
    speech.add_argument("--tts", choices=tts.ENGINES, help="speech engine to use")
    speech.add_argument("--tts-voice", help="voice name for the speech engine")
    speech.add_argument(
        "--tts-command",
        help="command template for --tts command, using {text}, {out} and {lang}; "
        "for example 'my-tts {text} {out}' with any Chatterbox-style model behind it",
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
    )


def cut_level(args: argparse.Namespace) -> str:
    """Saved cut level, overridden by --cut."""
    return args.cut or settings.load()["cut"]


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


def convert(
    input_path: Path,
    output_dir: Path,
    force: bool = False,
    announce: Announce | None = None,
    cover: Path | None = None,
    drop: str | None = None,
    cut: str = "chapter",
) -> int:
    """Convert one pack. Logs through this module's logger so a GUI can follow along."""
    try:
        audio.require_ffmpeg()
        if cover is not None and not cover.is_file():
            log.error("no such cover image: %s", cover)
            return 2
        with open_pack(input_path) as pack:
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
            report = build_story(book, target, announce, cover, cut)
            zip_path = write_story_zip(target, target.parent)
    except ChapterError as exc:
        log.error("%s", exc)
        return 2
    except (DaisyPackError, StoryError, images.ImageError, audio.AudioError) as exc:
        log.error("%s", exc)
        return 1

    log.info("wrote %d scene(s) to %s", len(report.stages), report.out_dir)
    log.info("zipped for Telmi Sync import: %s", zip_path)
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
        args.input, args.output, args.force, announce_options(args), args.cover, args.drop, cut_level(args)
    )


if __name__ == "__main__":
    raise SystemExit(main())
