"""
Tests for analyzers.text_file_analyzer.TextFileAnalyzer.

Phase 9 guardrails. The analyzer applies the zahir-layer concealment
catalog (zero-width, TAG block, bidi-control, homoglyph) to raw text
files. Tests here verify both the positive signal (every adversarial
payload fires the expected mechanism) and the negative signal (clean
text produces zero findings).

Tests live at the analyzer level — integration tests go through
``application.ScanService`` and live in ``tests/test_integration.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzers import TextFileAnalyzer
from analyzers.base import BaseAnalyzer
from domain import Finding, IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(TextFileAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert TextFileAnalyzer.name == "text_file"
    assert TextFileAnalyzer.error_prefix == "Text file scan error"
    assert TextFileAnalyzer.source_layer == "zahir"


def test_supported_kinds_covers_text_family() -> None:
    expected = frozenset({FileKind.MARKDOWN, FileKind.CODE, FileKind.HTML})
    assert TextFileAnalyzer.supported_kinds == expected


def test_supported_kinds_excludes_pdf_and_json() -> None:
    # The router sends PDFs to the PDF analyzers and JSON to JsonAnalyzer;
    # TextFileAnalyzer must stay off those paths.
    assert FileKind.PDF not in TextFileAnalyzer.supported_kinds
    assert FileKind.JSON not in TextFileAnalyzer.supported_kinds


def test_instantiable() -> None:
    a = TextFileAnalyzer()
    assert a.name == "text_file"
    assert "TextFileAnalyzer" in repr(a)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _scan(path: Path) -> IntegrityReport:
    return TextFileAnalyzer().scan(path)


def _mechanisms(report: IntegrityReport) -> list[str]:
    return [f.mechanism for f in report.findings]


# ---------------------------------------------------------------------------
# Clean input
# ---------------------------------------------------------------------------


def test_clean_text_produces_no_findings(tmp_path: Path) -> None:
    p = _write(tmp_path, "clean.md", "# Hello\n\nPlain ASCII paragraph.\n")
    report = _scan(p)
    assert report.findings == []
    assert report.integrity_score == 1.0
    assert not report.scan_incomplete
    assert report.error is None


# ---------------------------------------------------------------------------
# Zero-width
# ---------------------------------------------------------------------------


def test_zero_width_detects_zwsp(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.md", "Hello\u200bWorld\n")
    mechs = _mechanisms(_scan(p))
    assert "zero_width_chars" in mechs


def test_zero_width_finding_is_zahir(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.md", "a\u200bb")
    (f,) = [x for x in _scan(p).findings if x.mechanism == "zero_width_chars"]
    assert f.source_layer == "zahir"
    assert "U+200B" in f.description


def test_zero_width_groups_per_line(tmp_path: Path) -> None:
    # Two zero-widths on the same line → one finding, count reflected
    # in description.
    p = _write(tmp_path, "a.md", "aa\u200bbb\u200bcc")
    zw = [x for x in _scan(p).findings if x.mechanism == "zero_width_chars"]
    assert len(zw) == 1
    assert "2 zero-width" in zw[0].description


# ---------------------------------------------------------------------------
# TAG block
# ---------------------------------------------------------------------------


def test_tag_chars_detects_unicode_tag_block(tmp_path: Path) -> None:
    payload = "".join(chr(0xE0000 + ord(c)) for c in "SECRET")
    p = _write(tmp_path, "a.md", "Hello" + payload)
    mechs = _mechanisms(_scan(p))
    assert "tag_chars" in mechs


def test_tag_chars_decodes_shadow(tmp_path: Path) -> None:
    payload = "".join(chr(0xE0000 + ord(c)) for c in "HIDDEN")
    p = _write(tmp_path, "a.md", payload)
    (f,) = [x for x in _scan(p).findings if x.mechanism == "tag_chars"]
    assert "'HIDDEN'" in f.description


def test_tag_chars_is_tier_1_highest_confidence(tmp_path: Path) -> None:
    payload = "".join(chr(0xE0000 + ord(c)) for c in "X")
    p = _write(tmp_path, "a.md", payload)
    (f,) = [x for x in _scan(p).findings if x.mechanism == "tag_chars"]
    assert f.tier == 1
    assert f.confidence == 1.0


# ---------------------------------------------------------------------------
# Bidi control
# ---------------------------------------------------------------------------


def test_bidi_control_detects_rlo(tmp_path: Path) -> None:
    # U+202E embedded in source — the Trojan Source pattern.
    p = _write(tmp_path, "a.py", "user" + "\u202E" + "admin\n")
    mechs = _mechanisms(_scan(p))
    assert "bidi_control" in mechs


# ---------------------------------------------------------------------------
# Homoglyph
# ---------------------------------------------------------------------------


def test_homoglyph_detects_cyrillic_a(tmp_path: Path) -> None:
    # 'admin' with Cyrillic 'а' (U+0430) replacing the Latin 'a'.
    p = _write(tmp_path, "a.md", "Welcome, \u0430dmin.")
    mechs = _mechanisms(_scan(p))
    assert "homoglyph" in mechs


def test_homoglyph_recovers_visible_string(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.md", "\u0430dmin")
    (f,) = [x for x in _scan(p).findings if x.mechanism == "homoglyph"]
    assert "'admin'" in f.description
    assert f.source_layer == "zahir"


def test_homoglyph_does_not_fire_without_confusables(tmp_path: Path) -> None:
    # Cyrillic word whose letters are NOT in the confusables table
    # (я, з, ы, к — none impersonate Latin). No firing expected.
    p = _write(tmp_path, "a.md", "\u044F\u0437\u044B\u043A")
    mechs = _mechanisms(_scan(p))
    assert "homoglyph" not in mechs


def test_homoglyph_fires_on_multi_confusable_word(tmp_path: Path) -> None:
    # Pure Cyrillic word with 2+ confusables (р, у, с) — the detector
    # treats this as impersonation since any single word with multiple
    # Latin-lookalikes is more likely an attack than genuine Russian.
    # This mirrors v0.1's ZahirTextAnalyzer PDF-side behaviour.
    p = _write(tmp_path, "a.md", "\u0440\u0443\u0441\u0441")
    mechs = _mechanisms(_scan(p))
    assert "homoglyph" in mechs


# ---------------------------------------------------------------------------
# Read error path
# ---------------------------------------------------------------------------


def test_missing_file_returns_scan_error_report(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.md"
    report = _scan(missing)
    assert report.scan_incomplete
    assert report.error is not None
    assert report.error.startswith("Text file scan error")
    assert [f.mechanism for f in report.findings] == ["scan_error"]
    assert report.findings[0].source_layer == "zahir"


# ---------------------------------------------------------------------------
# Integration on Phase 9 fixtures
# ---------------------------------------------------------------------------


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "text_formats"
)


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("clean/clean.md", []),
        ("clean/clean.py", []),
        ("adversarial/zero_width.md", ["zero_width_chars"]),
        ("adversarial/tag_chars.md", ["tag_chars"]),
        ("adversarial/bidi_control.py", ["bidi_control"]),
        ("adversarial/homoglyph.md", ["homoglyph"]),
    ],
)
def test_fixture_fires_exactly_expected(rel: str, expected: list[str]) -> None:
    path = FIXTURE_ROOT / rel
    if not path.exists():
        pytest.skip(f"fixture {rel} not yet generated")
    report = _scan(path)
    observed = sorted({f.mechanism for f in report.findings})
    assert observed == sorted(expected), (
        f"{rel}: expected {expected}, got {observed}"
    )
