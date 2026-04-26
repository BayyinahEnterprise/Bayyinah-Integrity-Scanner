"""
Bayyinah HTTP API — thin FastAPI wrapper over `bayyinah.scan_file`.

This module is the deployment surface. It exposes the existing public
Python API (`bayyinah.scan_file`) over HTTP so that reviewers, judges,
and integrators can hit a URL with a file and receive an
`IntegrityReport` as JSON.

Endpoints
---------
GET  /          Simple HTML upload form (drag-drop a file in the browser).
GET  /healthz   Liveness probe — returns {"status": "ok", "version": ...}.
GET  /version   Returns the installed Bayyinah version.
POST /scan      Multipart file upload. Returns IntegrityReport.to_dict().

Design notes
------------
* The wrapper does no analysis of its own. It writes the uploaded bytes
  to a temp file, calls `scan_file`, returns the dict, deletes the temp
  file. Behaviour is therefore exactly what the library guarantees.
* No auth on the demo endpoint. Rate limiting is delegated to the
  hosting provider (Railway free tier).
* Max upload size is enforced server-side at MAX_UPLOAD_BYTES to prevent
  trivially large uploads. Bayyinah itself enforces deeper scan limits
  in `domain.scan_limits`.
* Errors from `scan_file` are caught and returned as 500 with a small
  JSON body. A failed scan that returns a report with `scan_incomplete`
  is still a successful HTTP response — the caller is meant to inspect
  the `scan_incomplete` flag, not the HTTP status.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

# Make sibling packages (analyzers/, application/, domain/, infrastructure/)
# importable when this module is run directly (e.g. `uvicorn api:app`).
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

import bayyinah
from bayyinah import scan_file

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MiB hard cap for the demo endpoint

app = FastAPI(
    title="Bayyinah Integrity Scanner",
    description=(
        "Pre-LLM file integrity verification. Detects hidden, concealed, or "
        "adversarial content across 23 file kinds. Input-layer application "
        "of the Munafiq Protocol."
    ),
    version=getattr(bayyinah, "__version__", "1.1.1"),
)


# ---------------------------------------------------------------------------
# Health + meta
# ---------------------------------------------------------------------------

@app.get("/healthz")
def healthz() -> dict:
    """Liveness probe used by Railway/uptime monitors."""
    return {
        "status": "ok",
        "service": "bayyinah",
        "version": getattr(bayyinah, "__version__", "1.1.1"),
    }


@app.get("/version")
def version() -> dict:
    """Returns the installed Bayyinah version."""
    return {"version": getattr(bayyinah, "__version__", "1.1.1")}


# ---------------------------------------------------------------------------
# Scan endpoint
# ---------------------------------------------------------------------------

@app.post("/scan")
async def scan(file: UploadFile = File(...)) -> JSONResponse:
    """Scan an uploaded file. Returns IntegrityReport.to_dict() as JSON.

    The caller should inspect `integrity_score`, `findings`, and
    `scan_incomplete` to interpret the result. A 200 response with
    `scan_incomplete=true` indicates the scan ran but did not cover the
    full document; absence of findings in such a report is not evidence
    of cleanness.
    """
    if file is None or not file.filename:
        raise HTTPException(status_code=400, detail="No file uploaded.")

    # Read with a hard cap. Anything bigger than MAX_UPLOAD_BYTES is rejected.
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large for the demo endpoint. "
                f"Limit is {MAX_UPLOAD_BYTES // (1024 * 1024)} MiB."
            ),
        )
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    # Preserve the original extension — Bayyinah's FileRouter uses both
    # magic bytes and the extension to pick the analyzer set.
    suffix = Path(file.filename).suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(contents)
        tmp.close()
        try:
            report = scan_file(tmp.name)
        except Exception as exc:  # noqa: BLE001 — surfaced to caller as 500
            return JSONResponse(
                status_code=500,
                content={
                    "error": "scan_failed",
                    "detail": str(exc),
                    "trace": traceback.format_exc().splitlines()[-5:],
                },
            )
        # Substitute the original filename back into the report so the
        # caller does not see the temp path.
        payload = report.to_dict()
        payload["file_path"] = file.filename
        return JSONResponse(content=payload)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Browser-friendly upload form
# ---------------------------------------------------------------------------

_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Bayyinah Integrity Scanner</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    :root { color-scheme: light dark; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 720px;
      margin: 3rem auto;
      padding: 0 1.5rem;
      line-height: 1.5;
    }
    h1 { margin-bottom: 0.25rem; font-size: 1.6rem; }
    .tag { color: #888; font-size: 0.95rem; margin-top: 0; }
    .drop {
      border: 2px dashed #888;
      border-radius: 12px;
      padding: 2.5rem 1rem;
      text-align: center;
      margin: 1.5rem 0;
      cursor: pointer;
    }
    .drop:hover { border-color: #4a90e2; }
    .drop.dragover { border-color: #4a90e2; background: rgba(74, 144, 226, 0.05); }
    button {
      background: #1a1a1a; color: #fff; border: 0;
      padding: 0.6rem 1.2rem; border-radius: 8px;
      font-size: 1rem; cursor: pointer;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    pre {
      background: #f6f8fa; color: #111;
      padding: 1rem; border-radius: 8px;
      overflow-x: auto; font-size: 0.85rem;
      max-height: 60vh;
    }
    @media (prefers-color-scheme: dark) {
      pre { background: #1e1e1e; color: #eee; }
    }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
    .footer { color: #888; font-size: 0.85rem; margin-top: 2rem; }
    .footer a { color: inherit; }
  </style>
</head>
<body>
  <h1>Bayyinah Integrity Scanner</h1>
  <p class="tag">Pre-LLM file integrity verification &middot; v__VERSION__</p>

  <p>
    Upload a file (PDF, DOCX, XLSX, PPTX, HTML, EML, CSV, image, audio,
    video, plain text). Bayyinah will scan for hidden, concealed, or
    adversarial content and return a structured integrity report.
  </p>

  <form id="form">
    <label class="drop" id="drop">
      <input type="file" id="file" name="file" style="display:none" required>
      <div id="drop-text">Click to choose a file, or drop one here</div>
    </label>
    <button type="submit" id="submit" disabled>Scan</button>
  </form>

  <pre id="out" style="display:none"></pre>

  <p class="footer">
    API: <code>POST /scan</code> with multipart <code>file</code>. See
    <a href="https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner">repo</a>
    for the library and theory.
  </p>

  <script>
    const drop = document.getElementById('drop');
    const fileInput = document.getElementById('file');
    const dropText = document.getElementById('drop-text');
    const submit = document.getElementById('submit');
    const form = document.getElementById('form');
    const out = document.getElementById('out');

    drop.addEventListener('click', () => fileInput.click());
    drop.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('dragover'); });
    drop.addEventListener('dragleave', () => drop.classList.remove('dragover'));
    drop.addEventListener('drop', e => {
      e.preventDefault();
      drop.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        fileInput.files = e.dataTransfer.files;
        update();
      }
    });
    fileInput.addEventListener('change', update);

    function update() {
      if (fileInput.files.length) {
        dropText.textContent = fileInput.files[0].name +
          ' (' + (fileInput.files[0].size / 1024).toFixed(1) + ' KB)';
        submit.disabled = false;
      }
    }

    form.addEventListener('submit', async e => {
      e.preventDefault();
      submit.disabled = true;
      submit.textContent = 'Scanning...';
      out.style.display = 'block';
      out.textContent = 'Scanning...';
      const fd = new FormData();
      fd.append('file', fileInput.files[0]);
      try {
        const r = await fetch('/scan', { method: 'POST', body: fd });
        const j = await r.json();
        out.textContent = JSON.stringify(j, null, 2);
      } catch (err) {
        out.textContent = 'Request failed: ' + err;
      } finally {
        submit.disabled = false;
        submit.textContent = 'Scan';
      }
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serves the browser upload form."""
    html = _INDEX_HTML.replace(
        "__VERSION__", getattr(bayyinah, "__version__", "1.1.1")
    )
    return HTMLResponse(content=html)
