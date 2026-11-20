"""The Merlin story-teller's SD card: `playlist.bin` and the files it names.

The card's root holds `playlist.bin` beside flat `.mp3` and `.jpg` files: there
is no folder tree, and the record's name field is the file without its extension.
The file is a plain sequence of 152-byte records — no header, no count, no
checksum — so it can be written directly, and read back from a real card and
appended to.

Two reference implementations agree on every byte: djokeur/merlinator's
`write_merlin_playlist` (its GUI edits a card's own file) and gawen/pinpin's
`playlist.go` decoder. The kind values come from pinpin.

A folder record carries a title and a picture but no sound: merlinator's
`add_menu` gives one a uuid, a title and `type 6`, and only the audio kinds get
an MP3. The device has no display and no speech of its own, so a chapter's name
has to be heard at the start of its audio, not read from its record.
"""

from __future__ import annotations

import json
import struct
import subprocess
import time
import unicodedata
import uuid as uuid_module
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .audio import require_ffmpeg

PLAYLIST = "playlist.bin"
RECORD_SIZE = 152
NAME_FIELD = 64
TITLE_FIELD = 66

# The firmware reads a file name into a 59-byte buffer; a longer one overflows it
# and the device reboots, even though the record itself holds 64 bytes.
MAX_NAME = 57

KIND_ROOT = 0x0001
KIND_FOLDER = 0x0002
KIND_AUDIO = 0x0004
KIND_FOLDER_FAVOURITE = 0x000A

# Files the device made for itself: a cleanup must leave them alone.
KEEP = ("sleep.cfg", "wifi.cfg", "default")


class MerlinError(Exception):
    """The playlist cannot be read, or a record cannot be written."""


@dataclass
class Item:
    """One record: an entry in the card's tree, and the file it names."""

    id: int
    parent: int
    order: int
    kind: int
    name: str = ""
    title: str = ""
    children: int = 0
    fav_order: int = 0
    limit_time: int = 0
    add_time: int = 0


def _field(text: str, size: int, form: str, what: str) -> bytes:
    raw = unicodedata.normalize(form, text).encode("utf-8")
    if len(raw) > size:
        raise MerlinError(f"the {what} {text!r} does not fit in {size} bytes")
    return bytes([len(raw)]) + raw + b"\x00" * (size - len(raw))


def pack(item: Item) -> bytes:
    head = struct.pack(
        "<HHHHHHII",
        item.id,
        item.parent,
        item.order,
        item.children,
        item.fav_order,
        item.kind,
        item.limit_time,
        item.add_time,
    )
    # Names are NFD and titles NFC because that is how the card's FAT32 and the
    # device's font each happen to store them.
    return (
        head
        + _field(item.name, NAME_FIELD, "NFD", "file name")
        + _field(item.title, TITLE_FIELD, "NFC", "title")
    )


def unpack(record: bytes) -> Item:
    if len(record) != RECORD_SIZE:
        raise MerlinError(f"a record is {RECORD_SIZE} bytes, not {len(record)}")
    values = struct.unpack("<HHHHHHII", record[:20])
    return Item(
        id=values[0],
        parent=values[1],
        order=values[2],
        children=values[3],
        fav_order=values[4],
        kind=values[5],
        limit_time=values[6],
        add_time=values[7],
        name=_read_field(record, 20, NAME_FIELD, "file name"),
        title=_read_field(record, 20 + 1 + NAME_FIELD, TITLE_FIELD, "title"),
    )


def _read_field(record: bytes, at: int, size: int, what: str) -> str:
    length = record[at]
    if length > size:
        raise MerlinError(f"the {what} claims {length} bytes in a {size} byte field")
    return record[at + 1 : at + 1 + length].decode("utf-8", errors="replace")


def read_playlist(path: Path) -> list[Item]:
    data = Path(path).read_bytes()
    if len(data) % RECORD_SIZE:
        raise MerlinError(f"{path} holds {len(data)} bytes, which is not a whole number of records")
    return [unpack(data[at : at + RECORD_SIZE]) for at in range(0, len(data), RECORD_SIZE)]


def write_playlist(path: Path, items: Sequence[Item]) -> None:
    Path(path).write_bytes(b"".join(pack(item) for item in items))


def file_name() -> str:
    """A card file name: the factory's own shape, never the title.

    The title belongs to the record; naming a file after it would put the book's
    name on the card and burn it into every later edit.
    """
    return str(uuid_module.uuid4())


class Playlist:
    """Records being built, with the ids handed out as they are added."""

    def __init__(self, items: Sequence[Item] = ()) -> None:
        self.items = list(items)
        self._next = max((item.id for item in self.items), default=0) + 1

    def root(self) -> Item | None:
        return next((item for item in self.items if item.kind == KIND_ROOT), None)

    def add(self, parent: int, kind: int, title: str, name: str = "") -> Item:
        order = sum(1 for item in self.items if item.parent == parent)
        item = Item(
            id=self._next,
            parent=parent,
            order=order,
            kind=kind,
            name=name,
            title=unicodedata.normalize("NFC", title),
        )
        self._next += 1
        self.items.append(item)
        return item

    def folder(self, parent: int, title: str) -> Item:
        # A folder is named like a file as well: the card looks its picture up by
        # that name, and merlinator gives a new menu a uuid for the same reason.
        return self.add(parent, KIND_FOLDER, title, file_name())

    def audio(self, parent: int, title: str, name: str) -> Item:
        if len(name) > MAX_NAME:
            raise MerlinError(f"the file name {name!r} is over {MAX_NAME} characters")
        return self.add(parent, KIND_AUDIO, title, name)

    def write(self, path: Path) -> None:
        # The card walks a folder by reading `children` entries after it, so the
        # count is written last, once the whole tree is there.
        for item in self.items:
            item.children = sum(1 for other in self.items if other.parent == item.id)
        write_playlist(path, self.items)


# What the card's firmware asks its files for.
PICTURE = 128
SAMPLE_RATE = 44100
CHANNELS = 2
BITRATE = "128k"

IMPORT_NOTE = """Merlin story-teller

Copy every .mp3 and .jpg of this folder, and playlist.bin, into the root of the
micro-SD card. The card holds one flat folder: it has no sub-folders, and the
story's own folder is a record in playlist.bin, not a directory.

- playlist.bin written with --merlin-merge already holds the card's own content,
  with this story added under it. It replaces the card's file.
- Without --merlin-merge it holds only this story, so the card's own content is
  no longer listed. Keep the card's original playlist.bin to put it back.

Never delete sleep.cfg, wifi.cfg or the `default` folder: the device made them.

Each part begins with its title spoken, because the Merlin has no screen and a
menu's title is never read aloud: the record's title field is only ever seen by
the editor.
"""


def _run(args: list[str], description: str) -> None:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        detail = result.stderr.strip().splitlines()
        raise MerlinError(f"{description}: {detail[-1] if detail else 'ffmpeg failed'}")


def _encode(ffmpeg: str, clips: Sequence[Path], dest: Path) -> None:
    """One part's audio: its spoken card first, then its text, at the card's spec."""
    inputs: list[str] = []
    for clip in clips:
        inputs += ["-i", str(clip)]
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", *inputs]
    if len(clips) > 1:
        chains = "".join(f"[{index}:a]" for index in range(len(clips)))
        args += ["-filter_complex", f"{chains}concat=n={len(clips)}:v=0:a=1[a]", "-map", "[a]"]
    else:
        args += ["-map", "0:a"]
    args += [
        "-ar", str(SAMPLE_RATE),
        "-ac", str(CHANNELS),
        "-c:a", "libmp3lame",
        "-b:a", BITRATE,
        # The card reads its own tags; a cover embedded by ffmpeg would push the
        # file past what its reader takes for one.
        "-map_metadata", "-1",
        "-id3v2_version", "0",
        str(dest),
    ]
    _run(args, f"could not write {dest.name}")


def _picture(ffmpeg: str, source: Path, dest: Path) -> None:
    """The card's square picture: the middle of the scene, not a squash of it."""
    _run(
        [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
            # Both quotes matter: the filter graph reads min()'s comma as the end
            # of the crop filter.
            "-vf", f"crop=w='min(iw,ih)':h='min(iw,ih)',scale={PICTURE}:{PICTURE}",
            "-frames:v", "1", "-q:v", "2", str(dest),
        ],
        f"could not draw {dest.name}",
    )


def parts(story_dir: Path) -> list[tuple[dict, dict | None]]:
    """The story's parts in the order the player walks them, each with the spoken
    card that introduces it."""
    nodes = json.loads((Path(story_dir) / "nodes.json").read_text(encoding="utf-8"))["stages"]
    found: list[tuple[dict, dict | None]] = []
    for index in range(len(nodes)):
        stage = nodes.get(f"m{index}")
        if stage is None:
            break
        card = nodes.get((stage.get("ok") or {}).get("action", ""))
        found.append((stage, card if card and card.get("audio") else None))
    return found


def export(story_dir: Path, card_dir: Path, titles: Sequence[str], merge_into: Path | None = None) -> list[str]:
    """Write one finished Telmi story as the files a Merlin card holds.

    `titles` names each part in order. The record carries it, and the spoken card
    at the front of the audio is the only place the device can say it.

    `merge_into` is a card's own `playlist.bin`: every record of it is kept and
    ours are appended under its root, which is how a story joins what the card
    already holds.
    """
    ffmpeg = require_ffmpeg()
    story_dir = Path(story_dir)
    card_dir = Path(card_dir)
    metadata = json.loads((story_dir / "metadata.json").read_text(encoding="utf-8"))
    story_parts = parts(story_dir)
    if len(story_parts) != len(titles):
        raise MerlinError(
            f"the story has {len(story_parts)} part(s), but {len(titles)} title(s) were given"
        )

    card = Playlist(read_playlist(merge_into) if merge_into else ())
    root = card.root() or card.add(0, KIND_ROOT, "Root")
    now = int(time.time())
    book = card.folder(root.id, str(metadata.get("title") or story_dir.name))
    book.add_time = now

    card_dir.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    cover = story_dir / str(metadata.get("image") or "cover.png")
    if cover.is_file():
        _picture(ffmpeg, cover, card_dir / f"{book.name}.jpg")

    for (stage, card_stage), title in zip(story_parts, titles):
        name = file_name()
        clips = [
            story_dir / "audios" / clip["audio"]
            for clip in (card_stage, stage)
            if clip and clip.get("audio")
        ]
        _encode(ffmpeg, clips, card_dir / f"{name}.mp3")
        if stage.get("image") and (image := story_dir / "images" / stage["image"]).is_file():
            _picture(ffmpeg, image, card_dir / f"{name}.jpg")
        card.audio(book.id, str(title), name).add_time = now
        written.append(name)

    card.write(card_dir / PLAYLIST)
    (card_dir / "IMPORT.txt").write_text(IMPORT_NOTE, encoding="utf-8")
    return written
