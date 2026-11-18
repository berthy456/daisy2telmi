"""Build daisy2telmi.exe with PyInstaller.

ffmpeg found on the build machine is bundled into the exe, so the end user does
not have to install it. PyInstaller cannot cross-compile, so this must be run on
Windows:
    py -3.11 -m venv .venv
    .venv\\Scripts\\activate
    pip install -e .[dev]
    python build_windows.py
The result is dist\\daisy2telmi.exe.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    if sys.platform != "win32":
        print(
            f"error: PyInstaller must be run on Windows, this machine reports {sys.platform!r}.\n"
            "On Windows, run: python build_windows.py",
            file=sys.stderr,
        )
        return 1

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        print(
            "error: ffmpeg was not found on this machine, so it cannot be bundled.\n"
            "Install it first: winget install Gyan.FFmpeg",
            file=sys.stderr,
        )
        return 1
    print(f"bundling ffmpeg from {ffmpeg}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        "daisy2telmi",
        "--hidden-import",
        "lxml.etree",
        "--hidden-import",
        "lxml._elementpath",
        "--add-binary",
        f"{ffmpeg}{os.pathsep}.",
        str(ROOT / "launcher.py"),
    ]
    print(" ".join(command))
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
