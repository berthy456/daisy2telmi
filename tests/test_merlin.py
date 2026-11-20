"""The Merlin card's `playlist.bin`: the record layout, the names, the tree."""

from __future__ import annotations

import unicodedata

import pytest

from daisy2telmi.merlin import (
    KIND_AUDIO,
    KIND_FOLDER,
    KIND_ROOT,
    MAX_NAME,
    RECORD_SIZE,
    Item,
    MerlinError,
    Playlist,
    file_name,
    pack,
    read_playlist,
    unpack,
    write_playlist,
)


def test_a_record_is_152_bytes_and_lands_where_the_decoder_reads_it() -> None:
    record = pack(Item(id=7, parent=2, order=1, kind=KIND_AUDIO, name="abc", title="Le loup"))
    assert len(record) == RECORD_SIZE
    assert int.from_bytes(record[0:2], "little") == 7, "id"
    assert int.from_bytes(record[2:4], "little") == 2, "parent"
    assert int.from_bytes(record[10:12], "little") == KIND_AUDIO, "kind"
    assert record[20] == 3 and record[21:24] == b"abc", "the file name merlinator calls uuid"
    assert record[85] == len("Le loup".encode()) and record[86:93] == b"Le loup", "the title"
    assert record[93:] == b"\x00" * (RECORD_SIZE - 93), "and the field is padded out"


def test_a_record_survives_the_round_trip() -> None:
    item = Item(
        id=1,
        parent=0,
        order=0,
        kind=KIND_FOLDER,
        name="c" * 36,
        title="Contes du matin",
        children=3,
        fav_order=2,
        limit_time=0,
        add_time=1_700_000_000,
    )
    assert unpack(pack(item)) == item


def test_names_are_NFD_and_titles_NFC() -> None:
    """The card's FAT32 and the device's font normalise the other way round."""
    composed = unicodedata.normalize("NFC", "Épée")
    record = pack(Item(id=1, parent=0, order=0, kind=KIND_AUDIO, name=composed, title=composed))
    name = unpack(record).name
    title = unpack(record).title
    assert unicodedata.is_normalized("NFD", name), "the file name"
    assert unicodedata.is_normalized("NFC", title), "the title"
    assert name != title, "so the two are not the same bytes"


def test_a_name_the_firmware_would_choke_on_is_refused() -> None:
    card = Playlist()
    card.add(0, KIND_ROOT, "Root")
    with pytest.raises(MerlinError):
        card.audio(1, "Le loup", "x" * (MAX_NAME + 1))


def test_a_title_longer_than_its_field_is_refused() -> None:
    with pytest.raises(MerlinError):
        pack(Item(id=1, parent=0, order=0, kind=KIND_AUDIO, title="é" * 40))


def test_a_playlist_is_a_whole_number_of_records(tmp_path) -> None:
    items = [
        Item(id=1, parent=0, order=0, kind=KIND_ROOT, title="Root"),
        Item(id=2, parent=1, order=0, kind=KIND_FOLDER, title="Contes"),
    ]
    path = tmp_path / "playlist.bin"
    write_playlist(path, items)
    assert path.stat().st_size == 2 * RECORD_SIZE
    assert read_playlist(path) == items
    path.write_bytes(path.read_bytes()[:-1])
    with pytest.raises(MerlinError):
        read_playlist(path)


def test_a_card_built_from_scratch_has_a_root_and_its_story_under_it() -> None:
    card = Playlist()
    root = card.add(0, KIND_ROOT, "Root")
    book = card.folder(root.id, "Le loup et les sept chevreaux")
    for chapter in ("Premier chapitre", "Second chapitre"):
        card.audio(book.id, chapter, file_name())
    assert [item.kind for item in card.items] == [KIND_ROOT, KIND_FOLDER, KIND_AUDIO, KIND_AUDIO]
    assert [item.parent for item in card.items[2:]] == [book.id, book.id]
    assert [item.order for item in card.items] == [0, 0, 0, 1], "the chapters keep their order"
    assert all(item.title for item in card.items[1:]), "the title is in the record, not the file name"


def test_the_children_count_is_written_with_the_tree(tmp_path) -> None:
    card = Playlist()
    root = card.add(0, KIND_ROOT, "Root")
    book = card.folder(root.id, "Contes")
    card.audio(book.id, "Un", file_name())
    card.audio(book.id, "Deux", file_name())
    path = tmp_path / "playlist.bin"
    card.write(path)
    written = read_playlist(path)
    assert [item.children for item in written] == [1, 2, 0, 0]


def test_a_story_appends_after_a_real_card_and_under_its_root(tmp_path) -> None:
    """A card already holds the factory's tree; ours has to join it, not replace it."""
    card = Playlist(
        [
            Item(id=1, parent=0, order=0, kind=KIND_ROOT, title="Root", children=3),
            Item(id=2, parent=1, order=0, kind=KIND_FOLDER, name="a" * 36, title="Contes"),
            Item(id=3, parent=2, order=0, kind=KIND_AUDIO, name="b" * 36, title="Le loup"),
            Item(id=9, parent=1, order=1, kind=KIND_FOLDER, name="c" * 36, title="Comptines"),
        ]
    )
    root = card.root()
    book = card.folder(root.id, "Wesh la fée")
    card.audio(book.id, "Chapitre 1", file_name())
    assert card.items[-2].id == 10, "ids continue after the card's highest"
    assert card.items[-2].parent == root.id, "and the story hangs off the card's root"
    assert card.items[-2].order == 2, "after the two folders already there"
    path = tmp_path / "playlist.bin"
    card.write(path)
    written = read_playlist(path)
    assert written[:4] == card.items[:4], "the factory's own records are untouched"
    assert [item.title for item in written] == ["Root", "Contes", "Le loup", "Comptines", "Wesh la fée", "Chapitre 1"]


def test_a_card_file_name_is_the_factory_shape() -> None:
    name = file_name()
    assert len(name) == 36
    assert name.isascii()
    assert name.count("-") == 4
    assert len(f"{name}.mp3") <= MAX_NAME
