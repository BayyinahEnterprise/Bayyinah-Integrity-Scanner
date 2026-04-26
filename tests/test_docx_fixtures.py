"""
Phase 15 fixture-level guardrails — every DOCX fixture fires exactly its
intended mechanism(s) through the full ``application.ScanService``
pipeline.

Structurally mirrors ``tests/test_text_fixtures.py`` and
``tests/test_fixtures.py`` — the expectation table is the single source
of truth for "what does this fixture prove" and lives next to the
fixture builder in ``tests/make_docx_fixtures.py``.

Two guarantees enforced here:

    * Adversarial fixtures fire exactly (and only) the expected
      mechanism(s). Extra firings are false positives; missing firings
      are false negatives.
    * Clean fixtures score 1.0 and do not mark the scan incomplete.

``scan_error`` is always tolerated in the comparison because a
structural parse failure should surface as an incomplete scan, not as
an assertion failure — but none of the current fixtures should trigger
it, and ``test_clean_fixtures_score_1_and_complete`` catches the clean
case where ``scan_error`` would silently hide.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from application import ScanService
from tests.make_docx_fixtures import (
    DOCX_FIXTURE_EXPECTATIONS,
    FIXTURES_DIR,
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_docx_fixtures_built() -> None:
    """Regenerate fixtures if any are missing.

    Session-scoped so the regeneration happens at most once per test
    invocation. Running ``python -m tests.make_docx_fixtures`` from the
    repo root produces a byte-deterministic fixture corpus (fixed
    ZipInfo.date_time, STORED compression).
    """
    missing = [
        FIXTURES_DIR / rel
        for rel in DOCX_FIXTURE_EXPECTATIONS
        if not (FIXTURES_DIR / rel).exists()
    ]
    if not missing:
        return
    subprocess.run(
        [sys.executable, "-m", "tests.make_docx_fixtures"],
        check=True,
        cwd=str(FIXTURES_DIR.parent.parent),
    )


@pytest.fixture(scope="module")
def scanner() -> ScanService:
    return ScanService()


@pytest.mark.parametrize(
    "rel,expected",
    sorted(DOCX_FIXTURE_EXPECTATIONS.items()),
)
def test_fixture_fires_exactly_expected(
    rel: str, expected: list[str], scanner: ScanService,
) -> None:
    path = FIXTURES_DIR / rel
    report = scanner.scan(path)
    observed = sorted(
        {f.mechanism for f in report.findings if f.mechanism != "scan_error"}
    )
    assert observed == sorted(expected), (
        f"{rel}: expected {expected}, got {observed}. "
        f"Findings: "
        + "; ".join(f"{f.mechanism}@{f.location}" for f in report.findings)
    )


def test_clean_fixtures_score_1_and_complete(scanner: ScanService) -> None:
    """Every clean DOCX fixture must score exactly 1.0 and be a complete scan."""
    for rel, expected in DOCX_FIXTURE_EXPECTATIONS.items():
        if expected:
            continue
        report = scanner.scan(FIXTURES_DIR / rel)
        assert report.integrity_score == 1.0, (
            f"{rel}: clean fixture did not score 1.0 "
            f"(score={report.integrity_score}, "
            f"findings={[f.mechanism for f in report.findings]})"
        )
        assert not report.scan_incomplete, (
            f"{rel}: clean fixture marked scan_incomplete"
        )


def test_adversarial_fixtures_all_reduce_score(scanner: ScanService) -> None:
    """Adversarial fixtures must reduce the APS score below 1.0.

    The analyzer's mechanism / severity wiring can regress silently — a
    mechanism name might be removed from ``SEVERITY`` without flipping
    any unit test, and the finding would still ship (with severity 0,
    contributing nothing to the score). This guard makes the regression
    visible: an adversarial fixture whose findings cost zero is not
    doing its job.
    """
    for rel, expected in DOCX_FIXTURE_EXPECTATIONS.items():
        if not expected:
            continue
        report = scanner.scan(FIXTURES_DIR / rel)
        assert report.integrity_score < 1.0, (
            f"{rel}: adversarial fixture did not reduce score"
        )


def test_every_fixture_is_not_scan_incomplete(scanner: ScanService) -> None:
    """No fixture in the DOCX corpus should trigger a scan-incomplete clamp.

    Every fixture is a fully-parseable ZIP with a well-formed
    ``word/document.xml``. If any of them triggers ``scan_incomplete``,
    the analyzer has a bug (or the fixture itself is malformed — both
    are signals worth catching explicitly).
    """
    for rel in DOCX_FIXTURE_EXPECTATIONS:
        report = scanner.scan(FIXTURES_DIR / rel)
        assert not report.scan_incomplete, (
            f"{rel}: fixture unexpectedly marked scan_incomplete. "
            f"error={report.error!r}"
        )
