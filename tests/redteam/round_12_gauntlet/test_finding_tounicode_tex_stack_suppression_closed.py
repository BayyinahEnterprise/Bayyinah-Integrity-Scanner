"""Round 12 HIGH 2 closure: tounicode_anomaly TeX-stack suppression.

When /Info /Producer indicates a TeX-stack producer (pdfTeX, XeTeX,
LuaTeX, dvips, dvipdfmx) AND the flagged anomaly matches a canonical
TeX pattern (Greek-block target in math fonts, or ZWNJ at OT1 slot
0x17), the finding is suppressed. Documents whose producer claims
TeX but whose CMap carries non-canonical anomalies (Cyrillic
homoglyphs, ZWJ, bidi control, TAG) still fire.
"""
from __future__ import annotations
from pathlib import Path
import pytest
from bayyinah import scan_pdf
from analyzers.object_analyzer import BatinObjectAnalyzer

CORPUS = Path(__file__).parent


def test_tex_producer_detection_matches_pdftex():
    assert BatinObjectAnalyzer._is_tex_stack_producer("pdfTeX-1.40.27")
    assert BatinObjectAnalyzer._is_tex_stack_producer(
        "pdfTeX-1.40.22 (TeX Live 2022/Debian)"
    )
    assert BatinObjectAnalyzer._is_tex_stack_producer("XeTeX 0.99996")
    assert BatinObjectAnalyzer._is_tex_stack_producer("LuaTeX, Version 1.18.0")
    assert BatinObjectAnalyzer._is_tex_stack_producer("dvips(k) 5.999")
    assert BatinObjectAnalyzer._is_tex_stack_producer("dvipdfmx-20210318")


def test_tex_producer_detection_rejects_other_producers():
    assert not BatinObjectAnalyzer._is_tex_stack_producer("LibreOffice 26.2")
    assert not BatinObjectAnalyzer._is_tex_stack_producer("Microsoft Word")
    assert not BatinObjectAnalyzer._is_tex_stack_producer("Adobe Acrobat 11.0")
    assert not BatinObjectAnalyzer._is_tex_stack_producer("")
    assert not BatinObjectAnalyzer._is_tex_stack_producer(None)


def test_tex_canonical_greek_homoglyph_is_suppressed():
    """Greek capital Gamma (U+0393) in a math font is canonical."""
    canon = BatinObjectAnalyzer._is_tex_canonical_anomaly
    assert canon("<07>-<08>", "Υ", "homoglyph U+03A5 (looks like 'Y')")
    assert canon("<0B>-<0E>", "α", "homoglyph U+03B1 (looks like 'a')")
    # Multi-character Greek run: also canonical.
    assert canon("<00>", "Γ", "homoglyph U+0393 (looks like 'G')")


def test_tex_canonical_ot1_zwnj_at_slot_17_is_suppressed():
    """OT1 slot 0x17 mapped to ZWNJ (U+200C) is documented pdfTeX."""
    canon = BatinObjectAnalyzer._is_tex_canonical_anomaly
    assert canon("<17>", "‌", "zero-width U+200C")


def test_non_canonical_zwnj_at_other_slot_still_fires():
    """ZWNJ at any slot OTHER than 0x17 is not canonical OT1."""
    canon = BatinObjectAnalyzer._is_tex_canonical_anomaly
    assert not canon("<41>", "‌", "zero-width U+200C")  # 0x41 = 'A'
    assert not canon("<00>", "‌", "zero-width U+200C")


def test_cyrillic_homoglyph_still_fires_under_tex_producer():
    """Cyrillic capital A (U+0410) is not a Greek-block target;
    the TeX stack does not emit it. Even with a TeX producer,
    this remains flagged."""
    canon = BatinObjectAnalyzer._is_tex_canonical_anomaly
    # Cyrillic A is in U+0400 range, outside U+0370-U+03FF Greek block.
    assert not canon("<41>", "А", "homoglyph U+0410 (looks like 'A')")


def test_pdftex_article_fixture_returns_sahih():
    """Empirical: the canonical pdfTeX article fixture verdicts sahih."""
    p = CORPUS / "fixture_clean_pdftex_article.pdf"
    if not p.exists():
        pytest.skip("fixture not regenerated")
    rd = scan_pdf(p).to_dict()
    findings = rd.get("findings", [])
    tounicode_findings = [
        f for f in findings if f.get("mechanism") == "tounicode_anomaly"
    ]
    assert tounicode_findings == [], (
        f"tounicode_anomaly fired on canonical pdftex output: "
        f"{tounicode_findings}"
    )


def test_pdftex_with_hyperref_fixture_returns_sahih():
    """The hyperref fixture combines both bug classes; both close."""
    p = CORPUS / "fixture_clean_pdftex_with_hyperref.pdf"
    if not p.exists():
        pytest.skip("fixture not regenerated")
    rd = scan_pdf(p).to_dict()
    assert rd.get("integrity_score") == 1.0, (
        f"score should be 1.0 after both fixes, got "
        f"{rd.get('integrity_score')}; findings={rd.get('findings')}"
    )
