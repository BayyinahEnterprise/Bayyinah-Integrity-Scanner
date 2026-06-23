# Differential testing architecture (v1.8.0)

Canonical document for Bayyinah's external-witness testing layer.
Introduced at v1.8.0 (Round 18) per `CODING_STRATEGY_v1_2_4_to_v2_0.md`
§6 v1.8.0 Fatiha session.

Verse anchor: al-Baqarah 2:282 ("And call two witnesses from among
your men"). The architectural reading: Bayyinah's existing test suite
witnesses its own behavior only. The README invokes the two-witnesses
principle but Bayyinah is currently the only witness to its own
output. Q8 in `QUESTIONS.md` names this gap and asks which external
witness layer is prioritized. The v1.8.0 closure: prioritization
order documented here; first witness (pdfid) shipped; subsequent
witnesses queued.

## §1 The witness gap

Bayyinah's test taxonomy at v1.7.0:

- **Fixture-pinning tests** (`tests/test_fixtures.py` and per-format
  test modules): assert that `bayyinah.scan_pdf(path).to_dict()` is
  byte-identical to `bayyinah_v0.scan_pdf(path).to_dict()`. These
  pin parity with the reference implementation.
- **Contract pin tests** (`tests/contracts/`): pin the documented
  score-function shape (`docs/score.md`), clamp truth-table, budget
  controller honest accounting (`docs/budget.md`), cross-modal
  policy (`docs/cross_modal.md`).
- **Integration tests** (`tests/test_integration.py`,
  `tests/test_fixtures.py`): exercise the analyzer registry,
  scan_service merge logic, and report serialization.

What is missing at v1.7.0:

- **External witnesses**: no test compares Bayyinah's finding count
  on a fixture to an independent tool's finding count on the same
  fixture. The two-witnesses principle the README invokes is not yet
  applied to Bayyinah itself.
- **Property-based tests on the score function**: the score is
  `clamp(1.0 - sum(severity * confidence), 0, 1)`; its idempotence,
  monotonicity, and range invariants are not yet pinned over the
  space of plausibly constructed finding lists.
- **Mutation testing**: do the existing tests fail when an analyzer
  is silently broken? Deferred to a later release.
- **Adversarial fuzzing of FileRouter**: polyglot dispatch under
  malformed input. Deferred to a later release.

## §2 Witness contract

A differential witness is an external tool (or alternative
implementation) that consumes the same input file as Bayyinah and
emits a finding-equivalent observation. The contract for a
differential witness at v1.8.0:

### §2.1 Shape

A witness implements `DifferentialWitness` (an abstract base
class declared in `tests/differential/witness_contract.py`) and
returns a list of `WitnessFinding` records for a given file:

    @dataclass(frozen=True)
    class WitnessFinding:
        witness_name: str        # the tool emitting the finding
        finding_key: str         # the witness's mechanism name
        location: str            # a structural reference if known

### §2.2 Witness divergence

A differential pair compares `bayyinah_findings` and
`witness_findings` for a fixture and emits a `WitnessDivergence`
record when one of three conditions holds:

1. **Solo-Bayyinah**: Bayyinah fired a finding the witness did not.
2. **Solo-witness**: the witness fired a finding Bayyinah did not.
3. **Distinct-locus**: both fired equivalent findings but at
   different locations.

Divergence is not failure. A differential pair surfaces divergence
as evidence the project-lead reviews. The verse 2:282 reading: two
witnesses agreeing strengthens a finding; disagreement is a question,
not necessarily an error.

### §2.3 Skip behavior

External tools are optional dependencies. A witness that cannot
import its tool MUST be skipped via `@pytest.mark.skip` or
`@pytest.mark.skipif`, never silently passed. The skip message MUST
include the install hint for the missing tool. This preserves the
two-witnesses principle: a missing witness is reported, not silently
suppressed.

## §3 Prioritization order (Q8 closure)

The Q8 question lists four external witness candidates: pdfid,
oletools, yara, clamav. The v1.8.0 prioritization order, ranked by
threat-model overlap with Bayyinah's existing coverage and by
dependency-install footprint:

### §3.1 Priority 1: pdfid (shipping at v1.8.0)

Tool: Didier Stevens' `pdfid.py`. Scope: structural address-space
inspection of PDFs (`/JavaScript`, `/JS`, `/OpenAction`, `/AA`,
`/JBIG2Decode`, `/EmbeddedFile`, `/XFA`, `/Colors > 2^24`). Overlap
with Bayyinah: HIGH on `additional_actions`, `embedded_javascript`,
`embedded_attachment`. Install footprint: pure-Python single file.

Rationale for priority 1: pdfid is the canonical structural-address
PDF inspector. Bayyinah's PDF analyzer makes claims about the same
address space; pdfid is the natural two-witness counterpart.

### §3.2 Priority 2: oletools (deferred to v1.8.1 or later)

Tool: Decalage's `oletools` suite (`olevba`, `oledir`,
`oleobj`, `mraptor`). Scope: OLE / Office Open XML / DOCM / XLSM
macro and structural inspection. Overlap with Bayyinah: HIGH on
DOCX macro detection and embedded-object surfacing once Bayyinah's
DOCX analyzer reaches deeper macro coverage. Install footprint:
single pip dependency.

Deferred to v1.8.1 because Bayyinah's DOCX coverage is calibrated
through earlier rounds (Phase 13+); the v1.8.0 release focuses on
PDF where the witness gap is widest.

### §3.3 Priority 3: yara (deferred to later release)

Tool: VirusTotal's `yara-python` bindings. Scope: rule-based content
matching. Overlap with Bayyinah: MEDIUM on `tag_characters`,
`white_on_white`, `bidi_control`. Install footprint: native
extension (libyara + Python bindings).

Deferred because (a) install footprint is heavier, (b) yara is
rule-driven rather than structural, so the witness-shape mapping
requires per-fixture rule authoring (out of scope for v1.8.0 HEAVY
intensity).

### §3.4 Priority 4: clamav (deferred to later release)

Tool: ClamAV's `clamd` daemon + `pyclamd` client. Scope: signature-
based malware detection. Overlap with Bayyinah: LOW (clamav is
malware-signature driven; Bayyinah is concealment-shape driven).
Install footprint: heaviest (system daemon, signature database).

Deferred because the threat-model overlap is the lowest of the four
candidates; a clamav differential pair will surface "we agree on
nothing" most of the time, which is honest but does not advance the
two-witnesses thesis as productively as the higher-overlap pairs.

## §4 Property-based score tests (v1.8.0)

The score function `compute_muwazana_score` and verdict resolver
`tamyiz_verdict` have continuous-domain invariants that the existing
fixture-pinning tests sample but do not pin universally. v1.8.0
introduces Hypothesis-based property tests pinning four invariants:

### §4.1 Range invariant

For any list of findings, `0.0 <= compute_muwazana_score(findings) <= 1.0`.

### §4.2 Empty-list invariant

`compute_muwazana_score([]) == 1.0`. A scan with no findings produces
a perfect score per `docs/score.md` §1.

### §4.3 Idempotence

`compute_muwazana_score(findings)` called twice on the same list
returns the same float.

### §4.4 Monotonicity in finding count (saturating)

Adding a finding with non-zero severity to a list never INCREASES
the score. Per `docs/score.md` §1 the score is monotonic non-
increasing in severity * confidence.

### §4.5 Saturation at zero

A list of findings whose `sum(severity * confidence)` exceeds 1.0
saturates the score at 0.0; subsequent additions cannot drive it
negative.

These properties are pinned by Hypothesis strategies over
synthetically constructed `Finding` lists with bounded severity
and confidence. Hypothesis is added to
`[project.optional-dependencies] dev` at v1.8.0 (capped at the
current major).

## §5 What v1.8.0 does NOT do

The v1.8.0 release does NOT:

1. Mandate pdfid in `[project.dependencies]`. The differential test
   skips cleanly when pdfid is not installed; the `dev` extra adds
   it for development environments.
2. Author the oletools, yara, or clamav witnesses. Those are
   queued per §3.
3. Add mutation testing. Deferred to a later release per Q8
   prioritization (the four named tools come first).
4. Modify `compute_muwazana_score` or `tamyiz_verdict` behavior.
   The property-based tests pin the EXISTING behavior; any
   modification that breaks a pinned property requires the parity-
   break ceremony per `PARITY.md`.
5. Change the `IntegrityReport` schema. Witness divergence records
   live in the differential test results, not in the report.

## §6 Cross-references

- `tests/differential/witness_contract.py` -- `DifferentialWitness`
  ABC + `WitnessFinding` / `WitnessDivergence` dataclasses.
- `tests/differential/test_pdfid_witness.py` -- Priority 1 pdfid
  differential pair (skipped when pdfid not installed).
- `tests/contracts/test_score_properties.py` -- Hypothesis-based
  property tests for §4.1-§4.5.
- `docs/score.md` -- score-function contract that the property tests
  pin.
- `pyproject.toml` -- `hypothesis` and `pdfid` added to `dev` extra
  at v1.8.0.
- `QUESTIONS.md` Q8 -- closure log entry citing this document.
- `PARITY.md` -- parity-break ceremony required for any score-
  function modification that breaks a pinned property.
- `CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v1.8.0 -- release plan
  (HEAVY audit-intensity).
