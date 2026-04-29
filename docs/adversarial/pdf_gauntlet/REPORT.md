> **Update 2026-04-28 (v1.1.2):** This PDF gauntlet now closes at **6/6 catch with full payload recovery**. The v1.1.1 baseline below is preserved as the historical record of why each mechanism was added. The scanner currently in production at https://bayyinah.dev catches every PDF fixture in this directory. See the v1.1.2 CHANGELOG entry for the full mechanism list and `tests/analyzers/test_pdf_v1_1_2_payloads.py` for the per-mechanism unit tests.

---

# PDF Hidden-Text Gauntlet: v1.1.1 Baseline

**Date:** 2026-04-26
**Scanner version:** Bayyinah 1.1.1 (live at https://bayyinah.dev)
**Triggered by:** External adversarial probe by an independent software engineer ("I hid some text in a second PDF and it gave me the same score")
**Result:** 2 of 6 techniques caught. 4 misses documented as v1.1.2 targets.

This is an honest baseline. It is published so the next reviewer can verify each claim and so the gaps are visible to anyone considering Bayyinah for production use. Surfacing failures is part of the protocol; concealing them would defeat the tool's purpose.

## Summary table

| Fixture | Technique | Result | Mechanism that caught it | Score |
|---|---|---|---|---|
| 01 | White text on white background | **CAUGHT** | `white_on_white_text` (Tier 1) | 0.82 |
| 02 | Font size 0.1pt | **CAUGHT** | `microscopic_font` (Tier 2) | 0.92 |
| 03 | Text drawn off-page (y=-200) | **MISSED** | (off_page_text exists but does not fire - see root cause) | 1.00 |
| 04 | Hidden in PDF metadata (Keywords / Subject) | **MISSED** | (no metadata-payload analyzer) | 1.00 |
| 05 | Bytes appended after `%%EOF` | **MISSED** | (no after-trailer analyzer) | 1.00 |
| 06 | Hidden `/Text` annotation with `/F=2` flag | **MISSED** | (`/Annots` walked for other purposes; hidden text not extracted) | 1.00 |

**Hit rate: 2/6. Payload recovery via inversion_recovery: 2/6.**

In all six cases the visible text was identical: a Q3 financial summary mentioning $1,000 in revenue. In all six cases the hidden payload was identical: `HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex`. The contrast between $1,000 visible and $10,000 hidden is the canonical "contract that displays one figure and contains another" example from the bayyinah.dev landing page. Bayyinah currently catches this when the technique is naive (white-on-white, microscopic font) and misses it when the technique is structurally clever.

## Per-fixture root cause

### 01 - White on white - CAUGHT (0.82, Tier 1)

```
Surface:   (indistinguishable from page background)
Concealed: HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex
```

The text analyzer's `white_on_white_text` check compared the span's fill color (`#FFFFFF`) against the page background (`#FFFFFF`) and emitted a Tier 1 finding with confidence 0.99. This is the most naive concealment technique and the scanner handles it correctly.

### 02 - Microscopic font - CAUGHT (0.92, Tier 2)

```
Surface:   (effectively invisible at 0.100pt)
Concealed: HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex
```

The text analyzer's `microscopic_font` check fires when a span's font size is below the human-readable threshold (1.0pt). The 0.1pt span tripped it correctly. Tier 2 because below-threshold font is technically representable (some PDFs use 0.5pt for fingerprinting - context determines whether the use is malicious).

### 03 - Off-page text - MISSED

The text analyzer **does** have an `_check_offpage` method (`text_analyzer.py:793`) that compares span bboxes against the page's MediaBox with a 1pt tolerance. It would have fired correctly on this fixture if it had received the off-page span.

**Root cause:** the scanner extracts text via PyMuPDF (`fitz.Page.get_text('dict')`). PyMuPDF silently drops spans whose origin is outside the page rectangle during dictionary extraction. The off-page span at `y=-200` never appears in the input to `_check_offpage`, so the check has nothing to evaluate.

```python
# From the fixture's raw content stream:
# BT 1 0 0 1 72 -200 Tm (HIDDEN_TEXT_PAYLOAD: ...) Tj T* ET

# But fitz reports only the on-page spans:
# bbox=(72, 60, 495, 75)  'Q3 financial summary ...'
# bbox=(72, 80, 235,  95)  'dy. Cash position remains strong.'
# (the y=-200 span is silently dropped)
```

**Fix path for v1.1.2:** Walk the raw content stream directly with `pikepdf.Page.Contents.read_bytes()` (or use `fitz.Page.get_drawings()` + `get_textbox(rect)` with an oversized rect). Both options are local, deterministic, and add no dependencies. Estimated complexity: ~30 lines of code in `text_analyzer.py`.

### 04 - Hidden metadata - MISSED

Hidden text payload was injected into both `/Keywords` and `dc:description` of the PDF document info. Both are trivially readable via `pikepdf.Pdf.docinfo` and `pikepdf.Pdf.open_metadata()`.

**Root cause:** No analyzer reads PDF document info. The scanner checks the content stream and the structural tree but does not enumerate document metadata. This is a Tier 2 technique (metadata is *expected* to contain text, so the question is whether the metadata text matches the visible content) but the absence of any check at all is a Tier 1 architectural gap.

**Fix path for v1.1.2:** Add a `pdf_metadata_analyzer` that:
1. Extracts all docinfo and XMP fields
2. Compares each field's text against the page content stream's extracted text (corpus comparison)
3. Emits `metadata_text_divergence` (Tier 2) when metadata text contains substrings absent from the visible content
4. Emits `metadata_text_payload` (Tier 1) when metadata text length exceeds a threshold and contains entropy patterns suggesting a payload

Estimated complexity: ~60 lines, plus a new mechanism in MECHANISM_REGISTRY.

### 05 - Trailing bytes after %%EOF - MISSED

PDF spec allows comments and ignored bytes after the final `%%EOF` trailer, but the visible content of those bytes is significant: many real-world malware samples and steganographic tools use this region. Our fixture appended `HIDDEN_TEXT_PAYLOAD: ...` directly after the EOF.

**Root cause:** No analyzer inspects post-trailer bytes for PDFs. The audio analyzer has an `audio_container_anomaly` mechanism that catches the analogous case for MP3 trailers (we saw it fire on the SoundCloud-downloaded MP3s earlier today). PDFs need the same treatment.

**Fix path for v1.1.2:** Mirror the existing `audio_container_anomaly` logic in a new `pdf_trailer_analyzer`:
1. Find the position of the last `%%EOF`
2. Inspect bytes from EOF+5 to file end
3. If the trailing region contains printable ASCII, emit `pdf_after_eof_payload` (Tier 2, confidence 0.85)
4. If the trailing region contains binary data with high entropy, emit `pdf_after_eof_blob` (Tier 1, confidence 0.95)

Estimated complexity: ~25 lines.

### 06 - Hidden /Text annotation - MISSED

`object_analyzer.py` walks `/Annots` (line 418) for other purposes (URL extraction, action triggers) but does not extract `/Contents` text from `/Text` annotations, and does not check the `/F` flag for the hidden bit (PDF spec: `/F=2` means hidden bit set, `/F=32` means noview bit set; bit values per PDF 32000-1 §12.5.3 Table 165). The fixture set `/F=2` and stored the payload in `/Contents`.

**Root cause:** Annotation walker is not text-aware. It treats annotations as link-like objects rather than as text containers.

**Fix path for v1.1.2:** Extend the existing annotation walker to:
1. Extract `/Contents` text from any annotation with `/Subtype /Text`, `/FreeText`, `/Popup`, or `/Stamp`
2. Check the `/F` flag: if any of bits 2 (hidden, value 2), 6 (noview, value 32), or 7 (locked-contents, value 64) is set, emit `hidden_annotation_text` (Tier 1)
3. Otherwise compare extracted annotation text to visible content (similar to fixture 04's approach) and emit `annotation_text_divergence` (Tier 2) if substantial

Estimated complexity: ~40 lines.

## What this baseline says about Bayyinah v1.1.1

**Honest assessment:** Bayyinah handles the most naive PDF concealment techniques (color-based, size-based) correctly and misses the structurally clever techniques (location, metadata, trailers, annotations).

**This is consistent with the published scope.** The current README states 108 detection mechanisms across 23 file kinds. The four missed techniques here are not in that count. They are reasonable v1.1.2 additions and would bring the per-PDF mechanism count from ~22 to ~26.

**This is also consistent with the protocol's discipline.** The Munafiq Protocol says: a verifier must apply itself to itself. Bayyinah's documentation already states (in OpenAPI):

> A 200 response with scan_incomplete=true indicates the scan ran but did not cover the full document; absence of findings in such a report is not evidence of cleanness.

That sentence applies to this baseline too. Until v1.1.2 ships the four fixes above, **a clean Bayyinah report is not evidence that the PDF is clean** - it is evidence that the PDF does not match any of the 22 currently implemented PDF mechanisms. Users running Bayyinah on PDFs in production should layer it with a metadata extractor and a trailer-byte inspector until the gaps are closed.

## What's next

1. **v1.1.2 milestone:** ship the four fixes above. Each is small, local, and additive (does not modify existing analyzer behavior). Estimated total: ~155 LOC across 4 mechanisms.
2. **Extend the gauntlet:** add fixtures for DOCX, XLSX, HTML, EML, and image-format hidden-text techniques. Each format has its own characteristic concealment idioms. The PDF gauntlet is the model.
3. **CI integration:** wire the gauntlet into the test suite. Each fixture's expected outcome (caught or missed) becomes part of the test corpus, so future regressions are caught and future improvements are visible.
4. **Public version:** include this report (or a polished version) in the v1.1.2 release notes. "Here are the four things v1.1.1 missed; here are the four things v1.1.2 catches" is the most credible release note a security tool can ship.

## Reproducing this report

```bash
git clone https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner
cd Bayyinah-Integrity-Scanner/docs/adversarial/pdf_gauntlet
pip install reportlab pikepdf
python build_fixtures.py     # creates fixtures/
python run_gauntlet.py       # scans each fixture and writes results.json
```

The fixture builder is deterministic; running it twice produces byte-identical PDFs. The gauntlet hits the live API at `https://bayyinah.dev/scan` over HTTPS. Both scripts are < 200 LOC and have no dependencies beyond `reportlab`, `pikepdf`, and the standard library.

---

*This report was triggered by an external adversarial probe and produced in the same session as the v1.1.1 deployment. Honest baselines beat polished press.*
