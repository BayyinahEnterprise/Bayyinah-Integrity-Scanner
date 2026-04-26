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
  <title>Bayyinah — Pre-LLM File Integrity Verification</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="Bayyinah scans a file's surface and substrate, reports the gap. Pre-LLM file integrity verification across 23 file kinds.">
  <style>
    :root { color-scheme: light dark; --accent: #4a90e2; --muted: #888; }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      max-width: 720px;
      margin: 3rem auto;
      padding: 0 1.5rem 4rem;
      line-height: 1.6;
    }
    h1 { margin: 0 0 0.25rem; font-size: 2rem; letter-spacing: -0.01em; }
    h2 { margin: 2.5rem 0 0.5rem; font-size: 1.2rem; }
    .tag { color: var(--muted); font-size: 0.95rem; margin: 0 0 2rem; }
    .lede { font-size: 1.1rem; }
    .scan-card {
      border: 1px solid rgba(128,128,128,0.3);
      border-radius: 14px;
      padding: 1.5rem;
      margin: 2rem 0;
      background: rgba(128,128,128,0.04);
    }
    .scan-card h2 { margin-top: 0; }
    .drop {
      display: block;
      border: 2px dashed var(--muted);
      border-radius: 12px;
      padding: 2rem 1rem;
      text-align: center;
      margin: 0.75rem 0 1rem;
      cursor: pointer;
      transition: border-color 0.15s, background 0.15s;
    }
    .drop:hover, .drop.dragover {
      border-color: var(--accent);
      background: rgba(74, 144, 226, 0.05);
    }
    button {
      background: #1a1a1a; color: #fff; border: 0;
      padding: 0.65rem 1.3rem; border-radius: 8px;
      font-size: 1rem; cursor: pointer; font-weight: 500;
    }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    pre {
      background: #f6f8fa; color: #111;
      padding: 1rem; border-radius: 8px;
      overflow-x: auto; font-size: 0.85rem;
      max-height: 60vh;
    }
    code {
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.9em;
      background: rgba(128,128,128,0.12);
      padding: 0.1em 0.35em;
      border-radius: 4px;
    }
    pre code { background: transparent; padding: 0; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
    .meta-grid {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 0.4rem 1rem;
      font-size: 0.95rem;
      margin: 1rem 0;
    }
    .meta-grid dt { color: var(--muted); }
    .meta-grid dd { margin: 0; }
    .footer {
      margin-top: 3rem; padding-top: 1.5rem;
      border-top: 1px solid rgba(128,128,128,0.2);
      color: var(--muted); font-size: 0.85rem;
    }
    .footer a { color: var(--muted); text-decoration: underline; }
    @media (prefers-color-scheme: dark) {
      pre { background: #1e1e1e; color: #eee; }
    }
  </style>
</head>
<body>
  <h1>Bayyinah</h1>
  <p class="tag">Pre-LLM file integrity verification · v__VERSION__</p>

  <p class="lede">
    Every file has a <strong>surface</strong> and a <strong>substrate</strong>.
    The surface is what your reader, viewer, or inbox displays. The
    substrate is the actual bytes underneath — metadata, hidden text,
    embedded scripts, alternate streams. Most of the time the two agree.
    When they don't, it's usually deliberate.
  </p>

  <p>
    A contract that displays one figure and contains another. A PDF that
    opens cleanly while carrying instructions a language model would
    silently obey. An email whose visible sender and routing headers
    don't match. A spreadsheet whose hidden sheet does the actual math.
  </p>

  <p>
    Bayyinah pulls every layer of a file apart and reports whether the
    surface matches the substrate. It is a single-purpose scanner. It
    makes no moral judgement of its own — it surfaces the gap and lets
    the reader perform the recognition.
  </p>

  <div class="scan-card">
    <h2>Try it now</h2>
    <p style="margin-top:0">
      Drop in any file. Bayyinah returns a structured integrity report
      in a couple of seconds.
    </p>
    <form id="form">
      <label class="drop" id="drop">
        <input type="file" id="file" name="file" style="display:none" required>
        <div id="drop-text">Click to choose a file, or drop one here</div>
      </label>
      <button type="submit" id="submit" disabled>Scan</button>
    </form>
    <pre id="out" style="display:none"></pre>
    <p style="font-size:0.85rem; color:var(--muted); margin: 0.5rem 0 0;">
      Try a document you already trust to see a score of 1.0 with no
      findings. Then try one from a less-trusted source.
    </p>
  </div>

  <h2>Why it matters now</h2>
  <p>
    Modern AI systems ingest files all day. Every document Q&amp;A tool,
    every email summarizer, every customer-support agent reads files
    written by humans and by other models. When a file hides something,
    the model consumes the hidden content along with the visible content.
    Most AI-safety work focuses on what the model says back. Bayyinah
    addresses the input layer: vet the file <em>before</em> any model
    touches it.
  </p>

  <h2>What it covers</h2>
  <p>
    23 file kinds: PDF, DOCX, XLSX, PPTX, HTML, EML, CSV, JSON, plain
    text and source code, Markdown, RTF, SVG, PNG, JPEG, GIF, WebP,
    TIFF, MP3, WAV, FLAC, OGG, MP4, plus a fallback witness for unknown
    formats so nothing slips through silent-clean.
  </p>

  <h2>API</h2>
  <p>The same scanner is exposed over HTTP for integration:</p>
  <pre><code>curl -X POST -F "file=@suspicious.pdf" https://bayyinah.dev/scan</code></pre>
  <p>
    Returns the full <code>IntegrityReport</code> as JSON — mechanism,
    tier, confidence, severity, location, and inversion-recovery for
    every finding. See <a href="https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner#hosted-api">the repo</a>
    for the full endpoint list.
  </p>

  <h2>Status</h2>
  <dl class="meta-grid">
    <dt>Version</dt><dd>1.1.1 (production-stable)</dd>
    <dt>License</dt><dd>Apache 2.0</dd>
    <dt>Source</dt><dd><a href="https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner">github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner</a></dd>
    <dt>DOI</dt><dd><a href="https://doi.org/10.5281/zenodo.19677111">10.5281/zenodo.19677111</a></dd>
    <dt>Demo limit</dt><dd>25 MiB per upload, no auth</dd>
  </dl>

  <p>
    Every finding Bayyinah emits is tagged with a tier:
    <strong>Verified</strong> (unambiguous concealment),
    <strong>Structural</strong> (pattern of concealment, context may justify), or
    <strong>Interpretive</strong> (suspicious, context-dependent).
    The integrity score is a single continuous number; readers are expected
    to inspect the findings, not stop at the score.
  </p>

  <p class="footer">
    Bayyinah is a pre-LLM file integrity scanner. It does not call any
    language model. It does not store uploaded files. The demo endpoint
    runs the same library available on PyPI; the wrapper only handles
    transport. Bug reports and contributions welcome on
    <a href="https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner">GitHub</a>.
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
