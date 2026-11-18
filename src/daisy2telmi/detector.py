"""Locate DAISY 2.02 packs, on disk or inside a .zip archive."""

from __future__ import annotations

import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

_MAX_SEARCH_DEPTH = 4


class DaisyPackError(RuntimeError):
    """Raised when the input is not a usable DAISY 2.02 pack."""


@dataclass(frozen=True)
class DaisyPack:
    """A located pack. `root` is the folder holding every file the book links to."""

    root: Path
    ncc: Path | None = None
    opf: Path | None = None
    ncx: Path | None = None

    @property
    def toc_file(self) -> Path | None:
        """Table of contents source, preferring the NCC."""
        return self.ncc or self.ncx


def _child_ci(directory: Path, name: str) -> Path | None:
    """Find a child file by name, ignoring case (packs vary by producer)."""
    wanted = name.lower()
    for entry in directory.iterdir():
        if entry.is_file() and entry.name.lower() == wanted:
            return entry
    return None


def _scan(directory: Path, max_depth: int = _MAX_SEARCH_DEPTH) -> DaisyPack | None:
    """Breadth-first search for a folder that contains a DAISY table of contents."""
    frontier = [directory]
    depth = 0
    while frontier and depth <= max_depth:
        for current in frontier:
            ncc = _child_ci(current, "ncc.html")
            ncx = next((p for p in sorted(current.glob("*.ncx")) if p.is_file()), None)
            if ncc is None and ncx is None:
                continue
            opf = _child_ci(current, "package.opf")
            return DaisyPack(root=current, ncc=ncc, opf=opf, ncx=ncx)
        frontier = [p for d in frontier for p in sorted(d.iterdir()) if p.is_dir()]
        depth += 1
    return None


def detect(path: Path) -> DaisyPack | None:
    """Return the pack inside `path` (a folder), or None if it is not DAISY 2.02."""
    if not path.is_dir():
        return None
    return _scan(path)


def _safe_extract(archive: zipfile.ZipFile, dest: Path) -> None:
    """Extract while rejecting traversal paths and macOS resource forks."""
    dest = dest.resolve()
    kept: list[str] = []
    for member in archive.namelist():
        parts = Path(member).parts
        if "__MACOSX" in parts or (parts and parts[-1].startswith("._")):
            continue
        target = (dest / member).resolve()
        if not target.is_relative_to(dest):
            raise DaisyPackError(f"archive entry escapes the output folder: {member}")
        kept.append(member)
    archive.extractall(dest, members=kept)


@contextmanager
def open_pack(path: Path) -> Iterator[DaisyPack]:
    """Yield a pack rooted on a real folder, unpacking the archive if needed."""
    if path.is_dir():
        pack = detect(path)
        if pack is None:
            raise DaisyPackError(
                f"no DAISY 2.02 table of contents (ncc.html or *.ncx) found under {path}"
            )
        yield pack
        return

    if path.is_file() and path.suffix.lower() == ".zip":
        with tempfile.TemporaryDirectory(prefix="daisy2telmi-") as tmp:
            try:
                with zipfile.ZipFile(path) as archive:
                    _safe_extract(archive, Path(tmp))
            except zipfile.BadZipFile as exc:
                raise DaisyPackError(f"not a readable .zip archive: {path}") from exc
            pack = _scan(Path(tmp))
            if pack is None:
                raise DaisyPackError(
                    f"no DAISY 2.02 table of contents (ncc.html or *.ncx) found inside {path}"
                )
            yield pack
        return

    raise DaisyPackError(f"input is neither a folder nor a .zip archive: {path}")
