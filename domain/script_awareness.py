"""Script awareness for the invisible-character and homoglyph detectors.

Two detectors used to treat every writing system as if it were English:

* ``zero_width_chars`` reported every U+200B / U+200C / U+200D, although
  Persian, Arabic-script, Indic and South-East Asian orthographies
  *require* them, and emoji sequences are built from U+200D.
* ``homoglyph`` reported any word carrying two or more Latin-lookalike
  letters, which describes most ordinary Russian, Ukrainian and Greek
  words.

This module answers one question for each: is this character, or this
word, explained by the writing system it sits in?  The zero-width rules
began as a port of the heuristic in the FATIMA encoder's audit engine
(``_is_heuristic_exempt_zero_width``, v10.9.1) and add three guards that
heuristic lacks, because an exemption is also a hiding place:

1. Arabic script: U+200C is orthographic only after a letter that would
   otherwise join forward. After a right-joining letter (alef, dal, reh,
   waw ...) it changes nothing on screen, so it is not exempt.
2. Indic scripts: U+200C / U+200D are orthographic only next to a
   virama. Anywhere else in the word they are not exempt.
3. Density: when exempt-eligible characters exceed a fixed share of the
   script's letters, none are exempt. One bit per letter gap needs far
   more of them than any orthography uses.

An exemption is a statement about orthography, not about safety. A
patient attacker can still hide a few bits inside the allowed rate; the
caps bound that channel, they do not close it.

Pure functions, standard library only.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from typing import Final

ZWSP: Final[str] = "​"
ZWNJ: Final[str] = "‌"
ZWJ: Final[str] = "‍"
BOM: Final[str] = "﻿"

_LETTER_CATEGORIES: Final[frozenset[str]] = frozenset(
    {"Lu", "Ll", "Lt", "Lo", "Lm", "Mn", "Mc"}
)

ARABIC_SCRIPTS: Final[frozenset[str]] = frozenset({"ARABIC", "SYRIAC", "NKO"})
INDIC_SCRIPTS: Final[frozenset[str]] = frozenset({
    "DEVANAGARI", "BENGALI", "GURMUKHI", "GUJARATI", "ORIYA", "TAMIL",
    "TELUGU", "KANNADA", "MALAYALAM", "SINHALA",
})
OTHER_JOINING_SCRIPTS: Final[frozenset[str]] = frozenset({"MONGOLIAN"})
NO_SPACE_SCRIPTS: Final[frozenset[str]] = frozenset(
    {"THAI", "LAO", "KHMER", "MYANMAR", "TIBETAN"}
)

# Arabic-script letters that never join to the letter after them. A
# U+200C placed after one of these has no visual effect.
_RIGHT_JOINING: Final[frozenset[str]] = frozenset(
    "آأؤإاةدذرزو"
    "ٱٲٳٵٶٷ"
    "ڈډڊڋڌڍڎڏڐ"
    "ڑڒړڔڕږڗژڙ"
    "ۀۃۄۅۆۇۈۉۊۋۍۏ"
    "ےۓە"
)

# Share of a script's letters that exempt-eligible characters may reach
# before the exemption is withdrawn for the whole text, and the count
# below which the share is not tested (short strings are too noisy).
JOINER_DENSITY_CAP: Final[float] = 0.12
WORD_BREAK_DENSITY_CAP: Final[float] = 0.45
DENSITY_MIN_COUNT: Final[int] = 8

_EMOJI_RANGES: Final[tuple[tuple[int, int], ...]] = (
    (0x2600, 0x27BF),
    (0x1F300, 0x1F5FF),
    (0x1F600, 0x1F64F),
    (0x1F680, 0x1F6FF),
    (0x1F900, 0x1F9FF),
    (0x1FA70, 0x1FAFF),
)


def script_of(ch: str) -> str | None:
    """Script of a letter or mark: the first word of its Unicode name.

    ``'ARABIC LETTER FARSI YEH'`` gives ``'ARABIC'``. Anything that is
    not a letter or combining mark gives ``None``.
    """
    if unicodedata.category(ch) not in _LETTER_CATEGORIES:
        return None
    name = unicodedata.name(ch, "")
    return name.split(" ", 1)[0] if name else None


def _in_emoji_range(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _EMOJI_RANGES)


def _orthographic(text: str, i: int) -> str | None:
    """Which rule, if any, explains the zero-width character at ``i``.

    Returns ``"joiner"``, ``"word_break"``, ``"emoji"``, ``"bom"`` or
    ``None``. Density is applied by the caller.
    """
    ch = text[i]
    if ch == BOM:
        return "bom" if i == 0 else None
    if i == 0 or i + 1 >= len(text):
        return None
    prev_ch, next_ch = text[i - 1], text[i + 1]
    prev_script, next_script = script_of(prev_ch), script_of(next_ch)
    if ch in (ZWNJ, ZWJ):
        if ch == ZWJ and (_in_emoji_range(prev_ch) or prev_ch == "️") \
                and _in_emoji_range(next_ch):
            return "emoji"
        if prev_script is None or prev_script != next_script:
            return None
        if prev_script in ARABIC_SCRIPTS:
            if ch == ZWNJ and prev_ch not in _RIGHT_JOINING \
                    and unicodedata.category(prev_ch) == "Lo":
                return "joiner"
            return None
        if prev_script in INDIC_SCRIPTS:
            # Orthographic use sits against a virama (combining class 9).
            if unicodedata.combining(prev_ch) == 9 \
                    or unicodedata.combining(next_ch) == 9:
                return "joiner"
            return None
        if prev_script in OTHER_JOINING_SCRIPTS:
            return "joiner"
        return None
    if ch == ZWSP and prev_script in NO_SPACE_SCRIPTS \
            and prev_script == next_script:
        return "word_break"
    return None


def exempt_zero_width_indices(
    text: str, *, bom_at_start_ok: bool = False,
) -> frozenset[int]:
    """Indices of zero-width characters explained by orthography.

    A byte-order mark at offset 0 is exempt only when the caller says
    ``text`` is a whole file (``bom_at_start_ok``); the first character
    of a cell or a run is not the start of a file.
    """
    if not any(c in text for c in (ZWSP, ZWNJ, ZWJ, BOM)):
        return frozenset()
    by_rule: dict[str, list[int]] = {}
    for i, ch in enumerate(text):
        if ch in (ZWSP, ZWNJ, ZWJ, BOM):
            rule = _orthographic(text, i)
            if rule:
                by_rule.setdefault(rule, []).append(i)
    if not by_rule:
        return frozenset()
    letters = sum(1 for c in text if unicodedata.category(c) in ("Lo", "Lm"))
    exempt: set[int] = set()
    for rule, cap in (("joiner", JOINER_DENSITY_CAP),
                      ("word_break", WORD_BREAK_DENSITY_CAP)):
        hits = by_rule.get(rule, [])
        if len(hits) >= DENSITY_MIN_COUNT and letters \
                and len(hits) / letters > cap:
            continue  # too dense to be orthography: report all of them
        exempt.update(hits)
    exempt.update(by_rule.get("emoji", []))
    if bom_at_start_ok:
        exempt.update(by_rule.get("bom", []))
    # Disclose what is not reported (see domain/outcomes.py).
    from domain.outcomes import note_exempt_zero_width
    for rule, hits in by_rule.items():
        if rule != "bom":
            note_exempt_zero_width(
                rule, sum(1 for i in hits if i in exempt),
                key=(len(text), hash(text)))
    return frozenset(exempt)


def suspicious_zero_width(
    text: str, zero_width_chars: Iterable[str],
) -> list[str]:
    """Zero-width characters in ``text`` that orthography does not explain."""
    zw = frozenset(zero_width_chars)
    if not any(c in zw for c in text):
        return []
    exempt = exempt_zero_width_indices(text)
    return [c for i, c in enumerate(text) if c in zw and i not in exempt]


def suspicious_zero_width_indices(
    text: str, zero_width_chars: Iterable[str], *,
    bom_at_start_ok: bool = False,
) -> list[int]:
    zw = frozenset(zero_width_chars)
    if not any(c in zw for c in text):
        return []
    exempt = exempt_zero_width_indices(text, bom_at_start_ok=bom_at_start_ok)
    return [i for i, c in enumerate(text) if c in zw and i not in exempt]


# ---------------------------------------------------------------------------
# Homoglyphs
# ---------------------------------------------------------------------------

# Non-confusable letters of the word's own script that must appear
# elsewhere in the context before a whole-script word is read as
# ordinary text in that script.
SAME_SCRIPT_CONTEXT_LETTERS: Final[int] = 3


def _is_ascii_letter(ch: str) -> bool:
    return ("A" <= ch <= "Z") or ("a" <= ch <= "z")


def is_spoof_word(
    word: str, confusables: Iterable[str], context: str | None = None,
) -> bool:
    """Whether ``word`` uses lookalike letters to pass as Latin text.

    ``confusables`` is the set of non-Latin characters that resemble a
    Latin letter. Three cases:

    * Latin letters and lookalikes in one word: mixed-script, a spoof.
    * Every letter is a lookalike (a whole-script confusable such as
      Cyrillic ``сосо`` for ``coco``): a spoof, unless the
      surrounding text is written in that same script, in which case it
      is simply a word of that language.
    * Lookalikes alongside other letters of their own script: an
      ordinary word. This is the case the previous rule got wrong.
    """
    conf = confusables if isinstance(confusables, (set, frozenset, dict)) \
        else frozenset(confusables)
    hits = [c for c in word if c in conf]
    if not hits:
        return False
    if any(_is_ascii_letter(c) for c in word):
        return True
    letters = [c for c in word if unicodedata.category(c).startswith("L")]
    if len(hits) < 2 or len(hits) != len(letters):
        return False
    if context is None:
        return True
    scripts = {script_of(c) for c in hits}
    own = sum(
        1 for c in context
        if c not in conf and script_of(c) in scripts
    )
    return own < SAME_SCRIPT_CONTEXT_LETTERS


def spoof_words(
    text: str, confusables: Iterable[str],
) -> list[str]:
    """Words in ``text`` that :func:`is_spoof_word` flags."""
    conf = confusables if isinstance(confusables, (set, frozenset, dict)) \
        else frozenset(confusables)
    if not any(c in conf for c in text):
        return []
    return [w for w in text.split() if is_spoof_word(w, conf, text)]


def has_spoof_word(text: str, confusables: Iterable[str]) -> bool:
    return bool(spoof_words(text, confusables))
