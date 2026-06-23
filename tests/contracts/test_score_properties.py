"""
v1.8.0 (Round 18) Q8 score-function property pin (Hypothesis).

Pins docs/differential_testing.md §4 properties P1-P5 over
synthetically generated Finding lists using the Hypothesis
property-based testing framework.

Per CODING_STRATEGY §6 v1.8.0: this is a NEW property-based layer
shipped at v1.8.0 alongside the differential testing architecture.
The contract tests pin the EXISTING score-function semantics; they
do not redesign. Any modification to compute_muwazana_score that
breaks a pinned property is a regression requiring the parity-break
ceremony per PARITY.md.

Verse 2:282 anchor: external witnesses for Bayyinah's own score
function. The fixture-pinning tests sample finite points; Hypothesis
generates the strategy space and asserts the invariant holds across
it.

Hypothesis is added at v1.8.0 to [project.optional-dependencies] dev.
Tests skip with an install hint when hypothesis is unavailable.
"""
from __future__ import annotations

import importlib.util

import pytest

from domain import Finding
from domain.value_objects import compute_muwazana_score


_HYPOTHESIS_INSTALLED = importlib.util.find_spec("hypothesis") is not None
_SKIP_REASON = (
    "hypothesis not installed. Install with: pip install 'hypothesis<7' "
    "(also part of [project.optional-dependencies] dev at v1.8.0)."
)


if _HYPOTHESIS_INSTALLED:
    from hypothesis import given, strategies as st, settings, HealthCheck


# ---------------------------------------------------------------------------
# Finding strategy
# ---------------------------------------------------------------------------


if _HYPOTHESIS_INSTALLED:

    def _finding_strategy() -> "st.SearchStrategy[Finding]":
        """Generate a Finding across the realistic tier/confidence/override space.

        Tier: 1 (concealment) through 3 (informational). Tier 0 is
        reserved for routing-divergence findings that require a
        disclosure-schema evidence dict; excluded from the strategy
        space because constructing valid Tier 0 findings requires
        upstream routing context not relevant to score-function
        property pinning.

        Confidence: 0.0 to 1.0 inclusive.
        severity_override: None or 0.0 to 1.0.
        """
        return st.builds(
            Finding,
            mechanism=st.text(min_size=1, max_size=12),
            tier=st.integers(min_value=1, max_value=3),
            confidence=st.floats(
                min_value=0.0,
                max_value=1.0,
                allow_nan=False,
                allow_infinity=False,
            ),
            description=st.just(""),
            location=st.just(""),
            severity_override=st.one_of(
                st.none(),
                st.floats(
                    min_value=0.0,
                    max_value=1.0,
                    allow_nan=False,
                    allow_infinity=False,
                ),
            ),
        )

    def _finding_list_strategy(
        min_size: int = 0,
        max_size: int = 20,
    ) -> "st.SearchStrategy[list[Finding]]":
        return st.lists(_finding_strategy(), min_size=min_size, max_size=max_size)


# ---------------------------------------------------------------------------
# §4.1 Range invariant
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HYPOTHESIS_INSTALLED, reason=_SKIP_REASON)
class TestRangeInvariant:
    """compute_muwazana_score result is always in [0.0, 1.0]."""

    @given(_finding_list_strategy() if _HYPOTHESIS_INSTALLED else st.none())
    @settings(
        max_examples=200,
        suppress_health_check=[HealthCheck.too_slow] if _HYPOTHESIS_INSTALLED else [],
    )
    def test_score_in_unit_interval(self, findings: list) -> None:
        score = compute_muwazana_score(findings)
        assert 0.0 <= score <= 1.0


# ---------------------------------------------------------------------------
# §4.2 Empty-list invariant
# ---------------------------------------------------------------------------


class TestEmptyListInvariant:
    """compute_muwazana_score([]) == 1.0 — no Hypothesis needed."""

    def test_empty_list_returns_one(self) -> None:
        assert compute_muwazana_score([]) == 1.0

    def test_empty_tuple_returns_one(self) -> None:
        assert compute_muwazana_score(()) == 1.0

    def test_empty_generator_returns_one(self) -> None:
        assert compute_muwazana_score(iter([])) == 1.0


# ---------------------------------------------------------------------------
# §4.3 Idempotence
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HYPOTHESIS_INSTALLED, reason=_SKIP_REASON)
class TestIdempotence:
    """compute_muwazana_score is idempotent over the same input list."""

    @given(_finding_list_strategy() if _HYPOTHESIS_INSTALLED else st.none())
    @settings(max_examples=100)
    def test_two_calls_same_result(self, findings: list) -> None:
        a = compute_muwazana_score(findings)
        b = compute_muwazana_score(findings)
        assert a == b


# ---------------------------------------------------------------------------
# §4.4 Monotonicity in finding count (saturating)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HYPOTHESIS_INSTALLED, reason=_SKIP_REASON)
class TestMonotonicityInFindingCount:
    """Adding a finding never INCREASES the score (it may decrease or stay equal).

    The "stay equal" case is when severity * confidence == 0 (either
    a zero-severity finding or a zero-confidence finding) or when the
    score has already saturated at 0.0.
    """

    @given(
        _finding_list_strategy(min_size=0, max_size=15) if _HYPOTHESIS_INSTALLED else st.none(),
        _finding_strategy() if _HYPOTHESIS_INSTALLED else st.none(),
    )
    @settings(max_examples=100)
    def test_extending_does_not_increase_score(
        self, findings: list, extra: object
    ) -> None:
        before = compute_muwazana_score(findings)
        after = compute_muwazana_score(list(findings) + [extra])
        # before >= after (within float tolerance for very small values)
        assert after <= before + 1e-12


# ---------------------------------------------------------------------------
# §4.5 Saturation at zero
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HYPOTHESIS_INSTALLED, reason=_SKIP_REASON)
class TestSaturationAtZero:
    """A score driven below zero by accumulated deductions clamps to 0.0."""

    @given(_finding_list_strategy(min_size=0, max_size=30) if _HYPOTHESIS_INSTALLED else st.none())
    @settings(max_examples=100)
    def test_score_never_negative(self, findings: list) -> None:
        score = compute_muwazana_score(findings)
        assert score >= 0.0

    def test_high_deduction_saturates_at_zero(self) -> None:
        """A list of high-severity findings drives the score to exactly 0.0."""
        # severity_override=1.0, confidence=1.0 deducts 1.0 per finding;
        # two of these drives the sum to 2.0 > 1.0 and saturates at 0.0.
        high = Finding(
            mechanism="saturator",
            tier=1,
            confidence=1.0,
            description="",
            location="",
            severity_override=1.0,
        )
        assert compute_muwazana_score([high, high]) == 0.0
        assert compute_muwazana_score([high, high, high]) == 0.0


# ---------------------------------------------------------------------------
# Order invariance (consequence of sum-based deduction)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _HYPOTHESIS_INSTALLED, reason=_SKIP_REASON)
class TestOrderInvariance:
    """Reordering findings does not change the score (up to float tolerance).

    This is a consequence of the score being a sum of per-finding
    deductions, which is commutative. Hypothesis explores the
    permutation space.
    """

    @given(_finding_list_strategy(min_size=0, max_size=10) if _HYPOTHESIS_INSTALLED else st.none())
    @settings(max_examples=100)
    def test_reversed_same_score(self, findings: list) -> None:
        forward = compute_muwazana_score(findings)
        backward = compute_muwazana_score(list(reversed(findings)))
        # Float-sum reordering can produce tiny epsilon differences;
        # pin to within 1e-9.
        assert abs(forward - backward) < 1e-9


# ---------------------------------------------------------------------------
# Hypothesis availability sanity (always runs)
# ---------------------------------------------------------------------------


def test_hypothesis_install_hint_documented() -> None:
    """The skip reason mentions the dev extra. This test pins that fact."""
    assert "pip install" in _SKIP_REASON
    assert "hypothesis" in _SKIP_REASON
