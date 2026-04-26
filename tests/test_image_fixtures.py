"""
Phase 10 fixture-level guardrails — every image-format fixture fires
exactly its intended mechanism(s) through the full
``application.ScanService`` pipeline.

Structurally mirrors ``tests/test_text_fixtures.py`` (Phase 9) and
``tests/test_fixtures.py`` (Phase 0 PDFs). The expectation table lives
in ``tests/make_image_fixtures.py`` — the single source of truth for
"what does this fixture prove".

Two guarantees:

    * Adversarial fixtures fire exactly (and only) the expected
      mechanism(s). Extra mechanisms are a false positive; missing
      mechanisms are a false negative.
    * Clean fixtures fire zero non-``scan_error`` mechanisms.

``scan_error`` is always tolerated in the comparison — malformed-input
paths are tested independently in the per-analyzer test modules.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from application import ScanService
from tests.make_image_fixtures import (
    IMAGE_FIXTURE_EXPECTATIONS,
    generate_all,
)


FIXTURES_DIR: Path = (
    Path(__file__).resolve().parent / "fixtures" / "images"
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_image_fixtures_built() -> None:
    """Regenerate fixtures if any are missing.

    The Phase 10 image fixtures are deterministic (no timestamps, no
    randomness), so regeneration is a byte-identical no-op when all
    files already exist. We only invoke the generator when something
    is missing, to keep the test-run footprint small.
    """
    missing = [
        FIXTURES_DIR / rel
        for rel in IMAGE_FIXTURE_EXPECTATIONS
        if not (FIXTURES_DIR / rel).exists()
    ]
    if not missing:
        return
    # Prefer an in-process call so we don't depend on sys.path being
    # configured a particular way; fall back to subprocess if import
    # somehow fails (matches tests/test_text_fixtures.py shape).
    try:
        generate_all(FIXTURES_DIR)
    except Exception:  # pragma: no cover — defensive fallback
        subprocess.run(
            [sys.executable, "-m", "tests.make_image_fixtures"],
            check=True,
            cwd=str(FIXTURES_DIR.parent.parent.parent),
        )


@pytest.fixture(scope="module")
def scanner() -> ScanService:
    return ScanService()


# ---------------------------------------------------------------------------
# Per-fixture exact-match guardrail
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel,expected",
    sorted(IMAGE_FIXTURE_EXPECTATIONS.items()),
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


# ---------------------------------------------------------------------------
# Corpus-level invariants
# ---------------------------------------------------------------------------


def test_clean_fixtures_score_1_and_complete(scanner: ScanService) -> None:
    """Every clean fixture must score exactly 1.0 and be a complete scan."""
    for rel, expected in IMAGE_FIXTURE_EXPECTATIONS.items():
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
    for rel, expected in IMAGE_FIXTURE_EXPECTATIONS.items():
        if not expected:
            continue
        report = scanner.scan(FIXTURES_DIR / rel)
        assert report.integrity_score < 1.0, (
            f"{rel}: adversarial fixture did not reduce score "
            f"(findings={[f.mechanism for f in report.findings]})"
        )


def test_every_expected_mechanism_is_registered() -> None:
    """Sanity: each mechanism named in the expectation table must be a
    known key in the SEVERITY/TIER config, so scoring works end-to-end."""
    from domain.config import SEVERITY, TIER

    for rel, mechs in IMAGE_FIXTURE_EXPECTATIONS.items():
        for m in mechs:
            assert m in SEVERITY, (
                f"{rel}: mechanism {m!r} missing from SEVERITY map"
            )
            assert m in TIER, (
                f"{rel}: mechanism {m!r} missing from TIER map"
            )
