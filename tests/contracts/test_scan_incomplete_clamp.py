"""
v1.4.0 (Round 14) apply_scan_incomplete_clamp contract pin.

Regression guard for the clamp truth table documented in
docs/score.md §2. Any future modification to apply_scan_incomplete_clamp
or to the SCAN_INCOMPLETE_CLAMP constant that breaks one of these tests
is a regression and must go through the parity-break ceremony per
PARITY.md.

Per CODING_STRATEGY §6 v1.4.0: pins EXISTING behavior at SCAN_INCOMPLETE_CLAMP
= 0.5; does NOT redesign.

Q4 closure data point #1 (per QUESTIONS.md Q4 closure log): the clamp
semantics ship at v1.4.0 with `0.5` overloaded on the score channel
plus disambiguation via the `scan_incomplete: bool` companion field.
"""
from __future__ import annotations

import pytest

from domain.config import SCAN_INCOMPLETE_CLAMP
from domain.value_objects import apply_scan_incomplete_clamp


# ---------------------------------------------------------------------------
# §2.1 Truth table (docs/score.md §2.1)
# ---------------------------------------------------------------------------

class TestTruthTable:
    """Pin docs/score.md §2.1 clamp truth-table."""

    def test_scan_complete_pass_through_zero(self) -> None:
        """scan_incomplete=False: input score unchanged at 0.0."""
        assert apply_scan_incomplete_clamp(0.0, scan_incomplete=False) == 0.0

    def test_scan_complete_pass_through_half(self) -> None:
        """scan_incomplete=False: input score unchanged at 0.5."""
        assert apply_scan_incomplete_clamp(0.5, scan_incomplete=False) == 0.5

    def test_scan_complete_pass_through_one(self) -> None:
        """scan_incomplete=False: input score unchanged at 1.0."""
        assert apply_scan_incomplete_clamp(1.0, scan_incomplete=False) == 1.0

    def test_scan_complete_pass_through_arbitrary(self) -> None:
        """scan_incomplete=False: input score unchanged at intermediate values."""
        for score in (0.1, 0.25, 0.499, 0.501, 0.75, 0.99):
            assert apply_scan_incomplete_clamp(score, scan_incomplete=False) == score

    def test_scan_incomplete_below_clamp_pass_through(self) -> None:
        """scan_incomplete=True + score <= 0.5: input unchanged."""
        for score in (0.0, 0.1, 0.25, 0.499):
            assert apply_scan_incomplete_clamp(score, scan_incomplete=True) == score

    def test_scan_incomplete_at_clamp_preserves(self) -> None:
        """scan_incomplete=True + score == 0.5: preserved at 0.5."""
        assert apply_scan_incomplete_clamp(0.5, scan_incomplete=True) == 0.5

    def test_scan_incomplete_above_clamp_clamps_to_half(self) -> None:
        """scan_incomplete=True + score > 0.5: clamped to 0.5."""
        for score in (0.501, 0.6, 0.75, 0.9, 0.99):
            assert apply_scan_incomplete_clamp(score, scan_incomplete=True) == 0.5

    def test_scan_incomplete_one_clamps_to_half(self) -> None:
        """scan_incomplete=True + score == 1.0: clamped to 0.5."""
        assert apply_scan_incomplete_clamp(1.0, scan_incomplete=True) == 0.5


# ---------------------------------------------------------------------------
# §2.2 Purity / idempotence (docs/score.md §2.2)
# ---------------------------------------------------------------------------

class TestPurity:
    """Pin docs/score.md §2.2 purity contract."""

    def test_idempotent_clean(self) -> None:
        """Two calls with the same args produce bit-identical output."""
        a = apply_scan_incomplete_clamp(0.7, scan_incomplete=False)
        b = apply_scan_incomplete_clamp(0.7, scan_incomplete=False)
        assert a == b

    def test_idempotent_incomplete(self) -> None:
        """Two calls with scan_incomplete=True produce bit-identical output."""
        a = apply_scan_incomplete_clamp(0.7, scan_incomplete=True)
        b = apply_scan_incomplete_clamp(0.7, scan_incomplete=True)
        assert a == b
        assert a == 0.5

    def test_apply_twice_to_incomplete_score_idempotent(self) -> None:
        """Applying the clamp twice to an already-clamped score is a no-op."""
        once = apply_scan_incomplete_clamp(1.0, scan_incomplete=True)
        twice = apply_scan_incomplete_clamp(once, scan_incomplete=True)
        assert once == twice == 0.5


# ---------------------------------------------------------------------------
# Constant pinning
# ---------------------------------------------------------------------------

def test_scan_incomplete_clamp_value_is_half() -> None:
    """The SCAN_INCOMPLETE_CLAMP constant is 0.5 at v1.4.0.

    Modifications to this value require the parity-break ceremony
    per PARITY.md, with downstream-consumer migration notes.
    """
    assert SCAN_INCOMPLETE_CLAMP == 0.5


def test_scan_incomplete_clamp_is_float() -> None:
    """The clamp constant is a Python float (not int, not Decimal)."""
    assert isinstance(SCAN_INCOMPLETE_CLAMP, float)


# ---------------------------------------------------------------------------
# Q4 closure cross-reference
# ---------------------------------------------------------------------------

def test_clamp_returns_python_float() -> None:
    """apply_scan_incomplete_clamp returns Python float (not numpy, not Decimal)."""
    result = apply_scan_incomplete_clamp(0.7, scan_incomplete=True)
    assert isinstance(result, float)


def test_clamp_keyword_only_scan_incomplete() -> None:
    """scan_incomplete is keyword-only per signature; pin that interface."""
    # Positional-style invocation should not be permitted; verify by
    # exercising both styles.
    # Keyword: ok
    assert apply_scan_incomplete_clamp(0.7, scan_incomplete=True) == 0.5
    # Positional: TypeError expected because scan_incomplete is kw-only
    with pytest.raises(TypeError):
        apply_scan_incomplete_clamp(0.7, True)  # type: ignore[misc]
