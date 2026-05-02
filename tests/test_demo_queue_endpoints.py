"""Endpoint tests for the v1.2.2 summary queue surface.

Tests the three demo endpoints affected by the v1.2.2 work:
  * POST /demo/summarize: response shape + summary_status branches.
  * GET /demo/summary/{job_id}: state lookup + 404 + privacy contract.
  * GET /demo/queue/state: aggregate counts + recent_transitions.

Anthropic is never actually called from the request handlers. The
worker does the calls; tests for that path live in
test_summary_worker.py.
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

CLEAN_PDF = Path("tests/fixtures/clean.pdf")
ADV_PDF = Path("tests/fixtures/positive_combined.pdf")


@pytest.fixture
def app_with_demo(monkeypatch, tmp_path):
    """Build an api.app instance with BAYYINAH_DEMO_ENABLED=1 and a
    per-test SQLite DB so tests do not collide.
    """
    monkeypatch.setenv("BAYYINAH_DEMO_ENABLED", "1")
    monkeypatch.setenv(
        "BAYYINAH_SUMMARY_QUEUE_DB",
        str(tmp_path / "summary_queue.sqlite"),
    )
    # Reload modules so the env vars take effect.
    import bayyinah.summary_queue as sq
    importlib.reload(sq)
    import bayyinah.summary_worker as sw
    importlib.reload(sw)
    import bayyinah.demo as demo_module
    importlib.reload(demo_module)
    import api as api_module
    importlib.reload(api_module)
    # Ensure schema exists. Lifespan runs only when TestClient is used
    # as a context manager; rather than rely on that, initialise the
    # schema explicitly so the test fixture works with bare TestClient.
    sq.init_db()
    return api_module.app


def test_summarize_clean_pdf_returns_queued_status(app_with_demo, monkeypatch):
    """A clean PDF enqueues; response carries summary_status=queued."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = TestClient(app_with_demo)
    contents = CLEAN_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("clean.pdf", contents, "application/pdf")},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["blocked"] is False
    assert payload["summary_status"] == "queued"
    assert payload["summary_job_id"] is not None
    assert payload["summary"] is None  # always null on synchronous path


def test_summarize_blocked_pdf_does_not_enqueue(app_with_demo, monkeypatch):
    """An adversarial PDF is blocked; no job is enqueued."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = TestClient(app_with_demo)
    contents = ADV_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("adv.pdf", contents, "application/pdf")},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["blocked"] is True
    assert payload["summary_status"] == "skipped_blocked"
    assert payload["summary_job_id"] is None


def test_summarize_missing_api_key_does_not_enqueue(app_with_demo, monkeypatch):
    """Missing API key: short-circuit, no job enqueued."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client = TestClient(app_with_demo)
    contents = CLEAN_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("clean.pdf", contents, "application/pdf")},
    )
    assert r.status_code == 200
    payload = r.json()
    assert payload["blocked"] is False
    assert payload["summary_status"] == "skipped_no_key"
    assert payload["summary_error"] == "anthropic_key_missing"
    assert payload["summary_job_id"] is None


def test_summarize_extraction_failure_does_not_enqueue(
    app_with_demo, monkeypatch,
):
    """Force pymupdf to fail; verify summary_status=skipped_extraction_failed."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    # Patch fitz.open to raise. The demo handler imports fitz lazily
    # inside the handler body, so we patch via sys.modules.
    import fitz
    orig_open = fitz.open

    def boom(*args, **kwargs):
        raise RuntimeError("simulated text extraction failure")

    monkeypatch.setattr(fitz, "open", boom)
    client = TestClient(app_with_demo)
    contents = CLEAN_PDF.read_bytes()
    try:
        r = client.post(
            "/demo/summarize",
            files={"file": ("clean.pdf", contents, "application/pdf")},
        )
    finally:
        monkeypatch.setattr(fitz, "open", orig_open)
    assert r.status_code == 200
    payload = r.json()
    assert payload["summary_status"] == "skipped_extraction_failed"
    assert payload["summary_job_id"] is None


def test_summary_endpoint_404s_on_unknown_job_id(app_with_demo):
    """GET /demo/summary/unknown returns 404."""
    client = TestClient(app_with_demo)
    r = client.get("/demo/summary/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_summary_endpoint_returns_queued_state_for_fresh_job(
    app_with_demo, monkeypatch,
):
    """A freshly-enqueued job returns status=queued."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = TestClient(app_with_demo)
    contents = CLEAN_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("clean.pdf", contents, "application/pdf")},
    )
    job_id = r.json()["summary_job_id"]
    r2 = client.get(f"/demo/summary/{job_id}")
    assert r2.status_code == 200
    state = r2.json()
    assert state["job_id"] == job_id
    # Status is either queued (worker hasn't run) or in_flight or
    # delivered (worker already ran). Acceptable as long as it's a
    # known status string.
    assert state["status"] in {"queued", "in_flight", "delivered"}


def test_summary_endpoint_does_not_return_extracted_text(
    app_with_demo, monkeypatch,
):
    """Privacy contract: extracted_text is NEVER in the response."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = TestClient(app_with_demo)
    contents = CLEAN_PDF.read_bytes()
    r = client.post(
        "/demo/summarize",
        files={"file": ("clean.pdf", contents, "application/pdf")},
    )
    job_id = r.json()["summary_job_id"]
    r2 = client.get(f"/demo/summary/{job_id}")
    state = r2.json()
    # Documented response shape; extracted_text must not appear.
    expected_keys = {
        "job_id", "status", "summary", "error",
        "attempts", "next_retry_at", "delivered_at",
    }
    assert set(state.keys()) == expected_keys
    assert "extracted_text" not in state


def test_queue_state_endpoint_reflects_pending_count(app_with_demo, monkeypatch):
    """POSTing two clean PDFs surfaces in /demo/queue/state.pending."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    client = TestClient(app_with_demo)
    contents = CLEAN_PDF.read_bytes()
    client.post(
        "/demo/summarize",
        files={"file": ("a.pdf", contents, "application/pdf")},
    )
    client.post(
        "/demo/summarize",
        files={"file": ("b.pdf", contents, "application/pdf")},
    )
    r = client.get("/demo/queue/state")
    assert r.status_code == 200
    state = r.json()
    # Either two pending (worker hasn't drained) or some delivered.
    # The combined pending + delivered_last_hour should be at least 2.
    assert (
        state["pending"] + state["in_flight"] + state["delivered_last_hour"]
        >= 2
    )
    assert isinstance(state["recent_transitions"], list)


def test_queue_state_recent_transitions_bounded_at_20(app_with_demo):
    """Truthful contract: ring is at most 20 entries."""
    client = TestClient(app_with_demo)
    r = client.get("/demo/queue/state")
    assert r.status_code == 200
    state = r.json()
    assert len(state["recent_transitions"]) <= 20
