"""ffmpeg wrappers that cut, join and re-encode clips to the Telmi audio spec."""

from __future__ import annotations

import logging
import os
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


def bundled_ffmpeg() -> Path | None:
    """An ffmpeg shipped inside a PyInstaller bundle, if the build included one."""
    if not getattr(sys, "frozen", False):
        return None
    name = "ffmpeg.exe" if os.name == "nt" else "ffmpeg"
    candidates = [Path(sys._MEIPASS) / name] if hasattr(sys, "_MEIPASS") else []
    candidates.append(Path(sys.executable).parent / name)
    return next((c for c in candidates if c.is_file()), None)


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


def render(segments: list[AudioSegment] | tuple[AudioSegment, ...], dest: str | Path) -> None:
    """Render `segments`, in order, into one MP3 at `dest` matching the Telmi spec."""
    if not segments:
        raise AudioError(f"refusing to render an empty scene audio for {dest}")
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
        str(dest),
    ]
    _run(args, f"could not render {Path(dest).name}")


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
