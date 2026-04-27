# CSV / JSON Adversarial Gauntlet — v1.1.1 Honest Baseline

Six fixtures targeting concealment surfaces in CSV and JSON that the v1.1.1 analyzers do not yet read. Local and live results agree exactly (the analyzer is stateless content). One fixture surfaces a structural finding without recovering the payload; the other five pass clean.

## Summary

| # | Fixture | Score | Findings | T1/T2/T3 | Payload Recovered |
|---|---|---:|---:|---|---|
| 01 | 01_csv_type_mismatch.csv | 1.000 | 0 | 0/0/0 | NO |
| 02 | 02_csv_trailing_extra.csv | 0.865 | 1 | 0/1/0 | NO (structural only) |
| 03 | 03_csv_long_quoted_payload.csv | 1.000 | 0 | 0/0/0 | NO |
| 04 | 04_json_concealment_in_keys.json | 1.000 | 0 | 0/0/0 | NO |
| 05 | 05_json_prototype_pollution.json | 1.000 | 0 | 0/0/0 | NO |
| 06 | 06_json_long_string_payload.json | 1.000 | 0 | 0/0/0 | NO |

**Caught: 0/6 fully. Partial: 1/6 (structural disagreement noted, payload not extracted). Missed: 5/6.**

## What v1.1.1 Already Catches (CSV / JSON)

The two analyzers are not blind — this gauntlet is built around the gaps, not the hits.

**csv_analyzer.py** already detects: `csv_null_byte`, `csv_bom_anomaly`, `csv_mixed_encoding`, `csv_mixed_delimiter`, `csv_comment_row`, `csv_inconsistent_columns`, `csv_formula_injection`, `csv_oversized_field`, `csv_quoting_anomaly`, plus per-cell zero-width / TAG-char / bidi / homoglyph scanning.

**json_analyzer.py** already detects: `duplicate_keys`, `excessive_nesting`, plus per-string-VALUE zero-width / TAG-char / bidi / homoglyph scanning.

## Per-Fixture Root Cause and Fix Path

### 01 — csv_type_mismatch (MISSED)

A column header `amount_usd` would conventionally hold integers. Row 4's cell is the entire natural-language payload. The CSV analyzer reads each cell only for unicode anomalies; it does not infer per-column type signatures or flag a single cell that breaks an established type pattern.

**Fix path (v1.1.2):** add `csv_column_type_drift`. After parsing, infer a per-column type by majority vote across the first N rows (numeric / date / short-token / free-text). Flag any cell that violates its column's inferred type by more than a threshold (e.g. a 200-char free-text cell in a numeric column). Tier 2 structural divergence.

**LOC estimate:** ~45.

### 02 — csv_trailing_extra (PARTIAL — structural only)

Row 3 carries a trailing 3rd column that the header (2 columns) does not declare. v1.1.1 fires `csv_inconsistent_columns` Tier 2, score 0.865. But the finding's `concealed` field reads `"expected 2, got 3 — parser disagreement"` — it never extracts the actual content of the extra column, so the payload string is not surfaced and `payload_recovered` is false.

**Fix path (v1.1.2):** extend the existing `csv_inconsistent_columns` finding so when a row has MORE columns than the header, the contents of the surplus cells are written into the finding's `concealed` field (truncated at 500 chars). Same mechanism, payload now recovered.

**LOC estimate:** ~10.

### 03 — csv_long_quoted_payload (MISSED)

A normal quoted cell in a `notes` column carrying a 200+ character natural-language payload. No unicode tricks, no formula injection, no quoting anomaly. CSV's per-cell scan is purely for invisible-character mechanisms; long-form natural-language content in a free-text cell is not flagged.

**Fix path (v1.1.2):** any free-text-classed cell whose length exceeds a configurable threshold (default 500 chars) is surfaced as `csv_oversized_freetext_cell` Tier 3 with the cell content carried in `concealed`. Tier 3 because long notes columns are legitimate; the payload is recovered, the user judges intent.

**LOC estimate:** ~25.

### 04 — json_concealment_in_keys (MISSED)

Zero-width joiner and bidi codepoints embedded inside JSON object **keys** (e.g. `"amount\u200b_usd"`). v1.1.1's JSON analyzer walks values only when scanning for unicode anomalies; keys are read but not run through the zw/TAG/bidi/homoglyph scanner.

**Fix path (v1.1.2):** in the recursive walker that already visits string values, also pass each key through the same scanner. Reuse the existing zw/TAG/bidi/homoglyph routines from `domain/config.py` — no new detection code, just key-side coverage. New mechanism `json_key_invisible_chars` Tier 1.

**LOC estimate:** ~30.

### 05 — json_prototype_pollution (MISSED)

Top-level JSON object contains keys `__proto__`, `constructor`, and `prototype` — a well-known JS-side concealment / pollution surface that any downstream consumer treating JSON as a JS object inherits. v1.1.1 has no awareness of these reserved key names.

**Fix path (v1.1.2):** add `json_prototype_pollution_key`. Constant set: `{"__proto__", "constructor", "prototype"}`. Walk the parsed JSON; for any key that matches, emit Tier 1 with the key path. Carry the key's value into `concealed` so the payload is recovered.

**LOC estimate:** ~25.

### 06 — json_long_string_payload (MISSED)

A normal JSON string value carrying a 200+ character natural-language payload. No unicode tricks. v1.1.1's value-side scanner only flags invisible-character mechanisms; long natural-language strings are not flagged.

**Fix path (v1.1.2):** mirror the CSV `csv_oversized_freetext_cell` mechanism on the JSON side as `json_oversized_freetext_value` Tier 3 with the value carried in `concealed`. Same threshold, same rationale.

**LOC estimate:** ~20.

## v1.1.2 Milestone Contribution

| Mechanism | Tier | LOC |
|---|---|---:|
| csv_column_type_drift | 2 | ~45 |
| csv_inconsistent_columns surplus-column extraction | 2 (existing extended) | ~10 |
| csv_oversized_freetext_cell | 3 | ~25 |
| json_key_invisible_chars (reuse zw/TAG/bidi/homoglyph) | 1 | ~30 |
| json_prototype_pollution_key | 1 | ~25 |
| json_oversized_freetext_value | 3 | ~20 |
| **CSV / JSON subtotal** | | **~155** |

## Conclusion

CSV / JSON ties with HTML for the most tractable v1.1.2 surface — six clear fix paths totalling ~155 LOC, with two of the six (the long-freetext mechanisms on both sides) usable as a single shared helper. The structural-only result on fixture 02 is the cleanest extension target — a 10-LOC change that converts a partial hit into full payload recovery on a finding that already fires.

This baseline is published as part of the public v1.1.1 honest gauntlet.
