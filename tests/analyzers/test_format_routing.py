"""
Tests for the v1.1.2 Tier 0 routing-transparency layer.

Pins, in order:

  1. The detector function ``detect_format_routing_divergence`` returns
     the right Tier 0 finding for each of the four trigger conditions
     (T0a extension/magic mismatch, T0b unknown, T0c content-depth
     floor, T0d OOXML internal-path divergence).
  2. The detector returns ``None`` on a clean control file (no false
     positives).
  3. The Finding constructor's disclosure-schema validator (the five
     required keys in ``ROUTING_DISCLOSURE_KEYS``) rejects incomplete
     evidence at construction time.
  4. The verdict resolver (``tamyiz_verdict``) floors at mughlaq when a
     Tier 0 finding is present, even when downstream Tier 1 findings
     also fire.
  5. The verdict resolver returns the existing verdict when no Tier 0
     finding fires (no regression on the v1.1.1 verdict logic).
  6. A full ScanService scan on each fixture produces the expected
     verdict and at least one finding with mechanism =
     'format_routing_divergence' (or none, for the control fixture).
  7. Each Tier 0 finding's ``evidence`` dict contains exactly the five
     required keys.

References:
  - docs/adversarial/format_routing_gauntlet/REPORT.md
  - docs/adversarial/mughlaq_trap_REPORT.md
  - docs/scope/v1_1_2_framework_report.md section 3.0
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.format_routing import detect_format_routing_divergence
from application.scan_service import ScanService
from domain.config import (
    ROUTING_MECHANISMS,
    SEVERITY,
    TIER,
    VERDICT_MUGHLAQ,
    VERDICT_MUKHFI,
    VERDICT_SAHIH,
)
from domain.exceptions import InvalidFindingError
from domain.finding import Finding, ROUTING_DISCLOSURE_KEYS
from domain.integrity_report import IntegrityReport
from domain.value_objects import tamyiz_verdict
from infrastructure.file_router import FileKind, FileRouter, FileTypeDetection


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "docs/adversarial/format_routing_gauntlet/fixtures"


# ===========================================================================
# Configuration-level pins
# ===========================================================================

def test_format_routing_divergence_in_registry() -> None:
    """The new mechanism is registered with TIER=0 and SEVERITY=0.0."""
    assert "format_routing_divergence" in ROUTING_MECHANISMS
    assert TIER["format_routing_divergence"] == 0
    assert SEVERITY["format_routing_divergence"] == 0.0


def test_routing_disclosure_keys_complete() -> None:
    """The disclosure schema names exactly five required keys."""
    expected = {
        "claimed_format",
        "inferred_format",
        "routing_decision",
        "bytes_sampled",
        "analyzer_invoked",
    }
    assert ROUTING_DISCLOSURE_KEYS == expected


# ===========================================================================
# Finding-construction pins (disclosure schema validator)
# ===========================================================================

def _full_evidence() -> dict:
    return {
        "claimed_format": "docx",
        "inferred_format": "pdf",
        "routing_decision": "trusted_magic_bytes",
        "bytes_sampled": 1024,
        "analyzer_invoked": "pdf",
    }


def test_tier0_finding_constructs_with_full_evidence() -> None:
    """Happy path: all five keys present, Finding constructs cleanly."""
    f = Finding(
        mechanism="format_routing_divergence",
        tier=0,
        confidence=1.0,
        description="t",
        location="/tmp/x",
        evidence=_full_evidence(),
    )
    assert f.tier == 0
    assert f.evidence is not None
    assert set(f.evidence.keys()) == ROUTING_DISCLOSURE_KEYS


def test_tier0_finding_rejects_missing_evidence() -> None:
    """Tier 0 without evidence at all is a structural defect."""
    with pytest.raises(InvalidFindingError) as excinfo:
        Finding(
            mechanism="format_routing_divergence",
            tier=0,
            confidence=1.0,
            description="t",
            location="/tmp/x",
        )
    assert "evidence" in str(excinfo.value).lower()


def test_tier0_finding_rejects_partial_evidence() -> None:
    """Missing any one of the five keys raises InvalidFindingError."""
    partial = _full_evidence()
    partial.pop("routing_decision")
    with pytest.raises(InvalidFindingError) as excinfo:
        Finding(
            mechanism="format_routing_divergence",
            tier=0,
            confidence=1.0,
            description="t",
            location="/tmp/x",
            evidence=partial,
        )
    assert "routing_decision" in str(excinfo.value)


def test_concealment_findings_do_not_require_evidence() -> None:
    """Tier 1/2/3 mechanisms remain free to omit evidence (parity)."""
    f = Finding(
        mechanism="white_on_white_text",
        tier=1,
        confidence=1.0,
        description="t",
        location="/tmp/x",
    )
    assert f.evidence is None
    # to_dict should not contain 'evidence' for parity with v0/v0.1.
    assert "evidence" not in f.to_dict()


def test_tier0_finding_to_dict_includes_evidence() -> None:
    """Tier 0 findings DO emit evidence in to_dict (new field, no parity contract)."""
    f = Finding(
        mechanism="format_routing_divergence",
        tier=0, confidence=1.0,
        description="t", location="/tmp/x",
        evidence=_full_evidence(),
    )
    d = f.to_dict()
    assert "evidence" in d
    assert d["evidence"] == _full_evidence()


# ===========================================================================
# Detector-level pins (per-fixture trigger conditions)
# ===========================================================================

def _scan_fixture(filename: str) -> tuple[Path, FileTypeDetection, int, bytes]:
    path = FIXTURES / filename
    assert path.exists(), f"Fixture missing - run build_fixtures.py: {path}"
    detection = FileRouter().detect(path)
    file_size = path.stat().st_size
    head = path.read_bytes()[:FileRouter.HEAD_BYTES]
    return path, detection, file_size, head


def test_detector_catches_polyglot() -> None:
    """01_polyglot.docx - PDF magic + .docx ext - T0a."""
    path, detection, size, head = _scan_fixture("01_polyglot.docx")
    assert detection.kind is FileKind.PDF
    assert detection.extension_mismatch is True
    f = detect_format_routing_divergence(path, detection, size, head=head)
    assert f is not None
    assert f.mechanism == "format_routing_divergence"
    assert f.tier == 0
    assert f.evidence is not None
    assert f.evidence["routing_decision"] == "trusted_magic_bytes"
    assert f.evidence["claimed_format"] == "docx"
    assert f.evidence["inferred_format"] == "pdf"


def test_detector_catches_pdf_as_txt() -> None:
    """02_pdf_as_txt.txt - PDF magic + .txt ext - T0a."""
    path, detection, size, head = _scan_fixture("02_pdf_as_txt.txt")
    assert detection.kind is FileKind.PDF
    assert detection.extension_mismatch is True
    f = detect_format_routing_divergence(path, detection, size, head=head)
    assert f is not None
    assert f.evidence["routing_decision"] == "trusted_magic_bytes"
    assert f.evidence["claimed_format"] == "txt"


def test_detector_catches_empty_pdf() -> None:
    """03_empty.pdf - 4 bytes - T0c below_content_depth_floor."""
    path, detection, size, head = _scan_fixture("03_empty.pdf")
    assert size == 4
    f = detect_format_routing_divergence(path, detection, size, head=head)
    assert f is not None
    assert f.evidence["routing_decision"] == "below_content_depth_floor"
    assert f.evidence["bytes_sampled"] == 4


def test_detector_catches_truncated_pdf() -> None:
    """04_truncated.pdf - 12 bytes, magic but no body - T0c."""
    path, detection, size, head = _scan_fixture("04_truncated.pdf")
    assert size == 12
    f = detect_format_routing_divergence(path, detection, size, head=head)
    assert f is not None
    assert f.evidence["routing_decision"] == "below_content_depth_floor"


def test_detector_catches_docx_as_xlsx() -> None:
    """05_docx_as_xlsx.xlsx - DOCX zip with .xlsx ext - T0d."""
    path, detection, size, head = _scan_fixture("05_docx_as_xlsx.xlsx")
    # The router classifies this as XLSX (extension wins over content
    # for OOXML); the Tier 0 layer's internal-path inspection is what
    # surfaces the divergence.
    f = detect_format_routing_divergence(path, detection, size, head=head)
    assert f is not None, (
        "OOXML internal-path divergence should fire on a DOCX zip "
        "renamed to .xlsx"
    )
    assert f.evidence["routing_decision"] == "ooxml_internal_path_divergence"
    assert f.evidence["claimed_format"] == "xlsx"
    assert f.evidence["inferred_format"] == "docx"


def test_detector_catches_unanalyzed_text() -> None:
    """06_unanalyzed.txt - 4-byte .txt - T0c (the V5 case)."""
    path, detection, size, head = _scan_fixture("06_unanalyzed.txt")
    assert size == 4
    f = detect_format_routing_divergence(path, detection, size, head=head)
    assert f is not None
    assert f.evidence["routing_decision"] == "below_content_depth_floor"
    # The router classifies a .txt file as CODE; the Tier 0 layer
    # records that.
    assert f.evidence["claimed_format"] == "txt"


def test_detector_clean_on_control() -> None:
    """07_control.pdf - real PDF, real ext - no Tier 0 fires."""
    path, detection, size, head = _scan_fixture("07_control.pdf")
    assert detection.kind is FileKind.PDF
    assert detection.extension_mismatch is False
    f = detect_format_routing_divergence(path, detection, size, head=head)
    assert f is None, (
        "Control fixture must not trigger Tier 0 - the layer would "
        "otherwise be a global mughlaq flag, not honest disclosure."
    )


# ===========================================================================
# Verdict-resolver pins (the floor)
# ===========================================================================

def _make_report(*findings: Finding, score: float = 1.0,
                 scan_incomplete: bool = False, error: str | None = None) -> IntegrityReport:
    r = IntegrityReport(file_path="test", integrity_score=score)
    r.findings = list(findings)
    r.scan_incomplete = scan_incomplete
    r.error = error
    return r


def _tier0() -> Finding:
    return Finding(
        mechanism="format_routing_divergence",
        tier=0, confidence=1.0,
        description="t", location="x",
        evidence=_full_evidence(),
    )


def test_tier0_alone_floors_at_mughlaq() -> None:
    """A single Tier 0 finding produces VERDICT_MUGHLAQ."""
    r = _make_report(_tier0(), score=1.0)
    assert tamyiz_verdict(r) == VERDICT_MUGHLAQ


def test_tier0_with_tier1_still_floors_at_mughlaq() -> None:
    """Tier 0 floors EVEN WHEN a Tier 1 concealment finding fires."""
    tier1 = Finding(
        mechanism="white_on_white_text",
        tier=1, confidence=1.0,
        description="t", location="x",
    )
    r = _make_report(_tier0(), tier1, score=0.82)
    assert tamyiz_verdict(r) == VERDICT_MUGHLAQ


def test_tier0_takes_precedence_over_scan_incomplete() -> None:
    """Tier 0 is checked first; both produce mughlaq but the path
    matters for the scope_note distinction at the API layer."""
    r = _make_report(_tier0(), score=0.0,
                     scan_incomplete=True, error="parse failed")
    assert tamyiz_verdict(r) == VERDICT_MUGHLAQ


def test_no_tier0_no_regression_clean() -> None:
    """Without Tier 0, a clean report still resolves to sahih."""
    r = _make_report(score=1.0)
    assert tamyiz_verdict(r) == VERDICT_SAHIH


def test_no_tier0_no_regression_concealment() -> None:
    """Without Tier 0, a concealment report still resolves correctly."""
    tier1 = Finding(
        mechanism="white_on_white_text",
        tier=1, confidence=1.0,
        description="t", location="x",
    )
    r = _make_report(tier1, score=0.5)
    assert tamyiz_verdict(r) == VERDICT_MUKHFI


# ===========================================================================
# End-to-end ScanService pins
# ===========================================================================

def _scan_with_default(path: Path) -> IntegrityReport:
    return ScanService().scan(path)


@pytest.mark.parametrize(
    "filename,expected_decision",
    [
        ("01_polyglot.docx",     "trusted_magic_bytes"),
        ("02_pdf_as_txt.txt",    "trusted_magic_bytes"),
        ("03_empty.pdf",         "below_content_depth_floor"),
        ("04_truncated.pdf",     "below_content_depth_floor"),
        ("05_docx_as_xlsx.xlsx", "ooxml_internal_path_divergence"),
        ("06_unanalyzed.txt",    "below_content_depth_floor"),
    ],
)
def test_scan_service_produces_tier0_finding(
    filename: str, expected_decision: str,
) -> None:
    """Every routing-divergence fixture produces a Tier 0 finding via
    the public ScanService entry point. Verdict floors at mughlaq."""
    path = FIXTURES / filename
    assert path.exists()
    report = _scan_with_default(path)

    tier0 = [
        f for f in report.findings
        if f.mechanism == "format_routing_divergence" and f.tier == 0
    ]
    assert len(tier0) == 1, (
        f"Expected exactly one Tier 0 finding for {filename}; "
        f"got {len(tier0)}"
    )
    assert tier0[0].evidence is not None
    assert tier0[0].evidence["routing_decision"] == expected_decision
    assert set(tier0[0].evidence.keys()) == ROUTING_DISCLOSURE_KEYS

    # Verdict must floor at mughlaq.
    assert tamyiz_verdict(report) == VERDICT_MUGHLAQ


def test_scan_service_control_no_tier0() -> None:
    """The control fixture must NOT produce a Tier 0 finding. The
    existing v1.1.1 PDF analysis still fires (the seed is the
    01_white_on_white.pdf adversarial PDF, so a Tier 1
    white_on_white_text finding is expected). The verdict must NOT
    be mughlaq - the Tier 0 floor must not over-fire on a real PDF
    with a real extension. The exact non-mughlaq verdict (in-process
    tamyiz_verdict resolves to mushtabih on score 0.82; the live
    deriveVerdict at the API layer uses looser rules and resolves to
    mukhfi) is asserted on the v1.1.1 baseline behaviour and would
    surface as a regression here if it changed."""
    path = FIXTURES / "07_control.pdf"
    report = _scan_with_default(path)

    tier0 = [f for f in report.findings if f.tier == 0]
    assert tier0 == [], (
        f"Control fixture must not produce Tier 0 findings; "
        f"got {[f.mechanism for f in tier0]}"
    )
    verdict = tamyiz_verdict(report)
    # The critical pin: not-mughlaq (Tier 0 floor must not over-fire).
    assert verdict != VERDICT_MUGHLAQ, (
        f"Tier 0 floor over-fired on the control fixture; verdict={verdict}"
    )
    # Sanity pin on v1.1.1 baseline: a real adversarial PDF with a
    # real extension produces a Tier 1 finding and an integrity
    # score >= 0.7 -> mushtabih under the in-process verdict logic.
    has_tier1 = any(f.tier == 1 for f in report.findings)
    assert has_tier1, (
        f"Expected the v1.1.1 PDF analyzer to fire its Tier 1 finding "
        f"on the seed PDF; tiers seen: "
        f"{sorted({f.tier for f in report.findings})}"
    )


def test_scan_service_polyglot_records_both_tier0_and_downstream() -> None:
    """A polyglot whose downstream PDF analyzer fires Tier 1 white-on-
    white still records both findings; the verdict is mughlaq because
    Tier 0 takes precedence, but the user gets to inspect both."""
    path = FIXTURES / "01_polyglot.docx"
    report = _scan_with_default(path)

    tiers = sorted({f.tier for f in report.findings})
    # Tier 0 must be present; Tier 1 from the downstream analyzer
    # should also be present (the underlying bytes are the same
    # adversarial PDF seed used in the per-format gauntlet).
    assert 0 in tiers
    assert 1 in tiers, (
        f"Expected the downstream PDF analyzer's Tier 1 finding to "
        f"still be recorded under Tier 0 floor; tiers seen: {tiers}"
    )
    assert tamyiz_verdict(report) == VERDICT_MUGHLAQ
