#!/usr/bin/env python3
"""Build a .deb from a single binary, using only the standard library.

Written by hand so the package can be produced and verified on any OS, without
dpkg or fakeroot. ffmpeg is declared as a dependency rather than duplicated.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import math
from pathlib import Path
import tarfile

DEBIAN_VERSION = "2.0\n"
DEFAULT_DESCRIPTION = "Convert a DAISY 2.02 audio book pack into a Telmi story folder"


def _tar_gzip(entries: list[tuple[str, int, bytes]], mtime: int) -> bytes:
    """Build a tar.gz from (name, mode, payload) triples."""
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode="wb", mtime=mtime) as gz:
        with tarfile.open(fileobj=gz, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for name, mode, payload in entries:
                info = tarfile.TarInfo(name=name)
                info.size = len(payload)
                info.mode = mode
                info.mtime = mtime
                info.uid = 0
                info.gid = 0
                info.uname = "root"
                info.gname = "root"
                tar.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


AR_MAGIC = b"!<arch>\n"


def _ar_member(name: str, payload: bytes, mtime: int) -> bytes:
    header = f"{name:<16}{mtime:<12}{0:<6}{0:<6}{'100644':<8}{len(payload):<10}`\n".encode("ascii")
    padded = payload if len(payload) % 2 == 0 else payload + b"\n"
    return header + padded


def build_deb(
    binary: Path,
    output: Path,
    *,
    package: str,
    version: str,
    architecture: str,
    maintainer: str,
    description: str = "Convert a DAISY 2.02 audio book pack into a Telmi story folder",
    depends: str = "ffmpeg",
    mtime: int = 0,
) -> Path:
    install_path = Path("/usr/local/bin") / package
    payload = binary.read_bytes()

    data = _tar_gzip(
        [(str(install_path).lstrip("/"), 0o755, payload)],
        mtime,
    )

    md5 = hashlib.md5(payload).hexdigest()
    control = (
        f"Package: {package}\n"
        f"Version: {version}\n"
        f"Section: utils\n"
        f"Priority: optional\n"
        f"Architecture: {architecture}\n"
        f"Depends: {depends}\n"
        f"Maintainer: {maintainer}\n"
        f"Description: {description}\n"
    ).encode("utf-8")
    control_tar = _tar_gzip(
        [
            ("./control", 0o644, control),
            ("./md5sums", 0o644, f"{md5}  {install_path}\n".encode("utf-8")),
        ],
        mtime,
    )

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        handle.write(AR_MAGIC)
        handle.write(_ar_member("debian-binary", DEBIAN_VERSION.encode("ascii"), mtime))
        handle.write(_ar_member("control.tar.gz", control_tar, mtime))
        handle.write(_ar_member("data.tar.gz", data, mtime))
    return output


def read_ar_members(path: Path) -> list[tuple[str, bytes]]:
    """Parse an ar archive; used by the tests to check the output."""
    raw = path.read_bytes()
    if not raw.startswith(AR_MAGIC):
        raise ValueError(f"{path} is not an ar archive")
    members: list[tuple[str, bytes]] = []
    offset = 8
    while offset < len(raw):
        header = raw[offset : offset + 60]
        if len(header) < 60 or header[58:59] != b"`":
            raise ValueError(f"{path}: corrupt member header at {offset}")
        name = header[0:16].decode("ascii").rstrip()
        size = int(header[48:58].decode("ascii").strip())
        payload = raw[offset + 60 : offset + 60 + size]
        members.append((name, payload))
        offset += 60 + size + (size % 2)
    return members


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path, help="the compiled executable to install")
    parser.add_argument("output", type=Path, help="the .deb file to write")
    parser.add_argument("--package", default="daisy2telmi")
    parser.add_argument("--version", required=True)
    parser.add_argument("--architecture", default="amd64")
    parser.add_argument("--maintainer", default="daisy2telmi contributors")
    parser.add_argument(
        "--description",
        default="Convert a DAISY 2.02 audio book pack into a Telmi story folder",
    )
    args = parser.parse_args()
    path = build_deb(
        args.binary,
        args.output,
        package=args.package,
        version=args.version,
        architecture=args.architecture,
        maintainer=args.maintainer,
        description=args.description,
    )
    print(f"wrote {path} ({math.ceil(path.stat().st_size / 1024)} KiB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
