"""
v2.0.0 (Round 20) recursive self-verification harness.

Applies Bayyinah's own ScanService to its own release documents and
asserts every document scans clean (no findings) with
scan_incomplete=False and verdict sahih.

Per docs/v2_gate.md §2.2 + §2.3 commercialization-ready signal:
this test must be GREEN on the CI run that cuts any commercial-tier
release tag. A finding fired by Bayyinah's analyzers on its own
deliverables blocks the release.

Two kinds of failure modes the harness catches:

1. Genuine concealment shape in a release document. A maintainer
   inadvertently introduces bidi control characters, zero-width
   spacing, white-on-white text, or other concealment shapes into
   README, CHANGELOG, or strategy documents. The finding is
   absorbed by editing the release document.

2. False-positive analyzer on prose. An analyzer fires on a
   release document for a shape that is not actually concealment
   (e.g. a legitimate URL containing characters that an over-eager
   detector classifies as bidi). The finding is absorbed by
   calibrating the analyzer per the Round 12 corrective discipline,
   not by editing the document around the false-positive.

The corpus is enumerated rather than glob-discovered, so that a
new release document does not silently bypass scanning. Adding a
release document to the project means adding its path to the
corpus list.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from application.scan_service import ScanService


# ---------------------------------------------------------------------------
# Release document corpus
# ---------------------------------------------------------------------------

# Repo root, relative to this test file
# tests/recursive_self_verification/test_self_scan.py -> repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# Top-level release documents at the repo root.
# Adding a new release document means appending its filename here.
#
# v2.0.1 (Round 21) promotion: NAMING.md promoted from
# _PENDING_CALIBRATION_DOCS to _TOP_LEVEL_DOCS after the FileRouter
# calibration corrective at infrastructure/file_router.py (Round 21
# extension-guard: skip CSV content sniff when ext_kind is
# FileKind.MARKDOWN). The promotion was forced by the
# TestPendingCalibrationDiagnostic structural defense raising
# "PROMOTE NAMING.md" when the doc started scanning clean after
# calibration. See CHANGELOG [2.0.1] for the calibration absorption.
_TOP_LEVEL_DOCS: tuple[str, ...] = (
    "README.md",
    "CHANGELOG.md",
    "KNOWN_LIMITS.md",
    "QUESTIONS.md",
    "RETIREMENT_LEDGER.md",
    "MIGRATION.md",
    "PARITY.md",
    "FRAMEWORK.md",
    "NAMING.md",
)


# Release documents with known FileRouter calibration issues, queued
# for the next calibration round. NOT silently excluded: a separate
# diagnostic test in TestPendingCalibration asserts each pending doc
# CURRENTLY produces findings, so when the FileRouter is calibrated
# (and the doc scans clean), the diagnostic test fails and reminds us
# to promote the doc to _TOP_LEVEL_DOCS.
#
# At v2.0.1: empty tuple. Round 21 closed the NAMING.md mis-routing
# (the only entry at v2.0.0). Future false-positives surfaced by the
# recursive self-verification harness get added here with a documented
# calibration target.
_PENDING_CALIBRATION_DOCS: tuple[str, ...] = ()


# docs/ canonical contract documents authored across v1.4.0-v2.0.0.
_DOCS_FILES: tuple[str, ...] = (
    "docs/score.md",
    "docs/budget.md",
    "docs/supply_chain_disposition.md",
    "docs/cross_modal.md",
    "docs/differential_testing.md",
    "docs/principles.md",
    "docs/v2_gate.md",
)


def _resolve(relative_path: str) -> Path:
    """Resolve a release-doc relative path against repo root."""
    return _REPO_ROOT / relative_path


def _existing_corpus() -> list[tuple[str, Path]]:
    """Return (relative-path, resolved-path) tuples for files that exist.

    Files that do not exist in the current working tree are skipped
    (not silently passed). This handles the case where a downstream
    consumer extracts a subset of the repo without all release docs;
    the harness then verifies only what is present.
    """
    out: list[tuple[str, Path]] = []
    for rel in _TOP_LEVEL_DOCS + _DOCS_FILES:
        abs_path = _resolve(rel)
        if abs_path.exists():
            out.append((rel, abs_path))
    return out


# ---------------------------------------------------------------------------
# Corpus enumeration sanity
# ---------------------------------------------------------------------------


class TestCorpusEnumeration:
    """The release-document corpus is non-empty and explicit."""

    def test_corpus_is_non_empty(self) -> None:
        """The recursive self-verification harness has SOMETHING to verify."""
        corpus = _existing_corpus()
        assert len(corpus) > 0, (
            "Recursive self-verification corpus is empty. Check that "
            "_TOP_LEVEL_DOCS and _DOCS_FILES list current release docs "
            "and that _REPO_ROOT resolves to the project root."
        )

    def test_corpus_includes_changelog(self) -> None:
        """CHANGELOG.md is always in the corpus per v2.0.0 gate."""
        corpus_rels = {rel for rel, _ in _existing_corpus()}
        assert "CHANGELOG.md" in corpus_rels

    def test_corpus_includes_known_limits(self) -> None:
        """KNOWN_LIMITS.md is always in the corpus per v2.0.0 gate."""
        corpus_rels = {rel for rel, _ in _existing_corpus()}
        assert "KNOWN_LIMITS.md" in corpus_rels

    def test_corpus_includes_v2_gate(self) -> None:
        """docs/v2_gate.md is always in the corpus per v2.0.0 gate."""
        corpus_rels = {rel for rel, _ in _existing_corpus()}
        assert "docs/v2_gate.md" in corpus_rels

    def test_corpus_includes_principles(self) -> None:
        """docs/principles.md is always in the corpus per v2.0.0 gate."""
        corpus_rels = {rel for rel, _ in _existing_corpus()}
        assert "docs/principles.md" in corpus_rels


# ---------------------------------------------------------------------------
# Recursive self-scan
# ---------------------------------------------------------------------------


def _corpus_ids() -> list[str]:
    """Pytest IDs for corpus parametrization."""
    return [rel for rel, _ in _existing_corpus()]


def _corpus_paths() -> list[Path]:
    """Resolved paths for corpus parametrization."""
    return [path for _, path in _existing_corpus()]


@pytest.mark.parametrize("doc_path", _corpus_paths(), ids=_corpus_ids())
class TestRecursiveSelfScan:
    """Bayyinah scans its own release documents and finds them clean.

    Per docs/v2_gate.md §2.2: any finding on a release document is a
    structural failure. The harness is the project's self-
    compensation discipline (verse 2:281).
    """

    def test_release_doc_scan_completes(self, doc_path: Path) -> None:
        """ScanService completes a scan of the release doc without error."""
        svc = ScanService()
        report = svc.scan(doc_path)
        assert report.error is None, (
            f"Release doc {doc_path.name} scan returned error: "
            f"{report.error}"
        )

    def test_release_doc_scan_is_complete(self, doc_path: Path) -> None:
        """ScanService reports the scan as complete (not scan_incomplete)."""
        svc = ScanService()
        report = svc.scan(doc_path)
        assert report.scan_incomplete is False, (
            f"Release doc {doc_path.name} scan reported "
            f"scan_incomplete=True. Per docs/v2_gate.md §2.2, "
            f"incomplete coverage of a release document is a v2.0.0 "
            f"gate violation."
        )

    def test_release_doc_has_no_findings(self, doc_path: Path) -> None:
        """ScanService finds zero concealment shapes in the release doc.

        Per docs/v2_gate.md §2.2 commercialization-ready signal: a
        finding on a release document is either a genuine
        concealment shape (Tier 1 release blocker) or an analyzer
        false-positive (Round 12 calibration corrective).
        """
        svc = ScanService()
        report = svc.scan(doc_path)
        finding_summary = [
            f"{f.mechanism}@{f.location}" for f in report.findings
        ]
        assert len(report.findings) == 0, (
            f"Release doc {doc_path.name} scan produced findings: "
            f"{finding_summary}. Per docs/v2_gate.md §2.2, this is "
            f"either a genuine concealment shape (edit the document) "
            f"or an analyzer false-positive (Round 12 calibration "
            f"corrective)."
        )

    def test_release_doc_score_is_one(self, doc_path: Path) -> None:
        """Perfect score per docs/score.md §1: clean inputs return 1.0."""
        svc = ScanService()
        report = svc.scan(doc_path)
        assert report.integrity_score == 1.0, (
            f"Release doc {doc_path.name} integrity_score is "
            f"{report.integrity_score}; expected 1.0 per "
            f"docs/score.md §1 + docs/v2_gate.md §2.2 commercialization-"
            f"ready signal."
        )


# ---------------------------------------------------------------------------
# Pending-calibration diagnostic
# ---------------------------------------------------------------------------


def _pending_corpus() -> list[tuple[str, Path]]:
    """Return (rel, abs) tuples for pending-calibration docs that exist."""
    out: list[tuple[str, Path]] = []
    for rel in _PENDING_CALIBRATION_DOCS:
        abs_path = _resolve(rel)
        if abs_path.exists():
            out.append((rel, abs_path))
    return out


@pytest.mark.parametrize(
    "doc_path",
    [path for _, path in _pending_corpus()],
    ids=[rel for rel, _ in _pending_corpus()],
)
class TestPendingCalibrationDiagnostic:
    """Diagnostic: pending-calibration docs CURRENTLY fail to scan clean.

    These tests assert the KNOWN FAILURE on each pending-calibration doc
    so that when a future calibration round fixes the FileRouter (or the
    relevant analyzer) and the doc starts scanning clean, the diagnostic
    test FAILS and reminds the maintainer to promote the doc from
    `_PENDING_CALIBRATION_DOCS` to `_TOP_LEVEL_DOCS`.

    This is the structural defense per docs/v2_gate.md §2.2: a recursive
    self-verification false-positive is NOT silently excluded; the
    pending status is itself test-enforced.
    """

    def test_pending_doc_currently_produces_findings(self, doc_path: Path) -> None:
        """The pending doc currently fires findings (calibration target).

        When this assertion FAILS (the doc scans clean), the maintainer
        moves the doc from `_PENDING_CALIBRATION_DOCS` to `_TOP_LEVEL_DOCS`
        and deletes the corresponding KNOWN_LIMITS.md entry.
        """
        svc = ScanService()
        report = svc.scan(doc_path)
        if len(report.findings) == 0 and report.integrity_score == 1.0:
            pytest.fail(
                f"PROMOTE {doc_path.name}: pending-calibration doc now "
                f"scans clean. Move from _PENDING_CALIBRATION_DOCS to "
                f"_TOP_LEVEL_DOCS and remove the KNOWN_LIMITS.md entry."
            )
