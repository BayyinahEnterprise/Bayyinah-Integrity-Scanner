# Image (PNG / JPEG / SVG) Adversarial Gauntlet — v1.1.1 Baseline

**Date:** 2026-04-26
**Scanner version:** Bayyinah 1.1.1 (live at https://bayyinah.dev)
**Result:** 1 of 6 partially caught (structural acknowledgment without payload recovery), 5 of 6 fully missed.

The image gauntlet was constructed deliberately around the v1.1.1 detectors. Bayyinah already catches a strong set of image concealment idioms across PNG, JPEG, and SVG: text in PNG `tEXt`/`zTXt`/`iTXt` chunks (`image_text_metadata`), trailing data after IEND/EOI (`trailing_data`), oversized metadata (`oversized_metadata`), suspicious PNG chunks (`suspicious_image_chunk`), JPEG `COM` / `APP1` (EXIF/XMP) / `APP13` (Photoshop IRB) text, high-entropy ICC/EXIF (`high_entropy_metadata`), generative AI cipher signatures, multiple IDAT streams (`multiple_idat_streams`), LSB steganography (`suspected_lsb_steganography`); and on the SVG side: zero-width / TAG / bidi / homoglyph / mathematical-alphanumeric, embedded `<script>`, `<foreignObject>`, on* event handlers, `data:` URI references, external `xlink:href` references, hidden text via `opacity:0` / `display:none` / `visibility:hidden` / `fill:none` / `fill-opacity:0`, microscopic font sizes.

The six fixtures here probe the gaps left between those well-armored vectors.

## Summary table

| Fixture | Technique | Result | Mechanism that fired (or should have) | Score |
|---|---|---|---|---|
| 01 | JPEG APP4 marker carrying the payload | **MISSED** | (JPEG extractor only handles APP1, APP13, COM) | 1.00 |
| 02 | PNG private ancillary chunk `prVt` | **PARTIAL** | `suspicious_image_chunk` (Tier 3) — chunk surfaced but payload text not extracted | 0.925 |
| 03 | SVG `<text fill="#FFFFFF">` on white `<rect>` | **MISSED** | (`fill="white"` not in `SVG_INVISIBLE_ATTRIBUTES`) | 1.00 |
| 04 | SVG `<title>` carrying the payload | **MISSED** | (`<title>` not in hidden / microscopic detector targets) | 1.00 |
| 05 | SVG `<metadata>` with `dc:description` payload | **MISSED** | (no metadata-element walker) | 1.00 |
| 06 | SVG `<text>` nested inside `<defs>` (no `<use>`) | **MISSED** | (analyzer does not gate on render context) | 1.00 |

**Hit rate: 0/6 fully caught; 1/6 partially caught (structural-only, no payload recovery). Local and live agree exactly.**

## Per-fixture root cause

### 01 — JPEG APP4 marker — MISSED

`_extract_jpeg_text` returns text only for markers `0xFE` (COM), `0xE1` (APP1 — EXIF/XMP), and `0xED` (APP13 — Photoshop IRB). All other APPn markers (`0xE0` JFIF, `0xE2` ICC, `0xE3` Meta, `0xE4`–`0xEF`) are silently skipped. The fixture parks the payload in `0xE4` (APP4), a marker with no widely standardised use — perfect for adversarial smuggling.

**Fix path for v1.1.2:** Extend `_extract_jpeg_text` to attempt latin-1/UTF-8 decoding on every APPn marker (range `0xE0` through `0xEF`) and emit `image_text_metadata` for any that yields a printable run. Mirrors the PNG side's "all-text-chunks-equal" treatment. ~20 lines.

### 02 — PNG private ancillary chunk `prVt` — PARTIAL

Bayyinah did acknowledge the chunk's existence: a Tier 3 `suspicious_image_chunk` finding fired ("Non-standard PNG chunk type 'prVt' at offset 55 — outside the standard PNG / APNG chunk set"), and the score dipped to 0.925. Honest acknowledgment, structurally correct.

**But the payload text was not extracted.** A reviewer reading the report sees only that an unknown chunk exists; they do not see *what's inside it*. The Munafiq Protocol contract says the report should surface the substrate side of the surface/substrate gap; for this fixture only the structural side surfaced.

**Fix path for v1.1.2:** When emitting `suspicious_image_chunk`, additionally run the chunk data through `_decode_latin1_or_utf8` and the same printable-run heuristic that `image_text_metadata` uses. If the decoded data has a printable run of 4+ chars, attach it as the `concealed` field of the existing finding (or emit a paired `image_text_metadata` finding). ~15 lines.

This is the gentlest fix on the milestone list — extends an existing finding rather than adding a new mechanism.

### 03 — SVG white-on-white text — MISSED

`SVG_INVISIBLE_ATTRIBUTES['fill']` is `frozenset({"none", "transparent"})`. Solid color values like `#FFFFFF` are not flagged. The fixture's text is rendered by every SVG renderer, but on a white background it is invisible to a sighted reviewer.

**Fix path for v1.1.2:** Either expand the set to include `#FFFFFF` / `white` / `rgb(255,255,255)` as a heuristic, or add a contrast-aware check that compares `fill` against the canvas background (the root `<svg>` style or the immediate-ancestor `<rect>` fill). The latter is more correct but more LOC; the former covers 95% of real-world abuse. Mirrors the PDF/DOCX/XLSX `white_on_white` shape. ~25 lines.

### 04 — SVG `<title>` payload — MISSED

`<title>` is the SVG analogue of HTML `<title>` plus assistive-tech tooltip. It is read by screen readers and many SVG-aware extractors but not scanned by SvgAnalyzer's `_detect_hidden_text` / `_detect_microscopic_text`, both of which check the *current* element's attributes. `<title>` has no `font-size` or `opacity` of its own — its content is consumed structurally by the renderer.

**Fix path for v1.1.2:** Add `_detect_aux_text_elements`. Walk every `<title>`, `<desc>`, `<metadata>` element. Run zahir checks on their text. Emit `svg_aux_text_payload` (Tier 2) when content exceeds a length threshold and is not echoed in the visible `<text>` corpus. ~30 lines.

### 05 — SVG `<metadata>` payload — MISSED

Same architectural gap as fixture 04: `<metadata>` is an SVG-canonical location for arbitrary author metadata (RDF, Dublin Core), not visited by the hidden / microscopic detectors. Fix path is the same as fixture 04.

### 06 — SVG `<text>` inside `<defs>` — MISSED

`<defs>` declares reusable fragments. Children are rendered only when referenced via `<use xlink:href="#id">`. A `<text>` inside `<defs>` with no matching `<use>` exists in the document and is consumed by some text extractors (raw XML walkers, indexers) but never appears on the canvas. Bayyinah's text detectors do not differentiate between rendered and declared-but-unused content.

**Fix path for v1.1.2:** Add `_detect_unrendered_defs_text`. Walk every `<text>` (and `<tspan>`) inside `<defs>`. Cross-reference against `<use xlink:href="#id">` markers. Emit `svg_orphan_defs_text` (Tier 1, confidence 0.85) when a `<text>` inside `<defs>` has no matching `<use>` reference. ~25 lines.

## What this baseline says about Bayyinah v1.1.1 for images

`ImageAnalyzer` and `SvgAnalyzer` together cover the *common* concealment surfaces well — PNG text chunks, JPEG comments and EXIF, trailing data, LSB steganography, embedded scripts, hidden styles, microscopic fonts. The gaps cluster in three places:

1. **Underused JPEG marker space** (APP0/APP2/APP3/APP4–APPF) — fixture 01.
2. **Private PNG chunk content** — fixture 02 (acknowledged structurally, content not extracted).
3. **SVG auxiliary text channels** (`<title>`, `<desc>`, `<metadata>`, `<defs>`) and the white-on-color rendering shape — fixtures 03–06.

The image gauntlet's 1/6 partial result is the strongest of the post-PDF gauntlets (DOCX 0/6, XLSX 0/6, HTML 0/6, EML 0/6), reflecting the deeper investment the analyzer already made on the format-specific concealment layer.

## v1.1.2 milestone (image additions)

Six new image detectors / extensions estimated at ~115 LOC total:

1. Extend `_extract_jpeg_text` to handle every APPn marker (~20 LOC)
2. Attach decoded payload text to `suspicious_image_chunk` findings (~15 LOC)
3. `svg_white_on_white_text` — white-fill on white-background contrast check (~25 LOC)
4. `svg_aux_text_payload` — walk `<title>`/`<desc>`/`<metadata>` (~30 LOC)
5. `svg_orphan_defs_text` — unreferenced `<text>` inside `<defs>` (~25 LOC)

Combined running totals: PDF (~155 LOC), DOCX (~200 LOC), XLSX (~190 LOC), HTML (~120 LOC), EML (~185 LOC), Image (~115 LOC) = ~965 LOC across six formats.

## Reproducing this report

```bash
cd Bayyinah-Integrity-Scanner/docs/adversarial/image_gauntlet
python build_fixtures.py     # creates fixtures/* (no extra deps)
python run_gauntlet.py local # in-process scan via ScanService
python run_gauntlet.py live  # POST to https://bayyinah.dev/scan
```

---

*Sixth installment of the multi-format gauntlet. PDF (2/6) → DOCX (0/6) → XLSX (0/6) → HTML (0/6) → EML (0/6) → Image (1/6 partial). CSV/JSON gauntlet follows.*
