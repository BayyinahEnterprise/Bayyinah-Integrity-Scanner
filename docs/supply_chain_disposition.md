# Supply-chain disposition (Q-PRO-4 closure)

Canonical disposition document for the Q-PRO-4 question authored at
v1.6.0 (Round 16) per `CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v1.6.0
Fatiha session.

Verse anchor: al-Baqarah 2:188. Honest accounting includes honest scope
declaration. A scanner that claims to verify supply-chain integrity
because it can read PDFs and ZIPs would be performing alignment on the
buyer's threat model.

## §1 The question

Bayyinah's stated purpose is file integrity scanning: detecting hidden,
concealed, or adversarial content in digital documents. Supply-chain
attacks compromise the pipeline by which a file or binary came to exist:
dependency substitution, build-system tampering, provenance forgery,
signing-key compromise. The boundary between "content integrity" and
"supply-chain integrity" is not always obvious to a reader of the
README. Q-PRO-4 is the question: where does Bayyinah's scope end and
where does the supply-chain ecosystem (SPDX SBOM, CycloneDX SBOM,
in-toto attestations, Sigstore signing, SLSA framework levels)
take over?

## §2 The disposition

Supply-chain detection is OUT OF SCOPE for Bayyinah v1.x and v2.x.

The justification has three parts.

### §2.1 Different witnesses

Bayyinah's witnesses inspect the file as it sits in front of the
analyzer: its structural address space (PDF catalog, DOCX OOXML zip
members), its content layers (text spans, embedded streams, font
encodings), its cross-modal correlations (text-vs-image, declared
vs. rendered). These witnesses are mechanical and deterministic against
the file bytes.

Supply-chain witnesses inspect provenance: which source revision built
this artifact, which dependencies were pulled, who signed the build
attestation, whether the signing key chain is unbroken to a trusted
root. These witnesses are anchored OUTSIDE the file: in a registry,
in an attestation log, in a transparency ledger.

A scanner that claims both kinds of witness without distinguishing them
is conflating threat models. The buyer asking "is this PDF safe to
open" is asking about content. The buyer asking "did this binary come
from a build I trust" is asking about provenance. Both are legitimate;
they are not the same question.

### §2.2 Different ecosystem composition

The supply-chain ecosystem is mature: SPDX is ISO 5962:2021, CycloneDX
is OWASP-stewarded, in-toto is CNCF-graduated, Sigstore is in production
at the Linux Foundation, SLSA is a published framework with documented
maturity levels. The honest engineering decision is to compose with that
ecosystem at the integration tier, not to reimplement it as detectors
inside a content scanner.

Bayyinah's v3.0+ enterprise commercialization arc per `ROADMAP_TO_V5.md`
includes a supply-chain composition interface: the file scanner emits
findings, the SBOM verifier emits attestations, the operator-facing
report joins them. The join point is the operator workflow, not the
analyzer registry. This composition is the structurally honest path,
and it is NOT a v1.x or v2.x deliverable.

### §2.3 Patent-surface boundary

The five immutable patent surfaces per the patent invariant clause
(analyzer registry 130, layer-classification 132/136, producer-signature
calibration 134, verdict aggregator 150, witness emitter 160) describe
content witnesses, not provenance witnesses. Extending any of these
surfaces to ingest SBOM artifacts or in-toto attestations would escalate
to patent counsel as a scope expansion BEFORE merge. The honest scope
boundary at v1.x and v2.x is "what is in the file"; the patent
invariant boundary is the same.

## §3 What this means for the user

If a buyer's question is "did this PDF come from the build pipeline I
trust," Bayyinah is the wrong tool for that question. The buyer should
look at SLSA Build Level 3+ provenance, in-toto layouts, or
SPDX / CycloneDX SBOMs with Sigstore signatures.

If the buyer's question is "what is concealed inside this PDF, this
DOCX, this image, this code file," Bayyinah is the right tool. The
five-verdict mechanic (sahih / mushtabih / mukhfi / munafiq / mughlaq)
applies to content integrity. It does not extend to provenance
integrity.

If the buyer's question is "I want one operator report that joins both
threat models," Bayyinah's v3.0+ enterprise tier per `ROADMAP_TO_V5.md`
plans for this composition. It is not available at v1.x or v2.x and
the project does not claim it is.

## §4 What this disposition does NOT do

The disposition does NOT preclude the following:

1. A user manually correlating Bayyinah findings with an out-of-band
   SBOM or attestation. The two views are complementary; the operator
   does the join.
2. Detection of CONTENT inside a SBOM file (e.g., scanning an SPDX
   document as a markdown file). Bayyinah analyzes the file bytes
   regardless of what the file claims to be.
3. A future v3.0+ release adding a composition interface. That release
   would author its own disposition document superseding this one.

The disposition DOES preclude the following at v1.x and v2.x:

1. Marketing the scanner as supply-chain coverage.
2. Adding analyzers that ingest SBOM, in-toto, or Sigstore artifacts as
   their primary witnesses.
3. Extending the patent claim surface to provenance witnesses without
   patent-counsel review per the patent invariant clause.

## §5 Cross-references

- `README.md` -- scope claims align with this disposition.
- `STRATEGY_TO_V2.md` -- v2.0 commercialization gate excludes supply-chain.
- `ROADMAP_TO_V5.md` -- v3.0+ tier defines composition interface.
- `QUESTIONS.md` Q-PRO-4 -- closure log entry citing this document.
- `CODING_STRATEGY_v1_2_4_to_v2_0.md` §6 v1.6.0 -- release plan.
- `docs/budget.md` -- Q-PRO-3 closure (companion document).
