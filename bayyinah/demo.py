"""Document firewall demo: scan-then-summarize pipeline.

Mounted only when BAYYINAH_DEMO_ENABLED=1. The demo is a public-facing
example of the v1.1.8 scanner sitting in front of an LLM. The scanner
runs synchronously inside the request handler; if the verdict is
munafiq or mughlaq, or any Tier 1 finding fires, or any Tier 2 high-
confidence finding fires, the document is rejected before the LLM
ever sees it.

v1.2.2: Clean documents no longer block the response on the Anthropic
call. Their extracted text is enqueued to a SQLite-backed
summarization queue (bayyinah.summary_queue) and drained by an asyncio
worker (bayyinah.summary_worker) started by the FastAPI lifespan.
Network loss does not lose jobs; process restart does not lose jobs.
The synchronous response carries summary_status and summary_job_id;
the actual summary lands asynchronously on /demo/summary/{job_id}.

The demo's privacy contract holds: extracted text is held in the
queue only until delivery or permanent failure (24h cutoff), then
cleared and the row is deleted within 60 seconds. The text is never
returned by any endpoint and never logged.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from bayyinah.api_helpers import scan_file_bytes
from bayyinah import counter as _counter
from bayyinah import summary_queue

router = APIRouter()

_DEMO_MODEL = "claude-sonnet-4-6"
_DEMO_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB
_DEMO_MAX_TEXT_CHARS = 30_000
_DEMO_LANDING_DIR = (
    Path(__file__).resolve().parent.parent / "docs" / "landing-mock-v2"
)
_DEMO_FIXTURES_DIR = (
    Path(__file__).resolve().parent.parent / "docs" / "demo" / "fixtures"
)
# Strict whitelist of fixture names servable through /demo/fixtures/<name>.
# Anything not in this set returns 404 — prevents path traversal and
# avoids accidentally serving private documents from the fixtures dir.
_DEMO_FIXTURE_WHITELIST = {
    "clean_q3_report.pdf",
    "adversarial_invisible_text.pdf",
    "encrypted_locked.pdf",
}
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_TIMEOUT_S = 30.0
_ANTHROPIC_MAX_TOKENS = 300


def _block_decision(payload: dict[str, Any]) -> tuple[bool, str]:
    """Return ``(blocked, reason)``. Implements the gate from spec D.

    The Tier 1 and Tier 2 high-confidence checks are intentionally
    stricter than the scanner's verdict logic. They defend the demo
    against verdict-derivation drift between in-process and live
    deriveVerdict; the gate fires on the underlying findings even if
    the rolled-up verdict softens. Do not collapse this into a single
    verdict check, the redundancy is load-bearing.
    """
    verdict = payload.get("verdict", "")
    if verdict == "mughlaq":
        return True, "scan_incomplete_or_routing_dispute"
    if verdict == "munafiq":
        return True, "verified_concealment"
    for f in payload.get("findings", []):
        tier = f.get("tier")
        conf = f.get("confidence", 0.0)
        if tier == 1:
            return True, "tier_1_finding"
        if tier == 2 and conf >= 0.7:
            return True, "high_confidence_tier_2"
    return False, "clean_or_low_confidence"


@router.post("/demo/summarize")
async def demo_summarize(
    request: Request,
    file: UploadFile = File(...),
) -> JSONResponse:
    """Scan an uploaded PDF synchronously; enqueue the summary; return.

    Always returns 200 with a JSON envelope describing what happened.
    The only HTTP errors raised are 413 (oversize) and 400 (empty).
    Scan failures, blocked verdicts, missing API key, and text-
    extraction failures all surface as summary_status fields on the
    JSON envelope so the frontend can render the firewall metaphor
    accurately whether or not the summary lands.

    v1.2.2: clean PDFs enqueue a summarization job and return
    immediately. The synchronous response carries
    ``summary_status: "queued"`` and a ``summary_job_id``; the actual
    summary text lands asynchronously and is fetched via
    GET /demo/summary/{job_id}.

    summary_status values:
        - "queued": clean document, summarization in progress.
        - "skipped_blocked": document was blocked by the firewall.
        - "skipped_no_key": ANTHROPIC_API_KEY is unset.
        - "skipped_extraction_failed": pymupdf could not extract text.
    """
    contents = await file.read(_DEMO_MAX_UPLOAD_BYTES + 1)
    if len(contents) > _DEMO_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large for demo.")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty upload.")

    filename = file.filename or "upload.pdf"
    client_ip = _counter.client_ip(request)

    # Step 1: scan.
    scan_start = time.perf_counter()
    try:
        payload = scan_file_bytes(contents, filename)
    except Exception as exc:  # noqa: BLE001 - surfaced via JSON envelope
        return JSONResponse(content={
            "scan": None,
            "scan_duration_ms": int(
                (time.perf_counter() - scan_start) * 1000
            ),
            "blocked": True,
            "block_reason": "scan_failed",
            "summary": None,
            "summary_error": f"scan_error: {exc}",
            "summary_status": "skipped_blocked",
            "summary_job_id": None,
            "llm_input_tokens": 0,
        })
    scan_ms = int((time.perf_counter() - scan_start) * 1000)

    # The scan completed (no exception). Both blocked and clean outcomes
    # count as a successful scan from the user's perspective. HTTP-error
    # paths above (413, 400) and the scan_failed branch already returned.
    _counter.record_scan(client_ip)

    blocked, reason = _block_decision(payload)
    response: dict[str, Any] = {
        "scan": payload,
        "scan_duration_ms": scan_ms,
        "blocked": blocked,
        "block_reason": reason,
        "summary": None,
        "summary_error": None,
        "summary_status": None,
        "summary_job_id": None,
        "llm_input_tokens": 0,
    }
    if blocked:
        response["summary_status"] = "skipped_blocked"
        return JSONResponse(content=response)

    # Step 2: extract text from the same bytes via pymupdf. Note this
    # is a second parse on top of the scanner's ContentIndex; for demo
    # traffic the cost is acceptable, and surfacing extracted text from
    # ScanService would be a public-API change with byte-parity
    # implications (out of scope for the demo PR).
    try:
        import fitz  # type: ignore[import-untyped]
        doc = fitz.open(stream=contents, filetype="pdf")
        try:
            text = "\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    except Exception as exc:  # noqa: BLE001
        response["summary_error"] = f"text_extraction_failed: {exc}"
        response["summary_status"] = "skipped_extraction_failed"
        return JSONResponse(content=response)

    text = text[:_DEMO_MAX_TEXT_CHARS]

    # Step 3: enqueue. Missing API key short-circuits without enqueue
    # so the queue does not accumulate jobs that cannot run.
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        response["summary_error"] = "anthropic_key_missing"
        response["summary_status"] = "skipped_no_key"
        return JSONResponse(content=response)

    # v1.2.2: enqueue the job and wake the worker opportunistically.
    job_id = summary_queue.enqueue(text)
    wakeup = getattr(request.app.state, "summary_wakeup", None)
    if wakeup is not None:
        wakeup.set()
    response["summary_status"] = "queued"
    response["summary_job_id"] = job_id
    return JSONResponse(content=response)


@router.get("/demo/summary/{job_id}")
def demo_summary_status(job_id: str) -> JSONResponse:
    """Return the current state of a single summarization job.

    Privacy contract: extracted_text is NEVER returned. Only the
    documented response fields are emitted, regardless of which
    private columns the queue might also store.

    Returns 404 on unknown job_id.
    """
    job = summary_queue.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job_id.")
    return JSONResponse(content={
        "job_id": job["job_id"],
        "status": job["status"],
        "summary": job.get("summary"),
        "error": job.get("error"),
        "attempts": job.get("attempts", 0),
        "next_retry_at": job.get("next_retry_at"),
        "delivered_at": job.get("delivered_at"),
    })


@router.get("/demo/queue/state")
def demo_queue_state() -> JSONResponse:
    """Return aggregate queue state for the demo's drain-log panel.

    Counts and the in-memory recent_transitions ring. The ring is
    process-local (documented in README "Remaining limitations" and
    pinned by tests/test_documented_limits.py::
    test_recent_transitions_is_in_memory_only).
    """
    return JSONResponse(content=summary_queue.aggregate_state())


@router.get("/demo/stats")
def demo_stats() -> JSONResponse:
    """Return public scan + unique-visitor counts as JSON.

    The frontend fetches this on page load and again after every
    successful scan. All counts are computed live from SQLite (no
    cache); at single-digit-thousands-per-day this is fine.
    """
    return JSONResponse(content=_counter.get_stats())


@router.get("/demo")
def demo_page() -> FileResponse:
    """Serve the static demo page from docs/landing-mock-v2/demo.html."""
    p = _DEMO_LANDING_DIR / "demo.html"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Demo page not built.")
    return FileResponse(path=str(p), media_type="text/html")


@router.get("/demo/demo.js")
def demo_js() -> FileResponse:
    """Serve the demo's vanilla-JS controller alongside demo.html."""
    p = _DEMO_LANDING_DIR / "demo.js"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="demo.js not built.")
    return FileResponse(path=str(p), media_type="application/javascript")


@router.get("/demo/fixtures/{name}")
def demo_fixture(name: str) -> FileResponse:
    """Serve a whitelisted demo fixture PDF.

    The page-level redesign exposes three one-click "exhibit"
    buttons that fetch the fixture and upload it through the same
    ``/demo/summarize`` path a manual user upload would take.
    Hardcoded whitelist; no user-supplied path components reach the
    filesystem beyond exact-match lookup.
    """
    if name not in _DEMO_FIXTURE_WHITELIST:
        raise HTTPException(status_code=404, detail="Fixture not found.")
    p = _DEMO_FIXTURES_DIR / name
    if not p.is_file():
        raise HTTPException(status_code=404, detail="Fixture not found.")
    return FileResponse(path=str(p), media_type="application/pdf")


__all__ = ["router", "_block_decision", "demo_stats"]
