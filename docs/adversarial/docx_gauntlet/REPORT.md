# DOCX Hidden-Text Gauntlet — v1.1.1 Baseline

**Date:** 2026-04-26
**Scanner version:** Bayyinah 1.1.1 (live at https://bayyinah.dev)
**Triggered by:** Multi-format gauntlet expansion following the PDF gauntlet baseline.
**Result:** 0 of 6 techniques caught. All six are documented as v1.1.2 targets.

This is the second installment in the multi-format adversarial corpus. The PDF gauntlet showed Bayyinah catching the naive techniques (color, size) and missing the structurally clever ones (location, metadata, trailer, hidden annotation). The DOCX gauntlet shows a stronger result: every fixture lands clean.

The reason is structural and instructive. `DocxAnalyzer` was built to detect the *batin*-layer concealment idioms specific to OOXML (VBA macros, embedded objects, altChunks, external relationships, tracked changes) and the in-body *zahir* concealment that already had universal detectors (`<w:vanish/>` hidden runs, plus per-run zero-width / TAG / bidi / homoglyph). It was *not* yet extended to the OOXML-specific zahir vectors that the PDF gauntlet's lessons demand: color, font size, custom metadata parts, comments, headers/footers, and footnotes.

This baseline is what makes the v1.1.2 milestone concrete.

## Summary table

| Fixture | Technique | Result | Mechanism that should have caught it | Score |
|---|---|---|---|---|
| 01 | White font color (`w:color w:val="FFFFFF"`) | **MISSED** | (`docx_white_text` not implemented) | 1.00 |
| 02 | Microscopic font (`w:sz w:val="2"` = 1.0pt) | **MISSED** | (`docx_microscopic_font` not implemented) | 1.00 |
| 03 | Payload in `docProps/custom.xml` | **MISSED** | (`docx_metadata_payload` not implemented) | 1.00 |
| 04 | Payload in `word/comments.xml` | **MISSED** | (`docx_comment_payload` not implemented) | 1.00 |
| 05 | Payload in `word/header1.xml` (white text) | **MISSED** | (`docx_header_footer_payload` not implemented) | 1.00 |
| 06 | Payload in `word/footnotes.xml` (no in-body ref) | **MISSED** | (`docx_footnote_payload` not implemented) | 1.00 |

**Hit rate: 0/6. Payload recovery: 0/6. Local and live agree exactly.**

In all six cases the visible text was identical: a Q3 financial summary mentioning $1,000 in revenue. In all six cases the hidden payload was identical: `HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex`. The contrast between $1,000 visible and $10,000 hidden is the canonical "contract that displays one figure and contains another" example.

## What `DocxAnalyzer` v1.1.1 already catches (out of scope for this gauntlet)

For completeness, the following DOCX concealment classes are caught — these fixtures were deliberately *not* tested here because the PDF gauntlet's purpose was finding misses, not re-proving hits:

- `<w:vanish/>` hidden runs in `word/document.xml` (rendered zero-width, full text in stream)
- Tracked changes (`<w:ins>` / `<w:del>` revision history)
- VBA macro projects (`word/vbaProject.bin`)
- Embedded OLE objects under `word/embeddings/`
- altChunk relationships (foreign-content injection at render time)
- External relationships (`TargetMode="External"` — remote images/templates/beacons)
- Per-run zero-width characters, TAG block, bidi-control codepoints, and Latin homoglyphs

The misses below are orthogonal to all of the above.

## Per-fixture root cause

### 01 — White font color — MISSED

```
Surface:   (text rendered in #FFFFFF on default white page)
Concealed: HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex
```

The OOXML idiom for invisible text via color is `<w:rPr><w:color w:val="FFFFFF"/></w:rPr>`. `DocxAnalyzer._scan_text_runs` walks every `<w:t>` element but does not consult its parent run's `<w:rPr>` for color; the per-run pipeline checks zero-width / TAG / bidi / homoglyph and stops. The PDF analyzer's `white_on_white_text` mechanism caught the same technique in fixture 01 of the PDF gauntlet — the DOCX analogue does not exist.

**Fix path for v1.1.2:** Add `_detect_white_text` parallel to `_detect_hidden_text`. Walk every run; read `<w:color w:val="...">`; emit a Tier 1 finding when the color is `FFFFFF` or close (or `auto` when the page background is white via `<w:background>`). Estimated complexity: ~25 lines.

### 02 — Microscopic font — MISSED

```
Surface:   (rendered at 1.0pt - far below readable threshold)
Concealed: HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex
```

OOXML font size lives in `<w:rPr><w:sz w:val="N"/></w:rPr>`, where `N` is half-points (so `w:val="2"` = 1.0pt). `DocxAnalyzer` does not inspect `<w:sz>`. The PDF analyzer's `microscopic_font` mechanism caught fixture 02 of the PDF gauntlet — the DOCX analogue does not exist.

**Fix path for v1.1.2:** Add `_detect_microscopic_font`. Threshold at `w:sz <= 16` (8.0pt) for Tier 2, `w:sz <= 4` (2.0pt) for Tier 1. Mirror the PDF analyzer's threshold logic. Estimated complexity: ~20 lines.

### 03 — Custom XML metadata — MISSED

```
Surface:   (no document.xml indication)
Concealed: payload in docProps/custom.xml as <vt:lpwstr> property
```

`DocxAnalyzer` never opens `docProps/*` (custom.xml, app.xml, core.xml). The custom-properties part is a documented OOXML location for arbitrary author-defined metadata; Word reads it, indexers read it, an LLM ingesting the document via a competent extractor reads it. Bayyinah does not.

This mirrors the PDF gauntlet's fixture 04 (Keywords / dc:description) and is the same architectural gap: no metadata-payload analyzer.

**Fix path for v1.1.2:** New `_detect_metadata_payload` method that reads `docProps/core.xml`, `docProps/app.xml`, and `docProps/custom.xml`. Compare each text value against the document.xml extracted-text corpus. Emit `docx_metadata_text_divergence` (Tier 2) when metadata text contains substrings absent from visible content. Emit `docx_metadata_payload` (Tier 1) when metadata text is long enough to be a payload (>200 chars or matches entropy heuristics). Estimated complexity: ~50 lines.

### 04 — Comment payload — MISSED

```
Surface:   (review pane shows nothing in print/export view)
Concealed: payload inside word/comments.xml
```

`DocxAnalyzer` parses only `word/document.xml`. Comments live in their own part (`word/comments.xml`) and are referenced from document.xml via `<w:commentRangeStart>` / `<w:commentReference>` markers. The fixture writes a comment with the payload as its body; the rendered document shows no comment marker because the document.xml side of the reference is omitted, but Word still loads the comments part.

**Fix path for v1.1.2:** Add `_scan_comments_part`. Iterate `<w:comment>` elements, extract their text, run the same per-run zahir checks (zero-width, TAG, bidi, homoglyph) plus a divergence check against document.xml text. Emit `docx_comment_payload` (Tier 2) for any comment whose text exceeds a threshold and is not referenced from document.xml. Estimated complexity: ~35 lines.

### 05 — Header payload (white text) — MISSED

```
Surface:   (header text rendered white; even header-aware reader misses it)
Concealed: payload in word/header1.xml with <w:color w:val="FFFFFF"/>
```

Headers and footers are separate XML parts (`word/header*.xml`, `word/footer*.xml`). `DocxAnalyzer` never opens them. The fixture additionally renders the header text in white, so even a header-aware reviewer who opens Word and views the header in print preview misses it visually.

**Fix path for v1.1.2:** Add `_scan_headers_footers`. Enumerate parts whose names match `word/header*.xml` or `word/footer*.xml`. Run the same zahir checks and color/size detectors there. This is one of the highest-leverage v1.1.2 additions because headers are a common concealment location in real-world phishing documents (legal disclaimer, company letterhead). Estimated complexity: ~30 lines.

### 06 — Footnote payload — MISSED

```
Surface:   (no footnote reference in the body; reader sees no indicator)
Concealed: payload in word/footnotes.xml
```

Footnotes live in `word/footnotes.xml`, with `<w:footnoteReference>` markers in document.xml pointing to specific footnote IDs. The fixture writes a footnote whose ID is *not* referenced from document.xml. Word will preserve the orphaned footnote in the package, and any indexer that walks the ZIP finds the payload.

**Fix path for v1.1.2:** Add `_scan_footnotes_endnotes`. Extract every `<w:footnote>` and `<w:endnote>` element. Cross-reference against `<w:footnoteReference>` / `<w:endnoteReference>` markers in document.xml. Emit `docx_orphan_footnote` (Tier 1) for any footnote with payload content but no in-body reference; emit `docx_footnote_payload` (Tier 2) for non-orphan footnotes containing concealment patterns. Estimated complexity: ~40 lines.

## What this baseline says about Bayyinah v1.1.1 for DOCX

**Honest assessment:** `DocxAnalyzer` v1.1.1 is well-armored against *batin*-layer (structural) concealment but largely unarmored against the OOXML-specific *zahir*-layer techniques that mirror the naive PDF concealment vectors. A real attacker building a phishing or contract-fraud DOCX would reach for white text or a comment payload before reaching for VBA macros.

**The pattern matches the PDF gauntlet result.** Bayyinah catches what was lifted directly from the PDF analyzer (zero-width, TAG, bidi, homoglyph — those are universal text-layer detectors the DOCX path inherits) and misses the format-specific vectors that need their own DOCX-aware code paths (color, size, metadata, comments, headers, footnotes).

**This is also consistent with the protocol's discipline.** Bayyinah's documentation says: a clean report is not evidence of cleanness; it is evidence that no implemented mechanism fired. The DOCX gauntlet now puts six concrete misses next to that statement.

## v1.1.2 milestone (consolidated with PDF gauntlet)

Six new DOCX detectors estimated at ~200 LOC total:
1. `docx_white_text` — color check on every run
2. `docx_microscopic_font` — size check on every run
3. `docx_metadata_payload` — corpus comparison of docProps/* vs document.xml
4. `docx_comment_payload` — scan word/comments.xml + cross-reference
5. `docx_header_footer_payload` — scan word/header*.xml and word/footer*.xml
6. `docx_footnote_payload` / `docx_orphan_footnote` — scan word/footnotes.xml

Combined with the four PDF fixes (~155 LOC), the v1.1.2 milestone sits at roughly ~355 LOC across two file kinds.

## Reproducing this report

```bash
git clone https://github.com/BayyinahEnterprise/Bayyinah-Integrity-Scanner
cd Bayyinah-Integrity-Scanner/docs/adversarial/docx_gauntlet
pip install python-docx
python build_fixtures.py     # creates fixtures/*.docx
python run_gauntlet.py local # in-process scan via ScanService
python run_gauntlet.py live  # POST to https://bayyinah.dev/scan
```

The fixture builder is deterministic; it produces six DOCX files of stable size on every run. Local and live results agreed exactly when this baseline was recorded, which is the expected behavior for a stateless content-only analyzer.

---

*This is the second of the multi-format adversarial gauntlet series. PDF was first (2/6 caught); DOCX is second (0/6 caught); XLSX, HTML, EML, image, and CSV/JSON gauntlets follow. The consolidated REPORT.md will live at `docs/adversarial/REPORT.md` once all formats have been baselined.*
