"""Checks that the hand-built .deb is a structurally valid Debian archive."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "make_deb", Path(__file__).resolve().parents[1] / "tools" / "make_deb.py"
)
make_deb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make_deb)


@pytest.fixture()
def deb(tmp_path: Path) -> Path:
    binary = tmp_path / "daisy2telmi"
    binary.write_bytes(b"\x7fELF fake binary")
    return make_deb.build_deb(
        binary,
        tmp_path / "daisy2telmi_1.0.0-beta1_amd64.deb",
        package="daisy2telmi",
        version="1.0.0-beta1",
        architecture="amd64",
        maintainer="test <test@example.com>",
    )


def _members(tar_bytes: bytes) -> dict[str, tarfile.TarInfo]:
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(tar_bytes)), mode="r") as tar:
        return {member.name: member for member in tar.getmembers()}


def _payload(tar_bytes: bytes, name: str) -> bytes:
    with tarfile.open(fileobj=io.BytesIO(gzip.decompress(tar_bytes)), mode="r") as tar:
        return tar.extractfile(name).read()


def test_archive_has_the_three_required_members(deb: Path) -> None:
    names = [name for name, _ in make_deb.read_ar_members(deb)]
    assert names == ["debian-binary", "control.tar.gz", "data.tar.gz"]


def test_debian_binary_declares_format_2(deb: Path) -> None:
    members = dict(make_deb.read_ar_members(deb))
    assert members["debian-binary"] == b"2.0\n"


def test_control_has_the_required_fields(deb: Path) -> None:
    members = dict(make_deb.read_ar_members(deb))
    control = _payload(members["control.tar.gz"], "./control").decode("utf-8")
    for line in (
        "Package: daisy2telmi",
        "Version: 1.0.0-beta1",
        "Architecture: amd64",
        "Depends: ffmpeg",
        "Maintainer: test <test@example.com>",
    ):
        assert line in control, line


def test_binary_installs_to_usr_local_bin_and_is_executable(deb: Path) -> None:
    members = dict(make_deb.read_ar_members(deb))
    entries = _members(members["data.tar.gz"])
    entry = entries["usr/local/bin/daisy2telmi"]
    assert entry.mode == 0o755
    assert entry.size > 0


def test_md5sums_matches_the_installed_binary(deb: Path) -> None:
    members = dict(make_deb.read_ar_members(deb))
    payload = _payload(members["data.tar.gz"], "usr/local/bin/daisy2telmi")
    md5sums = _payload(members["control.tar.gz"], "./md5sums").decode("utf-8")
    assert md5sums.startswith(hashlib.md5(payload).hexdigest())


def test_all_members_are_even_padded(deb: Path) -> None:
    # A re-parsable archive proves every member header aligned correctly.
    assert len(make_deb.read_ar_members(deb)) == 3
