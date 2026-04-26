"""
JsonAnalyzer — both witnesses at once for JSON documents.

    قَالُوا إِنَّمَا نَحْنُ مُصْلِحُونَ أَلَا إِنَّهُمْ هُمُ الْمُفْسِدُونَ
    وَلَـٰكِن لَّا يَشْعُرُونَ
    (Al-Baqarah 2:11-12)

Architectural reading. A JSON document is TWO surfaces at once:

  * A rendered surface — the string values a human reads when a tool
    pretty-prints the document.
  * A structural surface — the object graph a machine consumes: keys,
    nesting depth, key ordering, duplicates.

Munafiq concealment can hide in either. A ``message`` string can carry
zero-width chars or TAG codepoints that only the downstream tokenizer
sees. The object graph can carry a second copy of an important key
(``{"admin": false, "admin": true}``) where one parser returns the
first occurrence and another returns the second — the same document
exhibits two different meanings for two different readers. Excessive
nesting can exhaust naive parsers while surface-inspecting clean.

``JsonAnalyzer`` is therefore *both* a batin witness (structural) and
a zahir witness (string-value content). The finding's ``source_layer``
is set per-mechanism:

    duplicate_keys, excessive_nesting     → batin
    zero_width_chars, tag_chars,          → zahir
    bidi_control, homoglyph
    scan_error (parse failure)            → batin (class default)

``supported_kinds`` is ``{FileKind.JSON}``. Code files that happen to
contain JSON are out of scope — the router only sends real JSON here.

Additive-only. Nothing in this module is imported by ``bayyinah_v0.py``
or ``bayyinah_v0_1.py``; the PDF pipeline is untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar, Iterable

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

# Read limit — 8 MB bounds the memory footprint of a single JSON scan.
# Legitimate configuration / data files are well below this.
_MAX_READ_BYTES = 8 * 1024 * 1024

# Nesting depth at which we emit a single ``excessive_nesting`` finding.
# Hand-authored JSON rarely exceeds ~10; 32 is a conservative threshold
# that avoids false positives on typical API payloads while still
# flagging parser-exhaustion attacks.
_EXCESSIVE_NESTING_THRESHOLD = 32

_LATIN_RANGES = (
    range(0x0041, 0x005B),  # A-Z
    range(0x0061, 0x007B),  # a-z
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


# ---------------------------------------------------------------------------
# JsonAnalyzer
# ---------------------------------------------------------------------------


class JsonAnalyzer(BaseAnalyzer):
    """Detects structural and embedded concealment in JSON files.

    The analyzer parses the file with ``json.loads`` and a custom
    ``object_pairs_hook`` that records every key-pair (not only the
    winning one) so duplicate keys are detectable. After parsing, it
    walks the tree: every string value gets the zahir zero-width / TAG /
    bidi-control / homoglyph scans; every object contributes to the
    depth and duplicate-key tallies.

    Malformed JSON is converted into a single ``scan_error`` finding via
    the inherited ``_scan_error_report`` helper — consistent with the
    middle-community contract (Al-Baqarah 2:143): one witness failing
    does not silence the others, and the failure itself is a signal.
    """

    name: ClassVar[str] = "json_file"
    error_prefix: ClassVar[str] = "JSON scan error"
    # Class default — batin — applies to ``scan_error`` findings emitted
    # via the base-class helper. Per-finding source_layer is set
    # individually for the zahir string-value scans below.
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.JSON})

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the JSON file at ``file_path`` for structural and embedded
        concealment."""
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            return self._scan_error_report(file_path, str(exc))

        if len(data) > _MAX_READ_BYTES:
            data = data[:_MAX_READ_BYTES]

        # Decode strictly — a JSON file with invalid UTF-8 is itself a
        # signal, and we surface it as a scan_error. The BOM case is the
        # only exception: RFC 7159 recommends parsers silently consume
        # a leading BOM, and ``json.loads`` does too, so we don't treat
        # one as a fatal decode error.
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            return self._scan_error_report(
                file_path,
                f"invalid UTF-8 in JSON file: {exc}",
            )

        # Parse with the duplicate-key-capturing hook.
        captured_duplicates: list[tuple[tuple[Any, ...], str]] = []

        def _pairs_hook(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            seen: dict[str, int] = {}
            for key, _ in pairs:
                seen[key] = seen.get(key, 0) + 1
            for key, count in seen.items():
                if count > 1:
                    # Path is recovered post-hoc; we only know the local
                    # object shape here. The walker annotates path context
                    # during the recursive walk — hook just reports the
                    # key and duplicate count.
                    captured_duplicates.append(((key,), f"count={count}"))
            # Later occurrence wins by convention — this matches Python
            # dict semantics and the majority of JSON parsers.
            return dict(pairs)

        try:
            tree = json.loads(text, object_pairs_hook=_pairs_hook)
        except json.JSONDecodeError as exc:
            return self._scan_error_report(
                file_path,
                f"could not parse JSON: {exc.msg} at line {exc.lineno} "
                f"column {exc.colno}",
            )

        findings: list[Finding] = []

        # ---- Structural (batin) ----
        findings.extend(self._emit_duplicate_keys(
            captured_duplicates, file_path,
        ))
        findings.extend(self._detect_excessive_nesting(tree, file_path))

        # ---- Embedded string-value zahir scans ----
        for path, value in _walk_strings(tree):
            if not isinstance(value, str):
                continue
            findings.extend(self._scan_string_value(
                value, path, file_path,
            ))

        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Structural (batin) detectors
    # ------------------------------------------------------------------

    def _emit_duplicate_keys(
        self,
        captured: list[tuple[tuple[Any, ...], str]],
        file_path: Path,
    ) -> Iterable[Finding]:
        """One finding per duplicate-key occurrence captured at parse time.

        The hook fired at the *local* object scope so the key is known
        but the full JSON pointer is not. We report the key and count;
        the reader can grep the document to locate the occurrences.
        """
        for (key, *_), detail in captured:
            yield Finding(
                mechanism="duplicate_keys",
                tier=TIER["duplicate_keys"],
                confidence=1.0,
                description=(
                    f"Duplicate key {key!r} in a JSON object ({detail}). "
                    "Different parsers may resolve duplicates differently "
                    "— the document presents different meanings to "
                    "different readers."
                ),
                location=f"{file_path}:{key}",
                surface=f"key {key!r} (later value wins in most parsers)",
                concealed="earlier occurrence(s) silently shadowed",
                source_layer="batin",
            )

    def _detect_excessive_nesting(
        self, tree: Any, file_path: Path,
    ) -> Iterable[Finding]:
        """Single finding if the tree exceeds ``_EXCESSIVE_NESTING_THRESHOLD``.

        Deep nesting is cheap to author and expensive to parse; many
        parser-exhaustion attacks ride on this. Legitimate documents
        almost never reach the threshold.
        """
        depth = _max_depth(tree)
        if depth >= _EXCESSIVE_NESTING_THRESHOLD:
            yield Finding(
                mechanism="excessive_nesting",
                tier=TIER["excessive_nesting"],
                confidence=0.9,
                description=(
                    f"JSON tree reaches depth {depth}, at or above the "
                    f"{_EXCESSIVE_NESTING_THRESHOLD} threshold. Deeply "
                    "nested documents are a known parser-exhaustion "
                    "vector and rarely appear in hand-authored data."
                ),
                location=f"{file_path}:root",
                surface=f"nested depth {depth}",
                concealed="potential parser-exhaustion payload",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Embedded zahir scan (per string value)
    # ------------------------------------------------------------------

    def _scan_string_value(
        self,
        value: str,
        json_path: str,
        file_path: Path,
    ) -> Iterable[Finding]:
        """Apply the zahir-layer checks to a single JSON string value.

        Each mechanism surfaces at most once per string value — the
        ``location`` field carries the JSON pointer so the reader can
        navigate directly to the offending key.
        """
        location_prefix = f"{file_path}@{json_path}"

        # Zero-width characters.
        zw = [c for c in value if c in ZERO_WIDTH_CHARS]
        if zw:
            codepoints = ", ".join(sorted({f"U+{ord(c):04X}" for c in zw}))
            yield Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.9,
                description=(
                    f"{len(zw)} zero-width character(s) in this string "
                    f"value ({codepoints}) — invisible to a human "
                    "reader, preserved by parsers and tokenizers."
                ),
                location=location_prefix,
                surface="(no visible indication)",
                concealed=f"{len(zw)} zero-width codepoint(s)",
                source_layer="zahir",
            )

        # TAG block — prompt-injection vector.
        tags = [c for c in value if ord(c) in TAG_CHAR_RANGE]
        if tags:
            shadow = "".join(
                chr(ord(c) - 0xE0000) if 0x20 <= ord(c) - 0xE0000 <= 0x7E
                else "?"
                for c in tags
            )
            yield Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=1.0,
                description=(
                    f"{len(tags)} Unicode TAG character(s) in this "
                    "string value. TAG codepoints are invisible to "
                    "human readers and decodable by LLMs — a "
                    "documented prompt-injection smuggling vector. "
                    f"Decoded shadow: {shadow!r}."
                ),
                location=location_prefix,
                surface="(no visible indication)",
                concealed=f"TAG payload ({len(tags)} codepoints)",
                source_layer="zahir",
            )

        # Bidi-control.
        bidi = [c for c in value if c in BIDI_CONTROL_CHARS]
        if bidi:
            codepoints = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in bidi})
            )
            yield Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(bidi)} bidi-control character(s) in this "
                    f"string value ({codepoints}) — reorders display "
                    "without changing the codepoint stream."
                ),
                location=location_prefix,
                surface="(reordered display)",
                concealed=f"{len(bidi)} bidi-override codepoint(s)",
                source_layer="zahir",
            )

        # Homoglyph — word-level mix of Latin + confusable.
        for word in value.split():
            if len(word) < 2:
                continue
            confusables = [c for c in word if c in CONFUSABLE_TO_LATIN]
            latin_letters = [c for c in word if _is_latin_letter(c)]
            if not confusables:
                continue
            if not (latin_letters or len(confusables) >= 2):
                continue
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
                location=location_prefix,
                surface=word,
                concealed=f"appears identical to {recovered!r}",
                source_layer="zahir",
            )


# ---------------------------------------------------------------------------
# Tree walkers
# ---------------------------------------------------------------------------


def _walk_strings(
    tree: Any, path: str = "$",
) -> Iterable[tuple[str, str]]:
    """Yield (json_pointer, string_value) for every string in the tree.

    Uses a simple JSONPath-like dotted notation:

        $            — root
        $.key        — object member
        $[0]         — array element

    A dict/list with mixed content yields the strings only; nested
    containers recurse.
    """
    if isinstance(tree, str):
        yield path, tree
    elif isinstance(tree, dict):
        for key, value in tree.items():
            subpath = f"{path}.{key}"
            yield from _walk_strings(value, subpath)
    elif isinstance(tree, list):
        for idx, value in enumerate(tree):
            subpath = f"{path}[{idx}]"
            yield from _walk_strings(value, subpath)
    # Primitives (int, float, bool, None) carry no string surface.


def _max_depth(tree: Any, current: int = 0) -> int:
    """Deepest nesting in the tree, counted by container levels.

    A bare primitive is depth 0, ``{}`` and ``[]`` are depth 1, and so
    on. Deterministic, pure, no stack-overflow guard — ``json.loads``
    already enforces CPython's recursion limit when it parses, so a
    tree we can iterate we can also measure.
    """
    if isinstance(tree, dict):
        if not tree:
            return current + 1
        return max(_max_depth(v, current + 1) for v in tree.values())
    if isinstance(tree, list):
        if not tree:
            return current + 1
        return max(_max_depth(v, current + 1) for v in tree)
    return current


__all__ = ["JsonAnalyzer"]
