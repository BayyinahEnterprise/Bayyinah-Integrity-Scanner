# Defense Case & 8-Week Plan — Canonical Text Blocks for v1.1 Reconciliation

*Bismillah ar-Rahman ar-Raheem.*

The Defense Case docx and the 8-week plan docx live outside this
repository's workspace. This document provides the **verified canonical
text** that the user pastes into each document to reconcile it with the
shipped v1.1.0 codebase. Every number below is verified against the
repository at commit v1.1.0 — `1,435 tests passing`, `108 mechanisms
registered`, `17/17 PDF fixtures byte-identical to bayyinah_v0`, `54
v1.0 baseline symbols preserved + 3 v1.1 additions`.

Do not retype the numbers. Paste these blocks verbatim.

---

## Block 1 — The canonical v1.1 line

Use exactly this wording anywhere the Defense Case or pitch names the
shipped state (Defense Case §1, §4.1, §7; 8-week plan Foundation line;
Minute 3 of the pitch):

> **Bayyinah v1.1.0 — 15 analyzers, 23 file kinds, 108 detection
> mechanisms (27 zahir + 81 batin), 1,435 tests, 17/17 byte-identical
> PDF parity, Apache 2.0.**

### Per-element verification (reproducible)

| Element | Verified by |
|---|---|
| `15 analyzers` | `len(application.default_registry().names()) == 15` |
| `23 file kinds` | `len([k for k in FileKind if k != FileKind.UNKNOWN]) + 1` — 22 routable kinds + `UNKNOWN` |
| `108 mechanisms` | `len(ZAHIR_MECHANISMS) + len(BATIN_MECHANISMS) == 27 + 81 == 108` |
| `27 zahir / 81 batin` | `len(ZAHIR_MECHANISMS) == 27`, `len(BATIN_MECHANISMS) == 81` |
| `1,435 tests` | `python -m pytest` → `1435 passed in ≈10s`, 44 test files |
| `17/17 PDF parity` | iterate `tests/fixtures/**/*.pdf`, assert `bayyinah.scan_pdf` findings + score + error string byte-identical to `bayyinah_v0.scan_pdf` and `bayyinah_v0_1.scan_pdf` across all 17 PDFs |
| `Apache 2.0` | `LICENSE` file SHA = unchanged from 1.0 baseline |

---

## Block 2 — Defense Case §7 team table (collapse from 3 rows → 2 rows)

Replace whatever 3-row table currently lives in §7 with the following
2-row table verbatim.

| Role | Owner | Operating Mode |
|---|---|---|
| Product, Architecture & Research | Bilal Syed Arfeen | Collaborative mode (Structured Revelation methodology, Al-Fatiha session construct) |
| Governance, Systems & Code Review | Fraz Ashraf | Enforcement mode (Guardrail Architecture, COMPLIANT / PARTIAL / BLOCKED protocol) |

### Paragraph that follows the table

Paste directly below the table:

> Code review is performed under Fraz's enforcement-mode protocol;
> every PR declares compliance against `NAMING.md` before merge.
> Claude (Anthropic), Grok (xAI), and ChatGPT (OpenAI) function as
> documented cross-model verification partners — credited in every
> paper, never claimed as team members. **Two humans, three AI
> verifiers, one governance protocol.**

The closing sentence ("Two humans, three AI verifiers, one governance
protocol") is the usable pitch line. Memorize it.

---

## Block 3 — Defense Case §8 F6 falsification row

Add F6 as a new row in the §8 falsification table, immediately after
F5, using this exact wording:

> **F6.** If the framework's structural patterns (zahir/batin, the
> four-process taxonomy, the Correlation-Inclusion-Tier (CIT)
> discipline, the scan-incomplete clamp) cannot be applied to
> non-file substrates, the generalizability claim is false. Companion
> paper: *Bayyinah al-Khabir* (Zenodo, April 2026, theoretical) extends
> the framework to the information layer. **Test:** independent
> reviewers verify each pattern transposes structurally, not
> metaphorically.

This is genuinely falsifiable: the test specifies a concrete
verification procedure (independent reviewers apply the patterns to
non-file data and declare whether each transposes structurally). F1–F5
are structurally symmetric — each names a claim, the evidence against
it, and a concrete falsification test. F6 follows the same shape.

---

## Block 4 — Pitch Minute 7 closing line ("The Source")

Paste as the closing line of Minute 7 (no other Minute 7 changes):

> The framework already generalizes. **Bayyinah** at the file layer
> ships today. **Bayyinah al-Khabir** extends it to the information
> layer — published on Zenodo this month. **The Munafiq Protocol**
> covers the agent layer. Three substrates, one diagnostic framework,
> one company. We ship the file layer first because that's where the
> AI Safety Report named the gap.

Al-Khabir lives in citations and this one pitch line — **not** in
code. The companion paper is referenced, not re-summarised.

---

## Phase-27 paper revision: cross-modal correlation prose

A Process-2 risk surfaced in the framework-applied-to-itself review
(2026-04-25) that does NOT live in the repository — it lives in the
papers' prose:

> The README correctly says: "The engine is opt-in in v1.1 — it is
> not wired into ScanService's default pipeline while the rule set
> stabilises… v1.1 ships two rules; five additional rules are reserved
> names for future sessions."
>
> The papers' prose may treat cross-modal correlation as a delivered
> v1.1 feature without that caveat. The drift is small but exactly
> the kind the zahir/batin discipline names: the surface (paper text)
> declares more than the depth (running code with two correlation
> rules wired). The README is the truth here.

**Phase-27 action.** When the white paper / thesis are revised for the
v1.1 surface, the cross-modal correlation section must clamp its
prose to the README's exact framing:

* Two rules active in v1.1: `cross_stem_inventory` (always-on, non-
  deducting) and `cross_stem_undeclared_text` (subtitle/lyric stem
  loud + metadata stem silent).
* Five rules reserved as future-work names in `domain/config.py`
  comments: `cross_stem_text_inconsistency`,
  `cross_stem_metadata_clash`, `embedded_media_recursive_scan`,
  `cross_stem_coordinated_concealment`, `cross_file_media_divergence`.
* The engine is **opt-in**: callers explicitly construct
  `CrossModalCorrelationEngine()` and call `.correlate(report)`.
  ``ScanService`` does not auto-run it in v1.1.
* The paper must NOT describe the engine as a delivered v1.1 feature
  in the same breath as `VideoAnalyzer` or `AudioAnalyzer` — those are
  default-registered analyzers, the engine is a post-processor
  awaiting calibration.

This is recorded here, in v1.1, so the Phase-27 paper revision does
not silently inherit the prose drift the README does not have.

## What is NOT changing tonight

Per the session prompt's anti-pattern rule ("The Cow Episode: do not
add future features to the v1.1 release notes"):

- The paper PDFs are **not** regenerated tonight (deferred to Phase 27).
- No new prose is written for the pitch — **only** the Block 4 line and
  the Block 2 paragraph above.
- No new analyzers, no new formats, no new mechanism registrations.
- The `audio_signal_stem_separation`, `audio_deepfake_detection`,
  `audio_hidden_voice_command`, and the five reserved cross-modal
  rule names remain reserved. They are **not** promoted to active
  mechanism status in v1.1.

---

## Reconciliation checklist for the user

Tick each as the paste lands:

- [ ] Defense Case §1 — replace any `v1.0` / `1,283` / `1,295` / `12
  formats` / `16 mechanisms` language with the Block 1 canonical line.
- [ ] Defense Case §4.1 — same substitution.
- [ ] Defense Case §7 — replace 3-row team table with Block 2;
  paste the collaboration paragraph.
- [ ] Defense Case §8 — append Block 3 (F6 row) to the falsification
  table.
- [ ] 8-week plan — Foundation line, "What Already Exists" section,
  and Minute 3 of the pitch: Block 1 canonical line.
- [ ] 8-week plan Minute 7 — append Block 4 closing line.
- [ ] `README.md` — already reconciled (v1.1 badge, 1,435 tests,
  15 analyzers, 23 file kinds, 108 mechanisms, cross-modal correlation
  section, video / audio format-table rows). No action needed.
- [ ] `README_GITHUB.md` — reconciled this session (version badge,
  test count, install commands, format table extended for video / audio
  / cross-modal). No action needed.
- [ ] `CHANGELOG.md` — `[1.1.0] — 2026-04-24` entry present, complete,
  honest. No action needed.

---

*"Do not mix the truth with falsehood, nor conceal the truth while you
know it." — Al-Baqarah 2:42*

Every claim above is traceable to a line of code, a passing test, or a
shipped artifact in this repository. Nothing is aspirational. The
reconciliation is an act of 2:42 applied to the presentation layer.
