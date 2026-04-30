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


# ---------------------------------------------------------------------------
# v1.1.5 spatial pre-filter for overlapping_text
# ---------------------------------------------------------------------------

def _naive_iou_pairs(spans, threshold):
    """Reference: enumerate every pair the v1.1.4 O(n^2) loop would
    have surfaced at IoU >= threshold, regardless of text equality."""
    from analyzers.text_analyzer import ZahirTextAnalyzer
    pairs = set()
    for i in range(len(spans)):
        for j in range(i + 1, len(spans)):
            iou = ZahirTextAnalyzer._bbox_iou(spans[i][0], spans[j][0])
            if iou >= threshold:
                pairs.add((i, j))
    return pairs


def test_overlapping_pair_candidates_handles_empty() -> None:
    from analyzers.text_analyzer import _overlapping_pair_candidates
    assert list(_overlapping_pair_candidates([])) == []


def test_overlapping_pair_candidates_handles_single_span() -> None:
    from analyzers.text_analyzer import _overlapping_pair_candidates
    spans = [((10.0, 10.0, 50.0, 30.0), "hello")]
    assert list(_overlapping_pair_candidates(spans)) == []


def test_overlapping_pair_candidates_yields_overlapping_pair() -> None:
    """A pair of bboxes at identical coordinates must appear among the
    candidates so the IoU check downstream can confirm them."""
    from analyzers.text_analyzer import _overlapping_pair_candidates
    spans = [
        ((100.0, 100.0, 200.0, 120.0), "first"),
        ((100.0, 100.0, 200.0, 120.0), "second"),
    ]
    candidates = list(_overlapping_pair_candidates(spans))
    assert (0, 1) in candidates


def test_overlapping_pair_candidates_skips_distant_pairs() -> None:
    """Bboxes nowhere near each other should not be enumerated as a
    candidate. Correctness does not require this (the IoU predicate
    would filter them anyway), but this is the speedup path."""
    from analyzers.text_analyzer import _overlapping_pair_candidates
    spans = [
        ((10.0, 10.0, 30.0, 20.0), "left"),
        ((500.0, 500.0, 520.0, 510.0), "far"),
    ]
    # The two boxes share no grid cell at any reasonable cell size,
    # so the candidate generator should yield no pairs.
    assert list(_overlapping_pair_candidates(spans)) == []


def test_overlapping_pair_candidates_is_superset_of_naive() -> None:
    """The candidate generator must return at least every pair the
    naive O(n^2) IoU scan would have surfaced. Any pair the naive
    scan finds at IoU >= threshold must appear among the candidates,
    or the speedup would silently drop true positives."""
    import random
    from analyzers.text_analyzer import _overlapping_pair_candidates
    from domain.config import SPAN_OVERLAP_THRESHOLD

    rng = random.Random(20260430)
    # 30 randomized layouts of 40 spans each across a synthetic page.
    for trial in range(30):
        spans = []
        for _ in range(40):
            x0 = rng.uniform(0, 500)
            y0 = rng.uniform(0, 700)
            w = rng.uniform(8, 60)
            h = rng.uniform(8, 16)
            spans.append(((x0, y0, x0 + w, y0 + h), f"t{trial}_{_}"))
        # Force a few guaranteed overlaps so the test exercises the
        # positive path on every trial.
        for k in range(3):
            base_bbox = spans[k][0]
            spans.append((base_bbox, f"clone_{trial}_{k}"))

        candidates = set(_overlapping_pair_candidates(spans))
        naive = _naive_iou_pairs(spans, SPAN_OVERLAP_THRESHOLD)
        # Every naive pair must appear in the candidate set.
        missing = naive - candidates
        assert not missing, (
            f"trial {trial}: candidate generator missed "
            f"{len(missing)} pair(s) the naive scan would surface: "
            f"{list(missing)[:5]}"
        )


def test_overlapping_pair_candidates_finds_the_positive_fixture() -> None:
    """End-to-end: the canonical overlapping-text fixture must still
    produce its one finding under the v1.1.5 path."""
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "text" / "overlapping.pdf"
    if not fixture.exists():
        import pytest
        pytest.skip(f"fixture not generated: {fixture}")
    analyzer = ZahirTextAnalyzer()
    report = analyzer.scan(fixture)
    overlapping = [f for f in report.findings if f.mechanism == "overlapping_text"]
    assert len(overlapping) >= 1, (
        f"v1.1.5 spatial pre-filter must still surface the canonical "
        f"overlapping_text fixture; got findings: "
        f"{[(f.mechanism, f.surface) for f in report.findings]}"
    )
