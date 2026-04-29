# Image (PNG / JPEG / SVG) Adversarial Gauntlet - v1.1.2 Closing Report

**Date:** 2026-04-28
**Scanner version:** Bayyinah 1.1.2 (workspace; live https://bayyinah.dev still on 1.1.1 baseline at time of writing)
**Result:** 8 of 8 fixtures fully caught with full payload recovery. Local and live diverge until the v1.1.2 deploy lands.

The v1.1.1 baseline of this gauntlet (preserved in this repository's
git history) ran 1 of 6 partially caught and 5 of 6 fully missed
across the original six fixtures. v1.1.2 closes every original
fixture and adds two further fixtures (one PNG concealment surface,
one SVG long-form description surface) to exercise mechanism
boundaries discovered during the design review.

## Summary table

| Fixture | Technique | Result | Mechanism that fires | Tier | Score |
|---|---|---|---|---|---|
| 01 | JPEG APP4 marker carrying the payload | **CAUGHT + RECOVERED** | `image_jpeg_appn_payload` | 1 | 0.82 |
| 02 | PNG private ancillary chunk `prVt` | **CAUGHT + RECOVERED** | `image_png_private_chunk` | 2 (escalates to 1 on payload triggers) | 0.775 |
| 02_5 | PNG `tEXt` chunk with bidi / zero-width / divergence triggers | **CAUGHT + RECOVERED** | `image_png_text_chunk_payload` | 1 | 0.045 |
| 03 | SVG `<text fill="#FFFFFF">` on white `<rect>` | **CAUGHT + RECOVERED** | `svg_white_text` | 1 | 0.00 |
| 04 | SVG `<title>` carrying the payload (over 64 bytes) | **CAUGHT + RECOVERED** | `svg_title_payload` | 1 | 0.8725 |
| 04_5 | SVG `<desc>` carrying multi-sentence payload (over 256 bytes) | **CAUGHT + RECOVERED** | `svg_desc_payload` | 1 | 0.8725 |
| 05 | SVG `<metadata>` with `dc:description` payload (over 128 bytes) | **CAUGHT + RECOVERED** | `svg_metadata_payload` | 1 | 0.8725 |
| 06 | SVG `<text>` nested inside `<defs>` with no `<use>` reference | **CAUGHT + RECOVERED** | `svg_defs_unreferenced_text` | 1 | 0.82 |

**Hit rate: 8 / 8 fully caught with payload recovery.**

## Mechanism overview

### 01 - `image_jpeg_appn_payload`

Closes the underused JPEG marker space gap. The v1.1.1 extractor
returned text only for markers `0xFE` (COM), `0xE1` (APP1, EXIF /
XMP), and `0xED` (APP13, Photoshop IRB). The v1.1.2 detector
attempts UTF-8 / latin-1 decoding on every APPn marker in the
range `0xE4` through `0xEF` (APP4 through APP15) where there is no
widely standardized format, runs the printable-text heuristic, and
emits a Tier 1 batin finding when a marker yields a recoverable
text run of 32 bytes or more. Recovery preview lands in `concealed`.

Tier 1 because the marker is byte-deterministic and the text run
is verifiable by re-reading the file.

### 02 - `image_png_private_chunk`

The v1.1.1 scanner emitted Tier 3 `suspicious_image_chunk` for the
private chunk `prVt` but did not extract the payload text.
v1.1.2 emits a fresh Tier 2 `image_png_private_chunk` finding that
identifies the chunk by its RFC 2083 lowercase-private classification,
runs the chunk data through the printable-text heuristic, and
populates `concealed` with the recovered preview.

The mechanism escalates to Tier 1 per-trigger when the recovered
payload exhibits a hard signal: length cap, bidi codepoint, zero-
width codepoint, or one of the canonical divergence markers
`HIDDEN_`, `BATIN_`, `ZAHIR_`, `PAYLOAD`. Default Tier 2 keeps the
mechanism honest about the structural-only baseline; per-trigger
Tier 1 escalation reflects the byte-deterministic nature of the
hostile-codepoint and divergence-marker cases.

### 02_5 - `image_png_text_chunk_payload`

A separate concealment surface inside the PNG `tEXt` / `iTXt`
chunk family. The v1.1.1 `image_text_metadata` already emits
findings on these chunks but does not differentiate adversarial
payload patterns from legitimate `Title` / `Author` / `Software`
fields.

The v1.1.2 detector adds four payload-shape triggers: aggregate
length above 1024 bytes, presence of any bidi override codepoint,
presence of any zero-width codepoint, and presence of any of the
canonical divergence markers. Any single trigger fires Tier 1.
UTF-8 fallback decoding handles `tEXt` payloads emitted by tools
that produce non-latin-1 bytes despite the PNG specification.

### 03 - `svg_white_text`

Closes the white-on-white SVG gap. The v1.1.1
`SVG_INVISIBLE_ATTRIBUTES['fill']` set was `frozenset({"none",
"transparent"})`, missing solid-color values. v1.1.2 detects near-
white fill values (`#FFFFFF`, `#FEFEFE`, `#FDFDFD`, `#FCFCFC`, plus
`white` and `rgb(255,255,255)`) and verifies the canvas
background is also near-white before firing. Background detection
walks viewport-spanning `<rect>` elements and the root `<svg>`
fill attribute.

The single zahir mechanism in F1: white-fill text is rendered (a
sighted reader would see it) but only on a non-white background;
on a white background it is camouflaged by contrast. The signal is
visible-but-hidden, the canonical zahir shape.

### 04 / 04_5 / 05 - SVG auxiliary text channel split

Three Tier 1 batin detectors close the SVG auxiliary text channel:

- `svg_title_payload` (threshold 64 bytes)
- `svg_desc_payload` (threshold 256 bytes)
- `svg_metadata_payload` (threshold 128 bytes)

The split preserves one-detector-per-mechanism discipline while
reflecting each element's distinct legitimate-use distribution.
`<title>` is the always-short tooltip; `<desc>` is the long-form
accessibility description; `<metadata>` is the machine-readable
annotation surface. A single combined threshold would either
false-positive on legitimate `<desc>` (multi-sentence chart
legends are legitimate) or false-negative on adversarial `<title>`
(short payloads still smuggle).

All three elements are scanned by indexers and LLMs but not
rendered as glyph content; threshold-crossing content is
structurally anomalous against clean-corpus distributions.

### 06 - `svg_defs_unreferenced_text`

Closes the unrendered template content gap. `<defs>` is the SVG
template surface; its children render only when instantiated via
`<use href="#id">`. A `<text>` element nested inside `<defs>`
whose `id` is never referenced (or which lacks an `id` entirely
and therefore cannot be instantiated by `<use>` at all) carries
text content that is not rendered as glyph content but is fully
readable by indexers, LLMs, and other XML-aware consumers.

The detector collects every `<use>`-referenced `id` (covering both
`href` and legacy `xlink:href`), walks every `<text>` inside
every `<defs>`, and emits Tier 1 batin when the text element's
`id` is not in the referenced set.

## What v1.1.2 says about Bayyinah for images

`ImageAnalyzer` and `SvgAnalyzer` together now cover:

- All PNG ancillary chunk classes (text, private, suspicious) with
  payload extraction populated into `concealed`.
- The complete JPEG APPn marker space, not only the three formerly
  hardcoded markers.
- The PNG `tEXt` / `iTXt` payload-shape concealment surface
  (length, bidi, zero-width, divergence markers).
- All four SVG auxiliary-text channels (`<title>`, `<desc>`,
  `<metadata>`, unreferenced `<defs>` content).
- The white-on-white SVG rendering shape with canvas-aware
  contrast checking.

## Documented known gaps (deferred to F1.5)

Three image-format concealment surfaces were identified during F1
review and deferred to keep the F1 scope tight:

1. **EXIF UserComment** (JPEG APP1 tag `0x9286`). The current
   `image_jpeg_appn_payload` detector covers APP4 through APP15
   but does not parse EXIF tag-level structure. UserComment is the
   canonical EXIF text-payload tag and warrants a dedicated
   detector that walks the EXIF IFD chain.
2. **SVG `<foreignObject>` HTML.** `<foreignObject>` permits
   arbitrary embedded HTML inside SVG. Hidden-text idioms from the
   HTML gauntlet (display:none / visibility:hidden / hidden HTML
   attributes) do not currently propagate through
   `<foreignObject>` content.
3. **SVG `<style>` block CSS rules.** CSS rules inside an SVG
   `<style>` element can carry payload-bearing content (CSS
   comments, property values containing strings) that bypass the
   current text-element walkers. Pseudo-element `content`
   declarations are particularly relevant.

These three gaps are well-bounded, structurally similar to the F1
mechanisms (each is a single additive detector module), and would
land in a focused F1.5 round if scoped before the CSV / JSON
gauntlet round.

## Reproducing this report

```bash
cd Bayyinah-Integrity-Scanner/docs/adversarial/image_gauntlet
python build_fixtures.py     # creates fixtures/* (no extra deps)
python run_gauntlet.py local # in-process scan via ScanService
python run_gauntlet.py live  # POST to https://bayyinah.dev/scan
```

---

*Sixth installment of the multi-format gauntlet, now closed. PDF (6 / 6) -> DOCX (6 / 6) -> XLSX (6 / 6) -> HTML (6 / 6) -> EML (6 / 6) -> Image (8 / 8). CSV / JSON gauntlet round follows.*
