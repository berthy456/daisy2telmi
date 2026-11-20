"""Saved options: the window writes them, the command line reads them."""

from __future__ import annotations

import json

import pytest

from daisy2telmi import cli, settings


def test_missing_file_gives_the_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "absent"))
    assert settings.load() == settings.DEFAULTS


def test_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    options = dict(settings.DEFAULTS, language="tr", announce="chapter", autoplay=True, voice="Cem")
    path = settings.save(options)
    assert settings.load() == options
    assert json.loads(path.read_text(encoding="utf-8"))["language"] == "tr"


def test_unknown_keys_are_ignored(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    settings.save(dict(settings.DEFAULTS, language="de", cover="nope"))
    assert settings.load()["language"] == "de"
    assert "cover" not in settings.load()


def test_night_mode_is_on_until_told_otherwise(tmp_path, monkeypatch) -> None:
    """A bedtime story is the point of an audiobook pack, so the flag starts on."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert cli.night_mode(cli._parse_args(["pack.zip", "out"])) is True
    assert cli.night_mode(cli._parse_args(["pack.zip", "out", "--no-night-mode"])) is False
    assert cli.night_mode(cli._parse_args(["pack.zip", "out", "--night-mode"])) is True

    settings.save(dict(settings.DEFAULTS, night_mode=False))
    assert cli.night_mode(cli._parse_args(["pack.zip", "out"])) is False
    assert cli.night_mode(cli._parse_args(["pack.zip", "out", "--night-mode"])) is True


def test_a_broken_file_does_not_stop_a_conversion(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    settings.config_path().parent.mkdir(parents=True, exist_ok=True)
    settings.config_path().write_text("{not json", encoding="utf-8")
    assert settings.load() == settings.DEFAULTS
