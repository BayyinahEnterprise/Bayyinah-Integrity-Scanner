# Contributing to Bayyinah

> *Wa laa talbisul-haqqa bil-baatili wa taktumul-haqqa wa antum ta'lamoon.*
>
> "And do not mix the truth with falsehood or conceal the truth while
> you know." Al-Baqarah 2:42

Bayyinah's central diagnostic question, *does what the file displays
match what the file contains?*, is applied recursively to the codebase
itself. Every change must be honest about what it did and did not do.
This guide describes how to make contributions that preserve that
discipline.

## Ground rules

1. **Additive-only public surface.** `bayyinah_v0.py`,
   `bayyinah_v0_1.py`, and the `bayyinah` package's `__all__` are
   append-only. New symbols, never renames or removals. The reference
   implementations ship in the wheel; their byte-for-byte PDF parity
   with the modular scanner is asserted on every fixture, in every
   release.
2. **Five-step workflow, no skipping.** Each change follows the same
   sequence: (1) understand the requirement and review prior work,
   (2) write the change, (3) write the tests, (4) run the full suite,
   (5) verify additive-only public surface and full-format parity.
   Skipping a step is how regressions enter. The revelation is
   gradual because haste is how hidden defects ship.
3. **Every ceiling lives in `ScanLimits`.** If your change needs a
   capacity ceiling (recursion depth, row count, attachment cap, …),
   declare it as a field on the frozen `ScanLimits` dataclass in
   `domain/config.py` and read it via `get_current_limits()` inside
   the analyzer. No hard-coded magic numbers inside `_walk_*` or
   `_scan_*` paths, the scanner's ceilings must all be visible in one
   place, so a reader can see what it cost the scanner to scan a file.
4. **Emit `scan_limited`, do not raise.** When an analyzer hits a
   ceiling, emit a `scan_limited` finding (tier 3, severity 0.0,
   non-deducting), set `scan_incomplete=True`, and return whatever
   findings it already gathered. The scanner degrades gracefully; it
   does not crash on pathologically-large inputs.
5. **No silent-clean on unknown.** A file the `FileRouter` classifies
   as `FileKind.UNKNOWN` must reach the `FallbackAnalyzer` and surface
   an `unknown_format` finding. If you add a new `FileKind`, make sure
   `supported_kinds` on the existing analyzers excludes it until its
   format-specific analyzer is registered, otherwise you will regress
   the disjoint-dispatch guarantee that keeps PDF parity intact.

## Development setup

```bash
git clone https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner.git
cd bayyinah
pip install -e '.[dev]'
python -m tests.make_test_documents   # one-time fixture generation
pytest                                 # full suite should go green
```

Runtime dependencies: `pymupdf>=1.24`, `pypdf>=4.0`. Python 3.10 or newer.

## Adding support for a new format

The scanner's format support follows the same shape for every format.
The example below uses a hypothetical `RTFAnalyzer`, but the same six
steps apply to any new format.

### Step 1: Register the file kind

Edit `infrastructure/file_router.py`:

```python
class FileKind(Enum):
    ...
    RTF = "rtf"
```

Add magic-byte and extension detection to `FileRouter._detect`. RTF
starts with `{\rtf`, extension `.rtf`.

### Step 2: Register the mechanisms

Edit `domain/config.py`. For each detector your analyzer will emit,
add a row to the `MECHANISMS` tuple:

```python
Mechanism(
    name="rtf_embedded_object",
    tier=2,
    severity=0.30,
    source_layer="batin",
    description="OLE object embedded inside an RTF stream",
),
```

Register the mechanism names in `domain/mechanisms.py` (if the project
tracks them there) and update any downstream taxonomies.

### Step 3: Write the analyzer

Under `analyzers/`, add `rtf_analyzer.py`:

```python
from pathlib import Path
from typing import ClassVar

from analyzers.base import BaseAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
    get_current_limits,
)
from infrastructure.file_router import FileKind


class RtfAnalyzer(BaseAnalyzer):
    name: ClassVar[str] = "rtf"
    error_prefix: ClassVar[str] = "RTF scan error"
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.RTF})

    def scan(self, pdf_path: Path) -> IntegrityReport:
        path = Path(pdf_path)
        if not path.exists():
            return self._scan_error_report(
                path, f"File not found: {path}"
            )

        limits = get_current_limits()
        findings: list[Finding] = []
        scan_incomplete = False

        # Your detection pass here. When you hit a ceiling:
        #
        #   findings.append(Finding(
        #       mechanism="scan_limited",
        #       tier=3,
        #       confidence=1.0,
        #       description=(
        #           f"RTF control-word walk halted at "
        #           f"max_field_length={limits.max_field_length}"
        #       ),
        #       ...
        #       source_layer=self.source_layer,
        #   ))
        #   scan_incomplete = True
        #   break

        return IntegrityReport(
            file_path=str(path),
            integrity_score=apply_scan_incomplete_clamp(
                compute_muwazana_score(findings),
                scan_incomplete=scan_incomplete,
            ),
            findings=findings,
            error=None,
            scan_incomplete=scan_incomplete,
        )
```

Key rules the analyzer must follow:

- `supported_kinds` must name **only** the new `FileKind`. The
  registry's filter is how every other analyzer stays disjoint from
  yours; a broader `supported_kinds` set regresses PDF / DOCX / every
  earlier format's parity.
- Read ceilings from `get_current_limits()` inside `scan()`, not from
  module-level constants. The limits context is per-scan.
- Missing files route through `self._scan_error_report(...)`, consistent
  with every other analyzer.
- Apply `apply_scan_incomplete_clamp` to the score whenever
  `scan_incomplete=True`.

### Step 4: Export the analyzer

Edit `analyzers/__init__.py` to add `RtfAnalyzer` to the `__all__` and
the imports. Edit `bayyinah/__init__.py` to re-export it from the public
API. Add it to the `default_registry` so `ScanService()` picks it up
out of the box.

### Step 5: Fixtures + tests

1. Add fixtures under `tests/fixtures/rtf/`, at minimum one clean RTF
   and one RTF per adversarial mechanism. Each fixture must be
   deterministically generated so CI can rebuild it; extend
   `tests/make_test_documents.py` with a generator.
2. Write `tests/analyzers/test_rtf_analyzer.py` mirroring the shape of
   the existing `test_*_analyzer.py` suites: contract tests
   (`is_base_analyzer_subclass`, class attributes, `supported_kinds`),
   happy-path detections, missing-file, oversize-file → `scan_limited`,
   and the scan-incomplete clamp.
3. Write `tests/test_rtf_fixtures.py` walking every fixture and
   asserting exactly its declared mechanism set + score.
4. Extend `tests/test_integration.py` with an end-to-end case that
   routes an RTF through `ScanService` and asserts the full
   `IntegrityReport`.

### Step 6: Verify additive-only + full parity

From the repo root:

```bash
pytest                                    # full suite, must be green

python - <<'PY'                           # PDF parity against v0
import bayyinah, bayyinah_v0
from pathlib import Path
mismatches = []
for f in sorted(Path("tests/fixtures").rglob("*.pdf")):
    r_v0 = bayyinah_v0.scan_pdf(f)
    r_new = bayyinah.scan_pdf(f)
    if (sorted(x.mechanism for x in r_v0.findings)
            != sorted(x.mechanism for x in r_new.findings)
            or abs(r_v0.integrity_score - r_new.integrity_score) > 1e-6
            or r_v0.error != r_new.error):
        mismatches.append(f.name)
assert not mismatches, f"PDF parity broken: {mismatches}"
print("PDF parity: OK")
PY

python - <<'PY'                           # additive-only surface check
import bayyinah
for sym in ("scan_pdf", "ScanService", "ScanLimits", "DEFAULT_LIMITS",
            "FallbackAnalyzer", "BaseAnalyzer", "Finding",
            "IntegrityReport"):
    assert sym in bayyinah.__all__, sym
print("Surface check: OK")
PY
```

Close the ring by walking the Phase 0 fixture corpus against both
`bayyinah_v0` and `bayyinah_v0_1`. A phase does not close without the
two witnesses. (Al-Baqarah 2:282, *two witnesses*.)

Update `CHANGELOG.md` with a new entry under the current version;
describe what was added, what ceilings were registered, and restate
the additive-only invariant that was preserved.

## Writing tests

- **Parametrise**, do not copy-paste, where the behaviour is uniform.
- **Contract tests first** (subclass check, class attributes,
  `supported_kinds`), these are the cheapest to write and the ones
  that catch refactor regressions fastest.
- **Missing-file + oversized-file** cases for every analyzer. The
  fallback analyzer's tests are the reference; copy their shape.
- **Fixture suites assert exact mechanism firings.** Never
  `assert "zero_width_chars" in mechanisms`, write
  `assert mechanisms == ["zero_width_chars"]`. If the detector fires
  anything else, we want to know.

## Scoring and the clamp

- Findings contribute a continuous deduction `severity × confidence`
  to the score; the score saturates at 0.0.
- `scan_incomplete=True` clamps the final score to 0.5
  (`SCAN_INCOMPLETE_CLAMP`). Always apply the clamp via
  `apply_scan_incomplete_clamp`, never set the score directly.
- The score is never the verdict. The scanner surfaces mechanisms;
  the reader performs the recognition.

## Commit / PR etiquette

- One phase per PR when possible. Phases are the unit of review.
- The PR description restates the guiding ayat, what was added, what
  was preserved, and the verification commands you ran. If you ran
  the integration parity check and it passed, say so. If you could
  not run it, say *why*, honesty about what was not verified is the
  2:42 discipline applied to review.
- Never squash away the per-step commits inside a phase. Reviewers
  need to see the five steps land in order.

## The stem-extractor-and-router pattern (for multi-stem formats)

Phases 23 (video) and 24 (audio) established a convention for
analyzers that handle container formats carrying multiple
semantically-distinct stems, subtitle tracks, metadata atoms,
embedded pictures, PCM sample data, lyric frames. New format
analyzers that fit this shape should follow the same pattern.

The convention has three load-bearing rules (Al-Baqarah 2:50, the
parting):

1. **Decompose via the container's natural multiplexing.** Do not
   invent stems the format does not already separate. MP4 separates
   subtitle tracks from metadata atoms from cover-art images; that is
   the parting. MP3 separates ID3 frames from APIC pictures from
   frame-synchronised audio; that is the parting. Implement the box
   walk / chunk iteration / frame sync at the container layer and
   surface each stem to the per-stem detectors.

2. **Route each stem to the analyzer that already knows its
   material** (Al-Baqarah 2:143, the middle community). Subtitle
   text, lyric text, and metadata text all route to
   `ZahirTextAnalyzer._check_unicode` for codepoint concealment.
   Embedded pictures route to `ImageAnalyzer().scan` and the
   image-layer findings re-emerge under a container-specific
   mechanism name. Do not reimplement what an existing analyzer
   already does, compose, do not duplicate.

3. **Emit an always-on `*_inventory` meta-finding** that enumerates
   what the decompose pass found (`video_stream_inventory`,
   `audio_stem_inventory`, `cross_stem_inventory`). The inventory is
   informational (severity 0.0, tier 3) and makes the parting
   visible to the reader. Without it, a clean file produces zero
   findings, and the analyst cannot tell whether the scanner
   inspected the stems or skipped them.

### Dependency policy for new format analyzers

Default to stdlib-only parsing. The pyproject.toml's dependency
comment block documents the rationale: adding a full-format library
(python-docx, openpyxl) pulls in a parser surface an adversarial
document can target, and defeats the point of a concealment
detector whose job is to inspect raw structural bytes.

Two external-library exceptions exist today, pymupdf/pypdf for
PDF and mutagen for audio. A third would require the same kind of
deliberation block in `pyproject.toml` and the same kind of
stdlib-fallback commitment (mutagen's presence does not collapse
WAV / FLAC coverage; AudioAnalyzer retains stdlib paths for those).

## Future-work reserved names in `domain/config.py`

When a mechanism is named in a session but its detector is not
implemented in that session, the name gets committed as a reserved
name in a `config.py` comment, not as a registered entry in
`ZAHIR_MECHANISMS` / `BATIN_MECHANISMS`. The commitment is load-
bearing: a later session implementing the detector must use the
reserved name, which prevents silent namespace collisions. Each
reserved name carries a dependency note, what the detector
requires before registration makes sense. Phase 24 reserved three
audio mechanism names this way (`audio_signal_stem_separation`,
`audio_deepfake_detection`, `audio_hidden_voice_command`); Phase
25+ reserved five cross-modal names. The registry is an isnad, the
chain of names persists.

## The post-processor pattern (Phase 25+)

Some v1.1 capabilities are **not** per-file analyzers but
post-processors that consume already-scanned `IntegrityReport`
objects. `CrossModalCorrelationEngine` is the first example.
Post-processors differ from `BaseAnalyzer` subclasses in three
ways:

* They do not inherit from `BaseAnalyzer` (the registry would
  otherwise treat them as per-`FileKind` analyzers and misfire).
* They do not reparse files, they read findings the upstream
  analyzers already emitted.
* They are idempotent and do not mutate their input reports.

When adding a new post-processor, register it in
`analyzers/__init__.py` and `bayyinah/__init__.py` but **do not**
register it in `application.default_registry()`. Opt-in invocation
is the convention until the post-processor's rule set has
stabilised, this keeps existing per-fixture mechanism expectations
intact while the logic calibrates.

## Architectural references

- [Munafiq Protocol, Detecting Performed Alignment in Artificial
  Systems](https://doi.org/10.5281/zenodo.19677111) (DOI:
  10.5281/zenodo.19677111). §9 is the input-layer framing this scanner
  ports from LLMs to files.
- `CHANGELOG.md`, the canonical record of what each version added and
  what was preserved.
- `README.md`, usage, supported formats, configuration.

*Bayyinah* (بَيِّنَة), "clear evidence." Contribute in that spirit.
