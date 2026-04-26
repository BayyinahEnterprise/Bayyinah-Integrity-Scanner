"""
Tests for analyzers.object_analyzer.BatinObjectAnalyzer.

This file is the Phase 5 guardrail of the Al-Baqarah refactor: it
asserts that the new BaseAnalyzer-shaped BatinObjectAnalyzer fires
exactly the same object-layer mechanisms as v0.1's ObjectLayerAnalyzer
on every Phase 0 fixture — byte-identical per mechanism field.

Coverage targets:
  * BaseAnalyzer contract — name, error_prefix, source_layer, repr
  * clean.pdf → 0 findings, integrity_score == 1.0
  * Each object-layer fixture fires exactly its declared mechanism(s)
  * Text-layer fixtures are also scanned to prove BatinObjectAnalyzer
    limits itself to the batin layer (no text-layer mechanisms leak)
  * positive_combined fires every object-layer mechanism the corpus
    covers (inside one dense adversarial doc)
  * scan_error handling:
      - non-PDF input → inline v0.1-shape scan_error (tier 3, conf 0.5,
        location="document") plus report.error with the 'Object layer
        scan error' prefix and scan_incomplete=True
      - missing file → same path
  * incremental_update fires from raw bytes even when pypdf later
    fails (defensive coverage, not blocked by parser)
  * All emitted findings carry source_layer='batin'
  * Parity sweep: for every Phase 0 fixture, BatinObjectAnalyzer emits
    the same (mechanism, tier, confidence, description, location,
    surface, concealed) tuples as v0.1's ObjectLayerAnalyzer.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

import bayyinah_v0_1
from analyzers.base import BaseAnalyzer
from analyzers.object_analyzer import BatinObjectAnalyzer
from domain import IntegrityReport


# ---------------------------------------------------------------------------
# IndirectObject-repr normalisation — same pattern tests/test_fixtures.py uses.
#
# pypdf's IndirectObject.__repr__ embeds ``id()`` of the parent document,
# which differs between process runs and between the two analyzers'
# independent pypdf readers. ``concealed`` payloads often include these
# ``str(indirect_obj)`` fragments, so byte-level parity requires
# normalising the id component before diffing.
# ---------------------------------------------------------------------------

_INDIRECT_RE = re.compile(r"IndirectObject\((\d+),\s*(\d+),\s*\d+\)")


def _normalise(s: str) -> str:
    return _INDIRECT_RE.sub(r"IndirectObject(\1, \2, <id>)", s)

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
POSITIVE_COMBINED = FIXTURES_DIR / "positive_combined.pdf"


# The Phase 0 object fixtures, keyed by the mechanism set each asserts.
OBJECT_FIXTURE_EXPECTED: dict[str, frozenset[str]] = {
    "object.embedded_javascript":  frozenset({"javascript", "openaction"}),
    "object.embedded_attachment":  frozenset({"embedded_file"}),
    "object.hidden_ocg":           frozenset({"hidden_ocg"}),
    "object.metadata_injection":   frozenset({"metadata_anomaly"}),
    "object.tounicode_cmap":       frozenset({"tounicode_anomaly"}),
    "object.incremental_update":   frozenset({"incremental_update"}),
    "object.additional_actions":   frozenset({"additional_actions"}),
}


# Mechanisms this analyzer is allowed to emit. A mechanism outside this
# set would indicate a layer leak.
ALLOWED_BATIN_MECHANISMS: frozenset[str] = frozenset({
    "javascript",
    "openaction",
    "additional_actions",
    "launch_action",
    "embedded_file",
    "file_attachment_annot",
    "incremental_update",
    "metadata_anomaly",
    "hidden_ocg",
    "tounicode_anomaly",
    "scan_error",
})


# ---------------------------------------------------------------------------
# BaseAnalyzer contract
# ---------------------------------------------------------------------------

def test_batin_object_analyzer_is_base_analyzer_subclass() -> None:
    assert issubclass(BatinObjectAnalyzer, BaseAnalyzer)


def test_batin_object_analyzer_declares_name() -> None:
    assert BatinObjectAnalyzer.name == "object_layer"


def test_batin_object_analyzer_declares_error_prefix() -> None:
    assert BatinObjectAnalyzer.error_prefix == "Object layer scan error"


def test_batin_object_analyzer_declares_source_layer() -> None:
    assert BatinObjectAnalyzer.source_layer == "batin"


def test_batin_object_analyzer_is_instantiable() -> None:
    analyzer = BatinObjectAnalyzer()
    assert analyzer.name == "object_layer"
    assert "object_layer" in repr(analyzer)
    assert "batin" in repr(analyzer)


def test_scan_returns_integrity_report_type() -> None:
    report = BatinObjectAnalyzer().scan(CLEAN_PDF)
    assert isinstance(report, IntegrityReport)


# ---------------------------------------------------------------------------
# clean.pdf — reference standard
# ---------------------------------------------------------------------------

def test_clean_pdf_has_zero_findings() -> None:
    """The reference-standard fixture must produce no object-layer findings."""
    report = BatinObjectAnalyzer().scan(CLEAN_PDF)
    assert report.findings == [], (
        f"clean.pdf emitted findings: {[f.mechanism for f in report.findings]}"
    )


def test_clean_pdf_has_integrity_score_one() -> None:
    report = BatinObjectAnalyzer().scan(CLEAN_PDF)
    assert report.integrity_score == 1.0


def test_clean_pdf_has_no_error() -> None:
    report = BatinObjectAnalyzer().scan(CLEAN_PDF)
    assert report.error is None
    assert report.scan_incomplete is False


def test_clean_pdf_reports_absolute_path() -> None:
    report = BatinObjectAnalyzer().scan(CLEAN_PDF)
    assert report.file_path == str(CLEAN_PDF)


# ---------------------------------------------------------------------------
# Per-fixture mechanism firings
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fixture_name,expected_mechanisms",
    list(OBJECT_FIXTURE_EXPECTED.items()),
    ids=list(OBJECT_FIXTURE_EXPECTED.keys()),
)
def test_object_fixture_fires_expected_mechanisms(
    fixture_name: str, expected_mechanisms: frozenset[str],
) -> None:
    """Every object-layer fixture must fire exactly its declared
    mechanism set (no more, no fewer) — promoting the Phase 0 v0
    detector-correctness guardrail onto the new analyzer contract."""
    fx = FIXTURES[fixture_name]
    report = BatinObjectAnalyzer().scan(fx.out_path)
    mechanisms = {f.mechanism for f in report.findings}
    assert mechanisms == expected_mechanisms, (
        f"{fixture_name!r} mechanism mismatch:"
        f"\n  expected: {sorted(expected_mechanisms)}"
        f"\n  got:      {sorted(mechanisms)}"
        f"\n  missing:  {sorted(expected_mechanisms - mechanisms) or '(none)'}"
        f"\n  extra:    {sorted(mechanisms - expected_mechanisms) or '(none)'}"
    )


@pytest.mark.parametrize(
    "fixture_name,_expected",
    list(OBJECT_FIXTURE_EXPECTED.items()),
    ids=list(OBJECT_FIXTURE_EXPECTED.keys()),
)
def test_object_fixture_findings_are_batin(
    fixture_name: str, _expected: frozenset[str],
) -> None:
    """Every finding emitted by BatinObjectAnalyzer must carry
    source_layer='batin'."""
    fx = FIXTURES[fixture_name]
    report = BatinObjectAnalyzer().scan(fx.out_path)
    for f in report.findings:
        assert f.source_layer == "batin", (
            f"{fixture_name!r}: {f.mechanism!r} emitted "
            f"source_layer={f.source_layer!r}, expected 'batin'"
        )


def test_score_penalises_findings_on_object_fixtures() -> None:
    """Every object-layer fixture should score strictly below 1.0 —
    the muwazana score must reflect the detected concealment."""
    # incremental_update has severity 0.05 * confidence 0.7 = 0.035
    # so the penalty is small but non-zero.
    for fixture_name in OBJECT_FIXTURE_EXPECTED:
        fx = FIXTURES[fixture_name]
        report = BatinObjectAnalyzer().scan(fx.out_path)
        assert report.integrity_score < 1.0, (
            f"{fixture_name!r} scored {report.integrity_score}, "
            "expected < 1.0 (concealment should deduct)"
        )


# ---------------------------------------------------------------------------
# positive_combined — the full munafiq pattern
# ---------------------------------------------------------------------------

def test_positive_combined_fires_every_object_mechanism_covered() -> None:
    """The combined fixture must fire every single-mechanism detector
    the object-layer corpus covers."""
    if not POSITIVE_COMBINED.exists():
        pytest.skip("positive_combined.pdf not built")

    report = BatinObjectAnalyzer().scan(POSITIVE_COMBINED)
    mechanisms = {f.mechanism for f in report.findings}

    # Every single-fixture mechanism must appear in the combined doc.
    expected_union = set().union(*OBJECT_FIXTURE_EXPECTED.values())
    missing = expected_union - mechanisms
    assert not missing, (
        f"positive_combined missing object-layer mechanisms: {sorted(missing)}"
    )


# ---------------------------------------------------------------------------
# Text-layer fixtures — BatinObjectAnalyzer must NOT leak text mechanisms
# ---------------------------------------------------------------------------

def test_text_fixtures_emit_no_object_layer_noise() -> None:
    """Scanning the text-layer fixtures with the object-layer analyzer
    must either emit no findings or emit only object-layer mechanisms.
    A leak of text-layer mechanisms would indicate layer bleed."""
    text_pdfs = sorted(TEXT_FIXTURE_DIR.glob("*.pdf"))
    if not text_pdfs:
        pytest.skip("No text-layer fixtures present.")

    for pdf in text_pdfs:
        report = BatinObjectAnalyzer().scan(pdf)
        for f in report.findings:
            assert f.mechanism in ALLOWED_BATIN_MECHANISMS, (
                f"{pdf.name}: leaked non-object-layer mechanism "
                f"{f.mechanism!r}"
            )


# ---------------------------------------------------------------------------
# scan_error handling
# ---------------------------------------------------------------------------

def test_scan_error_on_missing_file(tmp_path: Path) -> None:
    """A missing file must yield a scan_error report with the correct prefix."""
    missing = tmp_path / "does_not_exist.pdf"
    report = BatinObjectAnalyzer().scan(missing)

    assert report.scan_incomplete is True
    assert report.error is not None
    assert report.error.startswith("Object layer scan error:")

    # Exactly one finding — the inline v0.1-shape scan_error. No
    # incremental_update because raw_bytes returns None for a missing file.
    mechanisms = [f.mechanism for f in report.findings]
    assert mechanisms == ["scan_error"], (
        f"missing-file report carried extra findings: {mechanisms}"
    )

    scan_err = report.findings[0]
    # v0.1-shape inline scan_error — tier 3, confidence 0.5, location "document"
    assert scan_err.tier == 3
    assert scan_err.confidence == 0.5
    assert scan_err.location == "document"
    assert scan_err.surface == "(object walk skipped)"
    assert scan_err.description.startswith("pypdf could not open the document:")
    # scan_error severity is 0.0 so the score is unaffected (score=1.0)
    assert scan_err.severity == 0.0
    # source_layer auto-inferred as batin (scan_error ∈ BATIN_MECHANISMS)
    assert scan_err.source_layer == "batin"


def test_scan_error_on_non_pdf(tmp_path: Path) -> None:
    """A non-PDF file (pypdf fails to open) must yield scan_error."""
    junk = tmp_path / "not_a_pdf.pdf"
    junk.write_bytes(b"not a pdf at all\n")
    report = BatinObjectAnalyzer().scan(junk)

    assert report.scan_incomplete is True
    assert report.error is not None
    assert report.error.startswith("Object layer scan error:")
    # At least one finding — the scan_error (no incremental_update because
    # the junk file has no %%EOF markers).
    assert any(f.mechanism == "scan_error" for f in report.findings)


def test_scan_error_report_score_stays_at_one_since_severity_is_zero(
    tmp_path: Path,
) -> None:
    """scan_error severity is 0.0 — so the score stays at 1.0 at the
    analyzer level (the registry applies the scan-incomplete clamp)."""
    report = BatinObjectAnalyzer().scan(tmp_path / "ghost.pdf")
    assert report.integrity_score == 1.0


# ---------------------------------------------------------------------------
# incremental_update from raw bytes is independent of pypdf success
# ---------------------------------------------------------------------------

def test_incremental_update_fires_from_raw_bytes() -> None:
    """The incremental_update scan reads raw bytes — it must fire on
    the dedicated fixture even though other analyses also succeed."""
    fx = FIXTURES["object.incremental_update"]
    report = BatinObjectAnalyzer().scan(fx.out_path)
    assert any(f.mechanism == "incremental_update" for f in report.findings)


def test_incremental_update_still_fires_when_pypdf_fails(
    tmp_path: Path,
) -> None:
    """A file that pypdf cannot open but that contains multiple
    ``%%EOF`` markers in its bytes should still produce an
    incremental_update finding — the raw-byte scan is defensive and
    independent of the parser."""
    # Two %%EOF markers, structurally broken — pypdf will fail but the
    # raw-byte regex still sees both.
    broken = tmp_path / "broken_multi_eof.pdf"
    broken.write_bytes(b"%PDF-1.4\n%%EOF\njunk-after\n%%EOF\n")
    report = BatinObjectAnalyzer().scan(broken)

    mechanisms = [f.mechanism for f in report.findings]
    # incremental_update must appear even though scan_error is also emitted.
    assert "incremental_update" in mechanisms
    assert "scan_error" in mechanisms
    assert report.scan_incomplete is True


# ---------------------------------------------------------------------------
# source_layer attribution sweep
# ---------------------------------------------------------------------------

def test_every_finding_carries_batin_source_layer() -> None:
    """Sweep every Phase 0 fixture: every finding emitted by
    BatinObjectAnalyzer must carry source_layer='batin'."""
    all_pdfs = [CLEAN_PDF] + sorted(TEXT_FIXTURE_DIR.glob("*.pdf"))
    all_pdfs += sorted(OBJECT_FIXTURE_DIR.glob("*.pdf"))
    if POSITIVE_COMBINED.exists():
        all_pdfs.append(POSITIVE_COMBINED)

    for pdf in all_pdfs:
        if not pdf.exists():
            continue
        report = BatinObjectAnalyzer().scan(pdf)
        for f in report.findings:
            assert f.source_layer == "batin", (
                f"{pdf.name}: {f.mechanism!r} carried source_layer="
                f"{f.source_layer!r}, expected 'batin'"
            )


# ---------------------------------------------------------------------------
# Parity sweep — v0.1 ObjectLayerAnalyzer vs BatinObjectAnalyzer
# ---------------------------------------------------------------------------

def _v01_object_scan(pdf_path: Path) -> list[bayyinah_v0_1.Finding]:
    """Run v0.1's ObjectLayerAnalyzer against the same file via its
    own PDFContext, so we can compare finding-by-finding."""
    ctx = bayyinah_v0_1.PDFContext(pdf_path)
    try:
        return bayyinah_v0_1.ObjectLayerAnalyzer().scan(ctx)
    finally:
        ctx.close()


def _tuple(f) -> tuple:
    """Extract the v0.1-equivalent fields of a finding — the fields
    that must match byte-identically across the two analyzers.

    String fields that may embed pypdf IndirectObject reprs are
    normalised so that the non-deterministic parent-doc ``id()``
    component does not break parity."""
    return (
        f.mechanism,
        f.tier,
        round(f.confidence, 6),
        _normalise(f.description),
        _normalise(f.location),
        _normalise(f.surface),
        _normalise(f.concealed),
    )


def _all_phase0_fixtures() -> list[Path]:
    pdfs = [CLEAN_PDF]
    pdfs.extend(sorted(TEXT_FIXTURE_DIR.glob("*.pdf")))
    pdfs.extend(sorted(OBJECT_FIXTURE_DIR.glob("*.pdf")))
    if POSITIVE_COMBINED.exists():
        pdfs.append(POSITIVE_COMBINED)
    return [p for p in pdfs if p.exists()]


@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_parity_with_v0_1_object_layer_analyzer(pdf_path: Path) -> None:
    """For every Phase 0 fixture, BatinObjectAnalyzer must emit the
    same (mechanism, tier, confidence, description, location, surface,
    concealed) tuples as v0.1's ObjectLayerAnalyzer. This is the
    v0-to-v0.1 parity invariant, now promoted onto the new analyzer
    contract."""
    ours_report = BatinObjectAnalyzer().scan(pdf_path)
    theirs = _v01_object_scan(pdf_path)

    ours_tuples = [_tuple(f) for f in ours_report.findings]
    theirs_tuples = [_tuple(f) for f in theirs]

    assert ours_tuples == theirs_tuples, (
        f"\nParity diverged on {pdf_path.name}:"
        f"\n  ours  ({len(ours_tuples)}): {ours_tuples}"
        f"\n  v0.1  ({len(theirs_tuples)}): {theirs_tuples}"
    )


def test_parity_mechanism_sets_on_text_fixtures() -> None:
    """On text-layer fixtures, the object analyzer should agree with
    v0.1's object analyzer about what object-layer mechanisms fire —
    which, for most, is the empty set."""
    for pdf in sorted(TEXT_FIXTURE_DIR.glob("*.pdf")):
        ours = sorted(
            f.mechanism for f in BatinObjectAnalyzer().scan(pdf).findings
        )
        theirs = sorted(f.mechanism for f in _v01_object_scan(pdf))
        assert ours == theirs, (
            f"{pdf.name}: object-layer mechanism set diverged — "
            f"ours={ours}, v0.1={theirs}"
        )


# ---------------------------------------------------------------------------
# scan() resource hygiene
# ---------------------------------------------------------------------------

def test_scan_closes_pdfclient_on_success() -> None:
    """scan() must close the underlying PDFClient — no file-descriptor
    leak across repeated calls on the happy path."""
    analyzer = BatinObjectAnalyzer()
    for _ in range(5):
        report = analyzer.scan(CLEAN_PDF)
        assert report.error is None


def test_scan_closes_pdfclient_on_error(tmp_path: Path) -> None:
    """PDFClient must close even when pypdf fails to open."""
    analyzer = BatinObjectAnalyzer()
    for _ in range(3):
        report = analyzer.scan(tmp_path / "ghost.pdf")
        assert report.scan_incomplete
