"""Shared test configuration.

Byte-parity tests compare the current scanner with the frozen v0 and
v0.1 reference implementations. Two passes added in v2.1 did not exist
in those versions: the stream-level PDF concealment pass and the
``concealed_instruction`` assessment. A parity comparison is only
meaningful over the detector set the reference had, so every test whose
name says it is a parity test runs with ``BAYYINAH_LEGACY_PARITY=1``,
which switches those two passes off. All other tests run with the
defaults a user gets. See PARITY.md.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _legacy_parity_for_parity_tests(request, monkeypatch):
    if "parity" in request.node.nodeid.lower():
        monkeypatch.setenv("BAYYINAH_LEGACY_PARITY", "1")
    yield
