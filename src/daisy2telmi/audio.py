"""ffmpeg wrappers that cut, join and re-encode clips to the Telmi audio spec."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .extractor import AudioSegment

log = logging.getLogger(__name__)

SAMPLE_RATE = 44100
CHANNELS = 1
BITRATE = "128k"
SPEC = f"{SAMPLE_RATE} Hz, {CHANNELS} channel, CBR {BITRATE}"


class AudioError(RuntimeError):
    """Raised when ffmpeg is missing or a render fails."""


def bundled_executable(name: str) -> Path | None:
    """A helper binary shipped inside a PyInstaller bundle, if the build included one."""
    if not getattr(sys, "frozen", False):
        return None
    exe = f"{name}.exe" if os.name == "nt" else name
    candidates = [Path(sys._MEIPASS) / exe] if hasattr(sys, "_MEIPASS") else []
    candidates.append(Path(sys.executable).parent / exe)
    return next((c for c in candidates if c.is_file()), None)


def bundled_ffmpeg() -> Path | None:
    """An ffmpeg shipped inside a PyInstaller bundle, if the build included one."""
    return bundled_executable("ffmpeg")


def ffmpeg_executable() -> str | None:
    bundled = bundled_ffmpeg()
    return str(bundled) if bundled else shutil.which("ffmpeg")


def require_ffmpeg() -> str:
    exe = ffmpeg_executable()
    if exe is None:
        raise AudioError(
            "ffmpeg is required but was not found on PATH. "
            "Install it (Windows: `winget install Gyan.FFmpeg`, macOS: `brew install ffmpeg`)."
        )
    return exe


def _run(args: list[str], description: str) -> None:
    log.debug("running: %s", " ".join(args))
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit code {result.returncode}"
        raise AudioError(f"{description}: {tail}")


_DURATION = re.compile(r"Duration:\s*(\d+):(\d{2}):(\d{2})\.(\d+)")
_AUDIO_STREAM = re.compile(r"Stream #\d+:\d+[^:]*: Audio: (\w+)[^,]*, (\d+) Hz, ([a-z0-9()]+)")

# A DAISY mark stops where the mark maker heard the clip end, while the container
# length counts the encoder delay and the padding frame, so the two differ by frames.
WHOLE_CLIP_TOLERANCE = 0.25

_headers: dict[Path, tuple[float | None, tuple[str, int, str] | None]] = {}


def _header(src: str | Path) -> tuple[float | None, tuple[str, int, str] | None]:
    """`(seconds, (codec, sample rate, channels))` from ffmpeg's container header.

    ffmpeg is asked for no output file, so it exits non-zero once it has printed
    the header: the header is the whole point, and decoding the file is not.
    """
    path = Path(src)
    if path not in _headers:
        result = subprocess.run(
            [require_ffmpeg(), "-hide_banner", "-i", str(path)], capture_output=True, text=True
        )
        seconds = None
        found = _DURATION.search(result.stderr)
        if found is not None:
            hours, minutes, secs, fraction = found.groups()
            seconds = int(hours) * 3600 + int(minutes) * 60 + int(secs) + float(f"0.{fraction}")
        stream = _AUDIO_STREAM.search(result.stderr)
        _headers[path] = (
            seconds,
            None if stream is None else (stream.group(1), int(stream.group(2)), stream.group(3)),
        )
    return _headers[path]


def duration(src: str | Path) -> float | None:
    """Seconds of audio in `src`."""
    return _header(src)[0]


def probe(src: str | Path) -> tuple[str, int, str] | None:
    """`(codec, sample rate, channels)` of `src`."""
    return _header(src)[1]


def _needs_trim(segment: AudioSegment) -> bool:
    if segment.begin not in (None, 0.0):
        return True
    if segment.end is None:
        return False
    whole = duration(segment.src)
    return whole is None or segment.end < whole - WHOLE_CLIP_TOLERANCE


def _copyable(segments: tuple[AudioSegment, ...] | list[AudioSegment]) -> bool:
    """Whole MP3 clips at one rate can be joined frame by frame, which is lossless.

    The player resamples, so the frames do not even have to match each other, but a
    mix of codecs would not be a valid MP3 any more, so anything else is re-encoded.
    """
    if any(_needs_trim(segment) for segment in segments):
        return False
    specs = {probe(segment.src) for segment in segments}
    return None not in specs and len(specs) == 1 and next(iter(specs))[0] == "mp3"


def _quote(path: Path) -> str:
    """A concat-list path: single quoted, a quote inside it escaped as '\\'''."""
    return "'" + str(path).replace("'", r"'\''") + "'"


def _copy_concat(paths: list[Path], dest: str | Path) -> None:
    exe = require_ffmpeg()
    listing = Path(f"{dest}.concat")
    listing.write_text("".join(f"file {_quote(path)}\n" for path in paths), encoding="utf-8")
    try:
        _run(
            [
                exe,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(listing),
                "-c",
                "copy",
                str(dest),
            ],
            f"could not join {len(paths)} MP3 clip(s)",
        )
    finally:
        listing.unlink(missing_ok=True)


def _trim_filter(segment: AudioSegment) -> str:
    steps: list[str] = []
    if segment.begin is not None or segment.end is not None:
        bounds = []
        if segment.begin is not None:
            bounds.append(f"start={segment.begin:.3f}")
        if segment.end is not None:
            bounds.append(f"end={segment.end:.3f}")
        steps.append("atrim=" + ":".join(bounds))
    steps.append("asetpts=PTS-STARTPTS")
    return ",".join(steps)


def render(
    segments: list[AudioSegment] | tuple[AudioSegment, ...], dest: str | Path, limit: float | None = None
) -> str:
    """Render `segments`, in order, into one MP3 at `dest`.

    `limit` keeps only the first so many seconds, which is what turns a part into
    the sound a card plays; a limited render always goes through the encoder.

    Returns "joined" when the clips went in as they were, "encoded" when they were
    decoded and rewritten to the Telmi spec.
    """
    if not segments:
        raise AudioError(f"refusing to render an empty scene audio for {dest}")
    if limit is None and _copyable(segments):
        log.info("joining %d whole MP3 clip(s) without re-encoding", len(segments))
        _copy_concat([Path(segment.src) for segment in segments], dest)
        return "joined"
    exe = require_ffmpeg()

    args = [exe, "-hide_banner", "-loglevel", "error", "-y"]
    for segment in segments:
        args += ["-i", str(segment.src)]

    labels: list[str] = []
    chains: list[str] = []
    for index, segment in enumerate(segments):
        label = f"seg{index}"
        chains.append(f"[{index}:a]{_trim_filter(segment)}[{label}]")
        labels.append(f"[{label}]")
    graph = ";".join(chains) + f";{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]"

    args += [
        "-filter_complex",
        graph,
        "-map",
        "[out]",
        "-vn",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-c:a",
        "libmp3lame",
        "-b:a",
        BITRATE,
    ]
    if limit is not None:
        args += ["-t", f"{limit:.3f}"]
    args.append(str(dest))
    _run(args, f"could not render {Path(dest).name}")
    return "encoded"


def convert_to_spec(src: str | Path, dest: str | Path) -> None:
    """Re-encode one existing audio file to the Telmi spec."""
    exe = require_ffmpeg()
    args = [
        exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(src),
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-c:a",
        "libmp3lame",
        "-b:a",
        BITRATE,
        str(dest),
    ]
    _run(args, f"could not convert {Path(src).name} to {Path(dest).name}")


def render_silence(dest: str | Path, seconds: float = 1.0) -> None:
    """Write a short silent MP3, used when a pack has no front-matter audio."""
    exe = require_ffmpeg()
    args = [
        exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r={SAMPLE_RATE}:cl=mono",
        "-t",
        f"{seconds:.3f}",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-c:a",
        "libmp3lame",
        "-b:a",
        BITRATE,
        str(dest),
    ]
    _run(args, f"could not render {Path(dest).name}")
