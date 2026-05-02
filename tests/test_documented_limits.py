"""Pinning tests for documented limitations.

Each test in this file asserts the current behavior of a
deliberately-deferred design choice, paired with the four-place
documentation pattern artifacts (CHANGELOG, README, fixture markdown,
this test) per the framework's §6 documentation pattern.

A pinning test exists not to prove the behavior is correct but to
ensure that any change in either direction (bug fix or regression) is
intentional. Promoting a limitation to a fix retires the fixture
markdown and this test together, per the retirement procedure in
PARITY.md.
"""
from __future__ import annotations

import collections


def test_recent_transitions_is_in_memory_only():
    """Pin v1.2.2's choice that recent_transitions is process-local.

    See tests/fixtures/documented_limits/
    recent_transitions_single_worker.md for the rationale and the
    documented-limit retirement procedure.
    """
    from bayyinah.summary_queue import (
        recent_transitions,
        RECENT_TRANSITIONS_MAX,
    )

    # Storage shape: in-memory deque, NOT a SQLite-backed structure.
    assert isinstance(recent_transitions, collections.deque), (
        "recent_transitions must remain a collections.deque. "
        "If the storage shape changed (e.g., promoted to SQLite), "
        "follow the retirement procedure in PARITY.md and remove "
        "this pinning test together with the fixture markdown."
    )
    # Bound at exactly 20 entries.
    assert recent_transitions.maxlen == RECENT_TRANSITIONS_MAX
    assert RECENT_TRANSITIONS_MAX == 20
