# Bayyinah Integrity Scanner v1.2.3 - False-positive incident report

**Reporter:** Bilal Syed Arfeen
**Date:** May 6, 2026 22:35 CDT
**Scanner version reproduced against:** v1.2.3 (commit c1c0e56)
**Reproducer environment:** local install of v1.2.3 in clean venv

## Headline

Two distinct bugs reproduced locally against v1.2.3.

- Bug 1 (openaction): heuristic fires on benign navigation
  destinations (LibreOffice, Word, most PDF tooling).
- Bug 2 (tounicode_anomaly): heuristic fires on the canonical
  pdfTeX-emitted ToUnicode CMaps (every academic LaTeX PDF).

Both are calibration problems at the analyzer-rule level, not
architectural problems.

## Bug 1: openaction heuristic

LibreOffice PDFs with /OpenAction as a bare destination array
([page_ref /XYZ null null null]) and pdfTeX PDFs with /OpenAction
as a /GoTo-wrapped destination both fire openaction. PDF spec ISO
32000-1 §12.6.3 defines both as navigation hints, not executable
content.

## Bug 2: tounicode_anomaly heuristic

The pdfTeX Computer Modern fonts emit CMap entries that the
heuristic flags as adversarial: Greek-letter targets in math
fonts (CMSY, CMMI) flagged as Latin homoglyphs, and (in OT1
encoding) slot 0x17 mapped to U+200C ZWNJ as a Unicode placeholder
flagged as zero-width concealment. Both are documented pdfTeX
behavior, present in every LaTeX document for the last 15 years.

## Severity miscalibration

tounicode_anomaly is currently tier 1 ("Verified: unambiguous
concealment"). The heuristic produces unverified positives on
the LaTeX population. Tier 2 is the correct tier until
CID-actually-drawn correlation lands.

## Recommended fix

1. openaction destination-vs-action filter per ISO 32000-1
   §12.6.3.
2. tounicode_anomaly producer-signature suppression for the
   TeX-stack producers (pdfTeX, XeTeX, LuaTeX, dvips, dvipdfm)
   when the CMap targets fall in the canonical TeX safe set
   (Greek for math fonts, ZWNJ at slot 0x17 in OT1).
3. tounicode_anomaly tier 1 -> tier 2.
4. Corpus widening: clean fixtures from pdftex and LibreOffice
   added so future regressions surface in CI rather than
   waiting for the next manual incident report.

## Recursive framework check

Worth verifying: the v3.0 Audit Framework PDF, if pdfTeX or
LibreOffice produced, would self-mushtabih against v1.2.3.
That is a v3 §9.7 Cross-Document Accounting Drift instance.
