"""
Phase 20 fixture-level guardrails — every CSV / TSV / PSV fixture fires
exactly its intended mechanism(s) through the full
``application.ScanService`` pipeline.

Structurally mirrors ``tests/test_eml_fixtures.py``,
``tests/test_pptx_fixtures.py``, ``tests/test_xlsx_fixtures.py``, and
``tests/test_docx_fixtures.py``. The expectation table
``CSV_FIXTURE_EXPECTATIONS`` lives next to the fixture builder in
``tests/make_csv_fixtures.py`` and is the single source of truth for
"what does this fixture prove".

Three guarantees enforced here:

    * Adversarial fixtures fire exactly (and only) the expected
      mechanism(s). Extra firings are false positives; missing
      firings are false negatives.
    * Clean fixtures score 1.0 and do not mark the scan incomplete.
    * Adversarial fixtures reduce the APS-continuous score below 1.0
      — a mechanism whose SEVERITY entry is missing or zero would
      silently pass otherwise; this guard makes that regression
      visible.

``scan_error`` is tolerated in the mechanism comparison (so a
structural parse failure doesn't fail the expectation table
comparison) — but ``test_every_fixture_is_not_scan_incomplete``
catches the case where ``scan_error`` would silently hide.

CSV fixtures are byte-deterministic — hand-crafted bytes with fixed
row terminators (CRLF per RFC 4180), no wall-clock content, no random
bytes. They regenerate byte-identically from
``tests/make_csv_fixtures.py``. Same discipline as the EML corpus in
Phase 19 and the PPTX corpus in Phase 18.

Al-Baqarah 2:42: "Do not mix truth with falsehood, nor conceal the
truth while you know it." CSV is the format where the human reader
(opening the file in a spreadsheet app and seeing rendered cells)
most literally disagrees with the automated parser (reading raw
bytes through quoting / comment / null-byte rules nobody inspects).
The fixtures here are the witnesses for every documented divergence
shape.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

from application import ScanService
from tests.make_csv_fixtures import (
    CSV_FIXTURE_EXPECTATIONS,
    FIXTURES_DIR,
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_csv_fixtures_built() -> None:
    """Regenerate fixtures if any are missing.

    Session-scoped so the regeneration happens at most once per test
    invocation. Running ``python -m tests.make_csv_fixtures`` from the
    repo root produces a byte-deterministic fixture corpus (fixed row
    terminators, no wall-clock, no random bytes).
    """
    missing = [
        FIXTURES_DIR / rel
        for rel in CSV_FIXTURE_EXPECTATIONS
        if not (FIXTURES_DIR / rel).exists()
    ]
    if not missing:
        return
    subprocess.run(
        [sys.executable, "-m", "tests.make_csv_fixtures"],
        check=True,
        cwd=str(FIXTURES_DIR.parent.parent),
    )


@pytest.fixture(scope="module")
def scanner() -> ScanService:
    return ScanService()


@pytest.mark.parametrize(
    "rel,expected",
    sorted(CSV_FIXTURE_EXPECTATIONS.items()),
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
    """Every clean CSV fixture must score exactly 1.0 and be a complete scan."""
    for rel, expected in CSV_FIXTURE_EXPECTATIONS.items():
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

    The analyzer's mechanism / severity wiring can regress silently —
    a mechanism name might be removed from ``SEVERITY`` without
    flipping any unit test, and the finding would still ship (with
    severity 0, contributing nothing to the score). This guard makes
    the regression visible: an adversarial fixture whose findings
    cost zero is not doing its job.
    """
    for rel, expected in CSV_FIXTURE_EXPECTATIONS.items():
        if not expected:
            continue
        report = scanner.scan(FIXTURES_DIR / rel)
        assert report.integrity_score < 1.0, (
            f"{rel}: adversarial fixture did not reduce score"
        )


def test_every_fixture_is_not_scan_incomplete(scanner: ScanService) -> None:
    """No fixture in the CSV corpus should trigger a scan-incomplete clamp.

    Every CSV fixture in the corpus is a fully-parseable delimited-data
    file (after the analyzer's NUL-sanitisation and BOM-strip
    preprocessing). If any of them trips ``scan_incomplete``, the
    analyzer has a bug (or the fixture itself is malformed — both are
    signals worth catching explicitly).
    """
    for rel in CSV_FIXTURE_EXPECTATIONS:
        report = scanner.scan(FIXTURES_DIR / rel)
        assert not report.scan_incomplete, (
            f"{rel}: fixture unexpectedly marked scan_incomplete. "
            f"error={report.error!r}"
        )
