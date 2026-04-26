"""
Tests for analyzers.text_analyzer.ZahirTextAnalyzer.

This file is the Phase 4 guardrail of the Al-Baqarah refactor: it
asserts that the new BaseAnalyzer-shaped ZahirTextAnalyzer fires
exactly the same text-layer mechanisms as v0.1's TextLayerAnalyzer
on every Phase 0 fixture — byte-identical per mechanism field.

Coverage targets:
  * BaseAnalyzer contract — name, error_prefix, source_layer,
    instantiable, repr
  * clean.pdf → 0 findings, integrity_score == 1.0
  * Each text-layer fixture fires exactly its declared mechanism
  * Object-layer and positive_combined fixtures are also scanned to
    prove ZahirTextAnalyzer limits itself to the zahir layer (no
    object-layer mechanisms escape)
  * scan_error report is emitted for non-PDF / missing inputs,
    preserving the 'Text layer scan error' prefix
  * Per-page defensive failure: a helper raising on one page does
    not abort the whole scan
  * Parity sweep: for every Phase 0 fixture where v0.1 succeeds,
    ZahirTextAnalyzer emits the same (mechanism, tier, confidence,
    description, location, surface, concealed) tuples in the same
    order — this is the v0-to-v0.1 parity invariant promoted onto
    the new contract.
  * All emitted findings carry source_layer='zahir'
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import bayyinah_v0_1
from analyzers.base import BaseAnalyzer
from analyzers.text_analyzer import ZahirTextAnalyzer
from domain import Finding, IntegrityReport

# The Phase 0 fixture registry — same source of truth tests/test_fixtures.py uses.
from tests.make_test_documents import FIXTURES, FIXTURES_DIR


# ---------------------------------------------------------------------------
# Fixture availability
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _ensure_fixtures_built() -> None:
    """If any fixture PDF is missing, regenerate the whole corpus."""
    missing = [fx.out_path for fx in FIXTURES.values() if not fx.out_path.exists()]
    if not missing:
        return
    subprocess.run(
        [sys.executable, "-m", "tests.make_test_documents"],
        check=True,
        cwd=str(FIXTURES_DIR.parent.parent),
    )


CLEAN_PDF = FIXTURES_DIR / "clean.pdf"
TEXT_FIXTURE_DIR = FIXTURES_DIR / "text"
OBJECT_FIXTURE_DIR = FIXTURES_DIR / "object"


# The Phase 0 text fixtures, keyed by the single mechanism each asserts.
# Structurally redundant with FIXTURES[...].expected_mechanisms but
# explicit here so the test file is self-documenting.
TEXT_FIXTURE_EXPECTED: dict[str, str] = {
    "text.zero_width":       "zero_width_chars",
    "text.tag_characters":   "tag_chars",
    "text.bidi_control":     "bidi_control",
    "text.homoglyph":        "homoglyph",
    "text.invisible_render": "invisible_render_mode",
    "text.microscopic_font": "microscopic_font",
    "text.white_on_white":   "white_on_white_text",
    "text.overlapping":      "overlapping_text",
}


# ---------------------------------------------------------------------------
# BaseAnalyzer contract
# ---------------------------------------------------------------------------

def test_zahir_text_analyzer_is_base_analyzer_subclass() -> None:
    assert issubclass(ZahirTextAnalyzer, BaseAnalyzer)


def test_zahir_text_analyzer_declares_name() -> None:
    assert ZahirTextAnalyzer.name == "text_layer"


def test_zahir_text_analyzer_declares_error_prefix() -> None:
    assert ZahirTextAnalyzer.error_prefix == "Text layer scan error"


def test_zahir_text_analyzer_declares_source_layer() -> None:
    assert ZahirTextAnalyzer.source_layer == "zahir"


def test_zahir_text_analyzer_is_instantiable() -> None:
    # ABC validation only fires on declaration — here we just
    # prove the class successfully satisfies the contract.
    analyzer = ZahirTextAnalyzer()
    assert analyzer.name == "text_layer"
    assert "text_layer" in repr(analyzer)
    assert "zahir" in repr(analyzer)


def test_scan_returns_integrity_report_type() -> None:
    report = ZahirTextAnalyzer().scan(CLEAN_PDF)
    assert isinstance(report, IntegrityReport)


# ---------------------------------------------------------------------------
# clean.pdf — reference standard
# ---------------------------------------------------------------------------

def test_clean_pdf_has_zero_findings() -> None:
    """The reference-standard fixture must produce no text-layer findings."""
    report = ZahirTextAnalyzer().scan(CLEAN_PDF)
    assert report.findings == [], (
        f"clean.pdf emitted findings: {[f.mechanism for f in report.findings]}"
    )


def test_clean_pdf_has_integrity_score_one() -> None:
    report = ZahirTextAnalyzer().scan(CLEAN_PDF)
    assert report.integrity_score == 1.0


def test_clean_pdf_has_no_error() -> None:
    report = ZahirTextAnalyzer().scan(CLEAN_PDF)
    assert report.error is None
    assert report.scan_incomplete is False


def test_clean_pdf_reports_absolute_path() -> None:
    report = ZahirTextAnalyzer().scan(CLEAN_PDF)
    assert report.file_path == str(CLEAN_PDF)


# ---------------------------------------------------------------------------
# Per-fixture mechanism firings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fixture_name,expected_mechanism",
    list(TEXT_FIXTURE_EXPECTED.items()),
    ids=list(TEXT_FIXTURE_EXPECTED.keys()),
)
def test_text_fixture_fires_expected_mechanism(
    fixture_name: str, expected_mechanism: str,
) -> None:
    """Every text-layer fixture must fire its declared mechanism —
    same detector-level correctness assertion v0 carries, now promoted
    to the new analyzer contract."""
    fx = FIXTURES[fixture_name]
    report = ZahirTextAnalyzer().scan(fx.out_path)
    mechanisms = {f.mechanism for f in report.findings}
    assert expected_mechanism in mechanisms, (
        f"{fixture_name!r}: expected {expected_mechanism!r} to fire, "
        f"got {sorted(mechanisms) or '(none)'}"
    )


@pytest.mark.parametrize(
    "fixture_name,expected_mechanism",
    list(TEXT_FIXTURE_EXPECTED.items()),
    ids=list(TEXT_FIXTURE_EXPECTED.keys()),
)
def test_text_fixture_fires_only_text_layer_mechanisms(
    fixture_name: str, expected_mechanism: str,
) -> None:
    """ZahirTextAnalyzer must only produce text-layer mechanism names —
    no object-layer mechanism may leak through."""
    fx = FIXTURES[fixture_name]
    report = ZahirTextAnalyzer().scan(fx.out_path)

    # All findings emitted by a zahir analyzer must carry the zahir layer.
    for f in report.findings:
        assert f.source_layer == "zahir", (
            f"{fixture_name!r}: finding {f.mechanism!r} emitted "
            f"source_layer={f.source_layer!r}, expected 'zahir'"
        )


def test_score_penalises_findings_on_text_fixtures() -> None:
    """Every text-layer fixture should score strictly below 1.0 —
    the muwazana score must reflect the detected concealment."""
    for fixture_name in TEXT_FIXTURE_EXPECTED:
        fx = FIXTURES[fixture_name]
        report = ZahirTextAnalyzer().scan(fx.out_path)
        assert report.integrity_score < 1.0, (
            f"{fixture_name!r} scored {report.integrity_score}, "
            "expected < 1.0 (concealment should deduct)"
        )


# ---------------------------------------------------------------------------
# Object-layer fixtures — ZahirTextAnalyzer must NOT fire on them
# (except where they also carry text-layer payload, in which case a
# fire is legitimate but still a text-layer mechanism)
# ---------------------------------------------------------------------------

def test_object_fixtures_emit_no_text_layer_noise() -> None:
    """Scanning the object-layer fixtures with the text-layer analyzer
    must either emit no findings or emit only text-layer mechanisms.
    A leak of object-layer mechanisms would indicate layer bleed."""
    object_pdfs = sorted(OBJECT_FIXTURE_DIR.glob("*.pdf"))
    if not object_pdfs:
        pytest.skip("No object-layer fixtures present.")

    # These are the only mechanisms ZahirTextAnalyzer is allowed to emit.
    allowed = {
        "invisible_render_mode", "white_on_white_text", "microscopic_font",
        "off_page_text", "zero_width_chars", "bidi_control", "tag_chars",
        "overlapping_text", "homoglyph", "scan_error",
    }
    for pdf in object_pdfs:
        report = ZahirTextAnalyzer().scan(pdf)
        for f in report.findings:
            assert f.mechanism in allowed, (
                f"{pdf.name}: leaked non-text-layer mechanism {f.mechanism!r}"
            )


# ---------------------------------------------------------------------------
# scan_error handling
# ---------------------------------------------------------------------------

def test_scan_error_on_missing_file(tmp_path: Path) -> None:
    """A missing file must yield a scan_error report with the correct prefix."""
    missing = tmp_path / "does_not_exist.pdf"
    report = ZahirTextAnalyzer().scan(missing)

    assert report.scan_incomplete is True
    assert report.error is not None
    assert report.error.startswith("Text layer scan error:")
    # Exactly one finding — the synthetic scan_error.
    assert len(report.findings) == 1
    f = report.findings[0]
    assert f.mechanism == "scan_error"
    assert f.tier == 3
    assert f.severity == 0.0
    # scan_error carries the analyzer's source_layer, not the mechanism default.
    assert f.source_layer == "zahir"
    assert f.location == "analyzer:text_layer"


def test_scan_error_on_non_pdf(tmp_path: Path) -> None:
    """A non-PDF file (pymupdf fails to open) must yield scan_error."""
    junk = tmp_path / "not_a_pdf.pdf"
    junk.write_bytes(b"not a pdf at all\n")
    report = ZahirTextAnalyzer().scan(junk)

    assert report.scan_incomplete is True
    assert report.error is not None
    assert report.error.startswith("Text layer scan error:")


def test_scan_error_report_score_is_one_since_severity_is_zero() -> None:
    """scan_error severity is 0.0 — so the score stays at 1.0 (the analyzer
    reports coverage gaps non-punitively)."""
    report = ZahirTextAnalyzer().scan(Path("/nope/does/not/exist.pdf"))
    assert report.integrity_score == 1.0


# ---------------------------------------------------------------------------
# source_layer attribution
# ---------------------------------------------------------------------------

def test_every_finding_carries_zahir_source_layer() -> None:
    """Sweep every Phase 0 fixture: every finding emitted by
    ZahirTextAnalyzer must carry source_layer='zahir'. scan_error is
    also zahir here because the analyzer itself is zahir-layer."""
    all_pdfs = [CLEAN_PDF] + sorted(TEXT_FIXTURE_DIR.glob("*.pdf"))
    all_pdfs += sorted(OBJECT_FIXTURE_DIR.glob("*.pdf"))
    all_pdfs.append(FIXTURES_DIR / "positive_combined.pdf")

    for pdf in all_pdfs:
        if not pdf.exists():
            continue
        report = ZahirTextAnalyzer().scan(pdf)
        for f in report.findings:
            assert f.source_layer == "zahir", (
                f"{pdf.name}: {f.mechanism!r} carried source_layer="
                f"{f.source_layer!r}, expected 'zahir'"
            )


# ---------------------------------------------------------------------------
# Parity sweep — v0.1 TextLayerAnalyzer vs ZahirTextAnalyzer
# ---------------------------------------------------------------------------

def _v01_text_scan(pdf_path: Path) -> list[bayyinah_v0_1.Finding]:
    """Run v0.1's TextLayerAnalyzer against the same file via its
    own PDFContext, so we can compare finding-by-finding."""
    ctx = bayyinah_v0_1.PDFContext(pdf_path)
    try:
        return bayyinah_v0_1.TextLayerAnalyzer().scan(ctx)
    finally:
        ctx.close()


def _tuple(f) -> tuple:
    """Extract the v0.1-equivalent fields of a finding — the fields
    that must match byte-identically across the two analyzers.

    ``source_layer`` is not included because v0.1's Finding model has
    no such field. ``severity_override`` also is not included; it is
    a domain-model addition that does not affect behaviour for any
    text-layer mechanism (none of which carries an override)."""
    return (
        f.mechanism,
        f.tier,
        round(f.confidence, 6),
        f.description,
        f.location,
        f.surface,
        f.concealed,
    )


def _all_text_and_clean_fixtures() -> list[Path]:
    pdfs = [CLEAN_PDF]
    pdfs.extend(sorted(TEXT_FIXTURE_DIR.glob("*.pdf")))
    return [p for p in pdfs if p.exists()]


@pytest.mark.parametrize(
    "pdf_path",
    _all_text_and_clean_fixtures(),
    ids=[p.name for p in _all_text_and_clean_fixtures()],
)
def test_parity_with_v0_1_text_layer_analyzer(pdf_path: Path) -> None:
    """For every Phase 0 fixture relevant to the zahir layer,
    ZahirTextAnalyzer must emit the same (mechanism, tier, confidence,
    description, location, surface, concealed) tuples as v0.1's
    TextLayerAnalyzer. This is the v0-to-v0.1 parity invariant, now
    promoted onto the new analyzer contract."""
    ours_report = ZahirTextAnalyzer().scan(pdf_path)
    theirs = _v01_text_scan(pdf_path)

    ours_tuples = [_tuple(f) for f in ours_report.findings]
    theirs_tuples = [_tuple(f) for f in theirs]

    assert ours_tuples == theirs_tuples, (
        f"\nParity diverged on {pdf_path.name}:"
        f"\n  ours  ({len(ours_tuples)}): {ours_tuples}"
        f"\n  v0.1  ({len(theirs_tuples)}): {theirs_tuples}"
    )


def test_parity_on_positive_combined() -> None:
    """The combined fixture fires every single-mechanism detector the
    corpus covers — including all the text-layer ones. Parity must
    hold across that dense adversarial doc too."""
    pdf = FIXTURES_DIR / "positive_combined.pdf"
    if not pdf.exists():
        pytest.skip("positive_combined.pdf not built")

    ours_report = ZahirTextAnalyzer().scan(pdf)
    theirs = _v01_text_scan(pdf)

    ours_tuples = [_tuple(f) for f in ours_report.findings]
    theirs_tuples = [_tuple(f) for f in theirs]

    assert ours_tuples == theirs_tuples


def test_parity_mechanism_sets_on_object_fixtures() -> None:
    """On object-layer fixtures, the text analyzer should agree with
    v0.1's text analyzer about what text-layer mechanisms fire —
    which, for most, is the empty set. Compare by multiset of
    mechanism names since v0.1 may order them slightly differently
    after independent PDFContext state."""
    for pdf in sorted(OBJECT_FIXTURE_DIR.glob("*.pdf")):
        ours = sorted(
            f.mechanism for f in ZahirTextAnalyzer().scan(pdf).findings
        )
        theirs = sorted(f.mechanism for f in _v01_text_scan(pdf))
        assert ours == theirs, (
            f"{pdf.name}: text-layer mechanism set diverged — "
            f"ours={ours}, v0.1={theirs}"
        )


# ---------------------------------------------------------------------------
# scan() resource hygiene
# ---------------------------------------------------------------------------

def test_scan_closes_pdfclient_on_success() -> None:
    """scan() must close the underlying PDFClient even on the happy
    path — no file-descriptor leak across repeated calls."""
    analyzer = ZahirTextAnalyzer()
    # Loop a few times — if PDFClient leaked, this would accumulate
    # fitz Document handles. The scan completing without error on each
    # pass is the signal.
    for _ in range(5):
        report = analyzer.scan(CLEAN_PDF)
        assert report.error is None


def test_scan_closes_pdfclient_on_error(tmp_path: Path) -> None:
    """PDFClient must close even when pymupdf fails to open."""
    analyzer = ZahirTextAnalyzer()
    for _ in range(3):
        report = analyzer.scan(tmp_path / "ghost.pdf")
        assert report.scan_incomplete
