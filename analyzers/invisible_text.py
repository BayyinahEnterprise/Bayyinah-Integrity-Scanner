"""Invisible-text checks shared by every analyzer that reads strings.

Four character-level mechanisms the per-format analyzers did not have,
and one decoder:

* ``ansi_escape_sequence``: terminal escape sequences that move the
  cursor, erase output, conceal text or write to the title bar or
  clipboard. Plain colour codes are not reported.
* ``variation_selector_payload``: runs of variation selectors, which
  can carry one byte each and render as nothing.
* ``invisible_format_chars``: invisible operators, interlinear
  annotation controls and filler letters that have no place in prose.
* ``soft_hyphen_obfuscation``: soft hyphens splitting many words, a way
  to defeat keyword filters while the text reads normally.
* ``invisible_payload_decoded``: the text an invisible channel spells
  out (TAG characters, variation selectors, or zero-width characters
  used as binary digits), recovered so the report can say what was
  hidden and the instruction assessor can read it.

The character lists and the zero-width binary format started from the
FATIMA encoder's sanitizer and audit engine (v10.4 to v10.9). FATIMA's
own watermark format is recognised by shape and labelled exactly that:
recognised, not authenticated. Anyone can write the same shape, so a
recognised payload is still decoded and still assessed.

Pure functions over ``str``; no file access.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Final

from domain import Finding
from domain.config import TIER
from domain.outcomes import note_undecodable_run
from domain.script_awareness import suspicious_zero_width_indices

# ---------------------------------------------------------------------------
# Terminal escape sequences
# ---------------------------------------------------------------------------

_ANSI: Final[re.Pattern[str]] = re.compile(
    r"(?:\x1b\[|\x9b)(?P<params>[0-9;:?<=>]*)(?P<final>[@-~])"   # CSI
    r"|\x1b\](?P<osc>[^\x07\x1b]{0,512})(?:\x07|\x1b\\)"          # OSC
    r"|\x1b(?P<single>[DEHMNOPVWXZc78=>^_])"                       # two-byte
)
_CSI_NAMES: Final[dict[str, str]] = {
    "A": "cursor up", "B": "cursor down", "C": "cursor forward",
    "D": "cursor back", "E": "cursor next line", "F": "cursor previous line",
    "G": "cursor column", "H": "cursor position", "f": "cursor position",
    "J": "erase display", "K": "erase line", "S": "scroll up",
    "T": "scroll down", "h": "set mode", "l": "reset mode",
    "s": "save cursor", "u": "restore cursor", "P": "delete characters",
    "X": "erase characters", "L": "insert lines", "M": "delete lines",
}


def _ansi_actions(text: str) -> list[str]:
    """Named actions of every escape sequence that changes what a reader
    of the terminal sees. Colour and style codes are skipped, except the
    conceal attribute (SGR 8)."""
    if "\x1b" not in text and "\x9b" not in text:
        return []
    actions: list[str] = []
    for m in _ANSI.finditer(text):
        if m.group("osc") is not None:
            code = m.group("osc").split(";", 1)[0]
            actions.append({
                "0": "set window title", "2": "set window title",
                "8": "terminal hyperlink", "52": "clipboard write",
            }.get(code, f"operating-system command {code[:8]}"))
        elif m.group("single") is not None:
            actions.append("terminal reset" if m.group("single") == "c"
                           else f"escape {m.group('single')}")
        else:
            final, params = m.group("final"), m.group("params") or ""
            if final == "m":
                if "8" in re.split(r"[;:]", params):
                    actions.append("conceal text")
                continue
            actions.append(_CSI_NAMES.get(final, f"control sequence {final}"))
    return actions


# ---------------------------------------------------------------------------
# Variation selectors
# ---------------------------------------------------------------------------

def _is_vs(cp: int) -> bool:
    return 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF


def _vs_byte(cp: int) -> int:
    return cp - 0xFE00 if cp <= 0xFE0F else cp - 0xE0100 + 16


def _vs_runs(text: str) -> list[tuple[int, int]]:
    """(start, length) of each run of two or more variation selectors.

    A single selector after its base character is ordinary (emoji
    presentation, ideographic variants). Two in a row select nothing.
    """
    runs: list[tuple[int, int]] = []
    i, n = 0, len(text)
    while i < n:
        if _is_vs(ord(text[i])):
            j = i
            while j < n and _is_vs(ord(text[j])):
                j += 1
            if j - i >= 2:
                runs.append((i, j - i))
            i = j
        else:
            i += 1
    return runs


# ---------------------------------------------------------------------------
# Invisible format characters
# ---------------------------------------------------------------------------

INVISIBLE_FORMAT_CHARS: Final[frozenset[int]] = frozenset({
    0x2061, 0x2062, 0x2063, 0x2064,      # invisible math operators
    0xFFF9, 0xFFFA, 0xFFFB,              # interlinear annotation controls
    0x180E,                              # Mongolian vowel separator
    0x115F, 0x1160, 0x3164, 0xFFA0,      # Hangul fillers
    0x034F,                              # combining grapheme joiner
    0x17B4, 0x17B5,                      # Khmer inherent vowels (invisible)
})
_INVISIBLE_FORMAT_MIN: Final[int] = 2

SOFT_HYPHEN: Final[str] = "­"
_SHY_MIN_WORDS: Final[int] = 3
_SHY_WORD_SHARE: Final[float] = 0.30


def _soft_hyphen_words(text: str) -> tuple[int, int]:
    """(words carrying a soft hyphen, total words)."""
    if SOFT_HYPHEN not in text:
        return 0, 0
    words = text.split()
    return sum(1 for w in words if SOFT_HYPHEN in w), len(words)


# ---------------------------------------------------------------------------
# Payload decoding
# ---------------------------------------------------------------------------

_ZW_SET: Final[frozenset[str]] = frozenset("​‌‍⁠﻿")
_ZW_RUN_MIN: Final[int] = 16
_BASMALA_PREFIX: Final[str] = "بِسْمِ"
_FATIMA_PROTOCOLS: Final[frozenset[str]] = frozenset(
    {"FATIMA-MURAQABAH", "FATIMA-MURAQABAH-COLOPHON"}
)
PAYLOAD_TEXT_LIMIT: Final[int] = 4000


@dataclass(frozen=True)
class DecodedPayload:
    channel: str          # "tag", "variation_selector", "zero_width"
    text: str             # recovered text
    carriers: int         # invisible characters that carried it
    start: int            # index of the first carrier in the source
    recognised_format: str | None = None


def _readable(s: str) -> bool:
    """Printable, and varied enough to be text rather than a repeating
    bit pattern that happens to land on one printable byte."""
    if len(s.strip()) < 3:
        return False
    ok = sum(1 for c in s if c.isprintable() or c in "\n\r\t")
    if ok / len(s) < 0.9:
        return False
    return len(set(s)) >= min(4, len(s))


def _bytes_to_text(data: bytes) -> str | None:
    try:
        s = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    s = s.rstrip("\x00")
    return s if _readable(s) else None


def _decode_zero_width(seq: str) -> str | None:
    """Recover text from zero-width characters used as binary digits.

    Tries, in order: separator-delimited groups of 8 bits (optionally
    behind a 4-byte length prefix) or 16 bits, as the FATIMA encoder
    writes them; then an unseparated bit stream over the two most
    common symbols, in both polarities.
    """
    body = seq.replace("﻿", "")
    if "‍" in body:
        groups = [g for g in body.split("‍") if g]
        if groups and all(set(g) <= {"​", "‌"} for g in groups):
            sizes = {len(g) for g in groups}
            vals = [int("".join("1" if c == "‌" else "0" for c in g), 2)
                    for g in groups]
            if sizes == {8}:
                data = bytes(vals)
                if len(data) > 4 and int.from_bytes(data[:4], "big") == len(data) - 4:
                    data = data[4:]
                out = _bytes_to_text(data)
                if out:
                    return out
            elif sizes == {16}:
                try:
                    s = "".join(chr(v) for v in vals)
                except ValueError:
                    s = ""
                if _readable(s):
                    return s
    counts: dict[str, int] = {}
    for c in body:
        counts[c] = counts.get(c, 0) + 1
    if len(counts) < 2:
        return None
    a, b = sorted(counts, key=lambda c: (-counts[c], c))[:2]
    bits_src = [c for c in body if c in (a, b)]
    for one in (b, a):
        bits = "".join("1" if c == one else "0" for c in bits_src)
        usable = len(bits) - len(bits) % 8
        if usable < 24:
            continue
        data = bytes(int(bits[i:i + 8], 2) for i in range(0, usable, 8))
        out = _bytes_to_text(data)
        if out:
            return out
    return None


def _recognised_format(text: str) -> str | None:
    if text.startswith(_BASMALA_PREFIX):
        return "FATIMA watermark (Basmala)"
    if text.startswith("{"):
        try:
            obj = json.loads(text)
        except (ValueError, TypeError):
            return None
        if isinstance(obj, dict) and obj.get("protocol") in _FATIMA_PROTOCOLS:
            return f"FATIMA watermark ({obj['protocol']})"
    return None


def decode_hidden_payloads(text: str) -> list[DecodedPayload]:
    """Every invisible channel in ``text`` that decodes to readable text."""
    out: list[DecodedPayload] = []

    tag_idx = [i for i, c in enumerate(text) if 0xE0020 <= ord(c) <= 0xE007E]
    if len(tag_idx) >= 3:
        s = "".join(chr(ord(text[i]) - 0xE0000) for i in tag_idx)
        if _readable(s):
            out.append(DecodedPayload("tag", s, len(tag_idx), tag_idx[0]))

    for start, length in _vs_runs(text):
        data = bytes(_vs_byte(ord(c)) for c in text[start:start + length])
        s = _bytes_to_text(data)
        if s:
            out.append(DecodedPayload("variation_selector", s, length, start))

    if any(c in _ZW_SET for c in text):
        runs: list[tuple[int, int]] = []
        i, n = 0, len(text)
        while i < n:
            if text[i] in _ZW_SET:
                j = i
                while j < n and text[j] in _ZW_SET:
                    j += 1
                if j - i >= _ZW_RUN_MIN:
                    runs.append((i, j))
                i = j
            else:
                i += 1
        decoded_any = False
        for a, b in runs:
            s = _decode_zero_width(text[a:b])
            if s:
                decoded_any = True
                out.append(DecodedPayload(
                    "zero_width", s, b - a, a, _recognised_format(s)))
        failed_runs = [(a, b) for a, b in runs
                       if not any(p.start == a for p in out)]
        if not decoded_any:
            # Interleaved encoding: digits scattered between visible
            # characters. Only the ones orthography does not explain.
            idx = suspicious_zero_width_indices(text, _ZW_SET)
            if len(idx) >= _ZW_RUN_MIN:
                s = _decode_zero_width("".join(text[k] for k in idx))
                if s:
                    failed_runs = []
                    out.append(DecodedPayload(
                        "zero_width", s, len(idx), idx[0],
                        _recognised_format(s)))
                elif not runs:
                    note_undecodable_run(len(idx), key=(len(text), hash(text), -1))
        # A run that decodes to nothing readable is disclosed, not dropped:
        # its content is unknown.
        for a, b in failed_runs:
            note_undecodable_run(b - a, key=(len(text), hash(text), a))
    return out


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------

_CHANNEL_LABEL: Final[dict[str, str]] = {
    "tag": "Unicode TAG characters",
    "variation_selector": "variation selectors",
    "zero_width": "zero-width characters used as binary digits",
}


def _clip(s: str, n: int = 160) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n] + "..."


def scan_string(value: str, location: str) -> list[Finding]:
    """Findings for the mechanisms in this module, for one string."""
    if not value or value.isascii() and "\x1b" not in value:
        return []
    findings: list[Finding] = []

    actions = _ansi_actions(value)
    if actions:
        kinds = ", ".join(sorted(set(actions)))
        findings.append(Finding(
            mechanism="ansi_escape_sequence",
            tier=TIER["ansi_escape_sequence"],
            confidence=0.9,
            description=(
                f"{len(actions)} terminal escape sequence(s) ({kinds}). "
                "Shown in a terminal, these rewrite or hide output, so "
                "the screen and the bytes disagree."
            ),
            location=location,
            surface="(rendered by the terminal, not shown as text)",
            concealed=f"{len(actions)} escape sequence(s): {kinds}",
        ))

    runs = _vs_runs(value)
    if runs:
        total = sum(length for _, length in runs)
        findings.append(Finding(
            mechanism="variation_selector_payload",
            tier=TIER["variation_selector_payload"],
            confidence=0.9 if total >= 8 else 0.6,
            description=(
                f"{total} variation selector(s) in {len(runs)} run(s) of "
                "two or more. A selector modifies the single character "
                "before it; a run selects nothing and can carry one byte "
                "per character, invisibly."
            ),
            location=location,
            surface="(no visible indication)",
            concealed=f"{total} variation selector codepoint(s)",
        ))

    fmt = [c for c in value if ord(c) in INVISIBLE_FORMAT_CHARS]
    if len(fmt) >= _INVISIBLE_FORMAT_MIN:
        names = ", ".join(sorted({f"U+{ord(c):04X}" for c in fmt}))
        findings.append(Finding(
            mechanism="invisible_format_chars",
            tier=TIER["invisible_format_chars"],
            confidence=0.8,
            description=(
                f"{len(fmt)} invisible format character(s) ({names}): "
                "operators, annotation controls or filler letters that "
                "render as nothing and are not part of ordinary prose."
            ),
            location=location,
            surface="(no visible indication)",
            concealed=f"{len(fmt)} invisible format codepoint(s)",
        ))

    shy_words, words = _soft_hyphen_words(value)
    if shy_words >= _SHY_MIN_WORDS and words \
            and shy_words / words >= _SHY_WORD_SHARE:
        plain = value.replace(SOFT_HYPHEN, "")
        findings.append(Finding(
            mechanism="soft_hyphen_obfuscation",
            tier=TIER["soft_hyphen_obfuscation"],
            confidence=0.5,
            description=(
                f"{shy_words} of {words} words are split by soft hyphens. "
                "The text reads normally but no longer matches a keyword "
                "search or filter. Typeset documents hyphenate long words; "
                "this density is unusual."
            ),
            location=location,
            surface=_clip(plain),
            concealed=f"recovered text: {_clip(plain, PAYLOAD_TEXT_LIMIT)!r}",
        ))

    for p in decode_hidden_payloads(value):
        label = _CHANNEL_LABEL[p.channel]
        if p.recognised_format:
            note = (
                f" Its shape matches a {p.recognised_format}. That is "
                "recognition by format only: nothing authenticates it, "
                "and anyone can write the same shape."
            )
        else:
            note = ""
        findings.append(Finding(
            mechanism="invisible_payload_decoded",
            tier=TIER["invisible_payload_decoded"],
            confidence=0.95,
            description=(
                f"{p.carriers} {label} decode to {len(p.text)} "
                f"character(s) of readable text: {_clip(p.text)!r}.{note}"
            ),
            location=location,
            surface="(no visible indication)",
            concealed=f"recovered text: {p.text[:PAYLOAD_TEXT_LIMIT]!r}",
        ))
    return findings


def scan_strings(pairs: Iterable[tuple[str, str]]) -> list[Finding]:
    out: list[Finding] = []
    for value, location in pairs:
        out.extend(scan_string(value, location))
    return out


__all__ = [
    "DecodedPayload", "INVISIBLE_FORMAT_CHARS", "PAYLOAD_TEXT_LIMIT",
    "decode_hidden_payloads", "scan_string", "scan_strings",
]
