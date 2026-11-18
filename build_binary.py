"""Build a self-contained daisy2telmi executable with PyInstaller.

ffmpeg found on the build machine is bundled into the binary, so the end user
does not have to install it. PyInstaller cannot cross-compile, so this produces
a binary for the machine it runs on. On Windows:

    py -3.11 -m venv .venv
    .venv\\Scripts\\activate
    pip install -e .[dev]
    python build_binary.py

The result is dist/daisy2telmi.exe (dist/daisy2telmi on macOS and Linux).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _locate_ffmpeg() -> str | None:
    """DAISY2TELMI_FFMPEG wins over PATH, because installers do not always refresh PATH."""
    explicit = os.environ.get("DAISY2TELMI_FFMPEG")
    if not explicit:
        return shutil.which("ffmpeg")
    if not Path(explicit).is_file():
        print(f"error: DAISY2TELMI_FFMPEG points at a missing file: {explicit}", file=sys.stderr)
        return None
    return explicit


def _locate_espeak() -> tuple[str, str] | None:
    """The espeak-ng binary and its data folder.

    The data folder matters more than the binary: without it espeak-ng knows no
    languages, and the chapter cards would be silent.
    """
    explicit = os.environ.get("DAISY2TELMI_ESPEAK")
    binary = explicit or shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary or not Path(binary).is_file():
        return None

    # Debian keeps the language data in /usr/share, Ubuntu in the multiarch
    # library directory, and Homebrew next to the binary's prefix.
    parent = Path(binary).parent
    candidates = [
        parent.parent / "share" / "espeak-ng-data",
        Path("/usr/share/espeak-ng-data"),
        Path("/usr/local/share/espeak-ng-data"),
        *sorted(Path("/usr/lib").glob("*/espeak-ng-data")),
        parent.parent / "lib" / "espeak-ng-data",
        parent / "espeak-ng-data",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return binary, str(candidate)
    looked = ", ".join(str(c) for c in candidates)
    print(f"warning: found {binary} but no espeak-ng-data folder in {looked}; speech will not be bundled", file=sys.stderr)
    return None


# On macOS everything outside /usr/lib and /System was installed by the user, so
# it all has to travel. On Linux the distribution puts real dependencies in
# /usr/lib too, so only the C and C++ runtime stays behind.
_LINUX_RUNTIME = (
    "ld-linux",
    "libc.so",
    "libdl.so",
    "libgcc_s.so",
    "libm.so",
    "libpthread.so",
    "libresolv.so",
    "librt.so",
    "libstdc++.so",
    "libutil.so",
)


def _linked_libs(binary: str) -> list[str]:
    """Absolute paths of the shared libraries `binary` loads, system ones excluded."""
    if sys.platform == "darwin":
        out = subprocess.run(["otool", "-L", binary], capture_output=True, text=True).stdout
        paths = [line.split()[0] for line in out.splitlines()[1:]]
        return [p for p in paths if p.startswith("/") and not p.startswith(("/usr/lib", "/System"))]

    out = subprocess.run(["ldd", binary], capture_output=True, text=True).stdout
    paths = [parts[2] for parts in (line.split() for line in out.splitlines()) if len(parts) >= 3]
    return [p for p in paths if p.startswith("/") and not p.split("/")[-1].startswith(_LINUX_RUNTIME)]


def _stage_espeak(binary: str, data: str) -> list[str]:
    """Copy espeak-ng, its libraries and its language data into dist/speech.

    The libraries matter: the installed binary names them by absolute path, so a
    bare copy would look for Homebrew or apt files on the user's machine and fail.
    On macOS the load commands are rewritten to `@loader_path`; on Linux the
    runtime sets LD_LIBRARY_PATH instead, which needs no rewriting.
    """
    stage = ROOT / "dist" / "speech"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    staged_exe = stage / Path(binary).name
    shutil.copy2(binary, staged_exe)
    staged_exe.chmod(0o755)

    staged_libs: list[Path] = []
    pending = [binary]
    seen: set[str] = set()
    while pending:
        for dep in _linked_libs(pending.pop()):
            # apt and Homebrew name the same library through different paths, so
            # the copy's file name is what identifies it.
            if Path(dep).name in seen or not Path(dep).is_file():
                continue
            seen.add(Path(dep).name)
            target = stage / Path(dep).name
            shutil.copy2(dep, target)
            target.chmod(0o755)
            staged_libs.append(target)
            pending.append(dep)

    if sys.platform == "darwin":
        for target in [staged_exe, *staged_libs]:
            if target.suffix == ".dylib":
                subprocess.run(
                    ["install_name_tool", "-id", f"@loader_path/{target.name}", str(target)],
                    check=True,
                    capture_output=True,
                )
            for dep in _linked_libs(str(target)):
                subprocess.run(
                    ["install_name_tool", "-change", dep, f"@loader_path/{Path(dep).name}", str(target)],
                    check=True,
                    capture_output=True,
                )

    print(f"bundling espeak-ng from {binary} with data {data} and {len(staged_libs)} librar{'y' if len(staged_libs) == 1 else 'ies'}")
    return [
        "--add-binary",
        f"{staged_exe}{os.pathsep}.",
        *(arg for lib in staged_libs for arg in ("--add-binary", f"{lib}{os.pathsep}.")),
        "--add-data",
        f"{data}{os.pathsep}espeak-ng-data",
    ]


def _speech_options() -> list[str]:
    found = _locate_espeak()
    if found is None:
        return []
    return _stage_espeak(*found)


def _gui_options() -> list[str]:
    """tkinterdnd2 carries Tcl/Tk scripts and a tkdnd library PyInstaller cannot see."""
    if importlib.util.find_spec("tkinterdnd2") is None:
        return []
    return ["--collect-all", "tkinterdnd2"]


def main() -> int:
    ffmpeg = _locate_ffmpeg()
    if ffmpeg is None:
        print(
            "error: ffmpeg was not found on this machine, so it cannot be bundled.\n"
            "Install it, or point DAISY2TELMI_FFMPEG at an ffmpeg executable.",
            file=sys.stderr,
        )
        return 1
    print(f"bundling ffmpeg from {ffmpeg} for {sys.platform}")

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
        *_speech_options(),
        *_gui_options(),
        str(ROOT / "launcher.py"),
    ]
    print(" ".join(command))
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
