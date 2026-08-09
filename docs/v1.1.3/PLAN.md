# Bayyinah v1.1.3 Implementation Plan, v3

**Status:** DRAFT for review (Bilal greenlight pending; Grok greenlit v2; Claude parallel-review greenlit v2 with starting-count baseline flag; Claude co-work greenlit v2 with starting-count baseline flag + Item 3/4 layer-consistency flag). v3 addresses both v2 flags below using actual counts from main HEAD `2fc6a54` measured against the live registry.
**Target ship date:** Day 21 of 41 (May 6, 2026 code-freeze) + Day 22 (May 7, 2026 live-deploy gate).
**Scope decision (locked first per Claude flag):** v1.1.3 ships the **8 pre-registered F2 calibration items only**. F1.5 image-gauntlet deferred items are **deferred to v1.1.4**.

---

## Preamble: Framework Reflexivity (G5)

This plan is itself an artifact of the discipline it implements. Bayyinah's standing claim is that pre-registered scope, layered-tier classification, falsifiable thresholds, and version-chain reporting are what make a detection framework credible. The same discipline governs this plan: scope is locked before implementation; LOC ceilings are pre-committed with re-review triggers; layer classification follows the v4.1 single-walk rule; each item carries an explicit fixture-test-report triple; co-firing arithmetic is specified before the first line of code lands. La talbisu al-haqqa bil-batil: do not clothe truth with falsehood, and do not conceal intent under noise of process. The plan eats its own dog food.

---

## Changelog v2 → v3

1. **§2.10:** Starting layer counts corrected from stale pre-F2 audit numbers to live-registry numbers measured against main HEAD `2fc6a54`. Actual baseline: ZAHIR 41, BATIN 113, ROUTING 1, total 155. Plan v2 used pre-F2 numbers (39/105/11) which both reviewers caught as drift.
2. **§2:** Item 3 (`json_key_invisible_chars`) reclassified from BATIN to ZAHIR per Claude co-work §2 v2 flag. Rationale: v1.1.1 precedent classifies `zero_width_chars`, `bidi_control`, `homoglyph`, `csv_zero_width_payload`, `csv_bidi_payload` all as ZAHIR. The rule is byte-stream visibility, not parsed-tree position. Item 3 inspects the same character classes in JSON key positions; consistency with v1.1.1 precedent requires ZAHIR.
3. **§2.10 byte-stream rule footnote added.** Layer classification rule: a mechanism is ZAHIR if its target characters/bytes are present in the file's byte stream regardless of parser pass count; BATIN if detection requires structural inference that no byte-stream walk could reveal (e.g., type drift across rows, schema-level analysis).
4. **Mechanism count summary unchanged at 155 → 159 total.** Layer deltas adjusted: ZAHIR 41 → 45 (+4: Items 2, 3, 4-reclass, 5), BATIN 113 → 114 (+1: Item 6 only, since Item 3 moves to ZAHIR), ROUTING 1 unchanged.
5. **§2.10 explicit registry-test assertion line added** per Grok mod #2.

## Changelog v1 → v2

1. **§1:** Added +2-over-v1.1.1-baseline transparency note (Items 6, 7 flagged as not in v1.1.1 published baseline, with depth-vs-scope rationale per Claude co-work §1).
2. **§2:** Reclassified three items from BATIN to ZAHIR per v4.1 single-walk surface-readability rule (Items 2, 4, 5). Item 8 expanded to three fixtures plus verdict-arithmetic dedup rule. Item 3 renamed back to `json_key_invisible_chars` and scope re-pinned to v1.1.1's four families. Per-item fixture-test-report triple added. LOC estimates converted to ceilings with 150% re-review trigger.
3. **§2 Day 7:** Mechanism count arithmetic pinned to **155 → 159** (4 new mechanisms, 4 extensions of existing). ZAHIR/BATIN deltas pinned per §2.10 below.
4. **§2.10 (new):** Registry and layer-count delta table.
5. **§4:** Tier 3 override discipline sentence added (Grok mod #1).
6. **§5:** No change (already names Fraz + Torah verification cycle explicitly per Claude co-work §7).
7. **§6:** Advisor close-out scoping clarified to 1-2 of 5 emails (not all 5) per Claude co-work §7 mod #3.
8. **§10:** Split May 6 (code-freeze) from May 7 (live-deploy gate) per Claude co-work §6.
9. **§11 (new):** Reviewer-flag traceability table.

*(v3 changelog above supersedes the v1→v2 changes for any item that v3 also touched.)*

---

## 1. Scope Decision (locked first)

### In scope for v1.1.3
The 8 pre-registered calibration items from `docs/adversarial/csv_json_gauntlet/REPORT.md` lines 110-123. All 8 carry regression-and-report commitments locked at v1.1.2 ship.

### Deferred to v1.1.4
The 3 F1.5 image-gauntlet items from `docs/adversarial/image_gauntlet/REPORT.md` lines 144-168:
1. EXIF UserComment (JPEG APP1 tag 0x9286)
2. SVG `<foreignObject>` HTML (hidden-text idioms not propagating)
3. SVG `<style>` block CSS rules (pseudo-element `content` declarations)

### Rationale for keeping v1.1.3 tight
1. **Pre-registration discipline.** The 8 items were named publicly in v1.1.2's REPORT.md with thresholds and LOC estimates. Adding scope mid-version dilutes the pre-registration signal and breaks the version-chain credibility argument.
2. **Falsifiability cadence.** v1.1.2 → v1.1.3 should test exactly what v1.1.2 said it would test. Bundling F1.5 work in muddies whether the F2 calibrations actually closed their fixtures or whether image work hid CSV/JSON gaps.
3. **Mechanism class separation.** F1.5 items are image/SVG parsing surfaces; F2 items are tabular/JSON structural surfaces. Different fixture infrastructure, different test harnesses, different review surfaces. Cleaner to ship them as independent verifiable closures.
4. **Schedule headroom.** 8 calibration items + tests + fixture re-runs + REPORT.md is ~7 days of focused work. Adding 3 image items pushes ship date past Day 24, eating into the v1.1.4 window before competition.

### Transparency note: items not in v1.1.1 published baseline
The v1.1.1 REPORT proposed 6 forward mechanisms. v1.1.3 ships 8 items. The +2 expansion:
- **Item 6 (`csv_payload_in_adjacent_cell`)** is genuinely new. Not in v1.1.1 baseline. Logged here as the only item not pre-disclosed at v1.1.1 ship; rationale: the cross-cell co-firing surface only became visible during v1.1.2's F2 closure when Tier 1 invisible-character findings landed in fixtures with adjacent free-text cells.
- **Item 7 (`csv_quoted_newline_payload extension`)** is depth on v1.1.1's `csv_quoting_anomaly` mechanism. Counts as calibration depth, not new scope, but flagged here for audit-trail completeness.
- Three of the eight items (1, 4, 8) are calibration depth on existing mechanisms (csv_column_type_drift second band; json_prototype_pollution payload extraction; csv_column_type_drift co-firing). Depth, not scope.

### What v1.1.4 inherits
The 3 F1.5 items get pre-registered in v1.1.3's REPORT.md with the same threshold/LOC/regression commitment format. v1.1.4 then tests against them with the same falsifiability discipline.

---

## 2. Per-Item Build Specs

For each item: mechanism name, layer classification (per v4.1 single-walk rule), tier, confidence, LOC ceiling, regression test target, fixture target, REPORT.md update line range, FP risk, sequencing slot. **All LOC values are ceilings: any item shipping at >150% of ceiling re-opens the plan for review before merge.**

### v4.1 byte-stream classification rule (locked, v3 footnote)
A mechanism is **ZAHIR** if its target characters or bytes are present in the file's byte stream, regardless of whether the parser walks them in one pass or several. A mechanism is **BATIN** if detection requires structural inference that no byte-stream walk could reveal (e.g., type drift across N rows, schema-level analysis, cross-document divergence). Layer is decided by byte-stream presence, not by analyzer module location, parser pass count, or key-vs-value position.

**Precedent:** v1.1.1 classifies `zero_width_chars`, `bidi_control`, `homoglyph`, `csv_zero_width_payload`, `csv_bidi_payload`, `subtitle_invisible_chars`, `invisible_render_mode` all as ZAHIR. All require some parser pass (Unicode codepoint extraction, bidi-class lookup, homoglyph table match), yet are classified ZAHIR because the target codepoints exist in the byte stream. v1.1.3 applies the same rule consistently across Items 2, 3, 4, 5, and 7.

### Item 1: csv_column_type_drift second band
- **Mechanism:** Add a second detection band to existing type-drift mechanism. 50-char threshold in numeric-typed columns *without* note/comment/description header allow-list match.
- **Layer:** BATIN. Detection requires (1) parse column, (2) infer majority type across N rows, (3) compare each cell. Multi-pass structural inference, not single-walk visibility.
- **Tier:** 2 (structural). **Confidence:** 0.6.
- **LOC ceiling:** 30. **Re-review trigger:** 45.
- **Registry:** Extends existing `csv_column_type_drift`. **No new registry entry.**
- **Regression test:** `test_csv_column_type_drift_second_band_numeric_no_allowlist` in `tests/analyzers/test_csv_column_type_drift.py`. Asserts fixture 01's specific row (numeric column, 60-char string value, no allow-list match) fires the second band.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/01_*.csv`.
- **REPORT.md update:** lines 60-72 (fixture 01 entry) gain v1.1.3 closure note.
- **FP risk:** Low. Allow-list gates on column-name regex (`note|comment|description|memo|narrative|.*_text$`) prevent legitimate free-text columns from firing.
- **Sequencing slot:** Day 1 (warm-up, smallest delta to existing mechanism).

### Item 2: csv_oversized_freetext_cell
- **Mechanism:** New mechanism. Dual-band detection on free-text-allow-listed columns: 100-char Tier 3 conf 0.6 (smell), 500-char Tier 3 conf 0.4 (deeper smell).
- **Layer:** **ZAHIR (reclassified from BATIN per Claude co-work §2).** A 500+ character cell is fully readable on a single walk through the CSV. Cell text is visible to any reader who opens the file. Severity stays Tier 3; layer corrects to ZAHIR.
- **Tier:** 3 (interpretive, both bands).
- **LOC ceiling:** 40. **Re-review trigger:** 60.
- **Registry:** **New entry.** Adds 1 ZAHIR mechanism.
- **Regression test:** `test_csv_oversized_freetext_cell_100char_band` and `test_csv_oversized_freetext_cell_500char_band` in `tests/analyzers/test_csv_oversized_freetext_cell.py` (new file). Two tests against fixture 03: assert 100-char band fires on the 150-char allow-list cell; assert 500-char band fires on the 600-char allow-list cell.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/03_*.csv`.
- **REPORT.md update:** lines 78-86 (fixture 03 entry) gain v1.1.3 closure note.
- **FP risk:** Medium. Free-text columns *will* legitimately contain long content. Tier 3 conf 0.4 explicitly signals "smell only, not finding-grade." REPORT.md lists expected-FP categories.
- **Sequencing slot:** Day 2.

### Item 3: json_key_invisible_chars (renamed from v1's `json_unicode_key_concealment`)
- **Naming reverted to v1.1.1 REPORT pre-registered name** per Claude co-work §3. Scope held to the four families v1.1.1 named: zero-width chars, TAG block, bidi controls, homoglyphs. No NFC/NFD divergence work in v1.1.3 (deferred if useful).
- **Mechanism:** New mechanism. Fires when JSON object key contains zero-width chars (U+200B-U+200D, U+FEFF), TAG block (U+E0000-U+E007F), bidi controls (U+202A-U+202E, U+2066-U+2069), or homoglyph mappings from existing scanner table.
- **Layer:** **ZAHIR (corrected from v2 BATIN per Claude co-work §2 v2 flag).** Byte-stream visibility rule: zero-width and bidi codepoints are present in the file's byte stream and v1.1.1 already classifies the same character families as ZAHIR (`zero_width_chars`, `bidi_control`, `homoglyph`, `csv_zero_width_payload`, `csv_bidi_payload`). Key-position vs value-position is a parser-pass detail, not a layer-classification criterion under the byte-stream rule. Consistency with v1.1.1 precedent requires ZAHIR.
- **Tier:** 1 (verified, key contains invisible chars is a smoking gun).
- **Confidence:** 0.9.
- **LOC ceiling:** 50 (key recursion + reuse of four existing char-class scanners + finding emit). **Re-review trigger:** 75.
- **Registry:** **New entry.** Adds 1 ZAHIR mechanism.
- **Regression test:** `test_json_key_invisible_chars_zw` and `test_json_key_invisible_chars_bidi` in `tests/analyzers/test_json_key_invisible_chars.py` (new file). Assert fixture 04's `amount\u200b_usd` and `n\u202eote` keys both fire Tier 1, with the Unicode codepoints surfaced in `concealed`.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/04_*.json`.
- **REPORT.md update:** lines 88-94 (fixture 04 entry) gain v1.1.3 closure note.
- **FP risk:** Very low. No legitimate JSON schema has zero-width or bidi chars in keys.
- **Sequencing slot:** Day 2 (parallel to Item 2 if disjoint files; otherwise Day 3).

### Item 4: json_prototype_pollution payload extraction
- **Mechanism:** Extend existing `json_prototype_pollution` to surface the *values* nested inside polluted keys (`__proto__`, `constructor`, `prototype`) into `concealed`, not just the key names.
- **Layer:** **ZAHIR (reclassified from BATIN per Claude co-work §2).** `__proto__` and `constructor` keys are surface-readable on a single walk through parsed JSON. Threat model (downstream JS prototype consumption) is a property of the consuming system, not of the file's concealment surface. Severity stays Tier 1; layer corrects to ZAHIR.
- **Tier:** 1 (already verified). **Confidence:** unchanged from v1.1.2.
- **LOC ceiling:** 25. **Re-review trigger:** 38.
- **Registry:** Extends existing `json_prototype_pollution`. **No new registry entry.** But the existing entry's layer flips from BATIN to ZAHIR (-1 BATIN, +1 ZAHIR).
- **Regression test:** `test_json_prototype_pollution_payload_extraction` extension in existing `tests/analyzers/test_json_prototype_pollution.py`. Assert fixture 05's polluted-key payload value appears in the finding's `concealed` field.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/05_*.json`.
- **REPORT.md update:** lines 96-102 (fixture 05 entry) gain v1.1.3 closure note.
- **FP risk:** Zero (extends existing Tier 1 mechanism, no new firing surface).
- **Sequencing slot:** Day 3.

### Item 5: json_oversized_string_band
- **Mechanism:** New mechanism. Fires on string values >200 chars containing repeated tokens (Shannon entropy heuristic on token frequency).
- **Layer:** **ZAHIR (reclassified from BATIN per Claude co-work §2).** A 200+ char string value is fully readable on a single walk through parsed JSON. Entropy heuristic operates on the visible string content; no cross-document inference required. Severity stays Tier 3; layer corrects to ZAHIR.
- **Tier:** 3 (interpretive). **Confidence:** 0.5.
- **LOC ceiling:** 45 (length check + tokenizer + entropy calc + emit). **Re-review trigger:** 67.
- **Registry:** **New entry.** Adds 1 ZAHIR mechanism.
- **Regression test:** `test_json_oversized_string_band_repeated_tokens` and `test_json_oversized_string_band_high_entropy_negative` in `tests/analyzers/test_json_oversized_string_band.py` (new file). Assert fixture 06's 250-char repeated-token string fires; assert a 250-char high-entropy natural-language string does NOT fire.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/06_*.json`.
- **REPORT.md update:** lines 104-110 (fixture 06 entry) gain v1.1.3 closure note.
- **FP risk:** Medium. Long strings with repeated structure (URLs, base64, structured logs) will fire. Tier 3 conf 0.5 signals smell. REPORT.md lists expected-FP categories.
- **Sequencing slot:** Day 4.

### Item 6: csv_payload_in_adjacent_cell
- **Mechanism:** New mechanism. Cross-cell co-firing rule: when a Tier 1 invisible-character finding fires on cell (row R, col C1), check whether row R has a free-text-allow-list cell at any other column with content >100 chars.
- **Layer:** BATIN. Detection requires cross-column inference within a row, not single-walk visibility.
- **Tier:** 2 (structural co-firing escalation). **Confidence:** 0.7.
- **LOC ceiling:** 35. **Re-review trigger:** 53.
- **Registry:** **New entry.** Adds 1 BATIN mechanism.
- **Regression test:** `test_csv_payload_in_adjacent_cell_fires` and `test_csv_payload_in_adjacent_cell_no_adjacent_long` in `tests/analyzers/test_csv_payload_in_adjacent_cell.py` (new file). Assert fixture 07's row with invisible-char finding *and* adjacent long free-text cell fires the co-firing rule; assert fixtures with isolated invisibles (no adjacent long cell) do not.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/07_*.csv`.
- **REPORT.md update:** lines 112-118 (fixture 07 entry) gain v1.1.3 closure note.
- **FP risk:** Low. Gated on Tier 1 anchor finding, which is already low-FP.
- **Sequencing slot:** Day 4-5 (depends on Item 1 plumbing).

### Item 7: csv_quoted_newline_payload extension
- **Mechanism:** Extend existing `csv_quoting_anomaly` (v1.1.1 mechanism) to fire on quoted cells with 2+ literal newlines, *regardless* of column-count consistency. (Current mechanism gates on column-count anomaly only.)
- **Layer:** ZAHIR. Newline characters in quoted cells are surface-readable on a single walk.
- **Tier:** 2 (structural). **Confidence:** 0.6.
- **LOC ceiling:** 30. **Re-review trigger:** 45.
- **Registry:** Extends existing `csv_quoting_anomaly`. **No new registry entry.**
- **Regression test:** `test_csv_quoted_newline_payload_2plus_newlines` and `test_csv_quoted_newline_payload_single_newline_negative` in existing `tests/analyzers/test_csv_quoting_anomaly.py`. Assert fixture 08's 2-newline quoted cell fires even when row column count matches header; assert single-newline quoted cells (legitimate prose) do not.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/08_*.csv`.
- **REPORT.md update:** lines 120-126 (fixture 08 entry) gain v1.1.3 closure note.
- **FP risk:** Low-medium. Multi-line free-text is legitimate (addresses, prose). Tier 2 conf 0.6 reflects this.
- **Sequencing slot:** Day 5.

### Item 8: csv_column_type_drift co-firing
- **Mechanism:** Calibrate existing type-drift mechanism to also fire on rows that trip column-count anomaly, with explicit FP risk reporting in the finding's `analysis` field. **Co-firing dedup rule: when `csv_column_type_drift` and `csv_oversized_freetext_cell` co-fire on the same `(row, col)` coordinates, both findings record but the verdict score recomputation uses the higher tier only.** Mirrors pdf_metadata_analyzer Day 2 precedent (when /Info dict and XMP stream both encode the same divergence, both findings record but verdict logic accounts for the same underlying concealment).
- **Layer:** BATIN. Co-firing requires cross-mechanism inference plus the existing structural type-drift inference.
- **Tier:** 2 (structural co-firing). **Confidence:** 0.7.
- **LOC ceiling:** 40 (co-firing detection + FP risk note formatter + verdict dedup hook). **Re-review trigger:** 60.
- **Registry:** Extends existing `csv_column_type_drift`. **No new registry entry.**
- **Regression test:** Three fixtures + assertions in existing `tests/analyzers/test_csv_column_type_drift.py`:
  1. **both-fire fixture (09):** long free-text cell in numeric column. Assert both `csv_column_type_drift` (Tier 2) and `csv_oversized_freetext_cell` (Tier 3) fire on same `(row, col)`. Assert verdict for this case equals verdict for drift-only case (dedup rule holds).
  2. **drift-only fixture:** short numeric-string in numeric column. Assert only `csv_column_type_drift` fires.
  3. **oversized-only fixture:** long free-text cell in free-text column. Assert only `csv_oversized_freetext_cell` fires.
- **Fixture target:** `tests/adversarial/csv_json_gauntlet/fixtures/09_*.csv` (existing both-fire) plus two new fixtures `09b_drift_only.csv` and `09c_oversized_only.csv` (negative controls).
- **REPORT.md update:** lines 128-134 (fixture 09 entry) gain v1.1.3 closure note documenting co-firing dedup behavior.
- **FP risk:** Low (co-firing gate prevents standalone type-drift FPs from escalating).
- **Sequencing slot:** Day 6.

### 2.10. Registry and layer-count delta (PINNED before Day 1, v3 corrected)

**Live-registry baseline (measured against main HEAD `2fc6a54`):**
```
$ python3 -c "from domain.config import MECHANISM_REGISTRY, ZAHIR_MECHANISMS, BATIN_MECHANISMS, ROUTING_MECHANISMS; print(len(MECHANISM_REGISTRY), len(ZAHIR_MECHANISMS), len(BATIN_MECHANISMS), len(ROUTING_MECHANISMS))"
155 41 113 1
```

This supersedes the stale pre-F2 audit baseline (39 / 105 / 11) used in v2. The F2 merge (commit `9a298ae`, 12 mechanisms across CSV and JSON) shifted both ZAHIR and BATIN counts and added zero ROUTING entries. The previous "11 Tier-0 / pre-existing" line was wrong; only `format_routing_divergence` exists outside ZAHIR/BATIN.

| Item | Mechanism action | Registry delta | Layer | Layer delta |
|------|------------------|----------------|-------|-------------|
| 1 | Extend `csv_column_type_drift` | 0 | BATIN (unchanged) | 0 |
| 2 | New `csv_oversized_freetext_cell` | +1 | ZAHIR | ZAHIR +1 |
| 3 | New `json_key_invisible_chars` | +1 | ZAHIR (v3 correction) | ZAHIR +1 |
| 4 | Extend `json_prototype_pollution_key` + reclassify | 0 | ZAHIR (was BATIN) | ZAHIR +1, BATIN -1 |
| 5 | New `json_oversized_string_band` | +1 | ZAHIR | ZAHIR +1 |
| 6 | New `csv_payload_in_adjacent_cell` | +1 | BATIN | BATIN +1 |
| 7 | Extend `csv_quoting_anomaly` | 0 | ZAHIR (unchanged) | 0 |
| 8 | Extend `csv_column_type_drift` co-firing | 0 | BATIN (unchanged) | 0 |
| **Total** | **4 new + 4 extensions** | **+4** | | **ZAHIR +4, BATIN 0 net (+1 −1), total +4** |

**Pinned counts (155 → 159 mechanisms total, arithmetic verified):**

| Layer | Start | Item-by-item delta | End |
|-------|-------|--------------------|-----|
| ZAHIR | 41 | +1 (Item 2 new) +1 (Item 3 new) +1 (Item 4 reclass from BATIN) +1 (Item 5 new) | **45** |
| BATIN | 113 | +1 (Item 6 new) −1 (Item 4 reclass to ZAHIR) | **113** |
| ROUTING | 1 | 0 | **1** |
| **Total** | **155** | **+4 registry entries (Items 2, 3, 5, 6 only; Items 1, 4, 7, 8 are extensions with 0 registry delta)** | **159** |

Verification: 45 + 113 + 1 = 159 ✓. Net BATIN delta is zero because Item 6's new BATIN entry is cancelled by Item 4's reclassification of an existing BATIN entry (`json_prototype_pollution_key`) into ZAHIR.

**Registry-test assertion (per Grok mod):** `tests/domain/test_mechanism_registry.py` will assert all four numbers (159 total, 45 ZAHIR, 113 BATIN, 1 ROUTING) before merge. Any drift discovered during build re-opens this table for review and re-circulation to reviewers.

### Day 7
Re-run full F2 gauntlet, regenerate REPORT.md with closure narrative for each fixture, update mechanism count to **155 → 159** (per §2.10), update test count (1,717 → ~1,765 estimated), update README mechanism/test counts, pre-register 3 F1.5 items for v1.1.4, push branch, open PR.

---

## 3. Sequencing Summary

| Day | Items | LOC ceiling | Notes |
|-----|-------|-------------|-------|
| 1 | Item 1 | 30 | Warm-up, extend existing mechanism |
| 2 | Items 2, 3 | 90 | Parallel if disjoint files |
| 3 | Items 3 (cont) or 4 | 25-50 | Item 4 is small extension |
| 4 | Items 5, 6 (start) | 80 | New mechanism + co-firing setup |
| 5 | Items 6 (finish), 7 | 65 | Co-firing tests + extension |
| 6 | Item 8 | 40 | Co-firing + dedup + FP-risk reporting |
| 7 | Gauntlet rerun, REPORT.md, README, pre-register F1.5, PR | n/a | No new mechanism work |

**Total mechanism LOC ceiling:** 295 (matches v1.1.1 pre-registration estimate).
**Total test LOC estimated:** ~520 (16 regression tests + 5 negative-control tests + 3 new co-firing fixtures at ~30 LOC avg).
**Closure deliverables:** updated REPORT.md, updated README, v1.1.4 pre-registration block, PR with full version-chain narrative.

---

## 4. Regression-and-Report Commitments

For each of the 8 items, the v1.1.3 REPORT.md will contain a per-fixture entry with:
1. Whether the mechanism fired on the target fixture.
2. Whether harness payload-recovery succeeded.
3. Honest reading (clean catch / partial / missed).
4. FP risk callout where Tier 3 conf <0.5 or where allow-list gates are involved.
5. Any tuning that happened mid-build (with rationale, not concealed).

**Tier 3 override discipline (per Grok mod #1):** Tier 3 findings (Items 2, 5) never override Tier 1 or Tier 2 findings on the same `(row, col)`, the same fixture, or in the same verdict computation. Tier 3 is smell-grade evidence: it surfaces information for human review but does not escalate severity beyond what Tier 1/2 mechanisms have already established. The co-firing dedup rule in Item 8 enforces this in the verdict score.

**Per-item triple commitment.** Each item ships with: (a) the test fixture it closes, (b) the test name(s) added, (c) the lines of `csv_json_gauntlet/REPORT.md` that get an update banner. If any of those three is missing at PR time, the item is not done. Same hygiene that kept the Day 2 PDF gauntlet audit clean.

Same five Standing Principles. Same Munafiq Protocol on the closure itself.

---

## 5. Bios Contingency (Day 15 Discord post)

**Decision (Claude co-work mod #2 Option 1):** Publish v1.1.3 plan tomorrow morning regardless of bios state. If Fraz hasn't aligned on bio language by Day 15 morning, defer bios with this exact line in the Discord post:

> *"Fraz is finishing his Torah verification cycle; bios land in next 48 hours."*

Rationale: shipping the plan on schedule outweighs gating on bios. Bios are a polish item; the plan is the falsifiability commitment. The deferral is honest (specific dependency named, specific timeframe given), not vague.

---

## 6. Outreach Refresh (post-plan-lock)

After this plan locks (Bilal greenlight), refresh `competition_assets/outreach_emails_ai_safety_researchers.md` with:
1. **Compressed cadence (Claude co-work mod #1):** all 5 emails fire within 48-72 hours of v1.1.3 plan publish, not weekly. Rationale: don't let plan publication stale before conversations open.
2. **Advisor close-out (Claude co-work mod #3, scope-clarified):** add advisor-style close-out paragraph to **1-2 of the 5 emails** where credentials warrant (candidates: Apollo Research, METR, academic). **Not all 5.** Cold-asked alignment teams (Anthropic alignment, Redwood) get standard close, not advisor close. Boilerplate advisor-asks dilute the credibility signal.
3. **Plan citation:** each email references the v1.1.3 plan as evidence of falsifiability discipline (link to the plan doc once committed to repo, or to REPORT.md once shipped). Plan becomes proof the framework practices what it preaches: pre-register the claims, then test them, then report results honestly.

---

## 7. Items Explicitly Out of Scope for v1.1.3

Logged for v1.1.4 or later, not folded in:
1. F1.5 image-gauntlet items (3 items, deferred per §1).
2. Named advisor outreach (folds into outreach refresh, not mechanism work).
3. Regulatory tailwind slide (Day 16-17, separate track).
4. "Perplexity Computer is operating leverage, not product" deck reframe (Day 16-17).
5. README mechanism count refresh (folds into Day 7 closeout).
6. ADR-001 file kind 21/22/23 reconciliation (separate ADR PR).
7. 227 em-dash sweep (separate PR before v1.1.3 ship).
8. Pre-commit deptry/pip-audit hooks (separate infra PR).
9. `docs/research.md` 9 vs 11 entries reconciliation (separate doc PR).
10. "Living demonstration of the framework it implements" Grok quote landing (separate marketing PR).
11. NFC/NFD divergence detection on JSON keys (out of v1.1.3 Item 3 scope; deferred if useful).

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Item 5 (entropy band) generates excessive Tier 3 noise on real-world JSON | Tier 3 conf 0.5 explicitly signals smell; REPORT.md lists expected-FP categories; Tier 3 override discipline (§4) prevents verdict escalation; can be tuned in v1.1.4 if signal-to-noise is bad |
| Items 6, 8 (co-firing rules) interact in unexpected ways | Build sequencing puts Item 6 before Item 8; Item 8 ships with three fixtures (both-fire, drift-only, oversized-only) that assert independent + composed behavior; verdict dedup rule pinned in §2 Item 8 |
| Item 3 (key invisible chars) misses bidi codepoints in non-Arabic JSON | Char-class scanner reuses full Unicode block ranges from existing scanner table, not just U+200B-D; regression test includes both zero-width and bidi cases |
| LOC overrun pushes ship past Day 21 | LOC ceilings with 150% re-review triggers (§2); Items 1, 4, 7 are smallest deltas (~85 LOC combined); if Day 6 slips, Item 8 can defer to v1.1.4 with same pre-registration discipline as F1.5 deferral. Cut order: Item 8 first (least load-bearing, co-firing on existing mechanism). |
| Mid-build mechanism count discovery contradicts §2.10 pinned table | Re-open §2.10 for review before merge; do not silently update README/REPORT.md to match drift |
| v4.1 reclassification (Items 2, 4, 5 BATIN→ZAHIR) breaks downstream count assertions | Pre-flight: run full test suite locally before Day 1 with reclassification applied; layer-count test in `tests/registry/test_layer_assertions.py` updated as part of Item 1 prep work, not deferred to Day 7 |
| Live-deploy gate finds verdict-derivation drift between in-process and live `deriveVerdict` (the v1.1.2 `test_scan_service_control_no_tier0` failure mode) | One-day separation between code-freeze (May 6) and live-deploy gate (May 7); drift surfaces against bayyinah.dev rather than rolling forward into v1.2 |

---

## 9. Approval Loop

- **Bilal:** greenlight on this plan locks scope. After greenlight, Computer commits plan to repo as `docs/v1.1.3/PLAN.md` (or workspace-only at Bilal's discretion).
- **Claude (parallel review v1):** flagged scope-decision-first ordering, addressed in §1. Flagged image-gauntlet inclusion question, answered: deferred to v1.1.4. **v1 mechanism-count-arithmetic flag addressed in v2 §2.10 (155→159 pinned).**
- **Claude co-work review v1:** three substantive flags addressed in v2 (see §11 traceability table).
- **Grok review v1:** greenlit base plan; two minor polish notes (Tier 3 override, MDL Discord, novelty/credibility line) addressed in v2 §4 and Discord post drafting.
- **Fraz:** plan does not require his sign-off (mechanism work is Bilal+Claude+Computer track); bios contingency in §5 covers his thread.

---

## 10. Day 15 Sequence (locked)

1. **Tomorrow morning (Day 15):** Bilal reviews v2 plan. On greenlight, Computer:
   - Refreshes outreach drafts per §6.
   - Drafts Day 15 Discord post citing plan + 8-item scope + bios state (per §5 contingency).
2. **Discord post fires Day 15 morning** after bios decision.
3. **Outreach emails fire within 48-72h of plan publish** (Day 15-17 window).
4. **Mechanism work begins Day 15 afternoon or Day 16** depending on review turnaround.
5. **Code-freeze target: Day 21 (May 6, 2026).** All 8 items merged to main, registry assertion test green, `make test` green.
6. **Live-deploy gate target: Day 22 (May 7, 2026).** Live curl against bayyinah.dev confirms verdict-derivation parity between in-process and live `deriveVerdict`. Any drift surfaces here, not in v1.2 cycle.

---

## 11. Reviewer-flag traceability (v1 → v3)

### v2 → v3 (this revision)

| Reviewer | v2 flag | v3 resolution |
|----------|---------|---------------|
| Claude parallel | Starting ZAHIR/BATIN counts in v2 §2.10 (39/105/11) drawn from pre-F2 audit, not from post-F2 main HEAD. Need to re-measure. | §2.10 corrected. Live measurement against main HEAD `2fc6a54`: ZAHIR 41, BATIN 113, ROUTING 1, total 155. F2 merge (`9a298ae`) shifted both ZAHIR and BATIN. New endpoint: 45 / 113 / 1 / 159. |
| Claude co-work §1 | Starting count baseline drift (155 vs 145); reconcile registry vs audit before Day 1 | Same correction as above. The audit's 145 was a pre-F2 snapshot; current main HEAD is 155. The "11 Tier-0 / pre-existing" line in v2 was wrong; only `format_routing_divergence` exists outside ZAHIR/BATIN. |
| Claude co-work §2 | Item 3 BATIN vs Item 4 ZAHIR layer inconsistency; v1.1.1 precedent classifies same character classes as ZAHIR | Item 3 reclassified BATIN → ZAHIR (Option A in co-work review). §2 byte-stream rule footnote added: layer is decided by byte-stream presence, not parser pass count or key-vs-value position. v1.1.1 precedent named explicitly (`zero_width_chars`, `bidi_control`, `homoglyph`, `csv_zero_width_payload`, `csv_bidi_payload`, `subtitle_invisible_chars`, `invisible_render_mode` all ZAHIR). |

### v1 → v2

| Reviewer | v1 flag | v2 resolution |
|----------|---------|---------------|
| Claude parallel | Mechanism count arithmetic (155→165 vs 155→163) needs pinning before Day 1; my read 155→159 | §2.10 pins 155→159 with per-item registry-delta and layer-delta table |
| Claude co-work §1 | +2-over-v1.1.1-baseline transparency note | §1 added (Items 6, 7 flagged with depth-vs-scope rationale) |
| Claude co-work §2 | v4.1 single-walk reclassification: Items 2, 4, 5 BATIN→ZAHIR | §2 reclassified Items 2, 4, 5 to ZAHIR with explicit single-walk rationale; §2.10 reflects layer deltas |
| Claude co-work §3 | Item 3 rename: revert to `json_key_invisible_chars`, scope to v1.1.1's four families | §2 Item 3 renamed; scope held to four families; NFC/NFD listed in §7 out-of-scope |
| Claude co-work §4 | Item 8 co-firing: three fixtures + verdict dedup rule | §2 Item 8 expanded with three fixtures (both-fire, drift-only, oversized-only) and verdict dedup rule mirroring pdf_metadata_analyzer Day 2 precedent |
| Claude co-work §5 | LOC ceilings + per-item triple commitment | §2 all items have LOC ceiling + 150% re-review trigger; §4 added per-item triple commitment language |
| Claude co-work §6 | Split code-freeze (May 6) from live-deploy gate (May 7) | §10 split into Day 21 code-freeze + Day 22 live-deploy gate; §8 risk added |
| Claude co-work §7 | Mod #3 (advisor close-out) scope: 1-2 of 5, not all 5 | §6 clarified: 1-2 of 5 emails get advisor close-out (Apollo, METR, academic), not boilerplate across all 5 |
| Claude co-work §8 | G5 reflexivity preamble | Preamble added (top of plan) |
| Grok mod #1 | Tier 3 override discipline sentence | §4 added explicit Tier 3 never-overrides-Tier-1/2 sentence |
| Grok mod #2 | MDL Discord post (focus on 8 items + ship date + bios) | Acknowledged for Day 15 Discord post drafting; not a plan-text change |
| Grok mod #3 | Novelty/credibility line in closure narrative | To land in REPORT.md at Day 7 closeout: "These 8 items close the exact pre-registered commitments made at v1.1.2 ship, maintaining the falsifiability discipline reviewers can verify themselves." |

---

Bismillah.
