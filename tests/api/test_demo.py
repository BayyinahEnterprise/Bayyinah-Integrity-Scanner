"""Tests for the v1.1.9 demo route (bayyinah/demo.py).

All tests live behind the BAYYINAH_DEMO_ENABLED env flag so they
mirror the deployment shape: production /scan path is unaffected
when the demo is off; the demo only loads when the flag is set.

The Anthropic API call is mocked via httpx.MockTransport so the
suite runs deterministically and without network access.
"""
from __future__ import annotations

import importlib
import json
import os
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


CLEAN_PDF = Path("tests/fixtures/clean.pdf")
ADVERSARIAL_PDF = Path("tests/fixtures/positive_combined.pdf")


def _build_app_with_flag_on(monkeypatch, mock_anthropic_handler=None):
    """Reload api with BAYYINAH_DEMO_ENABLED=1.

    If ``mock_anthropic_handler`` is provided, patch the AsyncClient
    used in bayyinah.demo so any outbound httpx call routes to the
    mock instead of the real Anthropic API.
    """
    monkeypatch.setenv("BAYYINAH_DEMO_ENABLED", "1")
    import bayyinah.demo as demo_module
    importlib.reload(demo_module)
    import api as api_module
    importlib.reload(api_module)

    if mock_anthropic_handler is not None:
        # Patch httpx.AsyncClient inside the demo module so requests
        # route through MockTransport without touching the network.
        original_async_client = httpx.AsyncClient

        class _PatchedAsyncClient(original_async_client):
            def __init__(self, *args, **kwargs):
                kwargs["transport"] = httpx.MockTransport(
                    mock_anthropic_handler
                )
                super().__init__(*args, **kwargs)

        monkeypatch.setattr(demo_module.httpx, "AsyncClient", _PatchedAsyncClient)

    return api_module.app


def _mock_anthropic_ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "content": [{"type": "text", "text": "Mocked summary."}],
            "usage": {"input_tokens": 287, "output_tokens": 12},
        },
    )


# ---------------------------------------------------------------------------
# 1. /demo returns 200 and serves HTML when env flag is on.
# ---------------------------------------------------------------------------
def test_demo_route_serves_html_when_flag_on(monkeypatch):
    app = _build_app_with_flag_on(monkeypatch)
    client = TestClient(app)
    r = client.get("/demo")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    assert "Bayyinah Demo" in r.text


# ---------------------------------------------------------------------------
# 2. /demo/summarize returns 413 on oversize upload.
# ---------------------------------------------------------------------------
def test_demo_summarize_returns_413_on_oversize(monkeypatch):
    app = _build_app_with_flag_on(monkeypatch)
    client = TestClient(app)
    # 26 MiB of zeros, one byte over the demo cap.
    big_bytes = b"\x00" * (25 * 1024 * 1024 + 1)
    r = client.post(
        "/demo/summarize",
        files={"file": ("big.pdf", big_bytes, "application/pdf")},
    )
    assert r.status_code == 413


# ---------------------------------------------------------------------------
# 3. /demo/summarize returns 400 on empty upload.
# ---------------------------------------------------------------------------
def test_demo_summarize_returns_400_on_empty(monkeypatch):
    app = _build_app_with_flag_on(monkeypatch)
    client = TestClient(app)
    r = client.post(
        "/demo/summarize",
        files={"file": ("empty.pdf", b"", "application/pdf")},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 4. /demo/summarize blocks an adversarial fixture.
# ---------------------------------------------------------------------------
def test_demo_summarize_blocks_adversarial_fixture(monkeypatch):
    app = _build_app_with_flag_on(monkeypatch, _mock_anthropic_ok)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = TestClient(app)
    contents = ADVERSARIAL_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("adversarial.pdf", contents, "application/pdf")},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["blocked"] is True, f"expected blocked=True, got {payload}"
    assert payload["summary"] is None
    assert payload["llm_input_tokens"] == 0
    assert payload["block_reason"] in (
        "tier_1_finding",
        "verified_concealment",
        "high_confidence_tier_2",
    )


# ---------------------------------------------------------------------------
# 5. /demo/summarize passes a clean fixture and includes a summary.
# ---------------------------------------------------------------------------
def test_demo_summarize_passes_clean_with_summary(monkeypatch):
    app = _build_app_with_flag_on(monkeypatch, _mock_anthropic_ok)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = TestClient(app)
    contents = CLEAN_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("clean.pdf", contents, "application/pdf")},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["blocked"] is False
    assert payload["summary"] == "Mocked summary."
    assert payload["llm_input_tokens"] == 287
    assert payload["scan"]["verdict"] == "sahih"


# ---------------------------------------------------------------------------
# 6. /demo/summarize returns anthropic_key_missing when API key unset.
# ---------------------------------------------------------------------------
def test_demo_summarize_no_api_key_returns_summary_error(monkeypatch):
    app = _build_app_with_flag_on(monkeypatch)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(app)
    contents = CLEAN_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("clean.pdf", contents, "application/pdf")},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["blocked"] is False
    assert payload["summary"] is None
    assert payload["summary_error"] == "anthropic_key_missing"
    assert payload["llm_input_tokens"] == 0


# ---------------------------------------------------------------------------
# 7. _block_decision unit test covering all branches.
# ---------------------------------------------------------------------------
def test_block_decision_branches(monkeypatch):
    monkeypatch.setenv("BAYYINAH_DEMO_ENABLED", "1")
    import bayyinah.demo as demo_module
    importlib.reload(demo_module)
    bd = demo_module._block_decision

    # mughlaq blocks (verdict-level)
    assert bd({"verdict": "mughlaq", "findings": []}) == (
        True, "scan_incomplete_or_routing_dispute"
    )
    # munafiq blocks (verdict-level)
    assert bd({"verdict": "munafiq", "findings": []}) == (
        True, "verified_concealment"
    )
    # Tier 1 finding blocks regardless of verdict
    assert bd({
        "verdict": "sahih",
        "findings": [{"tier": 1, "confidence": 0.9}],
    }) == (True, "tier_1_finding")
    # Tier 2 high confidence blocks regardless of verdict
    assert bd({
        "verdict": "sahih",
        "findings": [{"tier": 2, "confidence": 0.8}],
    }) == (True, "high_confidence_tier_2")
    # Tier 2 low confidence does NOT block on its own
    assert bd({
        "verdict": "sahih",
        "findings": [{"tier": 2, "confidence": 0.5}],
    }) == (False, "clean_or_low_confidence")
    # mukhfi with no findings passes
    assert bd({"verdict": "mukhfi", "findings": []}) == (
        False, "clean_or_low_confidence"
    )
    # mushtabih with low-conf Tier 3 only passes
    assert bd({
        "verdict": "mushtabih",
        "findings": [{"tier": 3, "confidence": 0.4}],
    }) == (False, "clean_or_low_confidence")
    # sahih clean passes
    assert bd({"verdict": "sahih", "findings": []}) == (
        False, "clean_or_low_confidence"
    )


# ---------------------------------------------------------------------------
# 8. /demo route returns 404 when env flag is off.
# ---------------------------------------------------------------------------
def test_demo_route_not_mounted_when_flag_off(monkeypatch):
    monkeypatch.delenv("BAYYINAH_DEMO_ENABLED", raising=False)
    import api as api_module
    importlib.reload(api_module)
    client = TestClient(api_module.app)
    r = client.get("/demo")
    assert r.status_code == 404
    # And the production /scan endpoint is still reachable.
    r2 = client.get("/version")
    assert r2.status_code == 200
    assert r2.json().get("version")
