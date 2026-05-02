"""Tests for the persistent scan counter (bayyinah/counter.py and the
/demo/stats endpoint in bayyinah/demo.py).

These tests monkeypatch BAYYINAH_COUNTER_DB to a tmp path and pin
BAYYINAH_COUNTER_SECRET so every test run is deterministic. The
``_utc_now`` function in bayyinah.counter is also monkeypatched in the
hash-determinism test so we can simulate same-day vs different-day
behaviour without waiting overnight.
"""
from __future__ import annotations

import datetime as _dt
import importlib
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_counter_env(monkeypatch, tmp_path: Path) -> Path:
    """Point the counter at a tmp DB and pin the salt secret."""
    db_path = tmp_path / "counter_test.db"
    monkeypatch.setenv("BAYYINAH_COUNTER_DB", str(db_path))
    monkeypatch.setenv("BAYYINAH_COUNTER_SECRET", "test-secret-fixed-value")
    monkeypatch.setenv("BAYYINAH_DEMO_ENABLED", "1")
    return db_path


def _build_app(monkeypatch, tmp_path: Path):
    """Reload the counter, demo, and api modules with env vars set."""
    _setup_counter_env(monkeypatch, tmp_path)
    import bayyinah.counter as counter_module
    importlib.reload(counter_module)
    import bayyinah.demo as demo_module
    importlib.reload(demo_module)
    import api as api_module
    importlib.reload(api_module)
    return api_module.app, demo_module, counter_module


def _stub_scan(demo_module, monkeypatch, payload=None):
    """Replace scan_file_bytes inside demo_module with a fast stub.

    The real scanner is heavy and irrelevant for counter tests. The stub
    returns a clean envelope so the handler proceeds past the scan-error
    branch and increments the counter.
    """
    if payload is None:
        payload = {"verdict": "sahih", "findings": []}

    def _fake_scan(_contents, _filename, mode="forensic"):
        return payload

    monkeypatch.setattr(demo_module, "scan_file_bytes", _fake_scan)


# ---------------------------------------------------------------------------
# 1. /demo/stats with an empty DB returns zeros.
# ---------------------------------------------------------------------------
def test_stats_empty_db_returns_zeros(monkeypatch, tmp_path):
    app, _demo, _counter = _build_app(monkeypatch, tmp_path)
    client = TestClient(app)
    r = client.get("/demo/stats")
    assert r.status_code == 200
    body = r.json()
    assert body["scans"] == 0
    assert body["unique_visitors_total"] == 0
    assert body["unique_visitors_today"] == 0
    assert body["since"] is None
    assert "as_of" in body and isinstance(body["as_of"], str)


# ---------------------------------------------------------------------------
# 2. Two scans from the same IP -> scans=2, unique_visitors=1.
# ---------------------------------------------------------------------------
def test_two_scans_same_ip_counts_one_unique(monkeypatch, tmp_path):
    app, demo_module, _counter = _build_app(monkeypatch, tmp_path)
    _stub_scan(demo_module, monkeypatch)
    client = TestClient(app)

    headers = {"X-Forwarded-For": "203.0.113.7"}
    for _ in range(2):
        r = client.post(
            "/demo/summarize",
            files={"file": ("a.pdf", b"%PDF-stub", "application/pdf")},
            headers=headers,
        )
        assert r.status_code == 200

    stats = client.get("/demo/stats").json()
    assert stats["scans"] == 2
    assert stats["unique_visitors_total"] == 1
    assert stats["unique_visitors_today"] == 1
    assert stats["since"] is not None


# ---------------------------------------------------------------------------
# 3. Two scans from different X-Forwarded-For values -> 2 unique visitors.
# ---------------------------------------------------------------------------
def test_two_scans_different_ips_count_two_unique(monkeypatch, tmp_path):
    app, demo_module, _counter = _build_app(monkeypatch, tmp_path)
    _stub_scan(demo_module, monkeypatch)
    client = TestClient(app)

    for ip in ("198.51.100.1", "198.51.100.2"):
        r = client.post(
            "/demo/summarize",
            files={"file": ("a.pdf", b"%PDF-stub", "application/pdf")},
            headers={"X-Forwarded-For": ip},
        )
        assert r.status_code == 200

    stats = client.get("/demo/stats").json()
    assert stats["scans"] == 2
    assert stats["unique_visitors_total"] == 2
    assert stats["unique_visitors_today"] == 2


# ---------------------------------------------------------------------------
# 4. Hash determinism: same IP + same day = same hash; different day = different.
# ---------------------------------------------------------------------------
def test_hash_determinism_same_day_same_hash(monkeypatch, tmp_path):
    _setup_counter_env(monkeypatch, tmp_path)
    import bayyinah.counter as counter_module
    importlib.reload(counter_module)

    ip = "203.0.113.42"

    # Two calls on the same UTC day yield the same hash.
    h1 = counter_module.hash_ip(ip, "2026-05-02")
    h2 = counter_module.hash_ip(ip, "2026-05-02")
    assert h1 == h2

    # Different UTC day yields a different hash for the same IP.
    h3 = counter_module.hash_ip(ip, "2026-05-03")
    assert h3 != h1

    # Different IP on the same day yields a different hash.
    h4 = counter_module.hash_ip("198.51.100.99", "2026-05-02")
    assert h4 != h1


# ---------------------------------------------------------------------------
# 5. Counter survives a scanner exception path: blocked-by-tier-1 still counts.
# ---------------------------------------------------------------------------
def test_blocked_scan_still_counted(monkeypatch, tmp_path):
    app, demo_module, _counter = _build_app(monkeypatch, tmp_path)
    _stub_scan(
        demo_module,
        monkeypatch,
        payload={
            "verdict": "munafiq",
            "findings": [{"tier": 1, "confidence": 0.95}],
        },
    )
    client = TestClient(app)

    r = client.post(
        "/demo/summarize",
        files={"file": ("a.pdf", b"%PDF-stub", "application/pdf")},
        headers={"X-Forwarded-For": "203.0.113.5"},
    )
    assert r.status_code == 200
    assert r.json()["blocked"] is True

    stats = client.get("/demo/stats").json()
    assert stats["scans"] == 1
    assert stats["unique_visitors_total"] == 1


# ---------------------------------------------------------------------------
# 6. Empty upload (400) does NOT increment the counter.
# ---------------------------------------------------------------------------
def test_empty_upload_does_not_increment(monkeypatch, tmp_path):
    app, demo_module, _counter = _build_app(monkeypatch, tmp_path)
    _stub_scan(demo_module, monkeypatch)
    client = TestClient(app)

    r = client.post(
        "/demo/summarize",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 400

    stats = client.get("/demo/stats").json()
    assert stats["scans"] == 0
    assert stats["unique_visitors_total"] == 0


# ---------------------------------------------------------------------------
# 7. Scanner exception path returns blocked but does NOT increment counter.
#    (We want the counter to reflect successful scans only; a scan that
#    raised before producing a verdict is not a meaningful data point.)
# ---------------------------------------------------------------------------
def test_scan_exception_does_not_increment(monkeypatch, tmp_path):
    app, demo_module, _counter = _build_app(monkeypatch, tmp_path)

    def _boom(_contents, _filename, mode="forensic"):
        raise RuntimeError("scanner crashed")

    monkeypatch.setattr(demo_module, "scan_file_bytes", _boom)
    client = TestClient(app)

    r = client.post(
        "/demo/summarize",
        files={"file": ("a.pdf", b"%PDF-stub", "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["blocked"] is True
    assert body["block_reason"] == "scan_failed"

    stats = client.get("/demo/stats").json()
    assert stats["scans"] == 0
