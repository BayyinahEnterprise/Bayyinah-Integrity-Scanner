"""
v1.4.0 (Round 14) compute_muwazana_score shape contract pin.

This module is a regression guard for the score function shape as
documented in docs/score.md. Any future modification to
compute_muwazana_score that breaks one of these tests is a regression
and must go through the parity-break ceremony per PARITY.md.

Per CODING_STRATEGY §6 v1.4.0 Cow Episode anchor: this file pins the
EXISTING behavior against the EXISTING fixture set. It does NOT
redesign and does NOT pre-specify every possible edge case.

Q3 closure data point #1 (per QUESTIONS.md Q3 closure log): the score
function ships at v1.4.0 with continuous-and-saturating shape pinned.
"""
from __future__ import annotations

import random

import pytest

from domain.finding import Finding
from domain.value_objects import compute_muwazana_score


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _f(mechanism: str, confidence: float = 1.0, severity_override: float | None = None) -> Finding:
    """Construct a minimal Finding for shape-pin tests.

    Uses the mechanism's SEVERITY-table value unless severity_override
    is provided. Confidence defaults to 1.0 so deductions are direct
    products of severity.
    """
    return Finding(
        mechanism=mechanism,
        tier=2,
        confidence=confidence,
        description="contract-pin test fixture",
        location="docs/score.md test",
        surface="",
        concealed="",
        severity_override=severity_override,
    )


# ---------------------------------------------------------------------------
# §1.1 Boundary conditions (docs/score.md §1.1)
# ---------------------------------------------------------------------------

class TestBoundaryConditions:
    """Pin docs/score.md §1.1 boundary-condition table."""

    def test_empty_findings_returns_one(self) -> None:
        """Empty iterable returns 1.0 (no deductions)."""
        assert compute_muwazana_score([]) == 1.0

    def test_zero_severity_zero_confidence_returns_one(self) -> None:
        """A finding with zero severity contribution leaves score at 1.0."""
        f = _f("tounicode_anomaly", confidence=0.0, severity_override=0.0)
        assert compute_muwazana_score([f]) == 1.0

    def test_full_severity_full_confidence_returns_zero(self) -> None:
        """A single finding with severity=1.0 and confidence=1.0 saturates to 0.0."""
        f = _f("tounicode_anomaly", confidence=1.0, severity_override=1.0)
        assert compute_muwazana_score([f]) == 0.0

    def test_half_severity_full_confidence_returns_half(self) -> None:
        """A single severity=0.5 confidence=1.0 finding produces score=0.5."""
        f = _f("tounicode_anomaly", confidence=1.0, severity_override=0.5)
        assert compute_muwazana_score([f]) == pytest.approx(0.5, abs=1e-9)

    def test_sum_exceeds_one_clamps_to_zero(self) -> None:
        """Sum of severity*confidence > 1.0 clamps to 0.0 (lower bound)."""
        findings = [
            _f("tounicode_anomaly", confidence=1.0, severity_override=0.6),
            _f("tounicode_anomaly", confidence=1.0, severity_override=0.6),
        ]
        # Sum = 1.2, clamped to 0.0
        assert compute_muwazana_score(findings) == 0.0

    def test_no_negative_score(self) -> None:
        """Score never goes negative regardless of severity sum."""
        findings = [
            _f("tounicode_anomaly", confidence=1.0, severity_override=1.0)
            for _ in range(10)
        ]
        # Sum = 10.0, clamped to 0.0
        assert compute_muwazana_score(findings) == 0.0
        assert compute_muwazana_score(findings) >= 0.0

    def test_no_above_one_score(self) -> None:
        """Score never exceeds 1.0 (upper clamp; theoretical, since all
        deductions are non-negative the empty-list case already gives 1.0)."""
        assert compute_muwazana_score([]) == 1.0
        assert compute_muwazana_score([]) <= 1.0


# ---------------------------------------------------------------------------
# §1.2 Monotonicity (docs/score.md §1.2)
# ---------------------------------------------------------------------------

class TestMonotonicity:
    """Pin docs/score.md §1.2 monotonicity contract."""

    def test_adding_finding_does_not_increase_score(self) -> None:
        """Adding a positive-severity-confidence finding never increases the score."""
        baseline = [
            _f("tounicode_anomaly", confidence=0.5, severity_override=0.1)
        ]
        extended = baseline + [
            _f("tounicode_anomaly", confidence=0.8, severity_override=0.2)
        ]
        assert compute_muwazana_score(extended) <= compute_muwazana_score(baseline)

    def test_monotonicity_holds_at_saturation(self) -> None:
        """When both lists already saturate to 0.0, equality holds."""
        baseline = [
            _f("tounicode_anomaly", confidence=1.0, severity_override=1.0),
            _f("tounicode_anomaly", confidence=1.0, severity_override=1.0),
        ]
        extended = baseline + [
            _f("tounicode_anomaly", confidence=1.0, severity_override=0.5)
        ]
        assert compute_muwazana_score(baseline) == 0.0
        assert compute_muwazana_score(extended) == 0.0
        assert compute_muwazana_score(extended) == compute_muwazana_score(baseline)


# ---------------------------------------------------------------------------
# §1.3 Order independence (docs/score.md §1.3)
# ---------------------------------------------------------------------------

class TestOrderIndependence:
    """Pin docs/score.md §1.3 permutation invariance."""

    def test_two_finding_permutations_match(self) -> None:
        """Two findings produce the same score in either order."""
        a = _f("tounicode_anomaly", confidence=0.7, severity_override=0.3)
        b = _f("tounicode_anomaly", confidence=0.9, severity_override=0.2)
        assert compute_muwazana_score([a, b]) == compute_muwazana_score([b, a])

    def test_five_finding_random_permutation(self) -> None:
        """A random permutation of five findings produces the same score."""
        findings = [
            _f("tounicode_anomaly", confidence=c, severity_override=s)
            for c, s in [(0.5, 0.1), (0.8, 0.15), (0.6, 0.25), (0.9, 0.05), (0.7, 0.1)]
        ]
        rng = random.Random(2026)  # deterministic seed for reproducibility
        permuted = list(findings)
        rng.shuffle(permuted)
        assert compute_muwazana_score(findings) == pytest.approx(
            compute_muwazana_score(permuted), abs=1e-9
        )


# ---------------------------------------------------------------------------
# §1.4 Rounding tolerance (docs/score.md §1.4)
# ---------------------------------------------------------------------------

class TestRoundingTolerance:
    """Pin docs/score.md §1.4 IEEE 754 floating-point behavior."""

    def test_returns_python_float(self) -> None:
        """The function returns a built-in Python float."""
        result = compute_muwazana_score([])
        assert isinstance(result, float)

    def test_idempotent_same_input_same_output(self) -> None:
        """Two calls with the same findings list produce bit-identical output."""
        f = _f("tounicode_anomaly", confidence=0.7, severity_override=0.3)
        a = compute_muwazana_score([f])
        b = compute_muwazana_score([f])
        # Bit-identical equality (not abs-tolerance)
        assert a == b


# ---------------------------------------------------------------------------
# §1.5 Patent invariant cross-reference
# ---------------------------------------------------------------------------

def test_compute_muwazana_score_is_pure() -> None:
    """The score function has no side effects: calling it does not
    mutate the findings list."""
    findings = [_f("tounicode_anomaly", confidence=0.7, severity_override=0.3)]
    findings_copy = list(findings)
    compute_muwazana_score(findings)
    assert findings == findings_copy
    assert findings is not findings_copy  # same content; different list identity
