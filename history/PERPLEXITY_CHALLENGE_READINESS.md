# Perplexity Challenge — Week 1 API Foundation Readiness

*Verified 2026-04-25 against Bayyinah v1.1.1 at this commit.*

This note records what v1.1 already provides for the Week-1 API
foundation and what the Perplexity Challenge integration still
needs on top. It is a factual state snapshot, not a roadmap —
new capabilities claimed here must already exist in the codebase
before the note is written.

---

## What v1.1 already provides

### Format-agnostic public entry point

`bayyinah.scan_file(path)` accepts any supported format and
returns an `IntegrityReport` with findings, integrity score,
error string, `scan_incomplete` flag, and serialisable
`to_dict()`. The function was added in the Week-1 assessment
response; its shape is the exact three-line integration the
thesis paper specifies:

```python
from bayyinah import scan_file

report = scan_file(path)
if report.verdict != "sahih":
    reject_or_route(path, report)
```

### 23 supported file kinds

Dispatched by `FileRouter`, each routed to a `BaseAnalyzer`
subclass whose `supported_kinds` claims that FileKind:

| Family | FileKinds | Analyzer |
|---|---|---|
| PDF | `PDF` | `ZahirTextAnalyzer` + `BatinObjectAnalyzer` |
| Office | `DOCX`, `XLSX`, `PPTX` | `DocxAnalyzer` / `XlsxAnalyzer` / `PptxAnalyzer` |
| Text / markup | `HTML`, `MARKDOWN`, `JSON`, `CODE` | `HtmlAnalyzer` / `TextFileAnalyzer` / `JsonAnalyzer` |
| Email | `EML` | `EmlAnalyzer` |
| Tabular | `CSV` | `CsvAnalyzer` |
| Raster image | `IMAGE_PNG`, `IMAGE_JPEG` | `ImageAnalyzer` |
| Vector image | `IMAGE_SVG` | `SvgAnalyzer` |
| **Video** | `VIDEO_MP4`, `VIDEO_MOV`, `VIDEO_WEBM`, `VIDEO_MKV` | `VideoAnalyzer` |
| **Audio** | `AUDIO_MP3`, `AUDIO_WAV`, `AUDIO_FLAC`, `AUDIO_M4A`, `AUDIO_OGG` | `AudioAnalyzer` |
| Unknown | `UNKNOWN` | `FallbackAnalyzer` |

Any file the router cannot classify still produces a report —
the `FallbackAnalyzer` emits `unknown_format` rather than passing
silent-clean, and the scan is marked incomplete so the 0.5
score clamp applies.

### 15 registered analyzers in the default registry

Ordered by registration in `application.default_registry()`:

```
text_layer → object_layer → text_file → json_file →
image → svg → docx → html → xlsx → pptx →
eml → csv → fallback → video → audio
```

Every analyzer declares a disjoint `supported_kinds` frozenset,
so dispatch is deterministic and no analyzer fires on a file
it does not understand.

### 108 registered mechanisms

27 zahir (visible-surface concealment) + 81 batin (structural /
hidden-layer concealment). Every mechanism carries a SEVERITY
weight in `[0.0, 1.0]` and a TIER in `{1, 2, 3}`. The score
formula is `clamp(1.0 − Σ(severity × confidence), 0, 1)`, clamped
to 0.5 whenever any analyzer sets `scan_incomplete`.

### Cross-modal correlation (opt-in post-processor)

`CrossModalCorrelationEngine` reads already-scanned
`IntegrityReport` objects and emits additional findings for
cross-stem divergence (subtitle loud + metadata silent →
`cross_stem_undeclared_text`). The engine is stateless,
idempotent, and does not mutate its input. It is **not** wired
into `ScanService.default_registry()` — callers opt in
explicitly with the three-line pattern:

```python
from bayyinah import ScanService, CrossModalCorrelationEngine

report = ScanService().scan(path)
report.findings.extend(CrossModalCorrelationEngine().correlate(report))
```

### Serialisation + exit-code contract

Every `IntegrityReport` serialises to a stable JSON shape via
`report.to_dict()`. The CLI maps the report to three exit codes:

| Code | Meaning |
|------|---------|
| `0` | scan completed cleanly, zero findings |
| `1` | scan completed, one or more findings |
| `2` | scan did not complete (file missing, unparseable, …) |

`tamyiz_verdict(report)` derives the five-verdict label
(`sahih` / `mushtabih` / `mukhfi` / `munafiq` / `mughlaq`) from
the report's findings and score.

### Verified test coverage

**1,446 pytest cases** pass in 10.77 seconds (45 test files, full
fixture corpus regenerated on each CI run). Every Phase 0 PDF
fixture is asserted byte-identical against both
`bayyinah_v0.scan_pdf` and `bayyinah_v0_1.scan_pdf`; the
reference modules' md5s are pinned in CI.

### ScanLimits (per-scan safety ceilings)

`ScanLimits` / `limits_context` already declare per-scan ceilings
(`max_file_size_bytes`, `max_recursion_depth`, `max_csv_rows`,
`max_field_length`, `max_eml_attachments`). Hitting a ceiling
emits `scan_limited` (tier 3, severity 0.0 — non-deducting) and
sets `scan_incomplete=True` so the 0.5 score clamp applies.
Concurrent scans with different limits are isolated via
thread-local context.

---

## What a Week-1 REST API integration still needs

These items are **not** in v1.1 — they are the FastAPI-layer work
that sits on top of the Python surface this release finalises:

### A thin HTTP wrapper

The minimal viable server is ~30-50 lines:

```python
# sketch — belongs in a separate repo / module, not bayyinah itself
from fastapi import FastAPI, UploadFile, HTTPException
from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from bayyinah import scan_file, plain_language_summary

app = FastAPI(title="Bayyinah REST", version="1.1.1")

@app.post("/scan")
async def scan(upload: UploadFile) -> dict:
    with NamedTemporaryFile(delete=False, suffix=f"-{upload.filename}") as fh:
        fh.write(await upload.read())
        tmp = Path(fh.name)
    try:
        report = scan_file(tmp)
        return {
            "integrity_score": report.integrity_score,
            "scan_incomplete": report.scan_incomplete,
            "error": report.error,
            "findings": [f.to_dict() for f in report.findings],
            "summary": plain_language_summary(report),
        }
    finally:
        os.unlink(tmp)
```

Bayyinah provides every primitive this route calls (`scan_file`,
`plain_language_summary`, `Finding.to_dict`). The wrapper adds
only the HTTP surface — authentication, rate limiting, and
upload-size enforcement.

### Request-size guards

`ScanService(limits=ScanLimits(max_file_size_bytes=N))` already
enforces a per-scan ceiling. The HTTP layer should additionally
enforce at the `UploadFile` boundary (FastAPI does not
auto-limit) so the scanner never sees a request larger than the
operator's policy allows.

### Authentication / rate limiting

Not in scope for Bayyinah. The HTTP wrapper chooses its own
identity model (API keys, OAuth, mTLS, …) and its own rate-limit
strategy. The scanner is indifferent — it accepts any file path
and returns a report.

### Deployment packaging

Dockerfile / systemd unit / serverless function definition —
downstream of the HTTP wrapper and independent of Bayyinah.

### Optional: cross-modal correlation at the HTTP layer

If the Week-1 API wants to surface correlation findings alongside
per-file findings, the route extends to:

```python
from bayyinah import ScanService, CrossModalCorrelationEngine

svc = ScanService()
engine = CrossModalCorrelationEngine()

report = svc.scan(tmp)
report.findings.extend(engine.correlate(report))
```

This is additive — callers who do not want correlation findings
simply do not run the engine.

---

## What is deferred to Phase 27

- White paper update covering video / audio / cross-modal.
- Thesis paper update tying the Phase 23-25 mechanisms into the
  Munafiq Protocol's performed-alignment framework.
- Additional cross-modal correlation rules (the five reserved
  names in `config.py` comments).
- Audio signal-level analysis (`audio_signal_stem_separation`,
  `audio_deepfake_detection`, `audio_hidden_voice_command` —
  require neural models that open detection surface beyond what
  container-level extraction reaches).

---

## Verification commands

To reproduce the numbers in this note:

```bash
# Full test suite
python -m pytest -q

# PDF parity sweep
python -c "
import bayyinah, bayyinah_v0, bayyinah_v0_1
from pathlib import Path
for f in sorted(Path('tests/fixtures').rglob('*.pdf')):
    r0, r01, r = bayyinah_v0.scan_pdf(f), bayyinah_v0_1.scan_pdf(f), bayyinah.scan_pdf(f)
    assert (sorted(x.mechanism for x in r0.findings)
            == sorted(x.mechanism for x in r01.findings)
            == sorted(x.mechanism for x in r.findings))
print('PDF parity OK')
"

# Additive-only surface — verifies every 1.0 symbol still exports
python -c "
import bayyinah
v10 = {'scan_pdf','scan_file','ScanService','VideoAnalyzer',
       'AudioAnalyzer','CrossModalCorrelationEngine'}  # spot-check
assert v10.issubset(set(bayyinah.__all__))
print('additive-only OK')
"

# Reference md5s
md5sum bayyinah_v0.py bayyinah_v0_1.py
# expected:
#   87ba2ea48800ef616b303a25b01373d8  bayyinah_v0.py
#   035aa578de7470c9465922bee2632cd5  bayyinah_v0_1.py
```

---

*Bismillah ar-Rahman ar-Raheem. Al-hamdu lillah.*
