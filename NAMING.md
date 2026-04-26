# Bayyinah: Naming Discipline

**Status:** v1.0, adopted. The scoring and verdict names were resolved in favor of the mundane-scholarly alternatives (`muwazana`, `tamyiz`); the remaining questions at the bottom are notes for future contributors, not blockers.

---

## Purpose

This document is the standing discipline for how Bayyinah draws on Qur'anic and classical Islamic scholarly vocabulary in code. It exists so that (a) the naming stays coherent as the project grows, (b) contributors understand *why* certain names are chosen and others are avoided, and (c) the reverence is layered correctly, no decorative sprinkling, no trivialization.

---

## The core principle

**Surahs name seasons. Classical scholarly methodology names modules.**

Development *phases* are temporal, they have a beginning, an energy, and an end. Naming a phase after a surah ("the al-Kawthar pass") describes the quality of that season of work without claiming the phase *is* the surah. That framing was already in the competition roadmap and it works.

Code *modules*, by contrast, are persistent artifacts. They sit in the repo, get imported by name, show up in stack traces, get published on PyPI. Putting a surah name on a Python class would either flatten the surah or elevate the class; neither is appropriate. Modules should instead draw from the methodological vocabulary of classical Islamic scholarship, tafsir, usul al-fiqh, ilm al-hadith, where the terms are precisely the kind of mundane technical language designed to be used in working analysis.

This is the same distinction that kept Islamic scholarship coherent for a thousand years: reverence for the text, rigor in the method. We apply it to code.

---

## Top-level naming

**Project name: `Bayyinah`** (Surah 98, "The Clear Evidence").

The *project* aspires to be clear evidence of file integrity. This is an aspirational, outward-facing name, and Surah 98's theme, distinguishing the clear from the obscure, is the theological spine of the project. This is appropriate for the repository name and for the top-level `ScanService` instance. Individual code artifacts inside should not themselves claim the name.

**Theoretical grounding: Munafiq Protocol** (DOI: 10.5281/zenodo.19677111).

Already established. Bayyinah applies Section 9 of the Munafiq Protocol (performed-alignment detection at the input layer) to data rather than to agents.

---

## Scanning layer names

The two-layer structure is already in `bayyinah_v0_1.py` as `TextLayerAnalyzer` and `ObjectLayerAnalyzer`. The proposal is to rename them using the tafsir distinction between apparent and inner meaning, which is a near-exact mapping of what the layers actually do.

**`ZahirAnalyzer`**, *zahir* (ظاهر) means the apparent, outer, manifest layer of a text. In tafsir it names the literal surface meaning. In Bayyinah it names the analyzer that reads what the file *renders*, what a human opening the PDF would see. Maps 1:1 to the current `TextLayerAnalyzer`.

**`BatinAnalyzer`**, *batin* (باطن) means the inner, hidden layer. Its tafsir counterpart to zahir. In Bayyinah it names the analyzer that reads what the file *contains*, the object tree, the incremental updates, the embedded streams. Maps 1:1 to the current `ObjectLayerAnalyzer`.

*Note on sectarian history:* the *batini* tradition of esoteric interpretation has specific associations in Islamic history, but zahir/batin as a methodological pair is entirely standard across Sunni and Shi'a tafsir. We are using the methodological pair, not invoking any particular school.

---

## Per-mechanism analyzers (inside `BatinAnalyzer`)

When we do the per-mechanism split deferred from today's refactor, these are the proposed names:

**`NaskhAnalyzer`**, *naskh* (نسخ) is the usul al-fiqh concept of abrogation: a later ruling supersedes an earlier one, but the earlier text remains present in the corpus. This is structurally identical to what happens in a PDF with incremental updates, the later revision supersedes the earlier, but the earlier objects remain in the byte stream. A forensic naskh analysis asks: what was superseded, and does anything downstream still reference it? That is exactly the question the incremental-update detector asks of a PDF. Excellent fit; not theologically elevated (naskh is a technical legal-hermeneutic term, used daily by working scholars).

**`KitmanAnalyzer`**, *kitman* (كتمان) means the deliberate concealment of truth. It appears in the Qur'an as a vice to be named and rejected ("and do not conceal testimony", Baqarah 2:283). Proposed fit: the analyzer that detects intentional concealment patterns, invisible text, color-matched fonts, zero-opacity overlays, steganographic embedding. We are naming the *detector of the vice*, not endorsing the vice, which is consistent with how the term functions in ethical discourse.

**`TahqiqValidator`**, *tahqiq* (تحقيق) means verification, authentication, critical investigation. Standard classical scholarly term; Ibn Taymiyya and al-Ghazali both use it routinely. Good fit for the cross-check layer that validates findings across independent signals (e.g., confirming that a ZWSP detection in the fitz text matches a raw-stream Unicode hit).

Further per-mechanism analyzers (homoglyph detection, bidi control, ToUnicode CMap, overlay/stacked text) can keep their current English names for now, or receive methodological names as the split proceeds. No need to name them all up front.

---

## Supporting infrastructure names

**`IsnadTracer`**, *isnad* (إسناد) is the chain of transmission in hadith science: the list of narrators through whom a report reached us, each link's reliability assessed independently, breaks flagged. This is the single most perfect mapping in the whole scheme: isnad methodology *is* file provenance analysis, separated only by a thousand years. A provenance layer that records "this finding was derived from fitz's text extraction, confirmed by raw-stream regex, cross-checked against pypdf's content stream" is a literal isnad. Strong recommendation to keep this name when we build the provenance layer.

**Scoring, `compute_muwazana_score` (adopted).** Mizan (ميزان) means scale, balance, and is also the Qur'anic name of the Balance of the Day of Judgment (Surah al-Rahman, al-Anbiya, al-A'raf). Putting that name on a Python function that computes `1.0 - sum(sev * conf)` would be too heavy, the eschatological charge of *Mizan* does not belong on a forensic arithmetic primitive. We therefore adopted *muwazana* (موازنة), "weighing, comparative assessment", a mundane scholarly term with no eschatological weight. The public API exports `compute_muwazana_score`; see `domain/scoring.py`.

**Verdict logic, `tamyiz_verdict` (adopted).** The same concern applied to Mizan applies to *Furqan* (فرقان), which names "the criterion" and is used as an epithet for the Qur'an itself (Surah 25). We adopted *tamyiz* (تمييز), "discrimination, distinction, separating one thing from another", a standard scholarly term used for the cognitive act of distinguishing cases. The public API exports `tamyiz_verdict`; see `domain/verdict.py`. The five verdicts themselves (`sahih`, `mushtabih`, `mukhfi`, `munafiq`, `mughlaq`) are classical descriptive terms, not judgments in the theological sense.

---

## Development phases (sketch: to refine)

Following the pattern of the competition roadmap's "energy of surah X" framing, Bayyinah's development phases could be:

*Pass 1, al-'Alaq energy.* Read and recite. Raw ingestion: pull every content layer out of every supported format, build the library, see what's there. (This is what v0 and v0.1 were.)

*Pass 2, al-Kawthar energy.* Abundance. Cover every mechanism: finish the per-mechanism split, close detection gaps identified in the EOD note, extend to DOCX and HTML.

*Pass 3, al-Zilzal energy.* The earthquake. Stress-test the whole stack: labeled benign/adversarial corpus, precision/recall measurement, shake out false positives, performance hot-path work. Everything that was standing but untested gets shaken.

*Pass 4, al-Bayyinah energy.* Clear evidence. Final hardening, reproducible-output fix, pytest golden fixtures, packaging, companion preprint tying back to the Munafiq Protocol. The project becomes what it's named.

This is a sketch; the actual phase structure should be whatever fits the work. The *discipline*, that phases carry surah energy while modules carry methodological names, is the load-bearing part.

---

## Terms to avoid and why

**`Taqiyya`**, means dissimulation of faith under duress; specific theological term primarily associated with Shia practice and repeatedly weaponized in Islamophobic discourse. Even though it superficially fits "concealment detection," *kitman* serves better and carries none of that charge. Do not use.

**`Shirk`** / **`Kufr`** / **Divine Names**, categories of the gravest theological weight. Never appropriate on code.

**`Fitnah`**, trial, tribulation, sedition. Too theologically and historically charged for forensic tooling.

**`Haram` / `Halal`**, religious-ruling terms, not fitting for binary scanner verdicts. A file is malicious or benign, not halal or haram.

**Surah names on persistent code artifacts**, `al_fatiha.py`, `class YaSinAnalyzer`. Do not. Surahs belong on phases, not files.

**The name of the Qur'an itself, Names of prophets, Names of Allah**, obviously never.

---

## Guidance for future contributors

Before proposing a new Qur'anic/scholarly name for a module, ask:

1. Is this term a methodological technical term in classical Islamic scholarship, or is it a name of something sacred? If the latter, do not use it.
2. Does the term name a *method* or a *vice-to-be-detected*? Both are fine. It should not name a virtue in a way that claims the code *embodies* that virtue.
3. Has the term been sectarianly weaponized or Islamophobically distorted in modern discourse? If yes, prefer an adjacent less-charged term.
4. Would a classical scholar find the mapping precise, or cute? We want precise.

When in doubt, use plain English. A `VerdictLogic` is better than a miscast Qur'anic name.

---

## Resolved questions (1.0 release)

**1. Scoring name, resolved as `muwazana`.** `MizanScorer` carried too much eschatological weight for an arithmetic primitive; `MuwazanaScorer` is the mundane scholarly term ("weighing, comparative assessment") with no such charge. The public API exports `compute_muwazana_score`; see the Scoring section above.

**2. Verdict logic name, resolved as `tamyiz`.** `FurqanLogic` would have conflicted with *al-Furqan* as an epithet of the Qur'an. `TamyizLogic` uses the classical scholarly term for the act of distinguishing cases, and the public API exports `tamyiz_verdict`; see the Verdict-logic section above.

**3. `Bayyinah` as class name, resolved: top-level only.** The name remains the project/package identifier (`bayyinah/__init__.py`, `ScanService` at the top of that namespace). No class inside the codebase is named `Bayyinah`; the aspiration of the project name is preserved precisely by not claiming it for any single internal artifact.

## Open notes (for future contributors)

**4. `KitmanAnalyzer`.** If a future contributor splits intentional-concealment detection into its own analyzer (as the per-mechanism split sketched above), `KitmanAnalyzer` is the preferred name. Plain `ConcealmentAnalyzer` is an acceptable alternative if the naming charge ever feels wrong in context; the four-question test above is the arbiter.

**5. Phase-naming sketch.** The al-'Alaq → al-Kawthar → al-Zilzal → al-Bayyinah arc described above remains the project's working frame; phase 22 (the 1.0 release) is the completion of *al-Bayyinah energy*. Future seasons of work may need different surah energies; the discipline is to name *phases*, never modules.

**6. `BAYYINAH_LEXICON.md`.** Not yet written. If the codebase grows enough scholarly vocabulary to warrant one, a one-page reference listing each term with Arabic script, transliteration, one-line definition, and a citation to the classical tradition, that is a welcome addition. For 1.0 the terminology footprint is small enough that this document suffices.

Pull requests that introduce new scholarly terminology should append to the appropriate section above and update the four-question test if a new category of concern appears.
