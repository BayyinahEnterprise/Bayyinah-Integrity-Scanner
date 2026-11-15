"""Every test that reaches a frozen reference module is marked.

The invariant, not a naming convention: a test added tomorrow that calls
``bayyinah_v0_1`` without the marker fails here, whatever it is called.
"""

from __future__ import annotations

from tests.parity_guard import TESTS_DIR, all_reference_tests


def test_every_reference_test_is_marked() -> None:
    unmarked = [
        f"{path.relative_to(TESTS_DIR)}::{name} (line {line})"
        for path, name, line, marked in all_reference_tests() if not marked
    ]
    assert not unmarked, (
        "These tests reach bayyinah_v0 / bayyinah_v0_1 without "
        "@pytest.mark.legacy_parity:\n  " + "\n  ".join(unmarked)
    )


def test_guard_sees_reference_tests() -> None:
    """The guard would pass trivially if it found nothing."""
    assert len(all_reference_tests()) >= 20
