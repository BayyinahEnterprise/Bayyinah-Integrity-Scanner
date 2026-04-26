"""
Tests for ``ScanLimits`` + the thread-local limits context
(``get_current_limits`` / ``set_current_limits`` / ``limits_context``).

Phase 21 contract (Al-Baqarah 2:286: "Allah does not burden a soul
beyond its capacity"). ``ScanLimits`` is the one place the scanner's
capacity ceilings are declared; analyzers read ``get_current_limits()``
to decide whether to halt a per-item loop. Limits are frozen
(immutable per instance), installed via a context manager scoped to
each ``ScanService.scan()`` call, and validated at construction
(``max_file_size_bytes`` must be positive; per-item ceilings must be
non-negative).

The tests here assert that contract; the per-analyzer integration
tests in ``tests/analyzers/test_fallback_analyzer.py`` and
``tests/application/test_scan_service.py`` assert the end-to-end
behaviour (``scan_limited`` findings on concrete oversized /
recursion-deep / row-bomb inputs).
"""

from __future__ import annotations

import threading

import pytest

from domain import (
    DEFAULT_LIMITS,
    ScanLimits,
    get_current_limits,
    limits_context,
    set_current_limits,
)


# ---------------------------------------------------------------------------
# Dataclass shape
# ---------------------------------------------------------------------------


def test_default_limits_values() -> None:
    """The shipped defaults match the documented ceilings. If these
    ever change the CHANGELOG / README must be updated — the test
    pins the numbers so that coupling is visible in code review."""
    assert DEFAULT_LIMITS.max_file_size_bytes == 256 * 1024 * 1024  # 256 MB
    assert DEFAULT_LIMITS.max_recursion_depth == 5
    assert DEFAULT_LIMITS.max_csv_rows == 200_000
    assert DEFAULT_LIMITS.max_field_length == 4 * 1024 * 1024        # 4 MiB
    assert DEFAULT_LIMITS.max_eml_attachments == 64


def test_scan_limits_is_frozen() -> None:
    """Frozen dataclass — reassigning a field raises."""
    lim = ScanLimits()
    with pytest.raises(Exception):
        lim.max_file_size_bytes = 1  # type: ignore[misc]


def test_scan_limits_equality_by_value() -> None:
    """Two instances with the same values compare equal (dataclass
    default). Used so test fixtures can assert the current limits are
    what they installed."""
    a = ScanLimits(max_csv_rows=100)
    b = ScanLimits(max_csv_rows=100)
    assert a == b
    c = ScanLimits(max_csv_rows=101)
    assert a != c


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_zero_file_size_bytes_raises() -> None:
    """A zero file-size ceiling would refuse every file. Reject at
    construction time with a message explaining the escape hatch."""
    with pytest.raises(ValueError, match="max_file_size_bytes"):
        ScanLimits(max_file_size_bytes=0)


def test_negative_file_size_bytes_raises() -> None:
    with pytest.raises(ValueError, match="max_file_size_bytes"):
        ScanLimits(max_file_size_bytes=-1)


@pytest.mark.parametrize(
    "field_name",
    [
        "max_recursion_depth",
        "max_csv_rows",
        "max_field_length",
        "max_eml_attachments",
    ],
)
def test_negative_per_item_ceilings_raise(field_name: str) -> None:
    """Per-item ceilings accept zero (the opt-out sentinel) but not
    negatives — a negative count has no sensible reading."""
    with pytest.raises(ValueError, match=field_name):
        ScanLimits(**{field_name: -1})


@pytest.mark.parametrize(
    "field_name",
    [
        "max_recursion_depth",
        "max_csv_rows",
        "max_field_length",
        "max_eml_attachments",
    ],
)
def test_zero_per_item_ceilings_allowed(field_name: str) -> None:
    """Zero means "no limit" — explicit opt-out for trusted corpora.
    Construction must succeed so a caller can write
    ``ScanLimits(max_csv_rows=0)`` when they know the input is safe."""
    ScanLimits(**{field_name: 0})  # does not raise


# ---------------------------------------------------------------------------
# Context manager + thread-local state
# ---------------------------------------------------------------------------


def test_get_current_limits_defaults_outside_context() -> None:
    """Outside ``limits_context`` and with no prior
    ``set_current_limits`` call, ``get_current_limits`` returns
    ``DEFAULT_LIMITS``."""
    # Clear any leakage from prior tests.
    import domain.config as _cfg
    state = _cfg._limits_state
    if hasattr(state, "current"):
        delattr(state, "current")
    assert get_current_limits() is DEFAULT_LIMITS


def test_limits_context_installs_and_restores() -> None:
    """Inside the context, ``get_current_limits`` returns the
    installed ceilings. On exit the prior value is restored — even on
    exception propagation."""
    tight = ScanLimits(max_csv_rows=10)

    import domain.config as _cfg
    state = _cfg._limits_state
    if hasattr(state, "current"):
        delattr(state, "current")

    assert get_current_limits() is DEFAULT_LIMITS
    with limits_context(tight):
        assert get_current_limits() is tight
    assert get_current_limits() is DEFAULT_LIMITS


def test_limits_context_nested() -> None:
    """Nested contexts stack correctly — the inner context's limits
    apply inside it, the outer's resume on exit."""
    outer = ScanLimits(max_csv_rows=100)
    inner = ScanLimits(max_csv_rows=5)

    with limits_context(outer):
        assert get_current_limits() is outer
        with limits_context(inner):
            assert get_current_limits() is inner
        assert get_current_limits() is outer


def test_limits_context_restores_after_exception() -> None:
    prior = ScanLimits(max_csv_rows=100)
    with limits_context(prior):
        with pytest.raises(RuntimeError):
            with limits_context(ScanLimits(max_csv_rows=5)):
                raise RuntimeError("boom")
        # After the inner context raises, the outer context's limits
        # must still be intact.
        assert get_current_limits() is prior


def test_set_current_limits_persists() -> None:
    """``set_current_limits`` is the long-lived setter — useful for
    test-fixture setup. Unlike ``limits_context`` it does not
    auto-restore, so every test that uses it should reset afterwards
    (done here with a finally)."""
    custom = ScanLimits(max_eml_attachments=1)
    try:
        set_current_limits(custom)
        assert get_current_limits() is custom
    finally:
        # Reset state so other tests are not affected.
        import domain.config as _cfg
        state = _cfg._limits_state
        if hasattr(state, "current"):
            delattr(state, "current")


def test_limits_are_thread_local() -> None:
    """Concurrent ``ScanService.scan`` calls with different limits
    must not clobber each other. The thread-local backing store is
    the guarantee."""
    observed: dict[str, ScanLimits] = {}

    def worker(name: str, limits: ScanLimits) -> None:
        with limits_context(limits):
            observed[name] = get_current_limits()

    t_a = ScanLimits(max_csv_rows=11)
    t_b = ScanLimits(max_csv_rows=22)
    threads = [
        threading.Thread(target=worker, args=("a", t_a)),
        threading.Thread(target=worker, args=("b", t_b)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert observed["a"] is t_a
    assert observed["b"] is t_b
