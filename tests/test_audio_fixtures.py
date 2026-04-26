"""
Phase 24 fixture-level guardrails — every audio-format fixture fires
exactly its intended mechanism(s) through the full
``application.ScanService`` pipeline.

Structurally mirrors ``tests/test_video_fixtures.py`` (Phase 23 video),
``tests/test_image_fixtures.py`` (Phase 10), and ``tests/test_text_fixtures.py``
(Phase 9). The expectation table lives in ``tests/make_audio_fixtures.py``
— the single source of truth for "what does this fixture prove".

Two guarantees:

    * Adversarial fixtures fire exactly (and only) the expected
      mechanism(s). Extra mechanisms are a false positive; missing
      mechanisms are a false negative.
    * Clean fixtures fire zero non-``scan_error`` mechanisms *except*
      the always-on ``audio_stem_inventory`` (non-deducting,
      informational meta-output).

``scan_error`` is always tolerated in the comparison — malformed-input
paths are tested independently in the per-analyzer test modules.

Clean fixtures must score exactly 1.0 (inventory is non-deducting).
Adversarial fixtures must score strictly below 1.0 (every adversarial
fixture except the cross-stem-divergence NULL case carries a deducting
mechanism by design — and cross_stem_divergence.mp3 is listed without
any adversarial mechanism in the expectation table, so it passes the
"score == 1.0" path).

Clean fixtures must have ``scan_incomplete = False`` — the analyzer
did complete the scan.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from application import ScanService
from tests.make_audio_fixtures import (
    AUDIO_FIXTURE_EXPECTATIONS,
    generate_all,
)


FIXTURES_DIR: Path = (
    Path(__file__).resolve().parent / "fixtures" / "audio"
)


@pytest.fixture(scope="session", autouse=True)
def _ensure_audio_fixtures_built() -> None:
    """Regenerate fixtures if any are missing.

    Audio fixtures are deterministic (seeded RNG, fixed bytes) so
    regeneration is idempotent.
    """
    missing = [
        FIXTURES_DIR / rel
        for rel in AUDIO_FIXTURE_EXPECTATIONS
        if not (FIXTURES_DIR / rel).exists()
    ]
    if not missing:
        return
    try:
        generate_all(FIXTURES_DIR)
    except Exception:  # pragma: no cover — defensive fallback
        subprocess.run(
            [sys.executable, "-m", "tests.make_audio_fixtures"],
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
    "rel_path,expected_mechs",
    sorted(AUDIO_FIXTURE_EXPECTATIONS.items()),
)
def test_fixture_fires_expected_mechanisms(
    rel_path: str,
    expected_mechs: set[str],
    scanner: ScanService,
) -> None:
    """Exact match on emitted mechanisms via the full pipeline."""
    path = FIXTURES_DIR / rel_path
    report = scanner.scan(path)

    observed = {f.mechanism for f in report.findings} - {"scan_error"}

    assert observed == expected_mechs, (
        f"{rel_path}: expected {expected_mechs}, got {observed}. "
        f"Full findings: {[f.mechanism for f in report.findings]}"
    )


# ---------------------------------------------------------------------------
# Clean-fixture invariants
# ---------------------------------------------------------------------------


def _clean_fixture_paths() -> list[str]:
    return sorted(
        rel for rel, mechs in AUDIO_FIXTURE_EXPECTATIONS.items()
        if mechs == {"audio_stem_inventory"}
    )


@pytest.mark.parametrize("rel_path", _clean_fixture_paths())
def test_clean_fixture_scores_one(rel_path: str, scanner: ScanService) -> None:
    report = scanner.scan(FIXTURES_DIR / rel_path)
    assert report.integrity_score == 1.0, (
        f"{rel_path}: expected 1.0, got {report.integrity_score}"
    )


@pytest.mark.parametrize("rel_path", _clean_fixture_paths())
def test_clean_fixture_scan_incomplete_is_false(
    rel_path: str, scanner: ScanService,
) -> None:
    report = scanner.scan(FIXTURES_DIR / rel_path)
    assert report.scan_incomplete is False


@pytest.mark.parametrize("rel_path", _clean_fixture_paths())
def test_clean_fixture_has_no_error(rel_path: str, scanner: ScanService) -> None:
    report = scanner.scan(FIXTURES_DIR / rel_path)
    assert not report.error, f"{rel_path}: unexpected error {report.error!r}"


# ---------------------------------------------------------------------------
# Adversarial-fixture invariants
# ---------------------------------------------------------------------------


def _adversarial_fixture_paths() -> list[str]:
    return sorted(
        rel for rel, mechs in AUDIO_FIXTURE_EXPECTATIONS.items()
        if mechs != {"audio_stem_inventory"}
    )


@pytest.mark.parametrize("rel_path", _adversarial_fixture_paths())
def test_adversarial_fixture_scores_below_one(
    rel_path: str, scanner: ScanService,
) -> None:
    """Every adversarial fixture must deduct."""
    report = scanner.scan(FIXTURES_DIR / rel_path)
    assert report.integrity_score < 1.0, (
        f"{rel_path}: expected score < 1.0, got {report.integrity_score}. "
        f"Mechanisms: {[f.mechanism for f in report.findings]}"
    )
