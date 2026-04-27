# Bayyinah v1.1.1 — Multi-Format Adversarial Gauntlet (Honest Baseline)

This is the public, honest baseline for Bayyinah Integrity Scanner v1.1.1 across seven file formats. Forty-two adversarial fixtures, every result run locally and against the live `bayyinah.dev/scan` endpoint, every hit and every miss disclosed. The scanner is stateless content; local and live always agree.

The purpose is not to advertise — it is to fix what the gauntlet exposes. Every miss in this corpus has a named fix path and a LOC estimate. v1.1.2 is the consolidation of those fixes.

## Consolidated Result Matrix

| Format | Fixtures | Caught (full) | Partial (structural only) | Missed | Avg score |
|---|---:|---:|---:|---:|---:|
| PDF | 6 | 2 | 0 | 4 | — |
| DOCX | 6 | 0 | 0 | 6 | 1.000 |
| XLSX | 6 | 0 | 0 | 6 | 1.000 |
| HTML | 6 | 0 | 0 | 6 | 1.000 |
| EML | 6 | 0 | 0 | 6 | 1.000 |
| Image (PNG/JPEG/SVG) | 6 | 0 | 1 | 5 | ~0.95 |
| CSV / JSON | 6 | 0 | 1 | 5 | ~0.98 |
| **Totals** | **42** | **2** | **2** | **38** | — |

**Honest read:** v1.1.1 fully recovers payloads on **2 of 42** adversarial fixtures, surfaces structural anomalies on a further **2**, and misses **38**. The PDF analyzer is the most mature surface and accounts for both full catches; every other format has known gaps that v1.1.2 closes.

This is exactly what an honest baseline looks like before a hardening release. The fixtures are designed to find gaps, not re-prove existing hits — every analyzer already detects a substantial set of mechanisms (documented per-format below) that this gauntlet deliberately does not retest.

## Per-Format Reports

Each gauntlet has its own directory with build script, runner, fixtures, raw `results_local.json` / `results_live.json`, and a detailed REPORT.md.

- [pdf_gauntlet/](pdf_gauntlet/) — 6 fixtures across PDF object/stream/annotation/metadata/trailer surfaces
- [docx_gauntlet/](docx_gauntlet/) — white-on-white text, microscopic font, metadata, comments, header/footer, footnote payloads
- [xlsx_gauntlet/](xlsx_gauntlet/) — white text, microscopic font, defined-name payload, comment payload, metadata, CSV-injection-via-formula
- [html_gauntlet/](html_gauntlet/) — `<noscript>`, `<template>`, comment, `<meta>`, CSS `content:`, title/text divergence
- [eml_gauntlet/](eml_gauntlet/) — Reply-To divergence, Return-Path divergence, Received chain anomaly, body/header divergence, header continuation, unknown header
- [image_gauntlet/](image_gauntlet/) — JPEG APP4 payload, PNG private chunk, SVG white-on-white, SVG aux text payload, SVG orphan defs text, SVG metadata
- [csv_json_gauntlet/](csv_json_gauntlet/) — CSV column-type drift, trailing-extra column extraction, long quoted free-text, JSON key invisibles, prototype-pollution keys, long string values

## What Each Analyzer Already Catches

This gauntlet targets gaps. Each analyzer's existing mechanisms (not retested here) are documented inline in the per-format REPORT.md. As a quick index:

- **PDF** — full pdf_object_analyzer + stream/text concealment + JS/launch action detection + selected metadata fields
- **DOCX** — relationships, ole-embed, vba-macro, custom XML parts, drawing canvas anomalies (format-specific zahir surfaces are the gap)
- **XLSX** — external links, defined-names with formulas, hidden sheets, drawing/comment XML structural checks (well-armored cells with payloads are the gap)
- **HTML** — script-tag content, attribute event handlers, base64/hex inline payloads, iframe/embed structural anomalies
- **EML** — DKIM/SPF/auth-results, body multipart structural anomalies, attachment surfaces (header-relationship divergence is the gap)
- **Image** — chunk integrity for known PNG chunks, EXIF text extraction (ICC/MPF/APP4 and SVG concealment surfaces are the gap)
- **CSV** — null byte, BOM, mixed encoding/delimiter, comment row, inconsistent columns, formula injection, oversized field, quoting anomaly + per-cell unicode
- **JSON** — duplicate keys, excessive nesting + per-string-VALUE unicode (key-side and oversized values are the gap)

## v1.1.2 Milestone — Consolidated Fix List

| Format | New mechanisms | LOC |
|---|---|---:|
| PDF | off_page raw stream, pdf_metadata_analyzer, pdf_trailer_analyzer, /Annots text-aware | ~155 |
| DOCX | docx_white_text, docx_microscopic_font, docx_metadata_payload, docx_comment_payload, docx_header_footer_payload, docx_footnote_payload | ~200 |
| XLSX | xlsx_white_text + xlsx_microscopic_font (shared styles parser), xlsx_defined_name_payload, xlsx_comment_payload, xlsx_metadata_payload (shared), xlsx_csv_injection_formula | ~190 |
| HTML | html_noscript_payload, html_template_payload, html_comment_payload, html_meta_payload, html_style_content_payload, html_title_text_divergence | ~120 |
| EML | eml_replyto_domain_divergence, eml_returnpath_divergence, eml_received_chain_anomaly, eml_body_payload_divergence, eml_header_continuation_payload, eml_unknown_header_payload | ~185 |
| Image | extend _extract_jpeg_text APPn coverage, attach payload to suspicious_image_chunk, svg_white_on_white_text, svg_aux_text_payload, svg_orphan_defs_text | ~115 |
| CSV / JSON | csv_column_type_drift, csv_inconsistent_columns surplus extraction, csv_oversized_freetext_cell, json_key_invisible_chars, json_prototype_pollution_key, json_oversized_freetext_value | ~155 |
| **Total v1.1.2 surface** | | **~1,120** |

Approximately 1,120 LOC across **42 new or extended mechanisms**, every one traceable back to a concrete adversarial fixture published in this corpus. No speculative additions.

## Reproducibility

Every gauntlet is reproducible from this repository:

```bash
cd docs/adversarial/<format>_gauntlet
python3 build_fixtures.py                    # regenerate fixtures
python3 run_gauntlet.py local                # scan via local ScanService
python3 run_gauntlet.py live                 # scan via https://bayyinah.dev/scan
```

Local mode imports `application.scan_service.ScanService`. Live mode posts each fixture to the production endpoint (Cloudflare-fronted Railway). Both modes write `results_local.json` / `results_live.json`. The two files are byte-for-byte equivalent on findings; they have always agreed across all 42 fixtures.

## Why Publish the Misses

Three reasons.

**One.** The scanner's first-principle is that concealment surfaces must be enumerated, not asserted. A miss list is the only honest enumeration of what the v1.1.1 surface does not yet cover.

**Two.** Every miss in this corpus is a named, scoped, LOC-estimated fix. Publishing them turns vague "future work" into a concrete v1.1.2 milestone that anyone can verify when v1.1.2 ships — re-run this exact corpus, count the converted misses.

**Three.** Reviewers, including the external adversarial tester currently probing the scanner, deserve to see the gaps before they find them. Pre-disclosing a miss list is more useful to a release reviewer than a sanitized highlight reel.

This baseline is the v1.1.1 honest commit. v1.1.2 will be measured against it.
