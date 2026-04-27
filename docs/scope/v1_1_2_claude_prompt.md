# v1.1.2 Execution Prompt (Claude)

> "And do not pursue that of which you have no knowledge. Indeed, the hearing, the sight and the heart - about all those one will be questioned." - Al-Isra 17:36

You are implementing Bayyinah Integrity Scanner **v1.1.2**. This prompt is the invocation. The plan is [v1_1_2_framework_report.md](v1_1_2_framework_report.md). Read it first, then execute under the rules below.

---

## 1. Identity of the Release

- **Name:** v1.1.2 - Adversarial Gauntlet Closure + Format Routing Layer
- **Win condition:** Depth, not breadth. Close the existing 42-fixture gauntlet AND add a Tier-0 format-routing layer. Do not add file kinds.
- **Honest baseline (v1.1.1):** 2/42 caught full, 2 partial, 38 missed. PDF is the only format with any catches. Mughlaq Trap stress test (April 27, 2026) revealed an additional class: silent format routing divergence. 2 of 4 vectors FAIL - polyglot (PDF magic + .docx ext) and spoofed (PDF magic + .txt ext) both return mukhfi instead of mughlaq because the scanner trusts magic bytes over extension without disclosing the routing decision. See [docs/adversarial/mughlaq_trap_REPORT.md](../adversarial/mughlaq_trap_REPORT.md).
- **Target (v1.1.2):** Every published adversarial fixture caught with at least one Tier-1 or Tier-2 finding. Every format-routing fixture caught with a Tier-0 finding that floors the verdict at mughlaq. No false positives on the clean corpus.

---

## 2. Framework Rules (verbatim, non-negotiable)

1. **No em-dashes** in any user-facing prose, README, doc, commit message, or output string. CSS and JS comments are exempt. Use ` - ` (space-hyphen-space) instead.
2. **Tier discipline.** Every new finding declares its tier in the code:
   - Tier 0 = routing transparency (format claimed by extension diverges from format inferred from magic bytes; scanner cannot decide which is canonical). Tier 0 findings floor the verdict at **mughlaq** regardless of downstream Tier 1/2/3 findings.
   - Tier 1 = verified evidence (offset, byte count, decoded payload, divergent header value).
   - Tier 2 = structural anomaly (off-page text, microscopic font, oversized cell, prototype-pollution key).
   - Tier 3 = interpretive heuristic. Tier 3 findings must not pull a clean file below 1.0 on their own.
3. **Fixture pairing.** No mechanism ships without a paired fixture in the matching `docs/adversarial/<format>_gauntlet/` directory. If the fixture does not exist, write it before the analyzer.
4. **Atomic commits.** One mechanism per commit. Commit message format: `v1.1.2: <format> <mechanism_name> (Tier <n>)`. Reference the gauntlet REPORT line if applicable.
5. **No silent rewrites.** If you find a v1.1.1 mechanism is wrong, open an ADR before changing it. Do not edit historical fixtures.
6. **Munafiq Protocol.** Before each PR, run the full clean corpus and confirm zero new false positives. A finding that fires on a clean file is a regression, not a feature.

---

## 3. Mechanism Slate (the only work in scope)

Read the per-format REPORT at each path. Implement exactly what is listed. Do not add mechanisms not on this slate.

| Format | Gauntlet REPORT | Mechanisms | LOC budget |
|---|---|---|---|
| Format Routing | [docs/adversarial/format_routing_gauntlet/REPORT.md](../adversarial/format_routing_gauntlet/REPORT.md) | 1 (Tier 0) | ~90 |
| PDF | [docs/adversarial/pdf_gauntlet/REPORT.md](../adversarial/pdf_gauntlet/REPORT.md) | 4 | ~155 |
| DOCX | [docs/adversarial/docx_gauntlet/REPORT.md](../adversarial/docx_gauntlet/REPORT.md) | 6 | ~200 |
| XLSX | [docs/adversarial/xlsx_gauntlet/REPORT.md](../adversarial/xlsx_gauntlet/REPORT.md) | 6 | ~190 |
| HTML | [docs/adversarial/html_gauntlet/REPORT.md](../adversarial/html_gauntlet/REPORT.md) | 6 | ~120 |
| EML | [docs/adversarial/eml_gauntlet/REPORT.md](../adversarial/eml_gauntlet/REPORT.md) | 6 | ~185 |
| Image | [docs/adversarial/image_gauntlet/REPORT.md](../adversarial/image_gauntlet/REPORT.md) | 5 | ~115 |
| CSV/JSON | [docs/adversarial/csv_json_gauntlet/REPORT.md](../adversarial/csv_json_gauntlet/REPORT.md) | 6 | ~155 |
| **Total** |  | **40 mechanisms / 48 finding shapes** | **~1,210 LOC** |

### 3.1 Tier 0 Format Routing Mechanism

The format-routing layer is the first thing the scanner runs after upload, before any per-format analyzer. It is one mechanism with one finding shape:

- **Mechanism:** `format_routing_divergence`
- **Tier:** 0
- **Trigger:** Extension-implied format does not match magic-byte-implied format, OR magic bytes are absent/ambiguous and extension is the only signal, OR file is empty/truncated below the magic-byte window.
- **Effect on verdict:** Tier 0 finding sets a floor of **mughlaq** on the verdict. Downstream Tier 1/2/3 findings still record but cannot raise the verdict above mughlaq while routing is unresolved.
- **Disclosure requirement:** The finding's `evidence` field must include `claimed_format` (from extension), `inferred_format` (from magic bytes), `routing_decision` (which path the scanner actually took), and `bytes_sampled` (count of leading bytes inspected).
- **Fixtures (6):** polyglot (PDF magic + .docx ext), spoofed (PDF magic + .txt ext), empty (4-byte .pdf), truncated (PDF header but no EOF), mismatched (DOCX zip + .xlsx ext), control (real .pdf).
- **Reference fixture set:** `/home/user/workspace/mughlaq_trap/` (v1-v4) is the seed; expand to 6 in `docs/adversarial/format_routing_gauntlet/fixtures/`.

---

## 4. Sequencing (14 days, ordered)

Work the slate in this order. Do not parallelize across formats - the cognitive cost of context-switching exceeds the wall-clock savings. The format-routing layer is Day 1 because every per-format mechanism downstream depends on the routing decision being honest. If routing is silent, every other mechanism is built on sand.

| Day | Format | Output |
|---|---|---|
| 1 | Format Routing | Tier 0 `format_routing_divergence` + 6 fixtures + green gauntlet + verdict-floor wiring |
| 2 | PDF | 4 mechanisms + matching fixtures + green gauntlet |
| 3-4 | DOCX | 6 mechanisms + fixtures + green gauntlet |
| 5-6 | XLSX | 6 mechanisms (one shared `_office_metadata_payload` with DOCX) |
| 7 | HTML | 6 mechanisms |
| 8-9 | EML | 6 mechanisms |
| 10 | Image | 5 mechanisms (JPEG APPn + SVG family) |
| 11 | CSV/JSON | 6 mechanisms |
| 12 | Full corpus regression. Munafiq run. Re-run Mughlaq Trap (v1-v4 + 2 new). Fix any clean-corpus false positives. |
| 13 | `docs/adversarial/REPORT.md` rewrite with new scores. CHANGELOG, version bump, README pass. |
| 14 | Tag `v1.1.2`, ship. |

---

## 5. Success Criteria

The release ships only when **all** are true:

1. `pytest docs/adversarial/` is green across all 8 gauntlets (format_routing + 7 per-format).
2. Every fixture in `docs/adversarial/*/fixtures/` produces at least one Tier-1 or Tier-2 finding (Tier 0 for format_routing fixtures).
3. Every clean file in the clean corpus scores 1.0 with zero findings.
4. Mughlaq Trap regression: v1 polyglot and v2 spoofed both return verdict=mughlaq with a Tier 0 finding. v3 empty and v4 control retain their April 27 behavior.
5. `docs/adversarial/REPORT.md` reflects the new scores honestly. No rounding up. No marketing language.
6. CHANGELOG entry lists every mechanism with its tier and gauntlet reference.
7. The README's "what we catch" section matches the implemented mechanism slate exactly.
8. No em-dashes anywhere in shipped prose.
9. Live `bayyinah.dev` continues to render the v2 mughlaq verdict for unsupported file kinds. Do not touch that surface.
10. **Version coherence across five surfaces.** `/scan` response `version`, `/version`, `/healthz`, OpenAPI `info.version`, and `pyproject.toml` `[project] version` all report `1.1.2`. Today `/scan` returns `0.1.0` while the others return `1.1.1`; this drift is fixed in the release commit, not deferred.
11. **EML 03 explicitly named as the unfixed fixture.** The 41/42 floor is honest only if `docs/adversarial/eml_gauntlet/fixtures/03_received_chain_anomaly.eml` is named in the release REPORT as the deferred Tier-2 borderline case. No silent rounding.

---

## 6. Explicit Refusals (do not do these)

- **Do not add new file kinds.** No RTF, no Jupyter, no ODF, no MSG, no EPUB, no macro-OOXML in v1.1.2. Those are v1.2.0+ scope per [ADR-001](ADR-001-v1_2_scope.md).
- **Do not add a mechanism without a fixture.** If you cannot construct a fixture that exercises the path, the mechanism is interpretive and belongs in v1.3+ research, not v1.1.2.
- **Do not refactor v1.1.1 analyzers** unless an ADR authorizes it. Add new mechanisms alongside; preserve the audit trail.
- **Do not raise the score floor.** A Tier-3-only finding does not pull a file below 1.0.
- **Do not edit fixtures after they are published.** If a fixture is wrong, mark it deprecated and add a successor. Historical scores must remain reproducible.
- **Do not introduce em-dashes.** Run the sweep before every commit:
  ```
  grep -r "-" --include="*.py" --include="*.md" --include="*.html" . && echo "FOUND - fix before commit" || echo "clean"
  ```
- **Do not collapse Tier 1 and Tier 2.** A structural anomaly is not verified evidence. The user-facing distinction is the entire epistemic claim of the product.
- **Do not let a Tier 0 finding be silenced by a downstream Tier 1.** Routing transparency is the floor. A polyglot file that also has off-page text is still mughlaq, not mukhfi. The verdict resolver respects the floor.
- **Do not let version drift slide.** If the `/scan` response still reports `0.1.0` after the v1.1.2 bump, the release is not shippable. Version coherence is the lowest-effort honesty surface in the codebase; a regression here would be embarrassing.
- **Do not write marketing copy in code.** Finding `description` fields are forensic, not promotional.

---

## 7. Per-Mechanism Implementation Pattern

Every mechanism follows the same shape. Do not deviate.

```python
# bayyinah/analyzers/<format>/<mechanism>.py

from bayyinah.findings import Finding, Tier

def detect_<mechanism_name>(parsed: <FormatParsed>) -> list[Finding]:
    """
    <One-line description of the structural property being checked.>

    Tier: <1 | 2 | 3>
    Fixture: docs/adversarial/<format>_gauntlet/fixtures/<fixture_name>
    Reference: <gauntlet REPORT.md line or section>
    """
    findings = []
    # ... structural inspection only. No interpretation here.
    if <condition>:
        findings.append(Finding(
            tier=Tier.<N>,
            mechanism="<format>_<mechanism_name>",
            description="<forensic, factual, one sentence>",
            evidence={"<key>": <verifiable_value>, ...},
        ))
    return findings
```

Each mechanism gets a paired test:

```python
# tests/analyzers/<format>/test_<mechanism>.py

def test_<mechanism>_catches_adversarial_fixture():
    findings = detect_<mechanism>(load("docs/adversarial/<format>_gauntlet/fixtures/<file>"))
    assert any(f.tier in (Tier.ONE, Tier.TWO) for f in findings)

def test_<mechanism>_clean_on_clean_corpus():
    for clean in clean_corpus("<format>"):
        assert detect_<mechanism>(clean) == []
```

---

## 8. Commit Discipline

- One mechanism = one commit.
- Commit message: `v1.1.2: <format> <mechanism_name> (Tier <n>)`
- Body: 1-3 sentences. Reference the fixture path and the gauntlet REPORT line.
- No squash. The audit trail is the product.
- Push after each format's gauntlet turns green, not after each mechanism.

---

## 9. When You Are Stuck

If a mechanism resists implementation:

1. Re-read the fixture. The fixture is the spec.
2. Check whether the gauntlet REPORT names a different structural signal. Use that one.
3. If the structural signal is absent and the only available signal is interpretive, **stop**. Open an issue. Do not promote a Tier-3 heuristic into a Tier-1 claim under deadline pressure. That is exactly the failure mode Al-Baqarah 2:42 names.

> "And do not mix the truth with falsehood, and do not conceal the truth while you know." - Al-Baqarah 2:42

---

## 10. Final Check Before Tagging v1.1.2

- [ ] All 7 gauntlets green.
- [ ] Munafiq Protocol clean run on clean corpus.
- [ ] `docs/adversarial/REPORT.md` rewritten with honest scores.
- [ ] CHANGELOG entry per mechanism.
- [ ] README "what we catch" matches implementation.
- [ ] Em-dash sweep returns clean.
- [ ] No new file kinds added.
- [ ] Live `bayyinah.dev` mughlaq path still works.
- [ ] Tag `v1.1.2`. Push. Ship.

---

Bismillah. Tawakkaltu 'ala Allah.
