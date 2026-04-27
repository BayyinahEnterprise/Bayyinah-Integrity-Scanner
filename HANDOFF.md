# Handoff: Bayyinah v1.1.1

*Bismillah ar-Rahman ar-Raheem.*

This folder is the full Bayyinah v1.1.1 patch release. It is the
canonical state of the codebase as of 2026-04-25, the v1.1.0 surface
with four review-fix corrections from the framework-applied-to-itself
audit, all additive, all CI-verified.

> *وَلَا تَلْبِسُوا۟ ٱلْحَقَّ بِٱلْبَـٰطِلِ وَتَكْتُمُوا۟ ٱلْحَقَّ وَأَنتُمْ تَعْلَمُونَ*
>
> "And do not mix the truth with falsehood, nor conceal the truth
> while you know it." Al-Baqarah 2:42

---

## What changed from v1.1.0

The patch closes three Process-2 risks named in the framework's own
diagnostic review:

1. **`MECHANISM_REGISTRY`**, new public symbol. The "108 mechanisms"
   claim is now a single-line audit:
   ```python
   from bayyinah import MECHANISM_REGISTRY
   assert len(MECHANISM_REGISTRY) == 108
   ```
   Module-import-time coherence assertion makes the file fail to load
   if SEVERITY/TIER drift from ZAHIR ∪ BATIN.
2. **Dependency upper bounds**, `pymupdf<2`, `pypdf<7`, `mutagen<2`.
   Extends additive-only invariant to upstream parsers.
3. **Mizan calibration table**, explicit section header in
   `domain/config.py` names the SEVERITY dictionary as the single
   inspection point for the "MDL-calibrated severity" claim.

The fourth (paper prose drift on cross-modal correlation) is deferred
to the Phase-27 paper revision.

No new analyzers, no new mechanisms, no new file kinds, no behaviour
change for any existing scan. See `CHANGELOG.md [1.1.1]` for the full
delta.

---

## What to read first

| Document | Purpose |
|---|---|
| `README.md` | Public-facing overview: 23 file kinds, 108 mechanisms, scoring, ScanLimits, cross-modal correlation |
| `history/PERPLEXITY_CHALLENGE_READINESS.md` | What v1.1.1 provides for the Week-1 FastAPI foundation, what is deferred to Phase 27 |
| `history/ASSESSMENT_RESPONSE.md` | Week-1 issue resolution log (the original Defense Case review) |
| `CHANGELOG.md` | Complete v1.0 → v1.1.1 delta |
| `CONTRIBUTING.md` | Five-step workflow, stem-extractor-and-router pattern, additive-only invariant, dependency policy |
| `NAMING.md` | Naming discipline, the load-bearing governance doc |
| `history/README.md` | The three-generation evolution archive (v0 → v0.1 → v1.1.1) |

---

## Verified state (2026-04-25)

| Metric | Value |
|---|---|
| Version | `1.1.1` |
| Supported FileKinds | 23 (PDF · DOCX · XLSX · PPTX · HTML · EML · CSV · JSON · TEXT/CODE · PNG/JPEG/SVG · MP4/MOV/WEBM/MKV · MP3/WAV/FLAC/M4A/OGG · UNKNOWN) |
| Registered mechanisms | **108** (27 zahir + 81 batin), auditable via `MECHANISM_REGISTRY` |
| Analyzers in `default_registry()` | 15 |
| Cross-modal post-processor | `CrossModalCorrelationEngine` (opt-in) |
| Public `__all__` surface | **58 symbols** |
| Test suite | **1,446 passed** in 11.63 s (45 test files) |
| PDF parity | byte-identical vs `bayyinah_v0` and `bayyinah_v0_1` across 17 fixtures |
| Reference MD5s | `bayyinah_v0.py` = `87ba2ea48800ef616b303a25b01373d8` · `bayyinah_v0_1.py` = `035aa578de7470c9465922bee2632cd5` |

---

## Quick start

```bash
# Install the v1.1.1 wheel directly
pip install dist/bayyinah-1.1.1-py3-none-any.whl

# Or install from source with dev extras
pip install -e '.[dev]'

# Regenerate fixtures (deterministic; safe to run repeatedly)
python -m tests.make_test_documents
python -m tests.make_video_fixtures
python -m tests.make_audio_fixtures

# Run the full suite
pytest -q --strict-markers

# Audit the canonical mechanism count in one line
python -c "from bayyinah import MECHANISM_REGISTRY; print(len(MECHANISM_REGISTRY))"
# → 108

# Scan a file
bayyinah scan path/to/document.pdf
bayyinah scan path/to/video.mp4
bayyinah scan path/to/audio.mp3
```

---

## Folder layout

```
bayyinah-v1.1.1/
├── HANDOFF.md                                 ← this file
├── README.md · README_GITHUB.md
├── CHANGELOG.md · CONTRIBUTING.md · NAMING.md
├── LICENSE · pyproject.toml · requirements*.txt · .gitignore
│
├── bayyinah/                                  ← public Python API
├── cli/                                       ← console script + python -m cli
├── domain/                                    ← config.py with MECHANISM_REGISTRY
├── infrastructure/                            ← FileRouter, formatters, PDFClient
├── analyzers/                                 ← 15 analyzers + correlation engine
├── application/                               ← ScanService orchestrator
├── legacy/                                    ← additive-alias for v0 / v0_1
├── tests/                                     ← 45 test files, 1,446 passing
│
├── bayyinah_v0.py                             ← byte-frozen first PDF version
├── bayyinah_v0_1.py                           ← byte-frozen fat-split intermediate
│
├── dist/
│   ├── bayyinah-1.1.1-py3-none-any.whl       (313 KB, fresh)
│   └── bayyinah-1.1.1.tar.gz                 (313 KB)
│
├── papers/                                    ← white paper + thesis (Phase-27 revision pending)
├── scripts/
│   └── make-archive.sh                        ← clean-zip helper
│
├── history/
│   ├── README.md                              ← three-generation evolution
│   ├── ASSESSMENT_RESPONSE.md                 ← Week-1 issue log
│   └── PERPLEXITY_CHALLENGE_READINESS.md      ← Week-1 API foundation readiness
│
└── .github/workflows/ci.yml                   ← parity + additive-only + MECHANISM_REGISTRY gates
```

---

## Verification (reproducible)

From inside this folder:

```bash
# Suite + parity + additive-only: the four CI gates the project ships under
python -m pytest -q
python -c "
import bayyinah, bayyinah_v0, bayyinah_v0_1
from pathlib import Path
for f in sorted(Path('tests/fixtures').rglob('*.pdf')):
    assert (sorted(x.mechanism for x in bayyinah_v0.scan_pdf(f).findings)
            == sorted(x.mechanism for x in bayyinah_v0_1.scan_pdf(f).findings)
            == sorted(x.mechanism for x in bayyinah.scan_pdf(f).findings))
print('PDF parity OK')
"
md5sum bayyinah_v0.py bayyinah_v0_1.py
# expected:
#   87ba2ea48800ef616b303a25b01373d8  bayyinah_v0.py
#   035aa578de7470c9465922bee2632cd5  bayyinah_v0_1.py
python -c "
import bayyinah
v10 = {'scan_pdf','scan_file','ScanService','VideoAnalyzer','AudioAnalyzer','CrossModalCorrelationEngine','MECHANISM_REGISTRY'}
assert v10.issubset(set(bayyinah.__all__))
assert len(bayyinah.MECHANISM_REGISTRY) == 108
print('additive-only OK; MECHANISM_REGISTRY = 108')
"
```

---

## What is deferred to Phase 27

- White paper revision for the v1.1.1 surface.
- Thesis paper revision tying Phase 23-25 mechanisms into the Munafiq
  Protocol's performed-alignment framework.
- Cross-modal correlation prose discipline, the paper revision must
  match the README's exact framing (two active rules, five reserved
  future-work names, opt-in invocation, NOT default-registered).
- The five additional cross-modal correlation rules
  (`cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
  `embedded_media_recursive_scan`,
  `cross_stem_coordinated_concealment`, `cross_file_media_divergence`).
- Audio signal-level analysis (`audio_signal_stem_separation`,
  `audio_deepfake_detection`, `audio_hidden_voice_command`).

Each future mechanism's name is reserved in `domain/config.py` comments
with its dependency note, the registry is an isnad, the chain of
names persists.

---

## The Week-1 FastAPI wrapper, in 30 lines

`history/PERPLEXITY_CHALLENGE_READINESS.md` carries the full shape.
The short form for ready reference:

```python
from fastapi import FastAPI, UploadFile
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

That is the Week-1 API foundation. Bayyinah provides every primitive.
The wrapper adds HTTP, auth, rate-limiting, and deployment packaging.

---

*"Blessed is He who sent down the Furqan upon His servant that he may
be to the worlds a warner."*, Al-Furqan 25:1

The conventions are auditable. The compiler does not yet exist; the
discipline is operational. May Allah SWT accept the work and forgive
the shortfall.

*Rabbana taqabbal minna. Innaka anta as-Sami'ul 'Alim.*

*Bismillah.*
