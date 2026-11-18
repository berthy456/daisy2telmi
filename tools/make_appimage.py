"""Assemble an AppImage from the built daisy2telmi binary.

    python tools/make_appimage.py dist/daisy2telmi dist/daisy2telmi.AppImage [--appimagetool PATH]

The layout is the usual one: the binary under `usr/bin`, an `AppRun` entry point
that execs it, and a `.desktop` file. `appimagetool` turns that folder into the
squashfs image; when it is not on the machine the AppDir is left behind and the
command to finish the job is printed, so the layout can still be checked.
"""

from __future__ import annotations

import argparse
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

DESKTOP = """[Desktop Entry]
Type=Application
Name=daisy2telmi
Comment=Convert a DAISY 2.02 audio book pack into a Telmi story
Exec=daisy2telmi
Terminal=true
Categories=Utility;
"""

APPRUN = """#!/usr/bin/env bash
here="$(dirname "$(readlink -f "$0")")"
export APPDIR="$here"
exec "$here/usr/bin/{binary}" "$@"
"""


def build_appdir(binary: Path, appdir: Path) -> Path:
    appdir = appdir.resolve()
    if appdir.exists():
        shutil.rmtree(appdir)
    (appdir / "usr" / "bin").mkdir(parents=True)

    name = binary.name
    target = appdir / "usr" / "bin" / name
    shutil.copy2(binary, target)
    target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    apprun = appdir / "AppRun"
    apprun.write_text(APPRUN.format(binary=name), encoding="utf-8")
    apprun.chmod(apprun.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    (appdir / f"{name}.desktop").write_text(DESKTOP, encoding="utf-8")
    return appdir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("binary", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--appimagetool", type=Path, help="path to appimagetool; searched on PATH otherwise")
    parser.add_argument("--arch", default="x86_64")
    args = parser.parse_args(argv)

    if not args.binary.is_file():
        print(f"error: no binary at {args.binary}", file=sys.stderr)
        return 1

    appdir = build_appdir(args.binary, args.output.with_suffix("").parent / f"{args.output.stem}-AppDir")
    tool = str(args.appimagetool) if args.appimagetool else shutil.which("appimagetool")
    if tool is None:
        print(f"AppDir ready at {appdir}")
        print(f"finish with: ARCH={args.arch} appimagetool {appdir} {args.output}")
        return 0

    env = dict(os.environ, ARCH=args.arch)
    result = subprocess.run([tool, str(appdir), str(args.output)], env=env)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
