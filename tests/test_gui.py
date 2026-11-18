"""The Tkinter front end. Skipped where no display or no Tk is available."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from daisy2telmi import gui


@pytest.fixture()
def app():
    try:
        root = gui.make_root()
    except tk.TclError as exc:  # headless CI
        pytest.skip(f"no display: {exc}")
    instance = gui.App(root)
    try:
        yield instance
    finally:
        root.destroy()


def test_the_window_builds(app: gui.App) -> None:
    assert app.convert_button.instate(["!disabled"])


def test_conversion_log_lines_reach_the_window(app: gui.App) -> None:
    handler = gui.attach_log_handler(app)
    try:
        logging.getLogger("daisy2telmi").info("rendering s0")
        app._drain()
    finally:
        logging.getLogger("daisy2telmi").removeHandler(handler)
    assert "INFO: rendering s0" in app.log_view.get("1.0", "end")


def test_a_missing_pack_is_refused_before_any_work(app: gui.App) -> None:
    app.pack_var.set("/nonexistent/pack.zip")
    app.out_var.set("/tmp/daisy2telmi-never")
    app._start()
    app._drain()
    assert "no such pack" in app.log_view.get("1.0", "end")
    assert not Path("/tmp/daisy2telmi-never").exists()


def test_a_dropped_path_becomes_the_pack(app: gui.App) -> None:
    if gui.DND_FILES is None:
        pytest.skip("tkinterdnd2 not installed")

    class Event:
        data = "{/tmp/some pack.zip}"  # tkdnd braces a path containing spaces

    app._on_drop(Event())
    assert app.pack_var.get() == "/tmp/some pack.zip"


def test_the_window_labels_follow_the_language(app: gui.App) -> None:
    app.language_var.set("fr")
    app._relabel()
    assert app._labels["convert"].cget("text") == "Convertir"
    assert app._labels["overwrite"].cget("text").startswith("Ecraser")


def test_the_options_page_saves_what_it_shows(app: gui.App, tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    page = gui.Options(app)
    page.language_box.set("fr - Francais")
    page.autoplay_var.set(True)
    page._close()

    assert app.options["language"] == "fr"
    assert app.options["autoplay"] is True
    saved = (tmp_path / "daisy2telmi" / "config.json").read_text(encoding="utf-8")
    assert '"language": "fr"' in saved
    assert app._labels["convert"].cget("text") == "Convertir"


def test_the_voice_list_follows_the_engine_and_language(app: gui.App) -> None:
    page = gui.Options(app)
    page.language_box.set("fr - Francais")
    espeak = next(e for e in gui.tts.engines() if e.name == "espeak")
    if not espeak.found:
        pytest.skip("no espeak-ng on this machine")
    page.engine_box.set(espeak.label)
    page._fill_voices()
    assert any("French" in name or "fr" in name for name in page.voice_box.cget("values"))


def test_the_announcement_setting_reaches_the_converter(app: gui.App) -> None:
    app.options.update({"announce": "chapter", "tts": "off"})
    app.language_var.set("de")
    announce = app.announce()
    assert announce.mode == "chapter"
    assert announce.engine == "off"
    assert announce.phrase(2) == "Kapitel 2"
