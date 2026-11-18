"""The glibc floor check, run on captured objdump output."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "check_glibc", Path(__file__).resolve().parents[1] / "tools" / "check_glibc.py"
)
check_glibc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_glibc)

OBJDUMP = """
/tmp/_MEI001/libtcl8.6.so:     file format elf64-x86-64
0000  0000000000000000      DF *UND*  0000 GLIBC_2.2.5 memcpy
0000  0000000000000000      DF *UND*  0000 GLIBC_2.42 close
"""


def test_the_newest_glibc_symbol_is_the_one_that_matters():
    assert max(check_glibc.glibc_needs(OBJDUMP)) == (2, 42)


def test_a_library_without_glibc_symbols_is_ignored():
    assert check_glibc.glibc_needs("no version info here") == set()


def test_the_toc_lists_every_collected_library(tmp_path: Path):
    library = tmp_path / "libtcl8.6.so"
    library.write_bytes(b"\x7fELF")
    (tmp_path / "build" / "daisy2telmi").mkdir(parents=True)
    (tmp_path / "build" / "daisy2telmi" / "Analysis-00.toc").write_text(
        f"[('{str(library)}', '/tmp/_MEI/libtcl8.6.so', 'BINARY')]\n", encoding="utf-8"
    )
    assert check_glibc.bundled_libraries(tmp_path / "build") == [library]


def test_a_library_that_is_not_on_disk_is_not_counted(tmp_path: Path):
    (tmp_path / "build" / "daisy2telmi").mkdir(parents=True)
    (tmp_path / "build" / "daisy2telmi" / "Analysis-00.toc").write_text(
        "[('/usr/lib/libgone.so', '/tmp/_MEI/libgone.so', 'BINARY')]\n", encoding="utf-8"
    )
    assert check_glibc.bundled_libraries(tmp_path / "build") == []
