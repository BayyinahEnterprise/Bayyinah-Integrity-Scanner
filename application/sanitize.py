"""Cleaning mode: return a copy of a text file with hidden content removed.

The scanner says what is hidden. This module removes it, for the file
families whose content is text (plain text, Markdown, source code, CSV,
JSON, HTML, XML, logs), and writes a receipt that binds the original to
the cleaned copy so the step can be audited later.

What is removed
---------------
* zero-width characters that orthography does not explain (Persian,
  Indic, Thai and emoji uses are kept: removing them would damage the
  text)
* Unicode TAG characters
* bidirectional embedding, override and isolate controls
* runs of variation selectors
* invisible format characters (invisible operators, annotation
  controls, filler letters)
* terminal escape sequences and C0 / C1 control characters other than
  tab, line feed and carriage return
* soft hyphens, when their density marks them as obfuscation

What is not changed
-------------------
* Lookalike letters. Replacing a Cyrillic letter with a Latin one
  rewrites the author's text; the scanner reports them instead.
* Anything in a binary container (PDF, Office, images). Use the scan
  report for those. This is stated in the receipt, never implied.

The approach follows the two-phase sanitizer in the FATIMA encoder
(terminal channel first, then the invisible-character channel), with
two differences: orthographic characters are preserved, and zero-width
and direction controls are removed rather than left in place.

A cleaned file is not a certified file. Cleaning removes the channels
listed above; it cannot remove an instruction written in plain sight.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from analyzers.invisible_text import (
    _SHY_MIN_WORDS,
    _SHY_WORD_SHARE,
    INVISIBLE_FORMAT_CHARS,
    SOFT_HYPHEN,
    _soft_hyphen_words,
    _vs_runs,
    decode_hidden_payloads,
)
from domain.config import BIDI_CONTROL_CHARS, TAG_CHAR_RANGE, ZERO_WIDTH_CHARS
from domain.script_awareness import suspicious_zero_width_indices

RECEIPT_SCHEMA: Final[str] = "bayyinah.clean-receipt/1"

TEXT_SUFFIXES: Final[frozenset[str]] = frozenset({
    ".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".jsonl",
    ".html", ".htm", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".log", ".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".h",
    ".cpp", ".cs", ".rb", ".php", ".sh", ".sql", ".tex", ".srt", ".vtt",
})

_ANSI_ANY: Final[re.Pattern[str]] = re.compile(
    r"(?:\x1b\[|\x9b)[0-9;:?<=>]*[@-~]"
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"
    r"|\x1b[@-Z\\-_]"
)
_KEEP_CONTROLS: Final[frozenset[str]] = frozenset("\t\n\r")
_ZW_ALL: Final[frozenset[str]] = frozenset(ZERO_WIDTH_CHARS) | {"﻿"}


class NotATextFile(ValueError):
    """The file is not one of the text families cleaning mode handles."""


@dataclass
class CleanResult:
    text: str
    removed: dict[str, int] = field(default_factory=dict)
    kept_orthographic: int = 0
    decoded_payloads: list[dict] = field(default_factory=list)

    @property
    def total_removed(self) -> int:
        return sum(self.removed.values())


def clean_text(text: str) -> CleanResult:
    """Remove hidden content from ``text``. Pure; no file access."""
    removed: dict[str, int] = {}

    def note(kind: str, n: int) -> None:
        if n:
            removed[kind] = removed.get(kind, 0) + n

    # What the hidden channels said, recorded before they are removed.
    payloads = [
        {"channel": p.channel, "characters": p.carriers,
         "recognised_format": p.recognised_format,
         "sha256": hashlib.sha256(p.text.encode("utf-8")).hexdigest(),
         "preview": p.text[:200]}
        for p in decode_hidden_payloads(text)
    ]

    # Phase 1: the terminal channel.
    text, n = _ANSI_ANY.subn("", text)
    note("terminal_escape_sequences", n)

    # Phase 2: the invisible-character channel. Indices are computed on
    # the text as it stands so orthographic context is judged correctly.
    drop: set[int] = set()
    zw = set(suspicious_zero_width_indices(
        text, _ZW_ALL, bom_at_start_ok=True))
    all_zw = sum(1 for c in text if c in _ZW_ALL)
    drop |= zw
    note("zero_width_characters", len(zw))
    kept = all_zw - len(zw)

    for start, length in _vs_runs(text):
        drop.update(range(start, start + length))
        note("variation_selectors", length)

    shy_words, words = _soft_hyphen_words(text)
    strip_shy = (shy_words >= _SHY_MIN_WORDS and words
                 and shy_words / words >= _SHY_WORD_SHARE)

    out: list[str] = []
    for i, ch in enumerate(text):
        if i in drop:
            continue
        cp = ord(ch)
        if cp in TAG_CHAR_RANGE:
            note("tag_characters", 1)
        elif ch in BIDI_CONTROL_CHARS:
            note("bidi_controls", 1)
        elif cp in INVISIBLE_FORMAT_CHARS:
            note("invisible_format_characters", 1)
        elif (cp < 0x20 and ch not in _KEEP_CONTROLS) or 0x7F <= cp <= 0x9F:
            note("control_characters", 1)
        elif strip_shy and ch == SOFT_HYPHEN:
            note("soft_hyphens", 1)
        else:
            out.append(ch)
    return CleanResult("".join(out), removed, kept, payloads)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def clean_file(
    source: Path, destination: Path | None = None, *,
    receipt_path: Path | None = None, force: bool = False,
) -> dict:
    """Clean ``source`` into ``destination`` and write a receipt.

    The source is never modified. Returns the receipt as a dict. The
    cleaned copy is scanned again and the count of findings that remain
    is recorded, so the receipt states what cleaning did not resolve.
    """
    source = Path(source)
    if source.suffix.lower() not in TEXT_SUFFIXES and not force:
        raise NotATextFile(
            f"{source.suffix or '(no extension)'} is not a text format. "
            "Cleaning mode handles text files only; scan binary containers "
            "(PDF, Office, images) and review the report instead."
        )
    raw = source.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise NotATextFile(f"{source} is not valid UTF-8 text: {exc}") from exc
    had_bom = text.startswith("﻿")
    result = clean_text(text)
    cleaned = result.text.encode("utf-8")

    destination = Path(destination) if destination else source.with_name(
        f"{source.stem}.clean{source.suffix}")
    if destination.resolve() == source.resolve():
        raise ValueError("destination must differ from source")
    destination.write_bytes(cleaned)

    from bayyinah import __version__, scan_file
    before = scan_file(source)
    after = scan_file(destination)

    def summary(report) -> dict:
        counts: dict[str, int] = {}
        for f in report.findings:
            counts[f.mechanism] = counts.get(f.mechanism, 0) + 1
        return {"findings": len(report.findings), "by_mechanism": counts,
                "integrity_score": round(report.integrity_score, 4)}

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "tool": "bayyinah",
        "tool_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"name": source.name, "bytes": len(raw), "sha256": _sha256(raw)},
        "cleaned": {"name": destination.name, "bytes": len(cleaned),
                    "sha256": _sha256(cleaned)},
        "removed": dict(sorted(result.removed.items())),
        "total_removed": result.total_removed,
        "kept_orthographic_zero_width": result.kept_orthographic,
        "leading_bom_kept": had_bom and result.text.startswith("﻿"),
        "hidden_payloads_removed": result.decoded_payloads,
        "scan_before": summary(before),
        "scan_after": summary(after),
        "not_changed": [
            "lookalike letters (reported by the scanner, not rewritten)",
            "anything written in visible text",
        ],
        "statement": (
            "This receipt records what was removed. It is not a "
            "certificate that the cleaned file is safe, and it is not "
            "signed: it shows integrity of the pair of files, not who "
            "produced them."
        ),
    }
    receipt_path = Path(receipt_path) if receipt_path else destination.with_name(
        destination.name + ".receipt.json")
    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    receipt["receipt_path"] = str(receipt_path)
    receipt["cleaned_path"] = str(destination)
    return receipt


__all__ = [
    "CleanResult", "NotATextFile", "RECEIPT_SCHEMA", "TEXT_SUFFIXES",
    "clean_file", "clean_text",
]
