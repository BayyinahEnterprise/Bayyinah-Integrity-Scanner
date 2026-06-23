# Round 11 Fixture Corpus

**Round:** 11 (multi-layer integrity traps).
**Surfaced:** 2026-05-04 red-team probe of bayyinah.dev v1.2.3.
**Closure target:** v1.2.5.
**Substrate-of-record:** `RETIREMENT_LEDGER.md` Round 11 entry.

## Scope per RETIREMENT_LEDGER.md

> The red-team probe of bayyinah.dev v1.2.3 on 2026-05-04 surfaced
> 4 CRITICAL silent-pass findings and 5 HIGH partial-catches against
> multi-layer integrity traps.

The specific trap classes for the 4 CRITICAL silent-pass findings + 5 HIGH partial-catches are NOT enumerated in `RETIREMENT_LEDGER.md` v1.2.4. The 2026-05-04 red-team probe document is the canonical scope; project-lead provides the document to populate this corpus.

## Status at v1.2.5 scaffold time

This directory holds the SCAFFOLD only. Per CODING_STRATEGY §6 v1.2.5 Cow Episode anchor: do NOT pre-specify the closure mechanism for each trap. For each trap: (1) reproduce empirically against a fixture; (2) write the minimal mechanism that catches it; (3) verify on the fixture and on the PARITY suite; (4) register in `MECHANISM_REGISTRY`.

This README documents the scaffold convention; the actual fixture files are added when the project-lead supplies the 2026-05-04 red-team probe document.

## Fixture convention

Each Round 11 trap is one fixture file named:

```
round11_<severity>_<n>_<short_descriptor>.<ext>
```

Where:
- `<severity>` is `CRIT` for the 4 CRITICAL silent-pass traps; `HIGH` for the 5 HIGH partial-catches.
- `<n>` is 1-indexed within severity class (CRIT_1 through CRIT_4; HIGH_1 through HIGH_5).
- `<short_descriptor>` is a lowercase snake_case substrate-trap descriptor.
- `<ext>` is the trap's file extension (`.pdf`, `.docx`, `.eml`, `.html`, etc.).

Each fixture is accompanied by a sibling text file `round11_<severity>_<n>_<short_descriptor>.expected.txt` containing:

```
expected_verdict: <sahih|mushtabih|mukhfi|munafiq|mughlaq>
expected_finding_mechanism: <mechanism_name from MECHANISM_REGISTRY>
expected_tier: <1|2|3>
trap_class: <one-line natural-language description>
substrate_locus: <which layer carries the concealment>
red_team_probe_reference: <probe document line/section reference if available>
```

## Best-judgement trap-class hypotheses (NOT canonical; awaiting project-lead confirmation)

Per user disposition 2026-06-22 ("use your best judgement") and per substrate-actual empirical check of existing analyzer coverage at v1.2.4 (MECHANISM_REGISTRY = 159 including 9 PPTX mechanisms + 4 PDF mechanisms + 7 each of DOCX/EML/JSON/XLSX + 6 HTML + 5 SVG + 4 image + 7 CSV), the following trap-class hypotheses are PLAUSIBLE candidates for the 4 CRITICAL + 5 HIGH classes the red-team probe surfaced.

**4 CRITICAL silent-pass candidates (genuinely new mechanism work):**

1. **pdf_objstm_concealed_text** -- PDF object streams (`/ObjStm`) compress multiple PDF objects into one stream; v1.2.4's 4 PDF analyzers may not decompress and walk object-stream-internal text. Adversarial trap: hide text inside a PDF object stream that the surface text extractor walks past.

2. **cross_format_payload_pairing** -- existing `cross_format_payload_match` (per `domain/config.py` Phase 12) matches payload strings across files, but the PAIRING variant (payload split across files where neither file alone carries the full payload) is plausibly under-covered. Adversarial trap: half-payload in `cover.pdf`, other half in `cover.docx`, recombine after exfiltration.

3. **html_inline_event_handler_payload** -- HTML inline event handlers (`onload`, `onclick`, etc.) carrying concealed payload; existing `html_template_payload` may not specifically detect inline-event-handler concealment.

4. **xlsx_worksheet_xml_comment_payload** -- XLSX shared strings / worksheet XML carrying concealed payload in XML comments; v1.2.4 has `xlsx_comment_payload` but XML-comment (vs cell-comment) concealment is plausibly under-covered.

**5 HIGH partial-catch candidates (tier reclassifications of existing analyzers):**

1. **svg_defs_unreferenced_text** -- existing analyzer at tier 2/3 (per `domain/config.py` Phase 11); Round 11 evidence likely supports tier 2.

2. **csv_payload_in_adjacent_cell** -- existing analyzer; likely tier 2 currently, upgrade-candidate to tier 2 with raised severity.

3. **eml_header_continuation_payload** -- existing analyzer (Phase 19); header-continuation concealment likely warrants tier upgrade.

4. **json_nested_payload** -- existing analyzer; deep-nesting concealment (depth > current threshold N) may warrant tier upgrade.

5. **xlsx_defined_name_payload** -- existing analyzer; defined-name-as-payload-redirect mechanism likely warrants tier-severity upgrade.

These hypotheses are scaffold-time best-judgement and may differ from the actual 2026-05-04 red-team probe findings. Project-lead disposition is the canonical source.

## Five-place documentation pattern

When each Round 11 closure ships, the five-place pattern applies:

1. **CHANGELOG.md** under `v1.2.5 (round 11 closure)` heading: six-element finding format entry per mechanism.
2. **README.md** repo-root: mechanism count line updated; substrate-kinds count unchanged.
3. **Fixture** in this directory: `round11_<severity>_<n>_<short>.<ext>` + `.expected.txt`.
4. **Pinning test** in `tests/round11/`: `test_round11_<short_descriptor>.py` exercises the fixture and asserts the expected verdict + mechanism.
5. **MECHANISM_REGISTRY entry** in `domain/config.py`: additions to `BATIN_MECHANISMS` (or `ZAHIR_MECHANISMS` per source-layer classification) + `SEVERITY` + `TIER`.

## PARITY contract for v1.2.5

Additive-only per `PARITY.md`. New `MECHANISM_REGISTRY` entries are additions; no existing tier modifications. The v0 / v0_1 / current three-way `to_dict()` byte-identity contract holds because Round 11 mechanisms are NEW additions, not modifications to existing analyzer output shape.

The single exception is the 5 HIGH partial-catch tier reclassifications: these are tier-table modifications. Per `domain/config.py` mechanism-registry coherence assertion, tier changes are additive-permissible if they do not alter the set of mechanisms (only the per-mechanism tier value). The `tests/test_fixtures.py::test_v0_v01_parity` test may flag tier-changed fixtures as expected divergences; the parity-break ceremony in `PARITY.md` applies if any Phase 0 fixture's `to_dict()` output changes byte-for-byte. Per scope: tier reclassifications follow the §6 v1.2.5 "additive-only" constraint; if a tier change forces a `to_dict()` byte change on Phase 0, that change is dispositioned as a `parity-break` issue per v1.3.0 ceremony rather than absorbed silently into v1.2.5.

## Project-lead next action

Provide the 2026-05-04 red-team probe document so this corpus can be populated with the actual 9 trap fixtures. The scaffold above is ready to receive them; the mechanism stubs in `analyzers/` are not yet written pending substrate confirmation per Cow Episode discipline.
