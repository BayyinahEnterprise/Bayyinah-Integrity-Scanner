"""
TextFileAnalyzer — zahir-layer witness for plain-text files.

    وَإِذَا قِيلَ لَهُمْ لَا تُفْسِدُوا فِي الْأَرْضِ قَالُوا إِنَّمَا نَحْنُ مُصْلِحُونَ
    أَلَا إِنَّهُمْ هُمُ الْمُفْسِدُونَ وَلَـٰكِن لَّا يَشْعُرُونَ
    (Al-Baqarah 2:11-12)

    "And when it is said to them, 'Do not cause corruption on the
    earth,' they say, 'We are but reformers.' Unquestionably, it is
    they who are the corrupters, but they perceive it not."

Architectural reading. The plain-text layer is where "we are but
reformers" is easiest to say: the file looks innocuous when opened in
any reader, because readers render the visible codepoints and silently
eat the invisible ones. The concealment is then a declaration of
reform paired with a payload that the declaration hides. This analyzer
reads the file's raw codepoint stream and reports every character
whose presence contradicts what the surface shows.

Supported FileKinds: ``MARKDOWN``, ``CODE``, plus any text-family file
the router dispatches here. JSON is handled separately by
``JsonAnalyzer``; HTML and DOCX remain roadmap.

Mechanisms emitted (all ``source_layer='zahir'``):

    zero_width_chars    ZWSP / ZWNJ / ZWJ / WORD JOINER / BOM sitting
                        inside the text stream. Surface hides them;
                        extractor keeps them.
    tag_chars           Codepoints in the Unicode TAG block
                        (U+E0000–U+E007F) — the LLM-prompt-injection
                        vector made famous by Riley Goodside. Invisible
                        on screen, decodable by models.
    bidi_control        RLO/LRO/FSI etc. that can reverse display order
                        while preserving logical order — "evil.doc" and
                        "exe.lave" look the same when the override is
                        in the middle.
    homoglyph           A word mixing scripts such that a non-Latin
                        glyph impersonates a Latin letter (Cyrillic
                        а for a, Greek ο for o, …).

Mechanisms are identical to the PDF zahir set where the detection
logic is shared — the same concealment catalog applies to any rendered
text, PDF or not. Severity, tier, and source_layer come from
``domain.config`` unchanged.

Additive-only. Existing analyzers (``ZahirTextAnalyzer``,
``BatinObjectAnalyzer``) are untouched; this new analyzer declares its
own ``supported_kinds`` and is selected by the registry's Phase 9
kind filter.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, Iterable

from analyzers.base import BaseAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    compute_muwazana_score,
)
from domain.config import (
    BIDI_CONTROL_CHARS,
    CONFUSABLE_TO_LATIN,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Read limit — 8 MB is far beyond any realistic text-injection payload
# and bounds the memory footprint of a single scan.
_MAX_READ_BYTES = 8 * 1024 * 1024

_LATIN_RANGES = (
    range(0x0041, 0x005B),  # A-Z
    range(0x0061, 0x007B),  # a-z
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


def _line_and_column(text: str, index: int) -> tuple[int, int]:
    """Convert a flat string index into 1-based (line, column)."""
    line = text.count("\n", 0, index) + 1
    last_nl = text.rfind("\n", 0, index)
    column = index - last_nl if last_nl >= 0 else index + 1
    return line, column


# ---------------------------------------------------------------------------
# TextFileAnalyzer
# ---------------------------------------------------------------------------


class TextFileAnalyzer(BaseAnalyzer):
    """Detects zahir-layer concealment in raw text files.

    The analyzer reads the file as UTF-8 (errors replaced, so malformed
    bytes do not crash the scan — they are themselves a signal and are
    reported via ``encoding_anomaly`` when present at non-trivial
    volume). Every detected mechanism emits a separate finding per
    occurrence line, so the report is auditable per-location.
    """

    name: ClassVar[str] = "text_file"
    error_prefix: ClassVar[str] = "Text file scan error"
    source_layer: ClassVar[SourceLayer] = "zahir"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({
        FileKind.MARKDOWN,
        FileKind.CODE,
        FileKind.HTML,
    })

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the text file at ``file_path`` for zahir-layer concealment."""
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            return self._scan_error_report(file_path, str(exc))

        if len(data) > _MAX_READ_BYTES:
            data = data[:_MAX_READ_BYTES]

        # Decode as UTF-8. ``replace`` puts U+FFFD in place of every
        # invalid byte so the downstream scans never crash, and so we
        # can count replacements as a signal of binary-in-text smuggling.
        text = data.decode("utf-8", errors="replace")

        findings: list[Finding] = list(self._scan_text(text, file_path))

        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Detection passes
    # ------------------------------------------------------------------

    def _scan_text(self, text: str, file_path: Path) -> Iterable[Finding]:
        yield from self._detect_zero_width(text, file_path)
        yield from self._detect_tag_chars(text, file_path)
        yield from self._detect_bidi_control(text, file_path)
        yield from self._detect_homoglyphs(text, file_path)

    def _detect_zero_width(
        self, text: str, file_path: Path,
    ) -> Iterable[Finding]:
        """One finding per line containing at least one zero-width char.

        Grouping per line keeps the report actionable: a zero-width
        smuggled into a paragraph surfaces one locator the reader can
        grep to, rather than hundreds of per-character findings.
        """
        flagged_lines: dict[int, list[str]] = {}
        for idx, ch in enumerate(text):
            if ch in ZERO_WIDTH_CHARS:
                line, _ = _line_and_column(text, idx)
                flagged_lines.setdefault(line, []).append(ch)
        for line, chars in flagged_lines.items():
            codepoints = ", ".join(sorted({f"U+{ord(c):04X}" for c in chars}))
            yield Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.9,
                description=(
                    f"{len(chars)} zero-width character(s) on this line "
                    f"({codepoints}) — invisible to a human reader, "
                    "preserved by parsers and tokenizers."
                ),
                location=f"{file_path}:{line}",
                surface="(no visible indication)",
                concealed=f"{len(chars)} zero-width codepoint(s)",
                source_layer="zahir",
            )

    def _detect_tag_chars(
        self, text: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Unicode TAG block — the prompt-injection smuggling vector."""
        flagged_lines: dict[int, list[str]] = {}
        for idx, ch in enumerate(text):
            if ord(ch) in TAG_CHAR_RANGE:
                line, _ = _line_and_column(text, idx)
                flagged_lines.setdefault(line, []).append(ch)
        for line, chars in flagged_lines.items():
            # Recover the plain-ASCII shadow — TAG codepoints encode the
            # ASCII character at offset 0xE0000. Showing it makes the
            # payload self-evident to the reader.
            shadow = "".join(
                chr(ord(c) - 0xE0000) if 0x20 <= ord(c) - 0xE0000 <= 0x7E
                else "?"
                for c in chars
            )
            yield Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=1.0,
                description=(
                    f"{len(chars)} Unicode TAG character(s) on this line. "
                    "TAG codepoints are invisible to human readers and "
                    "decodable by LLMs — a documented prompt-injection "
                    f"smuggling vector. Decoded shadow: {shadow!r}."
                ),
                location=f"{file_path}:{line}",
                surface="(no visible indication)",
                concealed=f"TAG payload ({len(chars)} codepoints)",
                source_layer="zahir",
            )

    def _detect_bidi_control(
        self, text: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Bidi-control codepoints that reorder display vs. logical order."""
        flagged_lines: dict[int, list[str]] = {}
        for idx, ch in enumerate(text):
            if ch in BIDI_CONTROL_CHARS:
                line, _ = _line_and_column(text, idx)
                flagged_lines.setdefault(line, []).append(ch)
        for line, chars in flagged_lines.items():
            codepoints = ", ".join(sorted({f"U+{ord(c):04X}" for c in chars}))
            yield Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(chars)} bidi-control character(s) on this line "
                    f"({codepoints}) — reorders display without changing "
                    "the codepoint stream. A Trojan-source pattern."
                ),
                location=f"{file_path}:{line}",
                surface="(reordered display)",
                concealed=f"{len(chars)} bidi-override codepoint(s)",
                source_layer="zahir",
            )

    def _detect_homoglyphs(
        self, text: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Words mixing Latin and lookalike scripts to impersonate letters.

        Mirrors the PDF ``ZahirTextAnalyzer`` heuristic: a word fires
        only if it (a) contains at least one Latin letter AND at least
        one confusable, OR (b) contains two or more confusables. Rule
        (b) catches pure-script words that are still attack candidates
        (a "word" in the wild with multiple Latin-lookalikes is far
        more likely a spoof than genuine non-Latin text) at the cost
        of occasional false positives on short legitimate strings.
        This is a deliberate tradeoff carried over from v0.1.
        """
        # Split on whitespace for word-level detection. Punctuation is
        # retained inside a "word"; the per-char logic ignores it.
        for match_start, word in _iter_words_with_offset(text):
            if len(word) < 2:
                continue
            confusables = [c for c in word if c in CONFUSABLE_TO_LATIN]
            latin_letters = [c for c in word if _is_latin_letter(c)]
            if not confusables:
                continue
            if not (latin_letters or len(confusables) >= 2):
                continue
            line, col = _line_and_column(text, match_start)
            recovered = "".join(
                CONFUSABLE_TO_LATIN.get(c, c) for c in word
            )
            cp_info = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in confusables})
            )
            yield Finding(
                mechanism="homoglyph",
                tier=TIER["homoglyph"],
                confidence=0.85,
                description=(
                    f"Word mixes Latin letters with {len(confusables)} "
                    f"confusable codepoint(s) ({cp_info}) — visually "
                    f"impersonates {recovered!r}."
                ),
                location=f"{file_path}:{line}:{col}",
                surface=word,
                concealed=f"appears identical to {recovered!r}",
                source_layer="zahir",
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iter_words_with_offset(text: str) -> Iterable[tuple[int, str]]:
    """Yield (start_index, word) for every whitespace-separated token.

    Pure Python, deterministic, no regex — keeps the analyzer dependency
    footprint at zero and makes the traversal easy to reason about.
    """
    start: int | None = None
    for idx, ch in enumerate(text):
        if ch.isspace():
            if start is not None:
                yield start, text[start:idx]
                start = None
        else:
            if start is None:
                start = idx
    if start is not None:
        yield start, text[start:]


__all__ = ["TextFileAnalyzer"]
