"""Shared test configuration.

Tests that compare the current scanner with the frozen v0 / v0.1
reference implementations carry ``@pytest.mark.legacy_parity`` and run
with ``BAYYINAH_LEGACY_PARITY=1``, which switches off the passes those
versions did not have. Every other test runs with the defaults a user
gets. ``tests/test_parity_guard.py`` asserts that no test reaching a
reference module is left unmarked. See PARITY.md.
"""

from __future__ import annotations

import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "legacy_parity: compares against bayyinah_v0 / bayyinah_v0_1; runs "
        "with BAYYINAH_LEGACY_PARITY=1",
    )


@pytest.fixture(autouse=True)
def _legacy_parity_env(request, monkeypatch):
    if request.node.get_closest_marker("legacy_parity") is not None:
        monkeypatch.setenv("BAYYINAH_LEGACY_PARITY", "1")
    else:
        monkeypatch.delenv("BAYYINAH_LEGACY_PARITY", raising=False)
    yield
