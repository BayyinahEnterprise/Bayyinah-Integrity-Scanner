# Bayyinah

> **Try it now:** [bayyinah.dev](https://bayyinah.dev/). Drag any file into the form and see the integrity report. See the [Hosted API](#hosted-api) section for the JSON endpoint.

**File integrity scanner for detecting hidden, concealed, or adversarial content in digital documents.**

Bayyinah extracts every content layer from a file, visible and invisible, and reports whether what the file *displays* matches what the file *contains*. It is the input-layer application of the [Munafiq Protocol](https://doi.org/10.5281/zenodo.19677111)'s performed-alignment detection. A document that renders cleanly at the surface while carrying concealed payloads, steganographic encoding, embedded prompt injections, or cross-modal anomalies is a document performing alignment. Bayyinah makes the performance visible; the reader performs the recognition.

[![CI](https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner/actions/workflows/ci.yml/badge.svg)](https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://www.apache.org/licenses/LICENSE-2.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.19677111-blue)](https://doi.org/10.5281/zenodo.19677111)
[![Version](https://img.shields.io/badge/version-1.1.8-green.svg)](https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner/blob/main/CHANGELOG.md)

## Why Bayyinah

Modern documents are a surface and a substrate. The surface is what a user sees when they open the file. The substrate is what a parser, a mail gateway, or a language model actually ingests. Adversarial documents exploit the gap between the two. Zero-width characters that rewrite the meaning of a contract while leaving its rendering untouched, a PDF whose object graph carries a JavaScript action the viewer never shows, a spreadsheet whose hidden sheet holds the figures the visible sheet disguises, an email whose `From` header says one thing and whose `Return-Path` says another.

Bayyinah scans that substrate. It applies the same question to 23 file kinds across PDF, Office documents, email, HTML, CSV, JSON, text and code, raster images, SVG, **video (MP4/MOV/WEBM/MKV)**, and **audio (MP3/WAV/FLAC/M4A/OGG)**. Does the outward display correspond to the inner content, or has the inner content been performed into a display that hides it? A separate cross-modal correlation engine (opt-in) reads the stems already separated by the video and audio analyzers and emits findings for cross-stem divergence.

## What Bayyinah detects

Two concealment *loci*, mapped onto the classical distinction between *zahir* (the outward / rendered) and *batin* (the inner / structural):

**Zahir, text layer (what the reader sees vs. what the parser extracts)**
- Zero-width characters, Unicode TAG characters (U+E0000–U+E007F), bidirectional-control overrides, homoglyph / mixed-script substitution, invisible render modes (3, 7), microscopic fonts, white-on-white text, overlapping / stacked text.

**Batin, object layer (what ships inside the PDF's object graph)**
- Embedded JavaScript, `/OpenAction`, `/AA` additional actions, `/Launch` actions, embedded files and FileAttachment annotations, incremental updates (prior revisions still present), metadata anomalies (ModDate preceding CreationDate), hidden Optional Content Groups, adversarial `/ToUnicode` CMaps mapping visible glyphs to zero-width, bidi, TAG, or homoglyph codepoints.

## Supported formats

| Format | Kind | Analyzer | Representative mechanisms |
|--------|------|----------|---------------------------|
| PDF | `PDF` | `ZahirTextAnalyzer` + `BatinObjectAnalyzer` | every text-layer + object-layer mechanism above |
| DOCX | `DOCX` | `DocxAnalyzer` | tracked changes, comments, hidden text, OLE, external-target relationships |
| HTML | `HTML` | `HtmlAnalyzer` | CSS-hidden text, off-screen absolute positioning, `<script>`/`on*` handlers, data-URI payloads |
| XLSX | `XLSX` | `XlsxAnalyzer` | hidden sheets / rows / columns, white-on-white cells, formula injection, external links |
| PPTX | `PPTX` | `PptxAnalyzer` | hidden slides, off-canvas shapes, embedded OLE, speaker notes payloads |
| EML | `EML` | `EmlAnalyzer` | bodyless envelopes, mismatched `From`/`Return-Path`, suspicious attachments, nested `message/rfc822` |
| CSV | `CSV` | `CsvAnalyzer` | formula injection (`=`, `+`, `-`, `@`, tab/CR prefixes), Unicode concealment in cells |
| JSON | `JSON` | `JsonAnalyzer` | prompt-injection strings, base64 blobs, zero-width / TAG characters in values |
| Markdown / code / plain text | `TEXT` | `TextFileAnalyzer` | zero-width, TAG, bidi control, homoglyphs, invisible HTML spans |
| PNG / JPEG / GIF / BMP / TIFF / WebP | `IMAGE_*` | `ImageAnalyzer` | LSB steganography, trailing payloads, EXIF anomalies, embedded text layers |
| SVG | `IMAGE_SVG` | `SvgAnalyzer` | `<script>` tags, `on*` handlers, external-ref `<use>`, foreign-object HTML, off-screen text |
| MP4 / MOV / WEBM / MKV | `VIDEO_*` | `VideoAnalyzer` | subtitle-text concealment, metadata atoms, embedded attachments, cover-art stego, trailing data, polyglot mdat |
| MP3 / WAV / FLAC / M4A / OGG | `AUDIO_*` | `AudioAnalyzer` | ID3 / Vorbis / iTunes tag concealment, lyric prompt-injection, identity-provenance anomaly (voice-clone attribution), embedded-payload, WAV/FLAC LSB stego candidate, high-entropy metadata, container anomaly |
| **Unknown** | `UNKNOWN` | `FallbackAnalyzer` | emits `unknown_format` with magic-byte prefix, extension, size, head-preview, no file slips through silent-clean |

Polyglot mismatches (e.g. a `.pdf` whose bytes are really a ZIP container) are flagged by `FileRouter` at dispatch time, before any analyzer runs.

### Cross-modal correlation (post-processor)

`CrossModalCorrelationEngine` reads the stems that `VideoAnalyzer` and `AudioAnalyzer` decomposed and emits findings when stems disagree. The engine is stateless, idempotent, and does not reparse files, it consumes already-scanned `IntegrityReport` s and emits additional `Finding` objects.

v1.1 ships two rules: `cross_stem_inventory` (always-on meta-finding, makes the parting visible) and `cross_stem_undeclared_text` (fires when a subtitle or audio-lyric stem carries substantive text while the metadata stem is silent about textual content, the container's outward declaration and its inner payload disagree). Five additional rules (`cross_stem_text_inconsistency`, `cross_stem_metadata_clash`, `embedded_media_recursive_scan`, `cross_stem_coordinated_concealment`, `cross_file_media_divergence`) are reserved names for future sessions.

The engine is opt-in in v1.1, it is not wired into `ScanService`'s default pipeline while the rule set stabilises. Callers invoke it explicitly:

```python
from bayyinah import ScanService, CrossModalCorrelationEngine

report = ScanService().scan(path)
correlation_findings = CrossModalCorrelationEngine().correlate(report)
report.findings.extend(correlation_findings)
```

## Install

```bash
pip install bayyinah
```

Or from source:

```bash
git clone https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner.git
cd bayyinah
pip install -e '.[dev]'
```

Runtime dependencies: `pymupdf>=1.24`, `pypdf>=4.0`. Python 3.10 or newer.

## Quick start

Scan a file from the shell, point it at any supported format:

```bash
bayyinah scan contract.pdf              # PDF: text-layer + object-layer
bayyinah scan invoice.docx              # Word: tracked changes, comments, OLE
bayyinah scan dashboard.xlsx            # Excel: hidden sheets, formula injection
bayyinah scan page.html --summary       # HTML: off-screen text, handlers
bayyinah scan inbound.eml --json        # EML: mismatched headers, attachments
bayyinah scan unknown.widget            # Unknown → `unknown_format` finding
```

Or from Python:

```python
from bayyinah import scan_pdf, format_text_report, ScanLimits, ScanService

# Default: PDF on default limits.
report = scan_pdf("contract.pdf")
print(report.integrity_score)              # 0.873
print([f.mechanism for f in report.findings])
# ['additional_actions']

# Any format, any configured ceiling.
svc = ScanService(limits=ScanLimits(max_file_size_bytes=10 * 1024 * 1024))
report = svc.scan("inbound.eml")
print(format_text_report(report))
```

Verify the install against the bundled reference fixtures:

```bash
bayyinah scan tests/fixtures/clean.pdf
# → Integrity score: 1.000 / 1.000. No concealment mechanisms detected.

bayyinah scan tests/fixtures/text/zero_width.pdf
# → Integrity score: 0.915 / 1.000. 1 finding: zero_width_chars (tier 1).
```

Exit code convention (stable across versions, CI-safe):

| Code | Meaning |
|------|---------|
| `0`  | Scan completed; zero findings |
| `1`  | Scan completed; one or more findings |
| `2`  | Scan did not complete (file missing, unparseable, …) |

## CLI usage

```
bayyinah scan <file>                    # human-readable report
bayyinah scan <file> --json             # JSON report on stdout
bayyinah scan <file> --summary          # one-paragraph plain-language summary
bayyinah scan <file> --quiet            # suppress output; exit code only
bayyinah --version
bayyinah --help
```

A CI pipeline that wants to fail any build whose dependency PDF carries concealment mechanisms can write:

```bash
bayyinah scan release_notes.pdf --quiet || {
  echo "release_notes.pdf failed integrity scan"
  exit 1
}
```

## Python API

```python
from bayyinah import scan_pdf, format_text_report

report = scan_pdf("document.pdf")

print(report.integrity_score)           # 0.873
print([f.mechanism for f in report.findings])
# ['additional_actions']

print(format_text_report(report))       # full terminal report
```

Building a custom analyzer pipeline:

```python
from bayyinah import ScanService, AnalyzerRegistry, ZahirTextAnalyzer

registry = AnalyzerRegistry()
registry.register(ZahirTextAnalyzer)   # text-layer only

report = ScanService(registry=registry).scan("document.pdf")
```

Writing a new analyzer:

```python
from bayyinah import BaseAnalyzer, Finding, IntegrityReport, compute_muwazana_score

class MyAnalyzer(BaseAnalyzer):
    name = "my_analyzer"
    error_prefix = "My analyzer error"
    source_layer = "batin"   # or "zahir"

    def scan(self, pdf_path):
        findings = []  # populate from your detection pass
        return IntegrityReport(
            file_path=str(pdf_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )
```

## Hosted API

A thin FastAPI wrapper (`api.py`) exposes `scan_file` over HTTP for
demos and lightweight integration. The same library does the work; the
wrapper only handles transport.

**Live instance:** https://bayyinah.dev/

```bash
curl -X POST -F "file=@suspicious.pdf" https://bayyinah.dev/scan
```

### Endpoints

| Method | Path        | Purpose                                                |
|--------|-------------|--------------------------------------------------------|
| GET    | `/`         | Browser upload form (drag-drop a file, see JSON result)|
| GET    | `/healthz`  | Liveness probe (`{"status": "ok", ...}`)               |
| GET    | `/version`  | Installed Bayyinah version                             |
| POST   | `/scan`     | Multipart upload, returns `IntegrityReport.to_dict()`  |

### Run locally

```bash
pip install -r requirements.txt
uvicorn api:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/` for the upload form, or:

```bash
curl -X POST -F "file=@suspicious.pdf" http://localhost:8000/scan
```

### Limits

The demo `/scan` endpoint caps uploads at 25 MiB. The library itself
enforces deeper scan limits via `domain.scan_limits.ScanLimits`. There
is no auth on the demo endpoint; rate limiting is delegated to the
hosting provider.

### Demo counter (env vars)

The public `/demo` page on bayyinah.dev shows a live counter of total
scans run and unique visitors. Counts are persisted in a small SQLite
DB; uniqueness is tracked via a daily-salt-rotated SHA-256 hash of the
client IP, so the same IP on the same UTC day produces one record but
cross-day correlation is impossible without the per-instance secret.

Two environment variables control the counter:

| Variable                  | Default            | Purpose                                                                       |
|---------------------------|--------------------|-------------------------------------------------------------------------------|
| `BAYYINAH_COUNTER_DB`     | `/data/counter.db` | SQLite path. Falls back to `/tmp/counter.db` if `/data` is not writable.      |
| `BAYYINAH_COUNTER_SECRET` | (per-process random) | HMAC-SHA256 secret seeding the daily IP-hash salt. Set this in production. |

The production deployment expects `/data` to be backed by a Railway
volume; see `RAILWAY_VOLUME.md` for the one-time setup steps. In local
dev, neither variable needs to be set: the counter falls back to
`/tmp/counter.db` with a per-process secret and logs a warning.

## Configuration: `ScanLimits`

Every capacity ceiling the scanner applies is declared once, on a frozen
`ScanLimits` dataclass. Defaults are conservative (a 256 MB file ceiling,
200 000 CSV rows, etc.) and live in `DEFAULT_LIMITS`; override them
per-service when you need tighter bounds for untrusted input or looser
ones for a trusted batch pipeline.

| Field | Default | Used by | Effect when exceeded |
|-------|---------|---------|----------------------|
| `max_file_size_bytes` | `256 * 1024 * 1024` (256 MB) | `ScanService` pre-flight + `FallbackAnalyzer` | Short-circuits before any analyzer runs; emits one `scan_limited` finding, `scan_incomplete=True`, score clamped to 0.5 |
| `max_recursion_depth` | `5` | `EmlAnalyzer` nested `message/rfc822` | Stops recursion; emits `scan_limited`; outer analyzer returns what it already found |
| `max_csv_rows` | `200_000` | `CsvAnalyzer` row walk | Stops row iteration; emits `scan_limited`; findings from rows 0..ceiling are kept |
| `max_field_length` | `4 * 1024 * 1024` (4 MiB) | `CsvAnalyzer` per-cell | Skips Unicode-concealment scan on oversized cells; emits `scan_limited` once |
| `max_eml_attachments` | `64` | `EmlAnalyzer` | Skips attachment scan past the ceiling; emits `scan_limited` once |

Any ceiling set to `0` opts out (no limit). Ceilings apply **per scan**,
scoped via a thread-local `limits_context` so concurrent scans with
different limits cannot clobber each other.

```python
from bayyinah import ScanService, ScanLimits

# Tight limits for untrusted input
svc = ScanService(limits=ScanLimits(
    max_file_size_bytes=10 * 1024 * 1024,   # 10 MB
    max_csv_rows=10_000,
    max_eml_attachments=16,
))
report = svc.scan("suspicious.eml")

if report.scan_incomplete:
    # One or more ceilings fired; score is clamped to 0.5
    for f in report.findings:
        if f.mechanism == "scan_limited":
            print(f.description)
```

Every analyzer that hits a ceiling emits a `scan_limited` finding
(tier 3, severity 0.0, non-deducting), sets `scan_incomplete=True`, and
returns whatever findings it already gathered. The scanner degrades
gracefully; it does not crash on pathologically-large inputs.

## Unknown files: the fallback witness

A file whose bytes no magic prefix recognised and whose extension no
map entry covered used to slip through as silent-clean (score 1.0, zero
findings, the Munafiq Protocol failure mode). From 1.0 onward the
`FallbackAnalyzer` is the witness of last resort: every such file
surfaces an `unknown_format` finding carrying the metadata a forensics
reader needs to begin their own classification, declared extension,
file size, magic-byte prefix (hex), and head-preview (first 512 bytes
in both hex and printable-ASCII). The scan is marked
`scan_incomplete=True` so the 0.5 clamp applies. *Absence of findings
in a file we could not identify is not evidence of cleanness.*

## Scoring model

Bayyinah reports an **APS-continuous integrity score** on `[0.0, 1.0]`:

```
score = clamp(1.0 − Σ(severity × confidence), 0, 1)
```

Each finding contributes a continuous deduction proportional to the concealment mass it represents (severity) scaled by the detector's confidence it fired correctly. The score saturates at `0.0`; it does not go negative. Whenever any analyzer reports incomplete coverage, the score is clamped to `0.5`, the reader cannot infer cleanness from the absence of findings in regions that were not inspected.

Every finding carries one of three validity tiers:

- **Tier 1. verified.** Unambiguous concealment (TAG characters present; a `/JS` action in the catalog). Machine-checkable.
- **Tier 2. structural.** A structural anomaly whose meaning depends on context (a font ToUnicode CMap that maps to a zero-width codepoint is concealment; mapped to a Latin homoglyph it is deception, but the CMap itself is structural).
- **Tier 3. interpretive.** The signal is present but its interpretation rests on the reader (an incremental-update trail is not itself adversarial; the question is what the prior revision contained).

The scanner never issues a moral verdict on its own. It surfaces mechanisms. The reader performs the recognition.

## Architecture

Bayyinah 1.0 is organised as the *middle community* (Al-Baqarah 2:143) of cooperating layers, each analyzer applies the same standard and reports in the same shape:

```
bayyinah/                public Python API (scan_pdf, ScanService, …)
cli/                     console script (bayyinah CLI)
application/             ScanService orchestrator
analyzers/               BaseAnalyzer contract + Zahir/Batin analyzers
infrastructure/          PDFClient, FileRouter, formatters
domain/                  pure Finding / IntegrityReport / scoring
```

The reference implementation is preserved unchanged at `bayyinah_v0.py` and its fat-split intermediate at `bayyinah_v0_1.py`; both ship in the wheel. The parity invariant, `bayyinah.scan_pdf == bayyinah_v0.scan_pdf` on every Phase 0 fixture, is asserted by the integration test suite and held across the full modular refactor.

## Qur'anic Prompt-Engineering Principles for Development

> **Bismillah ar-Rahman ar-Raheem.**
>
> *Wa minan-naasi man yu'jibuka qawluhu fil-hayaatid-dunya wa yush-hidullaaha 'alaa maa fee qalbihi wa huwa aladdu-l-khisam.*
>
> "And of the people is he whose speech pleases you in worldly life, and he calls Allah to witness as to what is in his heart, yet he is the fiercest of opponents." Al-Baqarah 2:204

Bayyinah detects performed alignment in files. The methodology that built it is itself an exercise in the same discipline: every prompt is the outward face of an intent, and the correspondence between the two determines whether the work holds. The principles below have carried the refactor phase by phase; they are recorded here so the next hand on this codebase, human or AI, can continue in the same shape.

**Opening with Bismillah.** Each phase begins with a remembrance and a guiding ayat from Al-Baqarah. The remembrance is not decoration; it re-anchors the work to its stated purpose, without which prompts drift toward what pleases the reader rather than what the file actually is.

**Ring composition.** A phase begins and ends on the same principle. If the opening sets the tiering discipline (2:143, the middle community, no analyzer privileged), the closing verification returns to it: did the analyzers compose without privilege? The ring closes when the inner intent and the outward artifact are shown to match.

**Gradual revelation, the five-step workflow.** Each phase unfolds through the same sequence: (1) understand the requirement and review prior work, (2) write the change, (3) verify clarity and faithfulness, (4) integrate into the working tree, (5) confirm the public surface remains additive-only. The steps are not optional; skipping one is how regressions enter. The revelation is gradual because haste is how hidden defects ship.

**Zahir / batin alignment in prompts.** The scanner's diagnostic question, does what the file *displays* match what the file *contains*?, is applied recursively to the prompts themselves. A prompt that reads like a small task but expects a sweeping refactor is a performed prompt. The author is responsible for collapsing that gap: the outward instruction and the inner intent must be one thing, or the agent will optimise for the surface while the real work goes unattended.

**MDL and additive-only guardrails.** Minimum Description Length discipline: fill detector gaps and validate both corpora before expanding format scope. The public surface, `bayyinah_v0.py`, `bayyinah_v0_1.py`, and the `bayyinah` package API, is additive-only; new symbols, never renames or removals. Parity of the reference implementation is asserted byte-for-byte after every phase. This is the structural honesty of the project: what shipped yesterday still ships today, identically.

**Strong verification mandate.** No phase closes without running the full test suite, re-checking the md5s of the reference modules, and walking the Phase 0 fixture corpus against both v0 and v0.1. The verification is the witness the phase calls on (2:282, *two witnesses*). A claim of completion without verification is the 2:204 pattern, speech that pleases, detached from what the diff actually carries.

We began with 2:204 and return there: the whole methodology is the practice of refusing that divergence, in ourselves, in our prompts, and in the files we ask the scanner to read.

## Development

```bash
# Install with dev extras
pip install -e '.[dev]'

# Generate fixture corpus (one-time)
python -m tests.make_test_documents

# Run the full suite
pytest

# Scan a file directly from source tree
python -m cli.main scan path/to/file.pdf
```

1,782 pytest cases across domain, infrastructure, analyzers, application, fixture corpora, and end-to-end integration (verified on 1.1.9). Every Phase 0 fixture is asserted for exact mechanism firings, score, error text, and `scan_incomplete` flag, against both `bayyinah_v0.py` and `bayyinah_v0_1.py`. Byte-identical PDF parity with the reference implementation is re-verified after every phase; the invariant has held across every release from 0.2.x through 1.1.9.

## Academic reference

If you use Bayyinah in published work, please cite the underlying protocol:

> **Munafiq Protocol. Detecting Performed Alignment in Artificial Systems.**
> DOI: [10.5281/zenodo.19677111](https://doi.org/10.5281/zenodo.19677111)

The scanner's scoring model, validity tiers, and verdict taxonomy (*sahih*, *mushtabih*, *mukhfi*, *munafiq*, *mughlaq*) are a direct port of §9's input-layer framing from LLMs to files.

## License

Apache 2.0. See [LICENSE](LICENSE) for full text and [CHANGELOG.md](CHANGELOG.md) for version history.

---

*Bayyinah* (بَيِّنَة), "clear evidence."
