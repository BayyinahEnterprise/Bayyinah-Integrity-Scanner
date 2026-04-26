# Bayyinah — Evolution Archive

*"And thus We have made you a middle community, that you might be witnesses over the people."* — Al-Baqarah 2:143

This directory documents Bayyinah's three-generation architecture. The codebase has been through three complete implementations, each one byte-identical-on-Phase-0-fixtures to its predecessor. The parity is the project's central honesty: three independent implementations producing the same evidence for the same inputs.

## The three generations

### Generation 0 — `bayyinah_v0.py` (first PDF test version)

*Al-'Alaq energy — read and recite.*

The original monolithic PDF integrity scanner. One Python module, top to bottom: every detector inline, every helper colocated with its caller, every finding constructed by literal `Finding(...)` calls in the same file. This is what a first-pass scanner looks like when the architect is still learning the shape of the problem — and it works.

- **Location in this tree:** `../bayyinah_v0.py`
- **MD5 (CI-asserted):** `87ba2ea48800ef616b303a25b01373d8`
- **Line count:** ~1,700
- **Detectors:** text-layer (zahir) + object-layer (batin) for PDFs only
- **Status:** Byte-frozen. The CI workflow re-asserts the MD5 on every push. No contributor may edit this file; adding a new detector means adding it to the modular 1.0 tree instead.

This is the "first test version" the project asks every refactor to measure itself against. `bayyinah.scan_pdf(f)` must return the same findings, the same integrity score, the same error string, and the same `scan_incomplete` flag as `bayyinah_v0.scan_pdf(f)` — for every one of the 17 Phase 0 PDF fixtures. That is the parity contract.

### Generation 0.1 — `bayyinah_v0_1.py` (fat-split intermediate)

*Al-Kawthar energy — abundance.*

The first reorganisation: the monolith was fat-split into a `PDFContext` (lazy parser access), a `TextLayerAnalyzer`, an `ObjectLayerAnalyzer`, a `ScanService` orchestrator, and formatter helpers. Still one file. Still produces the same bytes of output. But now the analyzers are separable enough that Phase 1+ could pull them into their own modules without changing output semantics.

- **Location in this tree:** `../bayyinah_v0_1.py`
- **MD5 (CI-asserted):** `035aa578de7470c9465922bee2632cd5`
- **Line count:** ~1,650
- **Status:** Byte-frozen. Same parity discipline as v0.

### Generation 1.0 — the modular refactor (current tree)

*Al-Bayyinah energy — clear evidence.*

The full hexagonal architecture. Pure domain primitives in `domain/`, parser adapters in `infrastructure/`, analyzer contract and implementations in `analyzers/`, orchestrator in `application/`, console script in `cli/`, public Python surface in `bayyinah/`. Twelve supported formats. Ninety registered mechanisms. One `ScanService.scan(file_path)` entry point that covers all of them.

- **Location in this tree:** `../bayyinah/`, `../analyzers/`, `../application/`, `../domain/`, `../infrastructure/`, `../cli/`
- **Phase count:** 22 implementation phases + 2 polish passes (22-polish, 23-polish)
- **Test count:** 1,301 passing (as of assembly)
- **Public surface size:** 54 exported symbols via `bayyinah.__all__`
- **Format coverage:** PDF, DOCX, HTML, XLSX, PPTX, EML, CSV, JSON, PNG/JPEG/GIF/BMP/TIFF/WebP, SVG, Markdown/code/plain text — plus `FallbackAnalyzer` catching everything else

The 1.0 release adds `scan_file()` as a format-agnostic public entry point. `scan_pdf()` remains a backward-compatible alias for callers pinned to the PDF-only surface, and both delegate to the same `ScanService` internally.

## Why the old generations ship in the wheel

Two load-bearing reasons, both documented in `../legacy/README.md`:

1. **Additive-only invariant.** Downstream code pinned to `import bayyinah_v0` must continue to resolve. The scanner's own CI parity sweep uses this import. Moving the files would be a silent breaking change — exactly the concealment pattern the project is built to detect.

2. **Byte-identical fingerprinting.** The two MD5s above are asserted by `.github/workflows/ci.yml` on every push. If either drifts, CI fails loudly. That is the structural honesty of the project: what shipped as v0 still ships as v0, identically. The refactor's claim to faithfulness is continuously verifiable.

## Phase roadmap (abbreviated)

| Phase | Work |
|-------|------|
| 0 | Bootstrap fixtures + parity harness |
| 1 | Domain primitives (`Finding`, `IntegrityReport`, scoring) |
| 2 | Analyzer base contract + registry |
| 3 | Infrastructure (PDF client, router, formatters) |
| 4 | `ZahirTextAnalyzer` — text-layer concealment detection |
| 5 | `BatinObjectAnalyzer` — object-layer concealment detection |
| 6 | `ScanService` orchestrator |
| 7 | Public API + CLI |
| 9 | FileRouter + analyzer dispatch by FileKind |
| 10 | Image analyzer (PNG/JPEG/GIF/BMP/TIFF/WebP) |
| 11 | Image depth detectors (LSB steganography, trailing data, EXIF) |
| 12 | Cross-modal correlation engine |
| 13 | Correlation hardening + gates |
| 14 | Qur'anic Prompt-Engineering methodology documentation |
| 15 | DOCX support |
| 16 | HTML support |
| 17 | XLSX support |
| 18 | PPTX support |
| 19 | EML support |
| 20 | CSV support |
| 21 | `FallbackAnalyzer` + `ScanLimits` (universal witness of last resort) |
| 22 | 1.0 packaging, CI workflow, wheel + sdist build, `file_path` rename, `legacy/` alias, polish passes |
| 23 | Docstring polish on early modules |
| Assessment | `scan_file()` addition, CLI help text refresh, `.DS_Store` cleanup, unified packaging |

## The parity contract, in one line

`bayyinah.scan_pdf(f) == bayyinah_v0.scan_pdf(f)` — same findings, same score, same error, same scan-incomplete flag — for every PDF in `tests/fixtures/`. Asserted by CI on every push. If it drifts, the refactor is lying, and the refactor has been wrong to do.

That is the project's standing witness (Al-Baqarah 2:282 — *"bring two witnesses"*): two independent implementations attesting to the same observations. The modular 1.0 scanner is the third witness, and all three agree.

## Bayyinah's place in the broader research program

This repository is the **shipped artifact** of an integrated research
program on structural honesty in artificial systems. Two companion
documents in this folder map how Bayyinah relates to the rest:

* `RESEARCH_PROGRAM_STACK.md` — the four-layer integrity stack (file,
  information, agent-diagnostic, agent-architectural) and how Bayyinah
  fits among the Munafiq Protocol (published, DOI
  10.5281/zenodo.19677111), Bayyinah al-Khabir (theoretical), Al-Khalifa
  (theoretical), Furqan (theoretical), the Fatiha Construct (published,
  applied across the program), and Computational Tawhid (ontological).
* `FURQAN_CORRESPONDENCE.md` — for each of Furqan's nine primitives
  (the seven compile-time + `scan_incomplete` + Fatiha session
  protocol), the exact Bayyinah file, mechanism, test, or workflow
  that validates it. Every primitive maps to at least one auditable
  artifact in this repository; the strongest map to CI-enforced
  invariants.

If anyone questions whether the research program's theoretical claims
are grounded, the auditable answer is the table in
`FURQAN_CORRESPONDENCE.md` — every primitive operated as a behavioural
convention here before being proposed as a language feature.

*Bismillah ar-Rahman ar-Raheem.*
