"""The language tables have to stay complete: a missing key would show a raw key
or an English label in a window the user asked to see in Turkish."""

from __future__ import annotations

import pytest

from daisy2telmi.i18n import LANGUAGES, UI, language, text

EXPECTED = {"en", "fr", "zh", "ar", "tr", "de", "it", "es", "pt", "nl"}


def test_the_ten_languages_are_present() -> None:
    assert EXPECTED == set(LANGUAGES)


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_every_language_can_speak_a_chapter_number(code: str) -> None:
    lang = LANGUAGES[code]
    assert "{n}" in lang.chapter
    assert lang.chapter.format(n=7).strip()
    assert lang.next_prompt.strip()


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_every_language_can_name_a_part(code: str) -> None:
    """A card that reads the part's title needs the words around the number too."""
    lang = LANGUAGES[code]
    assert "{n}" in lang.number_of and "{total}" in lang.number_of
    assert "{n}" in lang.number_title and "{title}" in lang.number_title
    assert "{n}" in lang.title_number and "{title}" in lang.title_number
    assert lang.number_of.format(n=3, total=9).strip()
    assert lang.number_title.format(n=3, title="X").strip()


@pytest.mark.parametrize("code", sorted(EXPECTED))
def test_every_window_language_is_translated(code: str) -> None:
    missing = set(UI["en"]) - set(UI[code])
    assert not missing, f"{code} is missing {sorted(missing)}"


def test_an_unknown_language_falls_back_to_english() -> None:
    assert language("xx").code == "en"
    assert language(None).code == "en"
    assert text("xx", "save") == UI["en"]["save"]


def test_speech_tags_are_set_for_every_language() -> None:
    for code, lang in LANGUAGES.items():
        assert lang.espeak, f"{code} has no espeak tag"
        assert lang.locale, f"{code} has no locale"
