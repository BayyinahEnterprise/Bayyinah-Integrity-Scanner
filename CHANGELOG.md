# Changelog

All notable changes to Bayyinah are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/spec/v2.0.0.html).

The modular refactor of 0.2.0 was organised as the eight-phase Al-Baqarah
roadmap. Each phase added one architectural slice behind the existing
reference implementation without touching it, the parity invariant
(`bayyinah.scan_pdf == bayyinah_v0.scan_pdf` on every Phase 0 fixture) has
held across every phase.

## [1.1.1]: 2026-04-25

Patch release. Phase 26 framework-applied-to-itself review. The
Munafiq Protocol's nine markers were applied to Bayyinah as if Bayyinah
were the system being diagnosed; the codebase was judged Process 1
(Aligned) overall, with four small surface-depth drifts named as
Process-2 risks. Three were mechanically fixable in this session ,
all additive, all behaviour-preserving, all CI-verified. The fourth
(paper prose drift) is recorded as a Phase-27 paper-revision constraint.

The release is a patch (no new analyzers, no new mechanisms, no new
file kinds, no behaviour change for existing scans). Every v1.1.0
public symbol is preserved; one symbol is added (`MECHANISM_REGISTRY`).

### Added

- **`MECHANISM_REGISTRY`**, `Final[frozenset[str]]` exposed at
  `bayyinah.MECHANISM_REGISTRY` and `domain.MECHANISM_REGISTRY`. The
  union of `ZAHIR_MECHANISMS ∪ BATIN_MECHANISMS`. Converts the
  documented "108 mechanisms" claim from a count anyone has to
  re-derive into a single auditable import:

  ```python
  >>> from bayyinah import MECHANISM_REGISTRY
  >>> len(MECHANISM_REGISTRY)
  108
  ```

  A reviewer auditing the calibration claim now resolves it in one
  line. Added to the CI required-symbol gate so the symbol cannot be
  silently removed in any future release.

- **Module-import-time coherence assertion** in `domain/config.py`.
  The file fails to load if any of three invariants drift apart:
  ZAHIR ∩ BATIN = ∅; SEVERITY.keys() == MECHANISM_REGISTRY;
  TIER.keys() == MECHANISM_REGISTRY. This converts the documented
  invariant ("every mechanism has SEVERITY and TIER, and exactly one
  source layer") from a convention into a structural constraint ,
  the file cannot import in a state where the documentation would lie.

- **`tests/domain/test_mechanism_registry.py`**, 11 new tests pinning
  the exact count (108), the per-layer counts (27 zahir, 81 batin),
  source-layer disjointness, SEVERITY/TIER coherence, severity-value
  range `[0,1]`, tier-value membership in `{1,2,3}`, and the public
  `from bayyinah import MECHANISM_REGISTRY` resolution path.

- **"THE MIZAN CALIBRATION TABLE" section header** in `domain/config.py`
  above the `SEVERITY` dictionary. Names this dictionary as the single
  inspection point for the "MDL-calibrated severity" claim and
  documents the calibration discipline (paired clean + adversarial
  fixtures across 23 file kinds; not benchmark-tuned). The reviewer
  named the missing single inspection point as one of the four
  Process-2 drifts; this header + the import-time coherence assertion
  together close it.

- **`history/DEFENSE_CASE_UPDATES.md`, Phase-27 paper prose constraint**.
  A new block records the cross-modal correlation prose discipline the
  Phase-27 paper revision must honour (two active rules + five reserved
  future-work names; the engine is opt-in, not default-registered). The
  README is the truth; the papers must clamp to it.

### Changed

- **Dependency upper bounds** in `pyproject.toml` and `requirements.txt`:
  `pymupdf>=1.24,<2`, `pypdf>=4.0,<7`, `mutagen>=1.47,<2`. Extends the
  additive-only invariant to upstream dependencies, a major-version
  release in any of the three could change the parse surface and break
  PDF parity silently. Capping at the current major versions forces any
  future compatibility step to be an explicit consumer act rather than
  a passive upgrade. The rationale is documented in the
  `[project.dependencies]` deliberation block.

### Verified

- **Test suite: 1,446 passed in 10.77s** (1,435 baseline + 11 new
  registry tests). 44 → 45 test files.
- **PDF parity: 17/17 byte-identical** vs both `bayyinah_v0.scan_pdf`
  and `bayyinah_v0_1.scan_pdf`. The parity invariant is preserved
  through the patch.
- **Reference md5s**: `bayyinah_v0.py` = `87ba2ea48800ef616b303a25b01373d8` ✓
  / `bayyinah_v0_1.py` = `035aa578de7470c9465922bee2632cd5` ✓ ,
  byte-identical to v1.0 baseline.
- **Public surface**: 54 v1.0 baseline symbols all preserved + 4 v1.1.x
  additions (`VideoAnalyzer`, `AudioAnalyzer`, `CrossModalCorrelationEngine`,
  `MECHANISM_REGISTRY`) = **58 exported symbols** in `bayyinah.__all__`.
  Strict additive-only invariant intact across the v1.1.0 → v1.1.1 step.

### Trigger

The four Process-2 drifts were surfaced by a framework-applied-to-itself
review on 2026-04-25. Applying the Munafiq Protocol's nine markers to
Bayyinah judged the codebase Process 1 (Aligned) overall, outputs
match internal state, scan-incomplete clamps to 0.5 honestly, unknown
formats route to FallbackAnalyzer rather than passing silent-clean,
and stress-probes produce coherent diagnostic output. The four named
drifts were the auditability-of-claims gaps the framework's own
discipline makes care-able. All three code-level drifts are now closed
in v1.1.1; the paper-prose drift is recorded for Phase 27 with explicit
constraints.

### Not changing

- No new analyzer, FileKind, or detection mechanism.
- No CLI surface change. `bayyinah scan <file>` works identically.
- No behaviour change for any existing scan. Every fixture produces the
  same findings, score, and `scan_incomplete` flag as it did under v1.1.0.
- The white paper and thesis paper updates remain deferred to Phase 27.

## [1.1.0]: 2026-04-24

v1.1 consolidation. Phases 23 (video), 24 (audio), and 25+ (cross-modal
correlation, session 1) land additively on the v1.0 surface. Al-Baqarah
2:286: *"Rabbana la tu'akhidhna in nasina aw akhta'na"*, Our Lord, do
not impose blame upon us if we have forgotten or erred. The parity
invariant (`bayyinah.scan_pdf == bayyinah_v0.scan_pdf` on every Phase 0
fixture) continues to hold; every v1.0 public symbol remains exported.

### Added

**Phase 23, VideoAnalyzer (MP4 / MOV / WEBM / MKV).** Al-Baqarah 2:19-20
, the rainstorm in which is darkness, thunder, and lightning. The
visible playback dominates attention while the container's stems ,
subtitle tracks, metadata atoms, embedded attachments, cover-art images,
trailing bytes, carry concealment the viewer never sees. VideoAnalyzer
decomposes the container (stdlib-only ISO BMFF box walker + basic EBML
head sniff; no ffmpeg, no pymediainfo) and routes each stem to the
analyzer that already handles its material, subtitle text to
`ZahirTextAnalyzer._check_unicode`, cover-art images to
`ImageAnalyzer().scan`. Composition, not duplication.

- 4 new `FileKind` values: `VIDEO_MP4`, `VIDEO_MOV`, `VIDEO_WEBM`,
  `VIDEO_MKV`.
- 8 new mechanisms: `video_stream_inventory`, `subtitle_injection`,
  `subtitle_invisible_chars`, `video_metadata_suspicious`,
  `video_embedded_attachment`, `video_frame_stego_candidate`,
  `video_container_anomaly`, `video_cross_stem_divergence` (the last
  registered for future-work detector logic).
- 10 new video fixtures (1 clean MP4 + 8 adversarial MP4 + 1 MKV with
  `Attachments` element ID).
- `FileRouter` detects MP4 / MOV via the `ftyp` box at offset 4 (brand
  distinguishes MP4 / MOV / audio-M4A family), MKV / WEBM via the
  `1A 45 DF A3` EBML magic (extension promotes MKV → WEBM when the
  extension is `.webm`).
- `VideoAnalyzer` exported from `bayyinah.__all__`; registered in
  `default_registry()` with `supported_kinds = {VIDEO_MP4, VIDEO_MOV,
  VIDEO_WEBM, VIDEO_MKV}`, disjoint from every pre-Phase-23 analyzer,
  so PDF / text / JSON / image / DOCX / HTML / XLSX / PPTX / EML / CSV
  parity is preserved.

**Phase 24, AudioAnalyzer (MP3 / WAV / FLAC / M4A / OGG).** Al-Baqarah
2:93, *"They said: we hear and disobey."* Audio declares compliance at
the surface while the container's batin stems carry payloads the ear
cannot reach. Identity theft through voice cloning is tazwir and
iftira' (Al-Nisa 4:112). AudioAnalyzer follows the stem-extractor-and-
router pattern, mutagen extracts ID3 / Vorbis / iTunes metadata and
embedded pictures; stdlib `wave` + `struct` handle WAV PCM and FLAC
METADATA_BLOCK walking; text routes to `ZahirTextAnalyzer`, embedded
pictures route to `ImageAnalyzer`.

- 5 new `FileKind` values: `AUDIO_MP3`, `AUDIO_WAV`, `AUDIO_FLAC`,
  `AUDIO_M4A`, `AUDIO_OGG`.
- 9 new active mechanisms: `audio_stem_inventory`,
  `audio_metadata_identity_anomaly`, `audio_lyrics_prompt_injection`,
  `audio_metadata_injection`, `audio_embedded_payload`,
  `audio_lsb_stego_candidate`, `audio_high_entropy_metadata`,
  `audio_container_anomaly`, `audio_cross_stem_divergence`. Identity-
  anomaly ranks at the highest audio-family severity (0.40), Al-Nisa
  4:112 names fabricated speech attributed to a speaker as the gravest
  form of falsehood.
- 3 mechanisms reserved as future work (not registered, name-committed
  in `config.py` comments): `audio_signal_stem_separation`,
  `audio_deepfake_detection`, `audio_hidden_voice_command`. Each carries
  an explicit dependency note.
- 11 new audio fixtures (3 clean: MP3 / WAV / FLAC; 7 adversarial
  covering every deducting mechanism; 1 NULL-case fixture for the
  divergence detector's future-work status).
- `FileRouter` detects audio via ID3 / fLaC / OggS magic prefixes, WAV
  via RIFF/WAVE shape, MP3 via sync-frame, and promotes M4A / M4B
  ftyp-brands off the video path.
- `mutagen>=1.47` added as a required runtime dependency. Deliberation
  documented in `pyproject.toml`: mutagen is pure-Python, ~300 KB, and
  the canonical Python audio-metadata parser; AudioAnalyzer retains
  stdlib fallbacks for WAV / FLAC so coverage does not collapse if
  mutagen is ever swapped out.
- `AudioAnalyzer` exported from `bayyinah.__all__`; registered in
  `default_registry()`; disjoint from every pre-Phase-24 analyzer.

**Phase 25+, CrossModalCorrelationEngine (session 1).** Al-Baqarah
2:164, *"signs for a people who use reason."* No single stem reveals
the full picture; the signs appear when the separated elements are
read together. The engine consumes already-scanned `IntegrityReport`
objects and emits findings for cross-stem divergence that single-stem
analysis misses. It does not reparse files, does not duplicate
detection logic, does not mutate its input, and is idempotent.

- 2 new active mechanisms: `cross_stem_inventory` (always-on meta-
  finding that makes the parting visible; severity 0.00) and
  `cross_stem_undeclared_text` (fires when a subtitle or audio-lyric
  stem carries substantive findings AND the metadata stem is silent
  or its findings do not declare textual content via a narrow keyword
  check, caption / subtitle / lyric / transcript / dialog / narration
  / sdh / cc).
- 5 mechanisms reserved as future work (name-committed in `config.py`
  comments): `cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
  `embedded_media_recursive_scan`, `cross_stem_coordinated_concealment`,
  `cross_file_media_divergence`.
- 2 paired correlation fixtures (`correlation_aligned.mp4`, subtitle
  and metadata both active, metadata declares captions; rule stays
  silent, vs `correlation_undeclared.mp4`, subtitle loud, metadata
  silent; rule fires).
- `CrossModalCorrelationEngine` exported from `bayyinah.__all__`.
  **Not** wired into `ScanService.default_registry()` in session 1 ,
  opt-in invocation until the rule set stabilises. Callers explicitly
  run the engine over a scanned report and extend findings as needed.

### Changed

- **Registry growth** (all additive): 89 mechanisms at 1.0 → 108
  mechanisms at 1.1 (+8 video, +9 audio, +2 cross-stem). SEVERITY +
  TIER tables grew in lockstep.
- **Public surface** (additive-only): 54 exported symbols at 1.0 → 57
  at 1.1 (+VideoAnalyzer, +AudioAnalyzer, +CrossModalCorrelationEngine).
  Every v1.0 symbol remains exported; removal would fail CI.
- **Default registry** (additive): 13 analyzers at 1.0 → 15 at 1.1
  (+video, +audio registered at the tail after the FallbackAnalyzer).
- **Test suite** (additive): **1,435 passing tests** (verified 2026-04-24,
  10.07-second full-suite runtime), up from the 1.0 baseline. The
  Phase-0 PDF parity sweep continues to pass byte-identically across
  all 17 fixtures.
- **Dependencies**: `mutagen>=1.47` added. `pymupdf` and `pypdf` retain
  their v1.0 constraints.

### Preserved

- **Reference-module MD5s**. `bayyinah_v0.py` (`87ba2ea4…`) and
  `bayyinah_v0_1.py` (`035aa578…`) remain byte-identical to their 1.0
  bytes. The CI workflow continues to assert both.
- **Parity invariant**. `bayyinah.scan_pdf(f) == bayyinah_v0.scan_pdf(f)`
  for every Phase 0 PDF fixture, same findings, same score, same
  error string, same `scan_incomplete` flag.
- **CLI surface**. `bayyinah scan <file>` unchanged; `--json` / `--summary`
  / `--quiet` / exit-code contract (0 / 1 / 2) unchanged.
- **`scan_pdf` / `scan_file` / `format_text_report` / `plain_language_summary`
  entry points** unchanged in behaviour. The kwarg-compat shim for
  `ScanService.scan(pdf_path=…)` that shipped in 1.0 continues to emit
  its `DeprecationWarning` without changing behaviour.

### Documentation

- README.md: supported-formats table extended for video / audio;
  new cross-modal-correlation section.
- CONTRIBUTING.md: stem-extractor-and-router pattern documented as
  the convention for multi-stem format analyzers.

### Known gaps (reserved work)

The following mechanism names are committed in `config.py` comments so
later sessions can register them without name collision, but no
detector fires them in v1.1:

- `video_cross_stem_divergence`, the Phase 23 divergence detector.
- `audio_cross_stem_divergence`, the Phase 24 counterpart.
- `audio_signal_stem_separation` (neural source separation),
  `audio_deepfake_detection`, `audio_hidden_voice_command`, Phase 24
  future work.
- `cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
  `embedded_media_recursive_scan`,
  `cross_stem_coordinated_concealment`, `cross_file_media_divergence`
 , Phase 25+ future sessions.

The white paper and thesis paper updates for the v1.1 surface are
deferred to Phase 27.

### Research-program cross-references

Bayyinah v1.1 is the empirical foundation for three theoretical papers
in the broader research program:

- **Furqan** (Ashraf, Arfeen, et al., 2026), proposes a programming
  language whose seven compile-time primitives + `scan_incomplete`
  return type + Fatiha session protocol formalize the behavioural
  conventions observed in this codebase. Each primitive is mapped
  to its Bayyinah validation in `history/FURQAN_CORRESPONDENCE.md`.
- **Al-Khalifa** (Arfeen et al., 2026), applies Furqan's seven
  primitives as runtime constraints on autonomous agents. Theoretical;
  Bayyinah's own development discipline is cited as the existence
  proof that the architecture is implementable.
- **The Fatiha Construct** (Arfeen, Claude, 2026), the seven-step
  session protocol that produced every phase of Bayyinah's
  development. Published independently; the per-phase prompts in
  this program's history are the construct's empirical record.

The relationships are mapped in `history/RESEARCH_PROGRAM_STACK.md`,
which sites Bayyinah within the four-layer integrity stack alongside
the Munafiq Protocol (DOI 10.5281/zenodo.19677111), Bayyinah al-Khabir
(theoretical), and Computational Tawhid (ontological).

## [1.0.0]: 2026-04-23

First stable release. Phase 22, Final Release Packaging. Al-Baqarah
2:286: *"Rabbana la tu'akhidhna in nasina aw akhta'na"*, Our Lord, do
not impose blame upon us if we have forgotten or erred. The release
is the ring closed on the twenty-two-phase Al-Baqarah roadmap: the
scanner now holds one contract for twelve file formats, degrades
gracefully under configured ceilings, and never returns silent-clean
on a file it could not identify.

### Added

- **Release status**: PyPI classifier promoted from
  `Development Status :: 3 - Alpha` to
  `Development Status :: 5 - Production/Stable`.
- **GitHub Actions CI** (`.github/workflows/ci.yml`). Matrix across
  Python 3.10 / 3.11 / 3.12 / 3.13. Every push and PR installs the
  package with dev extras, regenerates the fixture corpus, runs the
  full pytest suite, and executes the PDF byte-identical parity sweep
  against `bayyinah_v0` plus the additive-only public-surface check.
- **`CONTRIBUTING.md`**. Six-step "adding a new format" guide,
  five-step workflow restated, ground rules (additive-only,
  ceilings-in-`ScanLimits`, no silent-clean on `UNKNOWN`, emit
  `scan_limited` rather than raise). The contract future contributors
  work to.
- **README.md**, quick-start examples, 12-format support table with
  per-format mechanisms, `ScanLimits` configuration table with
  defaults, fallback-witness explanation, architecture callout
  refreshed to 1.0.

### Supported formats (twelve)

One contract, `BaseAnalyzer.scan(path) -> IntegrityReport`, applied
uniformly across every format:

- **PDF** (`ZahirTextAnalyzer` + `BatinObjectAnalyzer`), text-layer
  zahir/batin (zero-width, TAG, bidi, homoglyphs, invisible render
  modes, microscopic fonts, white-on-white, overlapping text) +
  object-layer batin (JavaScript, OpenAction, additional actions,
  launch actions, embedded files, FileAttachment annotations,
  incremental updates, metadata anomalies, hidden OCGs, adversarial
  ToUnicode CMap).
- **DOCX** (`DocxAnalyzer`), tracked changes, comments, hidden text,
  OLE, external-target relationships.
- **HTML** (`HtmlAnalyzer`), CSS-hidden text, off-screen absolute
  positioning, `<script>` / `on*` handlers, data-URI payloads.
- **XLSX** (`XlsxAnalyzer`), hidden sheets / rows / columns,
  white-on-white cells, formula injection, external links.
- **PPTX** (`PptxAnalyzer`), hidden slides, off-canvas shapes,
  embedded OLE, speaker-notes payloads.
- **EML** (`EmlAnalyzer`), bodyless envelopes, mismatched
  `From` / `Return-Path`, suspicious attachments, nested
  `message/rfc822` recursion.
- **CSV** (`CsvAnalyzer`), formula injection prefixes
  (`=`, `+`, `-`, `@`, tab, CR), Unicode concealment in cells.
- **JSON** (`JsonAnalyzer`), prompt-injection strings, base64 blobs,
  zero-width / TAG characters in values.
- **Markdown / code / plain text** (`TextFileAnalyzer`), zero-width,
  TAG, bidi, homoglyphs, invisible HTML spans.
- **PNG / JPEG / GIF / BMP / TIFF / WebP** (`ImageAnalyzer`), LSB
  steganography, trailing payloads, EXIF anomalies, embedded text
  layers.
- **SVG** (`SvgAnalyzer`), `<script>` tags, `on*` handlers,
  external-ref `<use>`, foreign-object HTML, off-screen text.
- **Unknown** (`FallbackAnalyzer`, Phase 21), universal witness of
  last resort. Every file the router cannot classify surfaces as
  `unknown_format` with forensic metadata (magic-byte prefix,
  extension, size, head preview in hex + ASCII) and
  `scan_incomplete=True`. Closes the silent-clean failure mode.

### Production hardening (Phase 21, carried forward)

- **`ScanLimits`**, single declaration point for every capacity
  ceiling (`max_file_size_bytes`, `max_recursion_depth`,
  `max_csv_rows`, `max_field_length`, `max_eml_attachments`). Frozen
  dataclass; installed per-scan via a thread-local `limits_context`
  so concurrent scans with different limits do not clobber each other.
  Ceiling `0` opts out.
- **`scan_limited` finding** (tier 3, severity 0.0, non-deducting).
  Every analyzer that hits a ceiling emits one, sets
  `scan_incomplete=True`, and returns whatever findings it already
  gathered, graceful degradation under adversarial sizing.

### Preserved (Additive-Only Invariant)

`bayyinah_v0.py` and `bayyinah_v0_1.py` remain byte-identical to their
0.1.0 releases. Every public symbol introduced in the 0.2.x / 0.3.x
refactor series is append-only, no rename, no removal. PDF parity
against `bayyinah_v0` is byte-identical across every Phase 0 fixture
(clean, positive_combined, eight text-layer, seven object-layer) and
re-verified on every CI run.

### Tested against

1283 pytest cases across domain, infrastructure, analyzer, application,
fixture, and end-to-end integration suites. Byte-identical PDF parity
holds on 17 / 17 Phase 0 fixtures. Every adversarial fixture (PDF,
DOCX, HTML, XLSX, PPTX, EML, CSV, JSON, text, image, SVG) asserts its
exact declared mechanism set.

## [0.3.0]: 2026-04-22

Phase 21, Production Hardening. Al-Baqarah 2:286: *"Allah does not burden
a soul beyond its capacity."* The scanner must not burden itself beyond
its configured capacity.

### Added

- **Universal Fallback Analyzer** (`analyzers/fallback_analyzer.py`). Any
  file the `FileRouter` leaves unclassified as `FileKind.UNKNOWN` now
  surfaces one `unknown_format` finding (tier 3, non-deducting) carrying
  forensic metadata: declared extension, file size, magic-byte prefix
  (first 16 bytes, hex-encoded), head-preview in both hex and
  printable-ASCII (first 512 bytes). Scan is marked `scan_incomplete=True`
  so the 0.5 `SCAN_INCOMPLETE_CLAMP` applies. Closes the silent-clean
  failure mode: a file we could not identify no longer slips through as
  score 1.0 with zero findings. Al-Baqarah 2:143 applied to format
  classification.
- **Configurable safety limits** (`domain/config.py`, `ScanLimits`,
  `DEFAULT_LIMITS`, `limits_context`, `get_current_limits`,
  `set_current_limits`). Five frozen-dataclass ceilings declared once:
  - `max_file_size_bytes` (default 256 MB), `ScanService` pre-flight
    before any analyzer runs. Oversize files short-circuit with a single
    `scan_limited` finding.
  - `max_recursion_depth` (default 5), `EmlAnalyzer` nested-message
    recursion. Supersedes the prior hard-coded 3.
  - `max_csv_rows` (default 200 000), `CsvAnalyzer` row walk.
  - `max_field_length` (default 4 MiB), `CsvAnalyzer` per-cell Unicode
    concealment cut-off.
  - `max_eml_attachments` (default 64), `EmlAnalyzer` per-message cap.
  Limits flow into analyzers via a thread-local context manager so the
  `BaseAnalyzer.scan(pdf_path) -> IntegrityReport` contract is unchanged.
  Every analyzer that hits a ceiling emits a `scan_limited` finding
  (tier 3, severity 0.0, non-deducting), sets `scan_incomplete=True`, and
  returns whatever findings it already gathered, graceful degradation,
  never crashes.
- **New mechanisms**: `unknown_format`, `scan_limited`. Both are batin,
  tier 3, severity 0.00 (non-deducting; rely on `scan_incomplete` clamp).
- **Public API surface**: `bayyinah.FallbackAnalyzer`,
  `bayyinah.ScanLimits`, `bayyinah.DEFAULT_LIMITS`,
  `bayyinah.limits_context`, `bayyinah.get_current_limits`,
  `bayyinah.set_current_limits`, `bayyinah.default_registry`.
- **`ScanService(limits=ScanLimits(...))`**, per-service limit override.
  The limits are scoped to the duration of each `scan()` call via
  `limits_context`, so concurrent scans with different limits do not
  clobber each other.

### Preserved (Additive-Only Invariant)

- `bayyinah_v0.py` and `bayyinah_v0_1.py` unchanged. PDF parity
  byte-identical across every Phase 0 fixture. `FallbackAnalyzer` never
  fires on an identified format (`supported_kinds = {FileKind.UNKNOWN}`),
  and the per-format analyzers never see the `scan_limited` mechanism
  unless a caller explicitly tightens `ScanLimits` past the default.

## [0.2.0]: 2026-04-22

### Added

- **Public Python API** (`bayyinah/__init__.py`). `from bayyinah import
  scan_pdf` is now the canonical entry point. Re-exports the orchestrator,
  analyzers, formatters, and domain types.
- **CLI** (`cli/main.py`) with subcommand surface:
  `bayyinah scan <file> [--json | --summary | --quiet]`. Exit codes
  preserved byte-for-byte from v0/v0.1 (0 / 1 / 2 for clean / findings /
  error). `bayyinah --version` added.
- **Domain layer** (`domain/`). Pure data types and scoring primitives ,
  `Finding`, `IntegrityReport`, `compute_muwazana_score`, `tamyiz_verdict`,
  `apply_scan_incomplete_clamp`, `BayyinahError` hierarchy. No I/O, no
  parser dependencies.
- **Infrastructure layer** (`infrastructure/`). `PDFClient` wraps the
  pymupdf + pypdf handles with context-manager safety. `FileRouter`
  detects PDF / DOCX / HTML / JSON / image / code by magic bytes and
  extension, flags polyglot files. `TerminalReportFormatter`,
  `JsonReportFormatter`, `PlainLanguageFormatter`, all byte-identical to
  v0.1's inline `format_text_report` / `plain_language_summary`.
- **Analyzer layer** (`analyzers/`). `BaseAnalyzer` contract enforces a
  uniform per-analyzer `IntegrityReport` shape. `ZahirTextAnalyzer` and
  `BatinObjectAnalyzer` port every detection mechanism from v0.1.
  `AnalyzerRegistry` composes registered analyzers into one merged report
  with the `scan_incomplete` clamp applied post-merge.
- **Application layer** (`application/`). `ScanService` orchestrator:
  file-exists short-circuit → pymupdf preflight → dispatch to the
  registry. Byte-identical behaviour to `bayyinah_v0_1.scan_pdf` across
  every Phase 0 fixture.
- **Test corpus**. 500+ pytest cases across domain, infrastructure,
  analyzers, application, and integration suites. Every Phase 0 fixture
  is asserted for exact mechanism firings, score, error text, and
  scan_incomplete flag against both v0 and v0.1.

### Changed

- `[project.scripts] bayyinah` now points to `cli.main:main` (was
  `bayyinah_v0_1:main`). The `bayyinah_v0` and `bayyinah_v0_1` module-level
  `main` functions remain callable for downstream pins.

### Preserved (Additive-Only Invariant)

- `bayyinah_v0.py` and `bayyinah_v0_1.py` are unchanged. Both remain in
  the wheel as reference implementations. No line was added, removed, or
  modified in either file during the 0.2.0 refactor. Module mtimes
  verified after each phase.

### Architectural References

- [Munafiq Protocol, Detecting Performed Alignment in Artificial
  Systems](https://doi.org/10.5281/zenodo.19677111) (DOI:
  10.5281/zenodo.19677111). The scanner's scoring model (APS-continuous,
  three validity tiers, tamyiz verdict) is a direct port of §9's
  input-layer framing from LLMs to files.
- Internal roadmap: `NAMING.md` captures the Al-Baqarah phase mapping.

## [0.1.0]: 2026-04-22

### Added

- `bayyinah_v0.py`, the original monolithic scanner. Detects:
  - Text-layer mechanisms: `zero_width_chars`, `tag_chars`, `bidi_control`,
    `homoglyph`, `invisible_render_mode`, `microscopic_font`,
    `white_on_white_text`, `overlapping_text`.
  - Object-layer mechanisms: `javascript`, `openaction`,
    `additional_actions`, `launch_action`, `embedded_file`,
    `file_attachment_annot`, `incremental_update`, `metadata_anomaly`,
    `hidden_ocg`, `tounicode_anomaly`.
- `bayyinah_v0_1.py`, fat-split intermediate introducing `PDFContext`,
  `BaseAnalyzer`, `TextLayerAnalyzer`, `ObjectLayerAnalyzer`,
  `ScanService`. Byte-identical output to v0 across the fixture corpus.
- Phase 0 fixture corpus (`tests/fixtures/`): `clean.pdf`,
  `positive_combined.pdf`, 8 text-layer fixtures, 7 object-layer fixtures.
  Each fires exactly its declared mechanism set under v0.

---

**License:** Apache-2.0. See `LICENSE` for the full text. Anthropic's
usage-policies apply when running Bayyinah as an agent tool; see
project README.
