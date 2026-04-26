"""
Tests for application.scan_service.ScanService + default_pdf_registry.

This file is the Phase 6 parity guardrail of the Al-Baqarah refactor:
it asserts that ``ScanService.scan`` produces byte-identical output to
``bayyinah_v0_1.scan_pdf`` on every Phase 0 fixture — every finding,
every error string, every score, every flag.

Coverage targets:
  * default_pdf_registry shape — names, order, class identity
  * ScanService construction — default / custom registry / custom router
  * Happy-path semantics per fixture (clean, text, object, positive_combined)
  * Error paths identical to v0.1:
      - missing file → "File not found: <path>"
      - unreadable bytes → "Could not open PDF: <pymupdf-message>"
      - non-PDF bytes → "Could not open PDF: <pymupdf-message>"
  * scan_incomplete clamp — if any path sets scan_incomplete, score ≤ 0.5
  * Parity sweep against bayyinah_v0_1.scan_pdf — every field matches
    after IndirectObject-id normalisation
  * Additive isolation — ScanService is distinct from v0.1.ScanService
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import bayyinah_v0_1
from analyzers import AnalyzerRegistry, BatinObjectAnalyzer, ZahirTextAnalyzer
from application import ScanService, default_pdf_registry
from domain import IntegrityReport
from infrastructure import FileRouter

from tests.make_test_documents import FIXTURES, FIXTURES_DIR


# ---------------------------------------------------------------------------
# Fixture regeneration (same pattern as tests/analyzers/test_object_analyzer.py)
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


# ---------------------------------------------------------------------------
# IndirectObject-repr normalisation — same pattern tests/test_fixtures.py uses.
#
# pypdf's IndirectObject.__repr__ embeds ``id()`` of the parent document,
# which differs between independent pypdf readers. Every parity
# comparison below normalises the id component to keep byte-level
# identity meaningful despite this environmental non-determinism.
# ---------------------------------------------------------------------------

_INDIRECT_RE = re.compile(r"IndirectObject\((\d+),\s*(\d+),\s*\d+\)")


def _normalise(s: str) -> str:
    return _INDIRECT_RE.sub(r"IndirectObject(\1, \2, <id>)", s)


def _finding_tuple(f: Any) -> tuple:
    """Byte-level comparison of a finding's v0.1-equivalent fields."""
    return (
        f.mechanism,
        f.tier,
        round(f.confidence, 6),
        _normalise(f.description),
        _normalise(f.location),
        _normalise(f.surface),
        _normalise(f.concealed),
    )


# ---------------------------------------------------------------------------
# default_pdf_registry
# ---------------------------------------------------------------------------

class TestDefaultPdfRegistry:
    """The shipped default registry factory."""

    def test_returns_analyzer_registry(self) -> None:
        assert isinstance(default_pdf_registry(), AnalyzerRegistry)

    def test_registers_exactly_two_analyzers(self) -> None:
        assert len(default_pdf_registry()) == 2

    def test_registration_order_is_text_then_object(self) -> None:
        """The order matches v0.1's DEFAULT_PDF_ANALYZERS list — text
        findings emit before object findings in the merged report."""
        assert default_pdf_registry().names() == ["text_layer", "object_layer"]

    def test_registers_zahir_text_analyzer(self) -> None:
        registry = default_pdf_registry()
        assert registry.get("text_layer") is ZahirTextAnalyzer

    def test_registers_batin_object_analyzer(self) -> None:
        registry = default_pdf_registry()
        assert registry.get("object_layer") is BatinObjectAnalyzer

    def test_returns_fresh_instance_each_call(self) -> None:
        """Factory, not singleton — tests need independent registries."""
        a = default_pdf_registry()
        b = default_pdf_registry()
        assert a is not b

    def test_fresh_registries_do_not_share_state(self) -> None:
        a = default_pdf_registry()
        a.unregister("text_layer")
        b = default_pdf_registry()
        assert "text_layer" in b
        assert "text_layer" not in a


# ---------------------------------------------------------------------------
# ScanService construction
# ---------------------------------------------------------------------------

class TestScanServiceConstruction:
    def test_no_args_uses_default_registry(self) -> None:
        # Phase 24: the shipped default registry carries the two PDF
        # analyzers (unchanged order), the text-file and JSON analyzers
        # (Phase 9), the image + SVG analyzers (Phase 10), the DOCX
        # analyzer (Phase 15), the HTML analyzer (Phase 16), the XLSX
        # analyzer (Phase 17), the PPTX analyzer (Phase 18), the EML
        # analyzer (Phase 19), the CSV analyzer (Phase 20), the universal
        # FallbackAnalyzer (Phase 21 — Al-Baqarah 2:143: the middle-
        # community witness of last resort for any file the router
        # leaves unclassified), and the VideoAnalyzer (Phase 24 —
        # Al-Baqarah 2:19-20: the rainstorm's darker layers carry
        # concealment while the lightning of playback holds attention).
        # The FileKind filter in scan_all skips non-matching analyzers
        # on a given input, so PDF parity is preserved across every
        # registration phase, FallbackAnalyzer itself only fires on
        # FileKind.UNKNOWN, and VideoAnalyzer only fires on the four
        # VIDEO_* kinds.
        s = ScanService()
        assert s.registry.names() == [
            "text_layer",
            "object_layer",
            "text_file",
            "json_file",
            "image",
            "svg",
            "docx",
            "html",
            "xlsx",
            "pptx",
            "eml",
            "csv",
            "fallback",
            "video",
            "audio",
        ]

    def test_no_args_uses_default_file_router(self) -> None:
        s = ScanService()
        assert isinstance(s.file_router, FileRouter)

    def test_accepts_custom_registry(self) -> None:
        custom = AnalyzerRegistry()
        custom.register(ZahirTextAnalyzer)
        s = ScanService(registry=custom)
        assert s.registry is custom
        assert s.registry.names() == ["text_layer"]

    def test_accepts_custom_file_router(self) -> None:
        router = FileRouter()
        s = ScanService(file_router=router)
        assert s.file_router is router

    def test_empty_registry_is_allowed(self) -> None:
        """An empty registry yields a clean, no-op scan — no findings,
        no errors, score 1.0."""
        empty = AnalyzerRegistry()
        s = ScanService(registry=empty)
        report = s.scan(CLEAN_PDF)
        assert report.findings == []
        assert report.integrity_score == 1.0
        assert report.error is None
        assert report.scan_incomplete is False

    def test_repr_mentions_registered_analyzers(self) -> None:
        s = ScanService()
        r = repr(s)
        assert "ScanService" in r
        assert "text_layer" in r
        assert "object_layer" in r


# ---------------------------------------------------------------------------
# scan() return type
# ---------------------------------------------------------------------------

class TestScanReturnType:
    def test_returns_integrity_report(self) -> None:
        report = ScanService().scan(CLEAN_PDF)
        assert isinstance(report, IntegrityReport)

    def test_accepts_string_path(self) -> None:
        """scan() should coerce strings to Path for caller convenience."""
        report = ScanService().scan(str(CLEAN_PDF))
        assert report.file_path == str(CLEAN_PDF)

    def test_accepts_path_object(self) -> None:
        report = ScanService().scan(CLEAN_PDF)
        assert report.file_path == str(CLEAN_PDF)

    def test_file_path_is_reported_as_string(self) -> None:
        report = ScanService().scan(CLEAN_PDF)
        assert isinstance(report.file_path, str)


# ---------------------------------------------------------------------------
# clean.pdf — the reference standard
# ---------------------------------------------------------------------------

class TestCleanPdf:
    def test_no_findings(self) -> None:
        report = ScanService().scan(CLEAN_PDF)
        assert report.findings == []

    def test_perfect_score(self) -> None:
        report = ScanService().scan(CLEAN_PDF)
        assert report.integrity_score == 1.0

    def test_no_error(self) -> None:
        report = ScanService().scan(CLEAN_PDF)
        assert report.error is None

    def test_not_incomplete(self) -> None:
        report = ScanService().scan(CLEAN_PDF)
        assert report.scan_incomplete is False


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

class TestMissingFile:
    def test_error_message_matches_v01(self, tmp_path: Path) -> None:
        ghost = tmp_path / "does_not_exist.pdf"
        report = ScanService().scan(ghost)
        assert report.error == f"File not found: {ghost}"

    def test_score_is_zero(self, tmp_path: Path) -> None:
        report = ScanService().scan(tmp_path / "ghost.pdf")
        assert report.integrity_score == 0.0

    def test_scan_incomplete(self, tmp_path: Path) -> None:
        report = ScanService().scan(tmp_path / "ghost.pdf")
        assert report.scan_incomplete is True

    def test_no_findings(self, tmp_path: Path) -> None:
        report = ScanService().scan(tmp_path / "ghost.pdf")
        assert report.findings == []

    def test_analyzers_are_not_called(self, tmp_path: Path) -> None:
        """The short-circuit must fire before any analyzer instantiation."""
        called: list[str] = []

        class RecordingAnalyzer:
            name = "recording"
            error_prefix = "Recording"
            source_layer = "zahir"

            def scan(self, pdf_path: Any) -> IntegrityReport:
                called.append(str(pdf_path))
                return IntegrityReport(
                    file_path=str(pdf_path), integrity_score=1.0,
                )

        # We bypass class-level validation by stashing an instance in the
        # registry's internal dict as if it were a class whose () yields it.
        class _ClassLike:
            name = "recording"
            def __call__(self) -> Any:
                return RecordingAnalyzer()

        registry = AnalyzerRegistry()
        registry._registry["recording"] = _ClassLike()  # type: ignore[assignment]
        s = ScanService(registry=registry)
        s.scan(tmp_path / "ghost.pdf")
        assert called == [], f"analyzer was called for a missing file: {called}"

    def test_file_path_reported(self, tmp_path: Path) -> None:
        ghost = tmp_path / "absent.pdf"
        report = ScanService().scan(ghost)
        assert report.file_path == str(ghost)


class TestUnopenablePdf:
    """pymupdf cannot parse the file → same short-circuit as v0.1."""

    def test_non_pdf_bytes_produce_could_not_open_error(
        self, tmp_path: Path,
    ) -> None:
        junk = tmp_path / "junk.pdf"
        junk.write_bytes(b"this is definitely not a PDF file")
        report = ScanService().scan(junk)
        assert report.error is not None
        assert report.error.startswith("Could not open PDF:")

    def test_error_string_matches_v01_byte_for_byte(
        self, tmp_path: Path,
    ) -> None:
        """The error string we produce must equal v0.1's string exactly —
        unwrapping PDFParseError.__cause__ is what makes this work."""
        junk = tmp_path / "not_a_pdf.pdf"
        junk.write_bytes(b"\x00\x00\x00not a pdf at all\x00\x00")
        ours = ScanService().scan(junk)
        theirs = bayyinah_v0_1.scan_pdf(junk)
        assert ours.error == theirs.error

    def test_score_is_zero_on_open_failure(self, tmp_path: Path) -> None:
        junk = tmp_path / "corrupt.pdf"
        junk.write_bytes(b"garbage")
        report = ScanService().scan(junk)
        assert report.integrity_score == 0.0

    def test_scan_incomplete_on_open_failure(self, tmp_path: Path) -> None:
        junk = tmp_path / "corrupt.pdf"
        junk.write_bytes(b"garbage")
        report = ScanService().scan(junk)
        assert report.scan_incomplete is True

    def test_no_findings_on_open_failure(self, tmp_path: Path) -> None:
        """Analyzers must not run when pymupdf pre-flight fails."""
        junk = tmp_path / "corrupt.pdf"
        junk.write_bytes(b"garbage")
        report = ScanService().scan(junk)
        assert report.findings == []


# ---------------------------------------------------------------------------
# Per-fixture happy-path semantics (intent preserved from v0 detector tests)
# ---------------------------------------------------------------------------

# (fixture_name, expected_mechanism_set)
_TEXT_FIXTURE_EXPECTED: dict[str, frozenset[str]] = {
    "text.zero_width":       frozenset({"zero_width_chars"}),
    "text.tag_characters":   frozenset({"tag_chars"}),
    "text.bidi_control":     frozenset({"bidi_control"}),
    "text.homoglyph":        frozenset({"homoglyph"}),
    "text.invisible_render": frozenset({"invisible_render_mode"}),
    "text.microscopic_font": frozenset({"microscopic_font"}),
    "text.white_on_white":   frozenset({"white_on_white_text"}),
    "text.overlapping":      frozenset({"overlapping_text"}),
}

_OBJECT_FIXTURE_EXPECTED: dict[str, frozenset[str]] = {
    "object.embedded_javascript":  frozenset({"javascript", "openaction"}),
    "object.embedded_attachment":  frozenset({"embedded_file"}),
    "object.hidden_ocg":           frozenset({"hidden_ocg"}),
    "object.metadata_injection":   frozenset({"metadata_anomaly"}),
    "object.tounicode_cmap":       frozenset({"tounicode_anomaly"}),
    "object.incremental_update":   frozenset({"incremental_update"}),
    "object.additional_actions":   frozenset({"additional_actions"}),
}


@pytest.mark.parametrize(
    "fixture_name,expected",
    list(_TEXT_FIXTURE_EXPECTED.items()),
    ids=list(_TEXT_FIXTURE_EXPECTED.keys()),
)
def test_text_fixture_fires_expected_mechanisms(
    fixture_name: str, expected: frozenset[str],
) -> None:
    fx = FIXTURES[fixture_name]
    report = ScanService().scan(fx.out_path)
    mechanisms = {f.mechanism for f in report.findings}
    assert mechanisms == expected, (
        f"{fixture_name!r} mechanism mismatch:"
        f"\n  expected: {sorted(expected)}"
        f"\n  got:      {sorted(mechanisms)}"
    )


@pytest.mark.parametrize(
    "fixture_name,expected",
    list(_OBJECT_FIXTURE_EXPECTED.items()),
    ids=list(_OBJECT_FIXTURE_EXPECTED.keys()),
)
def test_object_fixture_fires_expected_mechanisms(
    fixture_name: str, expected: frozenset[str],
) -> None:
    fx = FIXTURES[fixture_name]
    report = ScanService().scan(fx.out_path)
    mechanisms = {f.mechanism for f in report.findings}
    assert mechanisms == expected, (
        f"{fixture_name!r} mechanism mismatch:"
        f"\n  expected: {sorted(expected)}"
        f"\n  got:      {sorted(mechanisms)}"
    )


def test_text_fixtures_have_text_findings_before_object_findings() -> None:
    """Registration order = emission order. On a pure text fixture the
    object analyzer contributes nothing, but on positive_combined (mixed
    text + object) the order matters for byte-level parity with v0.1."""
    report = ScanService().scan(POSITIVE_COMBINED)
    text_idxs = [
        i for i, f in enumerate(report.findings) if f.source_layer == "zahir"
    ]
    batin_idxs = [
        i for i, f in enumerate(report.findings) if f.source_layer == "batin"
    ]
    if text_idxs and batin_idxs:
        assert max(text_idxs) < min(batin_idxs), (
            "text findings must emit before object findings — matches "
            "v0.1 DEFAULT_PDF_ANALYZERS order"
        )


# ---------------------------------------------------------------------------
# Byte-identical parity with bayyinah_v0_1.scan_pdf
# ---------------------------------------------------------------------------

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
def test_parity_finding_tuples_with_v01_scan_pdf(pdf_path: Path) -> None:
    """For every Phase 0 fixture, ScanService.scan must emit the same
    (mechanism, tier, confidence, description, location, surface,
    concealed) tuples as v0.1.scan_pdf — in the same order."""
    ours = ScanService().scan(pdf_path)
    theirs = bayyinah_v0_1.scan_pdf(pdf_path)

    ours_tuples = [_finding_tuple(f) for f in ours.findings]
    theirs_tuples = [_finding_tuple(f) for f in theirs.findings]

    assert ours_tuples == theirs_tuples, (
        f"\nParity diverged on {pdf_path.name}:"
        f"\n  ours  ({len(ours_tuples)}): {ours_tuples}"
        f"\n  v0.1  ({len(theirs_tuples)}): {theirs_tuples}"
    )


@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_parity_integrity_score_with_v01(pdf_path: Path) -> None:
    ours = ScanService().scan(pdf_path)
    theirs = bayyinah_v0_1.scan_pdf(pdf_path)
    assert abs(ours.integrity_score - theirs.integrity_score) < 1e-9, (
        f"{pdf_path.name}: score diverged — "
        f"ours={ours.integrity_score}, v0.1={theirs.integrity_score}"
    )


@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_parity_error_with_v01(pdf_path: Path) -> None:
    ours = ScanService().scan(pdf_path)
    theirs = bayyinah_v0_1.scan_pdf(pdf_path)
    assert ours.error == theirs.error, (
        f"{pdf_path.name}: error diverged — "
        f"ours={ours.error!r}, v0.1={theirs.error!r}"
    )


@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_parity_scan_incomplete_with_v01(pdf_path: Path) -> None:
    ours = ScanService().scan(pdf_path)
    theirs = bayyinah_v0_1.scan_pdf(pdf_path)
    assert ours.scan_incomplete == theirs.scan_incomplete, (
        f"{pdf_path.name}: scan_incomplete diverged — "
        f"ours={ours.scan_incomplete}, v0.1={theirs.scan_incomplete}"
    )


@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_parity_finding_count_with_v01(pdf_path: Path) -> None:
    ours = ScanService().scan(pdf_path)
    theirs = bayyinah_v0_1.scan_pdf(pdf_path)
    assert len(ours.findings) == len(theirs.findings), (
        f"{pdf_path.name}: count diverged — "
        f"ours={len(ours.findings)}, v0.1={len(theirs.findings)}"
    )


def test_parity_missing_file_error(tmp_path: Path) -> None:
    ghost = tmp_path / "does_not_exist.pdf"
    ours = ScanService().scan(ghost)
    theirs = bayyinah_v0_1.scan_pdf(ghost)
    assert ours.error == theirs.error
    assert ours.integrity_score == theirs.integrity_score
    assert ours.scan_incomplete == theirs.scan_incomplete


def test_parity_unopenable_pdf(tmp_path: Path) -> None:
    corrupt = tmp_path / "corrupt.pdf"
    corrupt.write_bytes(b"%PDF-1.4 garbled garbled garbled")
    ours = ScanService().scan(corrupt)
    theirs = bayyinah_v0_1.scan_pdf(corrupt)
    assert ours.error == theirs.error
    assert ours.integrity_score == theirs.integrity_score
    assert ours.scan_incomplete == theirs.scan_incomplete
    assert len(ours.findings) == len(theirs.findings)


# ---------------------------------------------------------------------------
# scan_incomplete clamp (defence-in-depth — registry already clamps)
# ---------------------------------------------------------------------------

class TestScanIncompleteClamp:
    def test_clamp_caps_score_at_half_when_incomplete(
        self, tmp_path: Path,
    ) -> None:
        """If scan_incomplete is set, integrity_score must not exceed 0.5."""
        corrupt = tmp_path / "corrupt.pdf"
        corrupt.write_bytes(b"broken")
        report = ScanService().scan(corrupt)
        assert report.scan_incomplete is True
        assert report.integrity_score <= 0.5

    def test_no_clamp_when_scan_is_complete(self) -> None:
        """On clean.pdf the score is 1.0, not clamped — scan_incomplete
        is false, so the clamp must not fire."""
        report = ScanService().scan(CLEAN_PDF)
        assert report.scan_incomplete is False
        assert report.integrity_score == 1.0

    def test_clamp_fires_when_analyzer_emits_scan_error(
        self, tmp_path: Path,
    ) -> None:
        """A scan_error finding by itself (no report.error) still sets
        scan_incomplete and triggers the clamp."""
        # Construct a minimal registry whose only analyzer emits a
        # scan_error but no top-level error. The clamp must still fire.
        from domain import Finding
        from analyzers.base import BaseAnalyzer

        class ScanErrorAnalyzer(BaseAnalyzer):
            name = "scan_error_only"
            error_prefix = "Scan error only"
            source_layer = "batin"

            def scan(self, pdf_path: Any) -> IntegrityReport:
                return IntegrityReport(
                    file_path=str(pdf_path),
                    integrity_score=1.0,
                    findings=[Finding(
                        mechanism="scan_error",
                        tier=3, confidence=0.5,
                        description="simulated", location="document",
                        surface="(skipped)", concealed="simulated",
                        source_layer="batin",
                    )],
                )

        custom = AnalyzerRegistry()
        custom.register(ScanErrorAnalyzer)
        report = ScanService(registry=custom).scan(CLEAN_PDF)
        assert report.scan_incomplete is True
        assert report.integrity_score <= 0.5


# ---------------------------------------------------------------------------
# Additive isolation — ScanService is distinct from v0.1
# ---------------------------------------------------------------------------

class TestAdditiveIsolation:
    def test_scan_service_class_distinct_from_v01(self) -> None:
        """The new class must not be the legacy class. If they became the
        same object, we would have accidentally re-bound v0.1's export."""
        assert ScanService is not bayyinah_v0_1.ScanService

    def test_legacy_scan_pdf_still_works(self) -> None:
        """v0.1's public surface must still produce a report — the
        Phase 6 port must not have broken it."""
        report = bayyinah_v0_1.scan_pdf(CLEAN_PDF)
        assert isinstance(report.findings, list)
        assert report.integrity_score == 1.0

    def test_default_pdf_registry_returns_new_instance_per_call(self) -> None:
        """Independence requirement for parallel tests / parallel scans."""
        a = default_pdf_registry()
        b = default_pdf_registry()
        assert a is not b


# ---------------------------------------------------------------------------
# Resource hygiene
# ---------------------------------------------------------------------------

class TestResourceHygiene:
    def test_repeated_scans_on_same_service(self) -> None:
        """The service must be reusable across many scans — no lingering
        state from a previous file."""
        service = ScanService()
        for _ in range(5):
            report = service.scan(CLEAN_PDF)
            assert report.integrity_score == 1.0
            assert report.error is None

    def test_repeated_scans_on_different_fixtures(self) -> None:
        service = ScanService()
        for pdf in _all_phase0_fixtures():
            report = service.scan(pdf)
            assert isinstance(report, IntegrityReport)


# ---------------------------------------------------------------------------
# Phase 12 — scan_batch + BatchScanResult + cross-file correlation
#
# Batch semantics we are pinning down:
#   * BatchScanResult is a lightweight dataclass: ``reports`` +
#     ``cross_file_findings``. No extra fields creep in.
#   * Empty batches return empty containers (no None, no exceptions).
#   * Per-file reports returned by scan_batch are byte-identical to a
#     single ``scan(path)`` call — batching never mutates the per-file
#     report, it only *adds* the cross-file view.
#   * Input order is preserved in ``reports``.
#   * A coordinated payload present in two non-PDF files surfaces as a
#     ``cross_format_payload_match`` finding in
#     ``cross_file_findings`` — this is the new-depth the batch API
#     exists to enable (Al-Baqarah 2:282 — two witnesses).
#   * PDFs are excluded from the correlation pool. A PDF in the batch
#     still gets scanned and reported (parity preserved), but its
#     findings are not rolled up into the cross-file buckets. This
#     guarantee is load-bearing: it protects the v0/v0.1 PDF parity
#     contract even when PDFs are batched alongside other formats.
# ---------------------------------------------------------------------------


# Late import — BatchScanResult is not exported from application.__init__
# (see application/__init__.py.__all__), so we reach into the module.
from application.scan_service import BatchScanResult  # noqa: E402


IMAGE_FIXTURES_DIR: Path = (
    Path(__file__).resolve().parent.parent / "fixtures" / "images"
)
ADVERSARIAL_IMAGES_DIR: Path = IMAGE_FIXTURES_DIR / "adversarial"


@pytest.fixture(scope="module", autouse=True)
def _ensure_image_fixtures_built() -> None:
    """Regenerate image fixtures if any Phase 12 batch fixture is missing.

    Matches the pattern in tests/test_image_fixtures.py — in-process
    first, subprocess fallback.
    """
    required = (
        ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png",
        ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg",
        ADVERSARIAL_IMAGES_DIR / "coordinated_concealment.svg",
        ADVERSARIAL_IMAGES_DIR / "generative_cipher.png",
    )
    if all(p.exists() for p in required):
        return
    try:
        from tests.make_image_fixtures import generate_all
        generate_all(IMAGE_FIXTURES_DIR)
    except Exception:  # pragma: no cover — defensive fallback
        subprocess.run(
            [sys.executable, "-m", "tests.make_image_fixtures"],
            check=True,
            cwd=str(IMAGE_FIXTURES_DIR.parent.parent.parent),
        )


class TestBatchScanResultShape:
    """The dataclass surface itself — small, stable, and additive."""

    def test_is_a_dataclass(self) -> None:
        from dataclasses import is_dataclass
        assert is_dataclass(BatchScanResult)

    def test_has_exactly_the_expected_fields(self) -> None:
        from dataclasses import fields
        names = {f.name for f in fields(BatchScanResult)}
        assert names == {"reports", "cross_file_findings"}

    def test_reports_and_cross_file_findings_are_lists(self) -> None:
        result = BatchScanResult(reports=[], cross_file_findings=[])
        assert isinstance(result.reports, list)
        assert isinstance(result.cross_file_findings, list)

    def test_cross_file_findings_default_is_empty_list(self) -> None:
        """The dataclass default makes the no-correlation case cheap."""
        result = BatchScanResult(reports=[])
        assert result.cross_file_findings == []

    def test_default_factory_is_not_shared_across_instances(self) -> None:
        """Guard against the ``field(default=[])`` bug — mutating one
        instance's list must not leak into other instances."""
        a = BatchScanResult(reports=[])
        b = BatchScanResult(reports=[])
        a.cross_file_findings.append("leak-canary")
        assert b.cross_file_findings == []


class TestScanBatchEmpty:
    def test_empty_iterable_returns_empty_batch_result(self) -> None:
        result = ScanService().scan_batch([])
        assert isinstance(result, BatchScanResult)
        assert result.reports == []
        assert result.cross_file_findings == []

    def test_empty_generator_returns_empty_batch_result(self) -> None:
        """scan_batch accepts any Iterable, not just lists."""
        def _gen():
            return
            yield  # pragma: no cover — make this a generator
        result = ScanService().scan_batch(_gen())
        assert result.reports == []
        assert result.cross_file_findings == []


class TestScanBatchSingleFile:
    def test_single_clean_pdf_has_one_report(self) -> None:
        result = ScanService().scan_batch([CLEAN_PDF])
        assert len(result.reports) == 1
        assert isinstance(result.reports[0], IntegrityReport)

    def test_single_file_report_matches_single_scan(self) -> None:
        """Batching must never perturb the per-file report — the
        single-file report returned from scan_batch must be byte-
        identical (finding-tuple-equal) to what ``scan(path)`` returns."""
        service = ScanService()
        single = service.scan(POSITIVE_COMBINED)
        batch = service.scan_batch([POSITIVE_COMBINED])
        batched = batch.reports[0]
        assert [_finding_tuple(f) for f in batched.findings] == [
            _finding_tuple(f) for f in single.findings
        ]
        assert batched.integrity_score == single.integrity_score
        assert batched.error == single.error
        assert batched.scan_incomplete == single.scan_incomplete

    def test_single_file_produces_no_cross_file_findings(self) -> None:
        """``cross_format_payload_match`` requires appearances in >=2
        files — a single file can never satisfy that."""
        result = ScanService().scan_batch([CLEAN_PDF])
        assert result.cross_file_findings == []


class TestScanBatchOrderAndIdentity:
    def test_input_order_is_preserved_in_reports(self) -> None:
        service = ScanService()
        order = [
            CLEAN_PDF,
            POSITIVE_COMBINED,
            CLEAN_PDF,
        ]
        result = service.scan_batch(order)
        assert [r.file_path for r in result.reports] == [
            str(p) for p in order
        ]

    def test_reports_length_equals_input_length(self) -> None:
        paths = [CLEAN_PDF, CLEAN_PDF, CLEAN_PDF]
        result = ScanService().scan_batch(paths)
        assert len(result.reports) == len(paths)

    def test_accepts_string_paths(self) -> None:
        """Callers shouldn't need to pre-convert paths — scan_batch
        follows scan()'s convention of coercing to Path internally."""
        result = ScanService().scan_batch([str(CLEAN_PDF)])
        assert len(result.reports) == 1
        assert result.reports[0].file_path == str(CLEAN_PDF)


class TestScanBatchCrossFileCorrelation:
    """The headline Phase 12 capability — same payload across files."""

    def test_coordinated_pair_surfaces_cross_format_payload_match(
        self,
    ) -> None:
        """coordinated_pair_a.png + coordinated_pair_b.svg carry the
        same hidden phrase via two different mechanisms
        (image_text_metadata + svg_hidden_text). Individually they fire
        one finding each; batched they also produce one
        ``cross_format_payload_match`` finding."""
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = ScanService().scan_batch([pair_a, pair_b])
        mechs = [f.mechanism for f in result.cross_file_findings]
        assert "cross_format_payload_match" in mechs, (
            f"expected cross_format_payload_match in {mechs}"
        )

    def test_cross_file_finding_references_both_files(self) -> None:
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = ScanService().scan_batch([pair_a, pair_b])
        cross = [
            f for f in result.cross_file_findings
            if f.mechanism == "cross_format_payload_match"
        ]
        assert cross, "no cross_format_payload_match finding emitted"
        loc = cross[0].location
        assert str(pair_a) in loc
        assert str(pair_b) in loc

    def test_cross_file_finding_carries_fingerprint_in_concealed(
        self,
    ) -> None:
        """The concealed field is where the fingerprint lives so callers
        can group cross-file findings by payload identity."""
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = ScanService().scan_batch([pair_a, pair_b])
        cross = [
            f for f in result.cross_file_findings
            if f.mechanism == "cross_format_payload_match"
        ]
        assert cross
        assert "fingerprint" in cross[0].concealed

    def test_cross_file_finding_source_layer_is_batin(self) -> None:
        """Cross-file correlation is a batin (structural) signal —
        no single-file surface shows it."""
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = ScanService().scan_batch([pair_a, pair_b])
        cross = [
            f for f in result.cross_file_findings
            if f.mechanism == "cross_format_payload_match"
        ]
        assert cross
        assert cross[0].source_layer == "batin"

    def test_per_file_reports_unchanged_by_cross_file_correlation(
        self,
    ) -> None:
        """The per-file reports inside ``reports`` must be byte-identical
        to standalone ``scan(path)`` output — batching *adds* the
        cross-file view; it never edits the per-file view."""
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        service = ScanService()
        solo_a = service.scan(pair_a)
        solo_b = service.scan(pair_b)
        batch = service.scan_batch([pair_a, pair_b])
        batched_a, batched_b = batch.reports
        assert [_finding_tuple(f) for f in batched_a.findings] == [
            _finding_tuple(f) for f in solo_a.findings
        ]
        assert [_finding_tuple(f) for f in batched_b.findings] == [
            _finding_tuple(f) for f in solo_b.findings
        ]

    def test_unrelated_files_produce_no_cross_file_findings(self) -> None:
        """Two independent fixtures with no shared payload must not
        trigger a cross_format_payload_match — otherwise we have a
        false positive that would be far worse than a missed detection."""
        gen_cipher = ADVERSARIAL_IMAGES_DIR / "generative_cipher.png"
        coord_conceal = ADVERSARIAL_IMAGES_DIR / "coordinated_concealment.svg"
        result = ScanService().scan_batch([gen_cipher, coord_conceal])
        mechs = [f.mechanism for f in result.cross_file_findings]
        assert "cross_format_payload_match" not in mechs, (
            "false-positive cross-file correlation on unrelated fixtures: "
            f"{mechs}"
        )


class TestScanBatchPdfExclusion:
    """PDF parity is load-bearing — batching PDFs alongside other
    formats must never contaminate the PDF reports or synthesise a
    cross-file finding from PDF payloads."""

    def test_pdf_report_in_batch_matches_standalone_scan(self) -> None:
        service = ScanService()
        solo = service.scan(POSITIVE_COMBINED)
        batch = service.scan_batch([
            POSITIVE_COMBINED,
            ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png",
        ])
        batched_pdf = batch.reports[0]
        assert [_finding_tuple(f) for f in batched_pdf.findings] == [
            _finding_tuple(f) for f in solo.findings
        ]
        assert batched_pdf.integrity_score == solo.integrity_score
        assert batched_pdf.error == solo.error
        assert batched_pdf.scan_incomplete == solo.scan_incomplete

    def test_pdf_findings_never_appear_in_cross_file_bucket(self) -> None:
        """Batching a PDF (with findings) alongside a non-PDF (no shared
        payload with the PDF) must not produce any cross-file finding
        that references the PDF's path."""
        result = ScanService().scan_batch([
            POSITIVE_COMBINED,
            ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png",
        ])
        for f in result.cross_file_findings:
            assert str(POSITIVE_COMBINED) not in f.location, (
                f"PDF leaked into cross-file correlation: "
                f"{f.mechanism} @ {f.location}"
            )

    def test_pdf_in_batch_does_not_suppress_non_pdf_correlation(
        self,
    ) -> None:
        """Interleaving a PDF between the two coordinated-pair files
        must not prevent the pair from correlating — PDF exclusion is
        one-way: PDFs are skipped, but the remaining non-PDFs still
        correlate normally."""
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = ScanService().scan_batch([pair_a, CLEAN_PDF, pair_b])
        mechs = [f.mechanism for f in result.cross_file_findings]
        assert "cross_format_payload_match" in mechs

    def test_all_pdf_batch_emits_no_cross_file_findings(self) -> None:
        """A batch of only PDFs must produce zero cross-file findings —
        they were all filtered out of the correlation pool."""
        result = ScanService().scan_batch([
            CLEAN_PDF,
            POSITIVE_COMBINED,
            CLEAN_PDF,
        ])
        assert result.cross_file_findings == []


class TestScanBatchParityIsolation:
    """Batch API must not perturb non-batch callers in any observable
    way — no global state, no shared mutable defaults."""

    def test_scan_after_scan_batch_still_matches_v01(self) -> None:
        """Running scan_batch then scan on a Phase 0 fixture must still
        parity-match v0.1 exactly — no residue from batching."""
        service = ScanService()
        service.scan_batch([ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"])
        ours = service.scan(POSITIVE_COMBINED)
        theirs = bayyinah_v0_1.scan_pdf(POSITIVE_COMBINED)
        assert [_finding_tuple(f) for f in ours.findings] == [
            _finding_tuple(f) for f in theirs.findings
        ]

    def test_two_separate_services_do_not_share_cross_file_state(
        self,
    ) -> None:
        """Independent ScanService instances must produce independent
        batch results — no shared correlation state."""
        a = ScanService()
        b = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        ra = a.scan_batch([pair_a, pair_b])
        rb = b.scan_batch([pair_a, pair_b])
        # Both surface the same correlation — determinism, not sharing.
        mechs_a = [f.mechanism for f in ra.cross_file_findings]
        mechs_b = [f.mechanism for f in rb.cross_file_findings]
        assert mechs_a == mechs_b


# ---------------------------------------------------------------------------
# Phase 13 — BatchScanResult reporting helpers
# ---------------------------------------------------------------------------


class TestBatchScanResultReportingHelpers:
    """The Phase 13 helpers on ``BatchScanResult`` are read-only views
    over ``reports`` and ``cross_file_findings``. Tests pin their
    contract against both empty and populated batches."""

    def test_empty_batch_has_no_cross_file_correlation(self) -> None:
        result = BatchScanResult(reports=[])
        assert result.has_cross_file_correlation is False
        assert result.cross_file_finding_count == 0
        assert result.involved_files == []

    def test_populated_batch_reports_count(self) -> None:
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = service.scan_batch([pair_a, pair_b])
        assert result.files_scanned == 2
        assert result.has_cross_file_correlation is True
        assert result.cross_file_finding_count == 1

    def test_involved_files_lists_both_paths_in_pair(self) -> None:
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = service.scan_batch([pair_a, pair_b])
        involved = result.involved_files
        assert str(pair_a) in involved
        assert str(pair_b) in involved

    def test_involved_files_is_deduplicated_and_sorted(self) -> None:
        """When the same file surfaces in multiple cross-file findings,
        ``involved_files`` reports it once. Ordering is lexicographic."""
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = service.scan_batch([pair_a, pair_b])
        involved = result.involved_files
        assert involved == sorted(involved)
        assert len(involved) == len(set(involved))

    def test_total_per_file_findings_sums_over_reports(self) -> None:
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = service.scan_batch([pair_a, pair_b])
        expected = sum(len(r.findings) for r in result.reports)
        assert result.total_per_file_findings == expected

    def test_total_findings_includes_cross_file(self) -> None:
        """``total_findings`` is the single number a caller reports to
        the user: every per-file finding plus every correlation."""
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = service.scan_batch([pair_a, pair_b])
        assert result.total_findings == (
            result.total_per_file_findings + result.cross_file_finding_count
        )

    def test_any_scan_incomplete_false_on_clean_batch(self) -> None:
        """The cross-file fixture pair is all non-PDF, well-formed
        content — no scan_incomplete should fire."""
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = service.scan_batch([pair_a, pair_b])
        assert result.any_scan_incomplete is False

    def test_any_scan_incomplete_true_when_missing_file_in_batch(self) -> None:
        """A path the router cannot find short-circuits with
        ``scan_incomplete=True``; the batch helper bubbles that up."""
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        missing = Path("/tmp/definitely_not_there_bayyinah_phase_13.png")
        assert not missing.exists()
        result = service.scan_batch([pair_a, missing])
        assert result.any_scan_incomplete is True

    def test_reports_by_path_returns_dict_view(self) -> None:
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        pair_b = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_b.svg"
        result = service.scan_batch([pair_a, pair_b])
        by_path = result.reports_by_path()
        assert str(pair_a) in by_path
        assert str(pair_b) in by_path
        # Every value is the same IntegrityReport object the list holds.
        for report in result.reports:
            assert by_path[report.file_path] is report

    def test_helpers_are_consistent_with_single_file_batch(self) -> None:
        """Single-file batch — correlation impossible by construction.
        Helpers should report zero on the cross-file side."""
        service = ScanService()
        pair_a = ADVERSARIAL_IMAGES_DIR / "coordinated_pair_a.png"
        result = service.scan_batch([pair_a])
        assert result.files_scanned == 1
        assert result.has_cross_file_correlation is False
        assert result.cross_file_finding_count == 0
        assert result.involved_files == []

    def test_default_registry_exported_from_module(self) -> None:
        """Phase 13.4 added ``default_registry`` to the scan_service
        module's ``__all__``. Ensure the symbol is importable through
        that surface, not only via ``application.__init__``."""
        from application.scan_service import default_registry
        registry = default_registry()
        # It is a factory, not a singleton — independent calls give
        # independent registries.
        assert registry is not default_registry()


# ---------------------------------------------------------------------------
# Phase 13 — cross-file fixture pair integration
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def _ensure_cross_file_fixtures_built() -> None:
    """Rebuild Phase 13 cross-file fixtures if any are missing.

    The generator is pure (no side effects besides file writes) and
    deterministic, so re-running it across test sessions is safe.
    """
    from tests.make_cross_file_fixtures import (
        CROSS_FILE_FIXTURE_EXPECTATIONS,
        FIXTURES_DIR as CF_DIR,
        build_all,
    )
    required: list[Path] = []
    for pair_dirname, spec in CROSS_FILE_FIXTURE_EXPECTATIONS.items():
        pair_dir = CF_DIR / pair_dirname
        for filename in spec["files"]:
            required.append(pair_dir / filename)
    if all(p.exists() for p in required):
        return
    build_all()


class TestCrossFileFixturePairBatchIntegration:
    """End-to-end: the Phase 13 cross-file fixture pairs drive the
    ``scan_batch`` + correlation pipeline to emit exactly one
    ``cross_format_payload_match`` per pair."""

    def test_readme_tag_plus_png_pair_emits_cross_file_finding(self) -> None:
        from tests.make_cross_file_fixtures import FIXTURES_DIR as CF_DIR

        service = ScanService()
        pair_dir = CF_DIR / "readme_tag_plus_png"
        result = service.scan_batch([
            pair_dir / "README.md",
            pair_dir / "banner.png",
        ])
        assert result.has_cross_file_correlation is True
        assert result.cross_file_finding_count == 1
        assert result.cross_file_findings[0].mechanism == (
            "cross_format_payload_match"
        )

    def test_config_tag_plus_svg_pair_emits_cross_file_finding(self) -> None:
        from tests.make_cross_file_fixtures import FIXTURES_DIR as CF_DIR

        service = ScanService()
        pair_dir = CF_DIR / "config_tag_plus_svg"
        result = service.scan_batch([
            pair_dir / "config.json",
            pair_dir / "logo.svg",
        ])
        assert result.has_cross_file_correlation is True
        assert result.cross_file_finding_count == 1

    def test_involved_files_match_input_paths(self) -> None:
        """The ``involved_files`` helper should list exactly the two
        input paths for a two-file coordination pair."""
        from tests.make_cross_file_fixtures import FIXTURES_DIR as CF_DIR

        service = ScanService()
        pair_dir = CF_DIR / "readme_tag_plus_png"
        inputs = [pair_dir / "README.md", pair_dir / "banner.png"]
        result = service.scan_batch(inputs)
        assert set(result.involved_files) == {str(p) for p in inputs}

    def test_pairs_do_not_cross_contaminate_each_other(self) -> None:
        """Running both fixture pairs through one batch scans all four
        files. Each pair must produce its own cross-file finding — two
        total — and the fingerprints must differ (distinct payloads)."""
        from tests.make_cross_file_fixtures import FIXTURES_DIR as CF_DIR

        service = ScanService()
        pair_1 = CF_DIR / "readme_tag_plus_png"
        pair_2 = CF_DIR / "config_tag_plus_svg"
        result = service.scan_batch([
            pair_1 / "README.md",
            pair_1 / "banner.png",
            pair_2 / "config.json",
            pair_2 / "logo.svg",
        ])
        assert result.cross_file_finding_count == 2
        # Each finding's fingerprint (embedded in concealed) must differ.
        fingerprints = [f.concealed for f in result.cross_file_findings]
        assert len(set(fingerprints)) == 2
