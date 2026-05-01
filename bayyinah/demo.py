"""Document firewall demo: scan-then-summarize pipeline.

Mounted only when BAYYINAH_DEMO_ENABLED=1. The demo is a public-facing
example of the v1.1.8 scanner sitting in front of an LLM. The scanner
runs first; if the verdict is munafiq or mughlaq, or if any Tier 1
finding fires, or any Tier 2 high-confidence finding fires, the
document is rejected before the LLM ever sees it. Clean documents are
summarized by Claude.

The demo is stateless. Files are read into memory, scanned, possibly
summarized, then the response is returned and the bytes are dropped.
No file is persisted. No request is logged with file content.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from bayyinah.api_helpers import scan_file_bytes

router = APIRouter()

_DEMO_MODEL = "claude-sonnet-4-6"
_DEMO_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB
_DEMO_MAX_TEXT_CHARS = 30_000
_DEMO_LANDING_DIR = (
    Path(__file__).resolve().parent.parent / "docs" / "landing-mock-v2"
)
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
async def demo_summarize(file: UploadFile = File(...)) -> JSONResponse:
    """Scan an uploaded PDF; if clean, summarize via Claude; else block.

    Always returns 200 with a JSON envelope describing what happened.
    The only HTTP errors raised are 413 (oversize) and 400 (empty).
    Scan failures, text extraction failures, missing API key, and
    Anthropic failures all surface as fields on the JSON envelope so
    the frontend can render the firewall metaphor accurately even when
    the LLM call fails.
    """
    contents = await file.read(_DEMO_MAX_UPLOAD_BYTES + 1)
    if len(contents) > _DEMO_MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large for demo.")
    if not contents:
        raise HTTPException(status_code=400, detail="Empty upload.")

    filename = file.filename or "upload.pdf"

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
            "llm_input_tokens": 0,
        })
    scan_ms = int((time.perf_counter() - scan_start) * 1000)

    blocked, reason = _block_decision(payload)
    response: dict[str, Any] = {
        "scan": payload,
        "scan_duration_ms": scan_ms,
        "blocked": blocked,
        "block_reason": reason,
        "summary": None,
        "summary_error": None,
        "llm_input_tokens": 0,
    }
    if blocked:
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
        return JSONResponse(content=response)

    text = text[:_DEMO_MAX_TEXT_CHARS]

    # Step 3: summarize via Claude. Missing API key is reported, not raised.
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        response["summary_error"] = "anthropic_key_missing"
        return JSONResponse(content=response)

    try:
        async with httpx.AsyncClient(timeout=_ANTHROPIC_TIMEOUT_S) as client:
            r = await client.post(
                _ANTHROPIC_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": _DEMO_MODEL,
                    "max_tokens": _ANTHROPIC_MAX_TOKENS,
                    "messages": [{
                        "role": "user",
                        "content": (
                            "Summarize this document in 2-3 sentences. "
                            "Do not speculate beyond the text:\n\n" + text
                        ),
                    }],
                },
            )
        if r.status_code >= 400:
            response["summary_error"] = f"anthropic_status_{r.status_code}"
            return JSONResponse(content=response)
        data = r.json()
        response["summary"] = data["content"][0]["text"]
        response["llm_input_tokens"] = (
            data.get("usage", {}).get("input_tokens", 0)
        )
    except httpx.TimeoutException:
        response["summary_error"] = "anthropic_timeout"
    except Exception as exc:  # noqa: BLE001
        response["summary_error"] = f"anthropic_error: {exc}"
    return JSONResponse(content=response)


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


__all__ = ["router", "_block_decision"]
