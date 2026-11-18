"""Command line entry point: daisy2telmi <daisy-pack> <output-folder>."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__, audio
from .detector import DaisyPackError, open_pack
from .extractor import extract
from .telmi_builder import StoryError, build_story

log = logging.getLogger("daisy2telmi")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="daisy2telmi",
        description="Convert a DAISY 2.02 audio book pack into a Telmi story folder.",
    )
    parser.add_argument("input", type=Path, help="path to a DAISY pack (.zip or already extracted folder)")
    parser.add_argument("output", type=Path, help="folder to write the Telmi story into")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every ffmpeg invocation")
    parser.add_argument("-f", "--force", action="store_true", help="write into the output folder even if it is not empty")
    parser.add_argument("--version", action="version", version=f"daisy2telmi {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    if args.output.exists() and any(args.output.iterdir()) and not args.force:
        log.error("%s is not empty; pass --force to overwrite", args.output)
        return 2

    try:
        audio.require_ffmpeg()
        with open_pack(args.input) as pack:
            log.info("pack root: %s", pack.root)
            book = extract(pack)
            if not book.chapters:
                log.error("no chapter with audio found in %s", args.input)
                return 2
            log.info("found %d chapter(s): %s", len(book.chapters), ", ".join(c.title for c in book.chapters))
            for chapter in book.chapters:
                log.debug("  %s -> %s", chapter.title, [str(s.src.name) for s in chapter.segments])
            args.output.mkdir(parents=True, exist_ok=True)
            report = build_story(book, args.output)
    except (DaisyPackError, StoryError, audio.AudioError) as exc:
        log.error("%s", exc)
        return 1

    log.info("wrote %d scene(s) to %s", len(report.stages), report.out_dir)
    log.info("audio written as %s", audio.SPEC)
    log.info("title.mp3 source: %s", report.title_source)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
