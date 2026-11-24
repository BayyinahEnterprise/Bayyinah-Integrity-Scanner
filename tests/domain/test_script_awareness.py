"""Script awareness: ordinary writing in any script is not an attack."""

from __future__ import annotations

import pytest

from domain.config import CONFUSABLE_TO_LATIN, ZERO_WIDTH_CHARS
from domain.script_awareness import (
    exempt_zero_width_indices, is_spoof_word, script_of, spoof_words,
    suspicious_zero_width,
)

ZWNJ, ZWJ, ZWSP = "‌", "‍", "​"


def _sus(text: str) -> int:
    return len(suspicious_zero_width(text, ZERO_WIDTH_CHARS))


@pytest.mark.parametrize("text", [
    f"من می{ZWNJ}خواهم کتاب{ZWNJ}ها را بخوانم",            # Persian
    f"क्{ZWJ}ष और श्{ZWNJ}री",                               # Hindi, beside a virama
    f"ภาษา{ZWSP}ไทย{ZWSP}เป็น{ZWSP}ภาษา",                    # Thai word breaks
    f"Family \U0001F468{ZWJ}\U0001F469{ZWJ}\U0001F467 here",  # emoji sequence
    f"\U0001F3F3️{ZWJ}\U0001F308",                       # flag with VS16
])
def test_orthographic_zero_width_is_not_reported(text: str) -> None:
    assert _sus(text) == 0


@pytest.mark.parametrize("text", [
    f"The ad{ZWNJ}min pass{ZWNJ}word",       # Latin has no use for a joiner
    f"word{ZWSP}break in English",
    f"{ZWNJ}leading",
    f"دار{ZWNJ}ند",                          # after reh: joins nothing, no effect
    f"क{ZWJ}म",                              # Indic joiner with no virama
    f"a{ZWNJ}{ZWNJ}b",
    "mid﻿stream",
])
def test_unexplained_zero_width_is_reported(text: str) -> None:
    assert _sus(text) >= 1


def test_bom_at_offset_zero_is_exempt_only_for_whole_files() -> None:
    text = "﻿hello"
    assert 0 not in exempt_zero_width_indices(text)
    assert 0 in exempt_zero_width_indices(text, bom_at_start_ok=True)


def test_density_cap_withdraws_the_exemption() -> None:
    """One bit per letter gap needs far more joiners than Persian uses."""
    letters = "بتثجحخسشصضطظعغفقكلمنهي"
    dense = "".join(c + ZWNJ for c in letters * 3) + "ب"
    assert _sus(dense) == dense.count(ZWNJ)
    sparse = f"می{ZWNJ}خواهم " * 3 + "کتاب خوب است و من آن را دوست دارم " * 4
    assert _sus(sparse) == 0


def test_script_of() -> None:
    assert script_of("ж") == "CYRILLIC"
    assert script_of("ی") == "ARABIC"
    assert script_of("a") == "LATIN"
    assert script_of("1") is None


RUSSIAN = ("Сегодня утром мы пошли в городской парк, чтобы посмотреть на "
           "новые деревья. Погода была хорошая, и дети играли возле реки.")
GREEK = "Σήμερα το πρωί πήγαμε στο πάρκο της πόλης για να δούμε τα νέα δέντρα."
UKRAINIAN = "Сьогодні вранці ми пішли до міського парку, щоб подивитися на дерева."


@pytest.mark.parametrize("text", [RUSSIAN, GREEK, UKRAINIAN])
def test_ordinary_prose_has_no_spoof_words(text: str) -> None:
    assert spoof_words(text, CONFUSABLE_TO_LATIN) == []


def test_mixed_language_notes_have_no_spoof_words() -> None:
    text = "Meeting notes: Иван сказал, что отчёт готов. Contact: Ольга Петрова."
    assert spoof_words(text, CONFUSABLE_TO_LATIN) == []


@pytest.mark.parametrize("word,context", [
    ("pаypal.com", "Please wire the funds to pаypal.com today."),   # mixed script
    ("аdmin@bank.com", "write to аdmin@bank.com"),
    ("сосо", "Buy сосо now"),         # whole-script, Latin context
])
def test_spoofs_are_still_caught(word: str, context: str) -> None:
    assert is_spoof_word(word, CONFUSABLE_TO_LATIN, context)


def test_whole_script_word_inside_its_own_language_is_ordinary() -> None:
    # "сосо" is all lookalikes, but the sentence around it is Russian.
    text = "Мой друг сосо живёт в Тбилиси уже много лет"
    assert not is_spoof_word("сосо", CONFUSABLE_TO_LATIN, text)
