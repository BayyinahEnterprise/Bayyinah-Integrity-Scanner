"""Tests for the v1.2.1 scan-timeout subprocess isolation.

The wall-clock timeout closes Q6 from QUESTIONS.md. These tests
exercise the actual subprocess path; they do NOT mock the worker.

The cross-process patching pattern relies on Linux fork semantics:
``monkeypatch.setattr(api_helpers, "scan_file", _slow_scan)`` mutates
the parent's module state, then ``Process.start()`` forks (default on
Linux, explicit ``get_context("fork")`` in api_helpers). The child
sees the patched module dict because fork copies parent memory at
start time. Windows has no fork and is unsupported by api_helpers; the
test file inherits that constraint.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from bayyinah import api_helpers
from domain.config import VERDICT_MUGHLAQ


# Module-level slow function. Defined here (not inside a test) so the
# forked worker process inherits it cleanly when monkeypatch swaps it
# in for ``api_helpers.scan_file``.
def _slow_scan(path, *, mode="forensic"):
    time.sleep(10)
    raise RuntimeError("should never reach here in timeout tests")


def test_normal_scan_completes_within_timeout(tmp_path):
    """A trivial clean PDF must scan well under the 30s budget."""
    fixture = Path("tests/fixtures/clean.pdf")
    if not fixture.exists():
        pytest.skip("clean.pdf fixture not present")
    contents = fixture.read_bytes()
    start = time.time()
    result = api_helpers.scan_file_bytes(
        contents, "clean.pdf", timeout=30
    )
    elapsed = time.time() - start
    assert result["scan_complete"] is True
    assert result["scan_incomplete"] is False
    assert "verdict" in result
    assert elapsed < 30


def test_timeout_returns_scan_incomplete(monkeypatch, tmp_path):
    """A scan that exceeds the timeout returns scan_incomplete=True."""
    monkeypatch.setattr(api_helpers, "scan_file", _slow_scan)
    contents = b"%PDF-1.4\n%fake\n"
    start = time.time()
    result = api_helpers.scan_file_bytes(
        contents, "fake.pdf", timeout=2
    )
    elapsed = time.time() - start
    assert result["scan_incomplete"] is True
    assert result["scan_complete"] is False
    assert elapsed < 10  # should land well under 10s for a 2s budget


def test_timeout_returns_mughlaq_verdict(monkeypatch):
    monkeypatch.setattr(api_helpers, "scan_file", _slow_scan)
    result = api_helpers.scan_file_bytes(
        b"%PDF-1.4\n%fake\n", "fake.pdf", timeout=2
    )
    assert result["verdict"] == VERDICT_MUGHLAQ
    assert result["verdict"] == "mughlaq"


def test_timeout_score_is_clamped(monkeypatch):
    """Timeout payload uses SCAN_INCOMPLETE_CLAMP (0.5)."""
    monkeypatch.setattr(api_helpers, "scan_file", _slow_scan)
    result = api_helpers.scan_file_bytes(
        b"%PDF-1.4\n%fake\n", "fake.pdf", timeout=2
    )
    assert result["integrity_score"] == 0.5


def test_timeout_findings_is_empty_list(monkeypatch):
    monkeypatch.setattr(api_helpers, "scan_file", _slow_scan)
    result = api_helpers.scan_file_bytes(
        b"%PDF-1.4\n%fake\n", "fake.pdf", timeout=2
    )
    assert result["findings"] == []


def test_worker_exception_propagates(monkeypatch):
    """A non-timeout exception inside the worker becomes a RuntimeError
    in the parent (the existing failure shape; api.py catches Exception
    and renders 500).
    """
    def bad_scan(path, *, mode="forensic"):
        raise ValueError("intentional test failure")

    monkeypatch.setattr(api_helpers, "scan_file", bad_scan)
    with pytest.raises(RuntimeError) as exc_info:
        api_helpers.scan_file_bytes(
            b"%PDF-1.4\n%fake\n", "fake.pdf", timeout=5
        )
    # The original exception class name appears in the message
    assert "ValueError" in str(exc_info.value)
    assert "intentional test failure" in str(exc_info.value)
