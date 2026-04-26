# The Research Program Stack — How Bayyinah Sits Among the Layers

*Bismillah ar-Rahman ar-Raheem.*

Bayyinah is one of six artifacts in an integrated research program on
structural honesty in artificial systems. This document maps the
relationships so any reader of this repository can locate Bayyinah's
specific contribution and trace the citation chain.

The program has one shipped artifact (Bayyinah), one published
foundational paper (the Munafiq Protocol), two published methodology
papers (the Fatiha Construct, Structured Revelation), and three
theoretical papers (Furqan, Al-Khalifa, Bayyinah al-Khabir). Every
theoretical paper cites Bayyinah as its empirical foundation. That
is what makes this repository's auditable state load-bearing for the
program's claims.

---

## The four-layer integrity stack

The diagnostic framework in this program operates on four substrates.
The same structural primitives — *zahir / batin*, the four-process
taxonomy (Aligned / Compliant / Performing / Misaligned), the
Correlation-Inclusion-Tier (CIT) discipline, the additive-only
invariant, the scan-incomplete return type — are applied at each
layer.

| Layer | System | Substrate | Status | Diagnostic question |
|---|---|---|---|---|
| 1. File | **Bayyinah v1.1.0** *(this repository)* | documents and media files | **shipped** | Does this file's surface match its depth? |
| 2. Information | Bayyinah al-Khabir | news reports and broadcast media | theoretical (published on Zenodo) | Does this source's reporting match the cross-source evidence? |
| 3. Agent — diagnostic | Munafiq Protocol | AI systems with inspectable internals | **published** (DOI 10.5281/zenodo.19677111) | Does this system's output match its internal state? |
| 4. Agent — architectural | Al-Khalifa | autonomous super agents | theoretical | Does this agent's behavior match its declared scope and purpose hierarchy? |

The four layers are not parallel projects. They are the **same
diagnostic framework on four different substrates**. Bayyinah's
twenty-seven *zahir* mechanisms detect surface-level concealment in
files; Bayyinah al-Khabir extends the same analytical primitives to
broadcast text; the Munafiq Protocol applies them to model output
inspection; Al-Khalifa builds them into the agent's runtime so the
agent's own behaviour is structurally honest by construction.

---

## Cross-cutting artifacts

Two papers do not live at one layer — they cut across all of them.

### Furqan (Thesis v1.0) — the language

Formalizes the behavioural conventions that operated in Bayyinah's
development as **language primitives**. Seven primitives:

* `bismillah` blocks (scope declaration with `authority` / `serves` /
  `scope` / `not_scope`)
* `zahir` and `batin` types (surface-depth verification)
* additive-only modules (compiler-enforced symbol persistence)
* `mizan` constraints (three-valued calibration: `la_tatghaw` /
  `la_tukhsiru` / `bil_qist`)
* `tanzil` build ordering (phased compilation with regression gates)
* ring-composition verification (opening-closing structural check)
* `marad` error types (diagnosis-structured errors)

…plus `scan_incomplete` as a return type and the Fatiha Construct as
a session protocol enforced at the IDE level.

**Bayyinah is Furqan's empirical foundation.** Every primitive existed
as a behavioural convention in this repository's development before
being proposed as a language feature. The validation map is in
`history/FURQAN_CORRESPONDENCE.md`.

No compiler exists. The paper is theoretical and falsifiable — eight
falsification criteria (F1–F8) define controlled studies that would
disprove specific claims.

### The Fatiha Construct (v1.0) — the session methodology

The seven-step session protocol that produced every phase of
Bayyinah's development. Each step maps to a verse of Surah al-Fatiha:

| Step | Verse | Engineering function |
|---|---|---|
| 1. Bismillah | 1:1 | Scope declaration: authority, optimization function, scope boundary |
| 2. Alhamdulillah | 1:2 | State acknowledgment: current test count, working components, what does not exist |
| 3. Ar-Rahman ar-Rahim | 1:3 | Calibration: MDL discipline, permitted deps, FRaZ awareness |
| 4. Maliki Yawm ad-Din | 1:4 | Deadline awareness: time budget, 20% skip rule |
| 5. Iyyaka Na'budu | 1:5 | Orientation check: am I building the deliverable or performing the appearance? |
| 6. Ihdina as-Sirat | 1:6 | Task execution in priority order with named deliverables |
| 7. Sirat Alladhina | 1:7 | Anti-pattern avoidance with specific historical examples |

Bayyinah's CHANGELOG is the externally-verifiable record of what the
Fatiha Construct produced when applied across 25+ phases. Every phase
prompt in this program followed the seven-step structure.

The construct is *recalibrational*, not informational. It works
because it is re-executed every session — the engineering analogue
of al-Fatiha being recited 17× daily across the five prayers.

---

## Lineage in one diagram

```
                            ┌─ Bayyinah (file)              [shipped, 1.1.0]
                            │
   Munafiq Protocol  ───────┼─ Bayyinah al-Khabir (info)    [theoretical]
   [published, the          │
    foundational            ├─ Al-Khalifa (agent)           [theoretical]
    diagnostic              │
    framework]              │
                            └─ Furqan (language)            [theoretical]
                                  │
                                  └─ formalizes Bayyinah's behavioural
                                     conventions as language primitives;
                                     Bayyinah is Furqan's empirical
                                     foundation

   Fatiha Construct ─── the session protocol that produced
   [published]          every phase of every artifact above

   Computational Tawhid ─── the ontological foundation:
   [theoretical]            reality as divine computation,
                            the Mizan principle (55:7-9) as
                            calibration, consciousness as
                            fundamental
```

---

## What it means for this repository

Bayyinah's auditable state is the **anchor** of the program's
empirical claims. If anyone questions whether Furqan's primitives are
implementable or whether Al-Khalifa's runtime constraints can govern
real software, the answer is: every Furqan primitive operated as a
Bayyinah convention before being proposed; every Al-Khalifa runtime
constraint corresponds to a Bayyinah workflow that produced 1,435
verified tests with zero cross-phase regressions and 17/17
byte-identical PDF parity. The theoretical papers do not assert
capabilities; they generalize observed-and-verifiable patterns.

This places three responsibilities on this repository:

1. **The numbers must remain auditable.** The CI workflow asserts
   the MD5 of `bayyinah_v0.py` and `bayyinah_v0_1.py` on every push;
   the test count is regenerated by `pytest`; the public surface is
   regression-checked. None of this is documentation — it is
   continuously verified evidence.

2. **The conventions must remain visible.** `NAMING.md`,
   `CONTRIBUTING.md`, `CHANGELOG.md`, and the per-file docstrings
   together carry the conventions Furqan formalizes. A new
   contributor who does not read NAMING.md cannot follow the
   conventions Furqan claims this codebase validates.

3. **The future-work register must remain honest.** The reserved
   names in `domain/config.py` comments (`audio_signal_stem_separation`,
   `audio_deepfake_detection`, `audio_hidden_voice_command`,
   `cross_stem_text_inconsistency`, `cross_stem_metadata_clash`,
   `embedded_media_recursive_scan`,
   `cross_stem_coordinated_concealment`, `cross_file_media_divergence`)
   are Bayyinah's analogue of Furqan's `scan_incomplete` return
   type: a structural acknowledgement that the work is incomplete,
   *named* so the reader cannot mistake silence for absence.

---

## Citation references

Short-form references for cross-document citation. Long-form citations
live in `CHANGELOG.md` and the white paper / thesis (the latter
deferred to Phase 27 for the v1.1 surface).

* **Bayyinah White Paper v1.1** — Arfeen, B. S. & Claude (Anthropic,
  Opus 4.6). (2026). *Bayyinah: Detecting concealed adversarial content
  in digital documents.*
* **Bayyinah Thesis v1.1** — Arfeen, B. S. & Claude (Anthropic, Opus
  4.6). (2026). *Bayyinah as input-layer defense in artificial-system
  safety pipelines.*
* **Munafiq Protocol** — Arfeen, B. S., Claude (Anthropic, Opus 4.6),
  & Grok (xAI). (2026). *Detecting performed alignment in artificial
  systems: The Munafiq Protocol.* Zenodo.
  https://doi.org/10.5281/zenodo.19677111
* **Bayyinah al-Khabir** — Arfeen, B. S. & Claude. (2026).
  *Bayyinah al-Khabir: Information-layer integrity scanning across
  national broadcast sources.* Zenodo.
* **Furqan** — Ashraf, F., Arfeen, B. S., Claude, Grok, & Perplexity
  Computer. (2026). *Furqan: A programming language with structural
  honesty, calibrated optimization, and surface-depth type
  verification derived from Quranic computational architecture.*
  Thesis Paper v1.0.
* **Al-Khalifa** — Arfeen, B. S., Claude, Grok, & Perplexity Computer.
  (2026). *Al-Khalifa: A Furqan-based super agent architecture for
  structurally honest autonomous project stewardship.* Theoretical
  Paper v1.0.
* **The Fatiha Construct** — Arfeen, B. S. & Claude. (2026). *The
  Fatiha Construct: A seven-step recursive session protocol for
  human-AI collaborative development.* v1.0.
* **Structured Revelation** — Arfeen, B. S. & Claude. (2026).
  *Structured Revelation as Prompt Architecture: Quranic compression
  principles applied to human-AI collaborative software development.*
* **Computational Tawhid** — Arfeen, B. S. (2026). *A thesis on divine
  computation, consciousness, and the structure of reality in Islamic
  ontology.*

---

*"Indeed, in the creation of the heavens and the earth, and the
alternation of the night and the day… are signs for a people who use
reason."* — Al-Baqarah 2:164

The reasoning is the work. The signs are the structure. Bayyinah is
the file-layer witness; the program is the multi-layer reading.
