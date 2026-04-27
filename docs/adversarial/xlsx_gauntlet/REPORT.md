# XLSX Hidden-Text Gauntlet — v1.1.1 Baseline

**Date:** 2026-04-26
**Scanner version:** Bayyinah 1.1.1 (live at https://bayyinah.dev)
**Result:** 0 of 6 techniques caught.

The XLSX gauntlet was constructed deliberately *around* the v1.1.1 detectors so the result is informative. `XlsxAnalyzer` already catches a strong set of structural concealment idioms (hidden sheets including `veryHidden`, hidden rows/columns, VBA macros, embedded objects, external links, revision history, and `INDIRECT/HYPERLINK`-based data-validation formulas). The six fixtures here probe different surfaces.

## Summary table

| Fixture | Technique | Result | Mechanism that should have caught it | Score |
|---|---|---|---|---|
| 01 | Cell font color #FFFFFF (white-on-white) | **MISSED** | (`xlsx_white_text` not implemented) | 1.00 |
| 02 | Microscopic font (1.0pt) | **MISSED** | (`xlsx_microscopic_font` not implemented) | 1.00 |
| 03 | Defined Name carrying a string payload | **MISSED** | (`xlsx_defined_name_payload` not implemented) | 1.00 |
| 04 | Cell comment (note) in `xl/comments1.xml` | **MISSED** | (`xlsx_comment_payload` not implemented) | 1.00 |
| 05 | Payload in `docProps/custom.xml` | **MISSED** | (`xlsx_metadata_payload` not implemented) | 1.00 |
| 06 | `=HYPERLINK(...)` and DDE-style formula payloads | **MISSED** | (`xlsx_csv_injection_formula` not implemented) | 1.00 |

**Hit rate: 0/6. Local and live agree.**

Surface text in every fixture: a Q3 financial summary mentioning $1,000 in revenue. Hidden payload in every fixture: `HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex`. Same canonical contract-fraud setup used in the PDF and DOCX gauntlets.

## What `XlsxAnalyzer` v1.1.1 already catches (out of scope)

For completeness, the XLSX classes already detected — the gauntlet deliberately avoided them:

- Hidden / `veryHidden` worksheets (`<sheet state="hidden|veryHidden"/>`)
- Hidden rows and columns (`<row hidden="1">` / `<col hidden="1">`)
- VBA macro projects (`xl/vbaProject.bin`)
- Embedded OLE objects under `xl/embeddings/`
- External-workbook links (`xl/externalLinks/` + `TargetMode="External"` rels)
- Revision history (`xl/revisions/`)
- Data-validation formulas containing `INDIRECT`, `HYPERLINK`, or external-name references

The misses below are orthogonal to all of the above.

## Per-fixture root cause

### 01 — White cell font color — MISSED

The OOXML cell-style stack puts font color in `xl/styles.xml` (`<font><color rgb="FFFFFFFF"/></font>`) and references it from `<c s="N">` cell elements. `XlsxAnalyzer` does not parse `xl/styles.xml`. The PDF analyzer's `white_on_white_text` mechanism caught the same technique; the XLSX analogue does not exist.

**Fix path for v1.1.2:** Parse `xl/styles.xml` to build a styleId → font-color map. Walk every cell element; emit a Tier 1 `xlsx_white_text` finding when a non-empty cell's resolved font color is `FFFFFFFF` against a default fill. Estimated complexity: ~50 lines (styles parsing is non-trivial).

### 02 — Microscopic font — MISSED

Font size is in the same `xl/styles.xml` font records (`<font><sz val="1"/></font>`). Same architectural gap as 01.

**Fix path for v1.1.2:** Once styles parsing exists for fixture 01, the microscopic-font check is one extra threshold (`sz <= 4` → Tier 1, `sz <= 8` → Tier 2). Estimated complexity: ~10 additional lines on top of fixture 01's fix.

### 03 — Defined Name carrying a payload — MISSED

`xl/workbook.xml` declares `<definedNames><definedName name="...">"payload"</definedName></definedNames>`. Defined Names are normally short range references like `Sheet1!$A$1:$B$10`, but the spec permits string-literal values. `XlsxAnalyzer` enumerates `<sheet>` elements but not `<definedName>` elements.

**Fix path for v1.1.2:** Add `_detect_defined_names_with_text`. Walk every `<definedName>` in `xl/workbook.xml`; emit `xlsx_defined_name_payload` (Tier 2) when the element body is a quoted string longer than ~50 chars or contains non-formula characters. Estimated complexity: ~25 lines.

### 04 — Cell comment payload — MISSED

XLSX comments live in `xl/comments1.xml` (and `xl/threadedComments/*` for the newer threaded variant). `XlsxAnalyzer` never opens either part. Comments are visible in Excel's hover tooltip but disappear from print/export views and from many CSV/DataFrame readers.

**Fix path for v1.1.2:** Add `_scan_comments_part`. Iterate `<comment>` elements (and threaded variants), extract their text, run zahir checks, and emit `xlsx_comment_payload` (Tier 2). Mirror the corresponding DOCX miss (fixture 04 of the DOCX gauntlet) so both formats use the same `comment_payload` family. Estimated complexity: ~35 lines.

### 05 — Custom XML metadata — MISSED

Same as the DOCX gauntlet's fixture 03 and the PDF gauntlet's fixture 04: no analyzer reads `docProps/custom.xml` (or `core.xml` / `app.xml`). This is the architectural metadata-payload gap shared across all three OOXML/PDF formats.

**Fix path for v1.1.2:** A single shared `_office_metadata_payload` helper that DocxAnalyzer and XlsxAnalyzer both call would be the cleanest fix. Mirrors the proposed `pdf_metadata_analyzer` for PDF. Estimated complexity: ~40 lines (reused across both DOCX and XLSX paths).

### 06 — CSV-injection / DDE formula payload — MISSED

A cell whose value begins with `=`, `+`, `-`, or `@` is interpreted as a formula. `=HYPERLINK("http://attacker/", "Click for refund")` is a known phishing-via-spreadsheet vector. `=cmd|'/c calc'!A1` is the classic DDE command-execution payload. CSV exports of the workbook carry the formulas as plaintext, and many CSV consumers (re-imported into Excel, ingested by an LLM) interpret them as formulas again.

`XlsxAnalyzer._detect_data_validation` catches `INDIRECT/HYPERLINK/etc.` *only* inside `<dataValidations>` blocks; it does not look at plain cell values for the same shapes. This is a real gap with documented real-world exploitation.

**Fix path for v1.1.2:** Add `_detect_csv_injection_formula`. Walk every cell's `<f>` element (formula). Pattern-match against a small allowlist of dangerous forms (HYPERLINK, DDE-pipe `|`, leading `=cmd`, leading `=mshta`). Emit `xlsx_csv_injection_formula` (Tier 1 for DDE patterns, Tier 2 for HYPERLINK with external URL). Estimated complexity: ~30 lines.

## What this baseline says about Bayyinah v1.1.1 for XLSX

**Honest assessment:** `XlsxAnalyzer` v1.1.1 covers the structural concealment surface (hidden sheets, hidden rows/columns, VBA, embeddings, external links, revisions, validation formulas) thoroughly. It does *not* yet cover the per-cell rendering surface (color, size) or the auxiliary text parts (defined names, comments, custom metadata) or the in-cell formula payload class (CSV injection / DDE).

This is a different shape of gap than DOCX's. DOCX missed everything in the gauntlet; XLSX missed everything in *this* gauntlet but the gauntlet was constructed to avoid the well-armored areas. The unweighted miss rate is misleading without that context — the weighted reality is that XLSX is the strongest of the three OOXML+PDF analyzers on its core domain (structural concealment) and the weakest on the same per-cell rendering surface that affects DOCX too.

## v1.1.2 milestone (consolidated additions for XLSX)

Six new XLSX detectors estimated at ~190 LOC total:

1. `xlsx_white_text` + `xlsx_microscopic_font` — share a `_resolve_cell_font` helper backed by `xl/styles.xml` parsing
2. `xlsx_defined_name_payload` — workbook-level Names with string bodies
3. `xlsx_comment_payload` — `xl/comments*.xml` + threaded comments
4. `xlsx_metadata_payload` — shared `_office_metadata_payload` helper with DOCX
5. `xlsx_csv_injection_formula` — pattern allowlist on cell `<f>` elements

Combined with the 6 DOCX fixes (~200 LOC) and the 4 PDF fixes (~155 LOC), the running v1.1.2 milestone now sits at roughly ~545 LOC across three formats.

## Reproducing this report

```bash
cd Bayyinah-Integrity-Scanner/docs/adversarial/xlsx_gauntlet
pip install openpyxl
python build_fixtures.py     # creates fixtures/*.xlsx
python run_gauntlet.py local # in-process scan via ScanService
python run_gauntlet.py live  # POST to https://bayyinah.dev/scan
```

---

*Third installment of the multi-format adversarial gauntlet series. PDF (2/6 caught) → DOCX (0/6) → XLSX (0/6 against gap-targeted fixtures). HTML, EML, image, and CSV/JSON gauntlets follow.*
