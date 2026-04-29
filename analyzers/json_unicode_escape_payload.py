"""
json_unicode_escape_payload -- v1.1.2 F2 mechanism 8.

Al-Baqarah 2:42 applied to the JSON string-escape grammar. JSON
permits ``\\uXXXX`` and ``\\UXXXXXXXX`` escape sequences in string
literals. Strict-JSON parsers decode them silently. The decoded
codepoint may be a bidi-override or zero-width character that the
existing v1.1.1 ``bidi_control`` and ``zero_width_chars`` mechanisms
catch when present as a literal codepoint.

The escape form bypasses those mechanisms. The raw byte stream
contains ASCII text (``\\u202E``); the decoded string carries the
hidden codepoint. The detection must run on the pre-parse byte
stream and decode each escape itself, not rely on the post-parse
string walk.

Detector contract (per docs/adversarial/csv_json_gauntlet/REPORT.md
and bayyinah_v1_1_2_f2_plan_v2.md Section 3.8):

  * Decode the file bytes as UTF-8 with errors='replace'.
  * Find every ``\\uXXXX`` and ``\\UXXXXXXXX`` escape sequence in the
    raw text using a regex.
  * For each escape, decode the codepoint integer.
  * If the codepoint falls in the bidi-override range (U+202A,
    U+202B, U+202C, U+202D, U+202E, U+2066, U+2067, U+2068, U+2069)
    or the zero-width range (U+200B, U+200C, U+200D, U+FEFF), emit
    a Tier 1 batin finding.

Tier 1 batin (parser-invisible structural concealment). The escape
sequence is hidden from any post-parse string walk because the
parser silently decodes it. The byte stream carries the truth; the
parsed object carries the deception.

Severity 0.20. Same calibration as csv_zero_width_payload and
csv_bidi_payload: a single escape decoding to a known concealment
codepoint is high-precision evidence of intent.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19700420.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Read limit. Same 8 MB ceiling the JsonAnalyzer enforces.
_MAX_READ_BYTES = 8 * 1024 * 1024

# Bidi-override codepoints: visible reorder hazards. The set matches
# the existing v1.1.1 BIDI_CONTROL_CHARS in domain/config.py so the
# escape form catches exactly what the literal form catches.
_BIDI_CODEPOINTS: frozenset[int] = frozenset({
    0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    0x2066, 0x2067, 0x2068, 0x2069,
})

# Zero-width codepoints: invisible-to-human concealment characters.
# Matches v1.1.1 ZERO_WIDTH_CHARS in domain/config.py.
_ZERO_WIDTH_CODEPOINTS: frozenset[int] = frozenset({
    0x200B, 0x200C, 0x200D, 0xFEFF,
})

# Combined target set for fast membership testing.
_TARGET_CODEPOINTS: frozenset[int] = (
    _BIDI_CODEPOINTS | _ZERO_WIDTH_CODEPOINTS
)

# Escape sequence regex. Matches:
#   \uXXXX     -- BMP escape (4 hex digits)
#   \UXXXXXXXX -- non-BMP escape (8 hex digits, rarely used in JSON
#                  but accepted by some lenient parsers)
# An even number of preceding backslashes confirms the sequence is
# not itself escaped (``\\u202E`` is a literal backslash + literal
# 'u202E', not a unicode escape).
_ESCAPE_RE = re.compile(
    r"(?<!\\)(?:\\\\)*\\u([0-9A-Fa-f]{4})"
    r"|(?<!\\)(?:\\\\)*\\U([0-9A-Fa-f]{8})"
)


# ---------------------------------------------------------------------------
# Codepoint classifier
# ---------------------------------------------------------------------------


def _classify_codepoint(cp: int) -> str | None:
    """Return ``'bidi'`` / ``'zero_width'`` / None for the codepoint."""
    if cp in _BIDI_CODEPOINTS:
        return "bidi"
    if cp in _ZERO_WIDTH_CODEPOINTS:
        return "zero_width"
    return None


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_unicode_escape_payload(
    text: str,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield json_unicode_escape_payload findings for the given JSON text.

    ``text`` is the file bytes already decoded as UTF-8 with
    ``errors='replace'``. ``file_path`` is the source path used in
    finding ``location`` strings. The function never raises; a regex
    that matches no escapes simply yields nothing.
    """
    for match in _ESCAPE_RE.finditer(text):
        # Group 1 is the 4-hex BMP escape; group 2 is the 8-hex form.
        hex_str = match.group(1) or match.group(2) or ""
        if not hex_str:
            continue
        try:
            cp = int(hex_str, 16)
        except ValueError:
            # Regex guarantees hex digits but defensive.
            continue
        kind = _classify_codepoint(cp)
        if kind is None:
            continue
        escape_form = match.group(0)
        # Approximate line/column for the reader. Counting newlines
        # in text[:match.start()] is O(N) but the file is bounded.
        prefix = text[: match.start()]
        line = prefix.count("\n") + 1
        col = match.start() - (prefix.rfind("\n") if "\n" in prefix else -1)
        kind_label = "bidi-override" if kind == "bidi" else "zero-width"
        yield Finding(
            mechanism="json_unicode_escape_payload",
            tier=TIER["json_unicode_escape_payload"],
            confidence=0.95,
            description=(
                f"JSON escape sequence {escape_form!r} at line {line} "
                f"column {col} decodes to U+{cp:04X}, a known "
                f"{kind_label} codepoint. The escape form bypasses "
                f"the v1.1.1 post-parse string walk: the raw byte "
                f"stream is ASCII, the decoded string carries the "
                f"hidden codepoint."
            ),
            location=f"{file_path}:line={line},column={col}",
            surface=f"escape sequence {escape_form!r} (renders invisibly)",
            concealed=(
                f"escape {escape_form!r} decodes to U+{cp:04X} "
                f"({kind_label})"
            ),
            source_layer="batin",
        )


__all__ = ["detect_unicode_escape_payload"]
