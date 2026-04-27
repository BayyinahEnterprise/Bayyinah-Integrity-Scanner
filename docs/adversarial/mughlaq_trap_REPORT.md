# The Mughlaq Trap: Stress-Testing Bayyinah's Verdict Logic

**Test conducted:** April 27, 2026, 1:30 AM CDT
**Scanner under test:** bayyinah.dev v0.1.0 (live, post-CC-1)
**Tester:** Bilal Syed Arfeen
**Test class:** Verdict-logic adversarial stress test (epistemic, not mechanism-based)

---

## 1. Why This Test

Bayyinah's published moat is the verdict taxonomy and the Tier 1/2/3 epistemic discipline. Section 07 of the live landing (shipped 1:00 AM tonight) names three rules of practice: kill our own claims first, publish what we miss, test against equivalent methodology.

Existing adversarial tests (the 7 gauntlet REPORTs) probe **mechanism coverage**: does Bayyinah catch this hidden payload, that microscopic font, that off-page text. Those tests assume the verdict logic itself is correct and only the mechanism count needs to grow.

This test asks the harder question: **is the verdict logic honest under adversarial framing**? Specifically, does Bayyinah's classification of mukhfi / mughlaq / mushtabih / sahih survive when the file's claimed identity (extension) and actual identity (magic bytes) diverge, or when the file is too empty to make any claim about?

If the verdict logic fails this test, v1.1.2's mechanism slate is not the priority. The priority is an epistemic layer that audits the routing decision itself.

---

## 2. The Three Vectors

| # | Vector | Construction |
|---|---|---|
| 1 | Polyglot | Real adversarial PDF (`01_white_on_white.pdf`) renamed to `.docx`. Magic bytes say PDF, extension claims DOCX. |
| 2 | Format-spoofed | Same adversarial PDF renamed to `.txt`. Magic bytes say PDF, extension claims plain text. |
| 3 | Empty-but-claimed | 4-byte file containing only `%PDF`, named `.pdf`. Extension and magic prefix agree, but there is no body to scan. |
| 4 (control) | Aligned | Same adversarial PDF with correct `.pdf` extension. |

All four were uploaded to the live `bayyinah.dev/scan` endpoint via `curl -F file=@`.

---

## 3. Raw Results

| Vector | score | scan_incomplete | findings | tiers | error |
|---|---|---|---|---|---|
| V1 polyglot (`.docx`) | 0.82 | false | 1 | T1 white_on_white_text | none |
| V2 spoofed (`.txt`) | 0.82 | false | 1 | T1 white_on_white_text | none |
| V3 empty (`.pdf`, 4 bytes) | 0.00 | true | 0 | - | "Could not open PDF: Failed to open file" |
| V4 control (`.pdf`) | 0.82 | false | 1 | T1 white_on_white_text | none |

**V1, V2, and V4 produced identical responses.** The scanner ran PDF analysis on all three files and returned the same finding, with zero acknowledgment that V1 was uploaded as `.docx` and V2 as `.txt`.

---

## 4. Verdict Logic Analysis

Per the deployed `deriveVerdict()` in `docs/landing-mock-v2/index.html`:

| Condition | Verdict | Color |
|---|---|---|
| score < 1.0 AND any Tier 1 or Tier 2 finding | mukhfi | terracotta |
| scan_incomplete=true OR unknown_format finding | mughlaq | slate |
| Tier 3 only, scan complete | mushtabih | sand |
| score = 1.0, no findings, scan complete | sahih | sage |

### V1 Polyglot - would render as: **mukhfi (terracotta, Tier 1 hidden)**

The user uploaded a file labeled `.docx`. Bayyinah ran PDF analysis without disclosing the routing decision and returned a Tier 1 hidden-text finding. The hidden text *is* real (the underlying file is a real adversarial PDF). But the verdict claims epistemic ground that the scanner has not earned: it asserts Tier 1 verified evidence about a file kind the user did not upload.

**Honest verdict:** mughlaq with a divergence finding ("file claimed `.docx` but magic bytes indicate PDF; analyzer routed by magic bytes; user should confirm file kind before trusting downstream finding"). The PDF finding could then be exposed as conditional Tier 1 *if the user accepts the routing decision*.

### V2 Format-spoofed - would render as: **mukhfi (terracotta, Tier 1 hidden)**

Same dishonesty as V1. The file was uploaded as `.txt`. The scanner ran PDF analysis silently. No mention of the divergence.

**Honest verdict:** mughlaq with the same divergence finding. The Tier 1 PDF finding is then conditional.

### V3 Empty-but-claimed - would render as: **mughlaq (slate, scan_incomplete=true)**

The scanner returned `scan_incomplete=true` and a clear error message ("Could not open PDF: Failed to open file"). This is the **correct** behavior for this vector. The verdict logic catches it cleanly.

But there is a subtle concern: the error message says "Failed to open file" rather than "File too small to contain a valid PDF body" or "PDF header present but no objects." The user is told the scan failed for an opaque reason, not that the file was structurally insufficient. This is a Tier 1 honest-but-uninformative result, not a Process 3 lie. It is honest enough for v1.1.1; it could be sharper in v1.2+.

### V4 control - would render as: **mukhfi (terracotta, Tier 1 hidden)**

Correct. This is the verdict the file deserves: real PDF, real adversarial payload, correct routing.

---

## 5. Pass / Fail Summary

| Vector | Renders as | Honest verdict | Status |
|---|---|---|---|
| V1 polyglot | mukhfi | mughlaq + conditional Tier 1 | **FAIL** |
| V2 spoofed | mukhfi | mughlaq + conditional Tier 1 | **FAIL** |
| V3 empty | mughlaq | mughlaq | **PASS** (informational note for v1.2+) |
| V4 control | mukhfi | mukhfi | **PASS** |

**Two of four pass. Two of four fail.**

The two failures share one root cause: **the scanner makes a routing decision (trust magic bytes over extension) without disclosing it as a finding.** When the user's claim about the file's kind disagrees with the file's actual structure, that disagreement is itself epistemically significant. The scanner currently silences it.

---

## 6. The Specific Honesty Failure

The published Tier 1 contract says:

> Tier 1 = Verified - unambiguous concealment

In V1 and V2, the scanner reports a Tier 1 finding about hidden PDF text. The finding *is* real evidence of concealment in the underlying bytes. But the user uploaded the file claiming a different format. The scanner has not verified that the user wanted PDF analysis; it inferred that intent from magic bytes. That inference is reasonable, defensible engineering - but reporting the result as Tier 1 without disclosing the inference is the exact Process 3 surface the Munafiq Protocol names: performing rigor without possessing it. The depth of the analysis is real. The surface that says "Tier 1 verified" is making a claim it cannot fully back.

There is a cleaner contract:

- **Tier 0 (new):** Format-routing finding. "User claimed extension X; magic bytes indicate format Y; scanner routed analysis to Y." This is *meta-evidence*, not content evidence.
- **Tier 1, 2, 3:** As currently defined, but conditional on the routing decision.

The verdict mughlaq becomes the correct frame when Tier 0 fires, because the scanner is saying: "I cannot complete an unambiguous verdict on the file you uploaded - only on the file my routing decision *interpreted* you to mean." That is exactly what mughlaq is for. The slate-blue "closed scope" panel was built for this.

---

## 7. The Empty Sahih Risk (Adjacent Issue)

V3 produced the right verdict (mughlaq) because the scanner errored on an unparseable PDF. But what about a 4-byte file with extension `.txt`, where there is no analyzer to fail? Let me probe:

```
$ printf 'aaaa' > v5_short.txt && curl -s https://bayyinah.dev/scan -X POST -F "file=@v5_short.txt"
```

This was not run in this Computer-side session (1:30 AM, deferred), but the verdict logic predicts: `unknown_format` finding (txt has no analyzer in the verified set), score 0.5, scan_incomplete=true, **mughlaq**. That would be honest. If instead it returns score 1.0 with no findings, that would be a Process 3 lie - claiming sahih on content the scanner did not actually verify.

**Independent confirmation (April 27, 2026, Claude session):** A parallel stress test from Claude's review confirmed that text files on the live scanner return `integrity_score: 1.0` with no findings regardless of content. This is structurally the same Process 3 lie that V1 and V2 produce, just at the empty-content boundary instead of the format-divergence boundary. The fix is a single `unknown_format` finding for any file the scanner cannot verifiably route to a known analyzer. The Tier 0 layer (Section 6) already implements the disclosure half; the verdict-resolver wiring (Section 6) already implements the floor. The remaining work is making `unknown_format` fire on extensionless / unanalyzed text files, which is structurally adjacent to the `format_routing_divergence` mechanism and ships in the same Day 1 commit.

This is named here as a deferred test for v1.1.2 verification. **Run V5 before any per-format mechanism work on Day 2.**

---

## 8. What This Means For v1.1.2

The v1.1.2 framework report and Claude prompt currently scope the work to closing the existing 42-fixture gauntlet (~1,120 LOC, 39 mechanisms across 7 formats). That scope is correct *for mechanism coverage*. It is **insufficient** for verdict honesty.

### 8.1 Required additions to v1.1.2 scope

**A. Tier 0 routing finding (new mechanism class)**

When the scanner's analyzer routing differs from the user's declared extension, emit a structural finding:

```python
{
    "mechanism": "format_routing_divergence",
    "tier": 0,  # new tier; meta-evidence about scanner behavior
    "confidence": 1.0,
    "severity": 0.0,
    "description": "User extension claim '.docx' diverges from detected format 'PDF' (magic bytes 25 50 44 46). Analysis routed to PDF analyzer; downstream findings are conditional on this routing.",
    "inversion_recovery": {
        "surface": "user-declared extension '.docx'",
        "concealed": "magic-byte-detected format 'PDF'"
    }
}
```

**B. Verdict logic update**

When a `format_routing_divergence` finding is present, the verdict floor becomes mughlaq, regardless of any downstream Tier 1/2/3 findings. The downstream findings are still reported, but the *verdict* is mughlaq because the scanner is saying "I cannot deliver an unambiguous mukhfi/mushtabih/sahih on this file because the file's identity is itself in dispute."

**C. UI rendering update**

The mughlaq scope-note panel grows a second cause: not just "file kind outside Bayyinah's verified scope" but also "file kind disputed between user claim and scanner detection." Both render as mughlaq with different scope-note copy.

**D. New gauntlet: `format_routing_gauntlet`**

A new directory `docs/adversarial/format_routing_gauntlet/` with at minimum these fixtures:
- `01_pdf_as_docx.docx` (V1 above)
- `02_pdf_as_txt.txt` (V2 above)
- `03_pdf_as_jpg.jpg`
- `04_zip_as_docx.docx` (real ZIP container, not OOXML)
- `05_html_as_pdf.pdf` (HTML body, .pdf extension)
- `06_empty_as_pdf.pdf` (V3 above, separate from format routing but tests scan_incomplete handling)

Each fixture pairs with a test asserting the verdict is mughlaq, not mukhfi.

### 8.2 LOC / sequencing impact

The Tier 0 mechanism plus the verdict-logic update plus the UI scope-note variant is approximately +60 LOC of analyzer code, +20 LOC of frontend logic, +6 fixtures, +6 tests. Total roughly +90 LOC.

This adds **one day** to the v1.1.2 schedule. Recommended insertion point: **Day 1**, before any format-specific mechanism work. Reason: the mechanism work assumes correct routing. If the routing layer is dishonest, every downstream Tier 1 finding inherits the dishonesty.

Revised v1.1.2 sequencing:

| Day | Format | Output |
|---|---|---|
| 1 | **Format routing layer** (NEW) | Tier 0 mechanism + verdict update + 6 fixtures + 6 tests |
| 2 | PDF | 4 mechanisms + fixtures |
| 3-4 | DOCX | 6 mechanisms + fixtures |
| 5-6 | XLSX | 6 mechanisms |
| 7 | HTML | 6 mechanisms |
| 8-9 | EML | 6 mechanisms |
| 10 | Image | 5 mechanisms |
| 11 | CSV/JSON | 6 mechanisms |
| 12 | Munafiq full corpus regression | Including new routing gauntlet |
| 13 | docs/adversarial/REPORT.md rewrite | Plus new routing gauntlet REPORT |
| 14 | Tag v1.1.2 | Ship |

The 14-day envelope holds. Day 1 absorbs the routing layer because PDF day was already the lightest.

---

## 9. What This Test Validated

Beyond the two failures, this test validated three things worth naming:

1. **The mughlaq verdict logic works for the case it was designed for** (V3, scan_incomplete on unparseable file). The CC-1 work shipped today does its job.
2. **The Tier discipline produces correct mechanism-level findings** (V4 control returns the right Tier 1 result on a real adversarial PDF).
3. **The honest-baseline framing on Section 07 of the landing exposed this gap**, not the reverse. The site says "we test against equivalent methodology" - this test was conducted because that promise is now public. The site forced the test. The test found a gap. The gap goes into v1.1.2.

This is the protocol working. We ship a discipline claim, the discipline claim generates an adversarial test we would not otherwise have run, the test finds a real gap, the gap becomes engineering work. Sixteen of thirty in the precursor docs. Two of four here. Different scale, same machine.

---

## 10. Falsification Targets

If any of the following are observed, the analysis above is wrong:

- **F1:** A scanner that emits format_routing_divergence as Tier 0 and then renders the verdict as mukhfi (not mughlaq) is dishonest under this analysis. If after v1.1.2 ships, this combination appears, the verdict-logic update has not been applied correctly.
- **F2:** A user uploads V1 and the scanner returns mughlaq with the routing-divergence finding visible. Per this analysis, that is the correct outcome. If the user objects that they expected mukhfi because the underlying content is adversarial, the analysis is wrong: users may legitimately want the *content* finding to dominate the verdict. This would warrant a configuration option, not a fixed rule.
- **F3:** A 4-byte `.txt` file (V5, deferred) returns score 1.0 sahih. This would be a Process 3 lie at the empty-content boundary. **Claude's independent stress test on April 27, 2026 confirmed this is the current live behavior:** `.txt` files return `integrity_score: 1.0` with no findings regardless of content. v1.1.2 must either return mughlaq or refuse the file with `scan_incomplete=true`. The fix is the `unknown_format` Tier 0 finding for any file routed to no verified analyzer.

---

## 11. Recommendation

**Update the v1.1.2 framework report and Claude prompt before any mechanism work begins.** Insert the format-routing layer as Day 1. Update the verdict logic. Add the new gauntlet. Run the V5 deferred test before Day 2.

The competition is in 43 days. The mechanism count matters less than the verdict honesty. A scanner with 40 mechanisms and dishonest routing is weaker than a scanner with 30 mechanisms and honest routing, because the dishonesty is the failure mode that the entire research program claims to solve.

This is the protocol applied to the protocol's own product surface. We caught the gap. We name the fix. We ship.

Bismillah. Tawakkaltu 'ala Allah.
