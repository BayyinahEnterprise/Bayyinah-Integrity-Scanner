"""
Phase 9 fixture-level guardrails — every text-format fixture fires
exactly its intended mechanism(s) through the full
``application.ScanService`` pipeline.

Structurally mirrors ``tests/test_fixtures.py`` (the PDF fixture
guardrail) but targets the Phase 9 fixture corpus at
``tests/fixtures/text_formats/``. The expectation table is the single
source of truth for "what does this fixture prove" and lives next to
the fixture builder in ``tests/make_text_fixtures.py``.

Two guarantees:

    * Adversarial fixtures fire exactly (and only) the expected
      mechanism(s). Extra mechanisms are a false positive; missing
      mechanisms are a false negative.
    * Clean fixtures fire zero non-``scan_error`` mechanisms.

``scan_error`` is always tolerated because a single malformed file in
the corpus should surface as an incomplete scan, not as an assertion
failure — but none of the current fixtures should trigger it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from application import ScanService
from tests.make_text_fixtures import (
    FIXTURES_DIR,
    TEXT_FIXTURE_EXPECTATIONS,
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_text_fixtures_built() -> None:
    """Regenerate fixtures if any are missing."""
    missing = [
        FIXTURES_DIR / rel
        for rel in TEXT_FIXTURE_EXPECTATIONS
        if not (FIXTURES_DIR / rel).exists()
    ]
    if not missing:
        return
    subprocess.run(
        [sys.executable, "-m", "tests.make_text_fixtures"],
        check=True,
        cwd=str(FIXTURES_DIR.parent.parent),
    )


@pytest.fixture(scope="module")
def scanner() -> ScanService:
    return ScanService()


@pytest.mark.parametrize(
    "rel,expected",
    sorted(TEXT_FIXTURE_EXPECTATIONS.items()),
)
def test_fixture_fires_exactly_expected(
    rel: str, expected: list[str], scanner: ScanService,
) -> None:
    path = FIXTURES_DIR / rel
    report = scanner.scan(path)
    # Drop scan_error from comparison — integrity failures are tested
    # independently in test_json_analyzer / test_text_file_analyzer.
    observed = sorted(
        {f.mechanism for f in report.findings if f.mechanism != "scan_error"}
    )
    assert observed == sorted(expected), (
        f"{rel}: expected {expected}, got {observed}. "
        f"Findings: "
        + "; ".join(f"{f.mechanism}@{f.location}" for f in report.findings)
    )


def test_clean_fixtures_score_1_and_complete(scanner: ScanService) -> None:
    """Every clean fixture must score exactly 1.0 and be a complete scan."""
    for rel, expected in TEXT_FIXTURE_EXPECTATIONS.items():
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
    """Adversarial fixtures must reduce score below 1.0."""
    for rel, expected in TEXT_FIXTURE_EXPECTATIONS.items():
        if not expected:
            continue
        report = scanner.scan(FIXTURES_DIR / rel)
        assert report.integrity_score < 1.0, (
            f"{rel}: adversarial fixture did not reduce score"
        )
