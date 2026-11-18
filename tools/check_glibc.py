"""Fail when a bundled library needs a newer glibc than the release floor.

PyInstaller copies the Tcl/Tk and espeak-ng libraries out of the build machine,
and each copy keeps the glibc symbols that machine resolved. A binary built on a
recent distribution then refuses to start on an older one, saying only
`version GLIBC_2.42 not found (required by libtcl8.6.so)`.

    python tools/check_glibc.py --build build --floor 2.35
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_NEED = re.compile(r"GLIBC_(\d+)\.(\d+)")
# Analysis-00.toc is a Python literal holding every file PyInstaller collected.
_PATH = re.compile(r"(/[^\"']+\.so[0-9.]*)")


def glibc_needs(text: str) -> set[tuple[int, int]]:
    return {(int(m.group(1)), int(m.group(2))) for m in _NEED.finditer(text)}


def bundled_libraries(build: Path) -> list[Path]:
    """Absolute paths of the shared libraries the build collected."""
    found: list[Path] = []
    seen: set[Path] = set()
    for toc in sorted(build.glob("*/[A-Za-z]*-00.toc")):
        for path in _PATH.findall(toc.read_text(encoding="utf-8", errors="replace")):
            library = Path(path)
            if library not in seen and library.is_file():
                seen.add(library)
                found.append(library)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--build", type=Path, default=Path("build"))
    parser.add_argument("--floor", default="2.35", help="highest glibc the release may need")
    args = parser.parse_args(argv)

    floor = tuple(int(part) for part in args.floor.split("."))
    libraries = bundled_libraries(args.build)
    if not libraries:
        print(f"error: no shared library found in {args.build}/*/…-00.toc", file=sys.stderr)
        return 1

    worst: tuple[int, int] = (0, 0)
    worst_by: Path | None = None
    for library in libraries:
        out = subprocess.run(["objdump", "-T", str(library)], capture_output=True, text=True).stdout
        needs = glibc_needs(out)
        if needs and max(needs) > worst:
            worst, worst_by = max(needs), library

    print(f"{len(libraries)} bundled libraries, newest glibc symbol: GLIBC_{'.'.join(map(str, worst))} ({worst_by})")
    if worst > floor:
        print(
            f"error: {worst_by} needs GLIBC_{'.'.join(map(str, worst))}, above the {'.'.join(map(str, floor))} floor.\n"
            "Build on an older runner: the bundled libraries carry their build machine's glibc.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
