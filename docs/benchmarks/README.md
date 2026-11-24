# Results on public benchmarks

Every result here can be reproduced with the scripts in
`scripts/benchmarks/`. Weak results stay on this page.

## CrackedPDFs (hidden prompt injection in PDFs)

Dataset: `volkthienpreecha/crackedpdfs` on Hugging Face, revision
`02d7e0be03b09d6a29c7e4d388440bc1f5a4907b`; paper arXiv 2607.19396.
Held-out test split: 973 injected files, 973 benign look-alikes that
hide harmless text the same way, 973 untouched originals.

A file counts as an attack when the report contains a
`concealed_instruction` finding. No flags, no second script.

| Version | Attacks caught | Look-alikes flagged | Originals flagged | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| 2.0.1 as released | 609 / 973 | 609 / 973 | 0 / 973 | 0.500 | 0.626 | 0.556 |
| Unreleased (2.1.0), defaults | 854 / 973 | 0 / 973 | 0 / 973 | 1.000 | 0.878 | 0.935 |
| Benchmark authors' detector | | | | | | 0.960 |

For 2.0.1 a file counted as an attack when it had any finding, because
that version had no instruction assessment.

Median scan time per file: 156 ms with the render check, 30 ms before it
(four worker processes on one machine; not a controlled timing).

### What this number does and does not show

- **In-distribution.** The English instruction patterns were developed
  on a 1,500-triplet sample of this benchmark's training split. The
  score shows fit to this benchmark's style of attack.
- **Labels are not used.** The benchmark wraps messages in tags. They
  are stripped before assessment; deleting every label changed 0 of
  1,946 verdicts.
- **The test split has been scored five times.** Between the first and
  third runs a truncation bug was fixed and the acrostic reader added,
  both developed on training files. The fourth and fifth runs changed
  no instruction pattern or threshold: the fourth moved the assessment
  into the scan report, the fifth added the render check (detector hash
  `582b3e21...9a02d32`). Totals were identical across runs three to
  five; in the fifth, two individual files changed verdict in opposite
  directions. A split scored five times is no longer a held-out split,
  and this number should be read with that in mind.
- **Where it misses.** Acrostic messages 40 of 80; one-character-per-
  operator messages 52 of 66; about 8% of the rest through phrasing the
  patterns do not anticipate.

### Reproduce

    python scripts/benchmarks/crackedpdfs_run.py  PDF_ROOT test_meta.csv results.jsonl
    python scripts/benchmarks/crackedpdfs_score.py results.jsonl

`test_meta.csv` is the test-split rows of the dataset's metadata with a
`file_path` column relative to `PDF_ROOT`.

## PhantomText toolkit (first outside check)

Source: `pajola/PhantomText` at commit `a92ae21`, the toolkit from "The
Hidden Threat in Plain Text: Attacking RAG Data Loaders" (ACM AISec
2025). Its authors' code generated every attack document; none of it
informed any detector here. The scanner was frozen first: commit
`3707348`, detector hash `a89c3b64...53e8316`. It was run once.

Every technique, modality and format the toolkit would produce was
generated on three clean base files (PDF, DOCX, HTML) with a neutral
marker sentence as payload: 24 attack documents and the 3 clean bases.
Eleven requested combinations do not exist in the toolkit (invalid
modality for the format, or "in development") and produced no file.

| | Reported | Not reported |
|---|---|---|
| Attack documents (24) | 18 | 6 |
| Clean base documents (3) | 0 | 3 |

Payload text recovered in 12 of 16 injection documents.

The six misses, all recorded in `phantomtext_frozen_a89c3b64.json`:

- PDF transparent text at opacity 0 and at opacity close to zero. The
  hidden line sat on top of a visible line, and the render check counted
  the visible line's pixels as its own. **This was a real flaw.**
- DOCX out-of-bounds text.
- HTML text in the background colour (set by CSS colour, not `display`).
- HTML diacritical-mark obfuscation, default and heavy. These marks are
  visible to a reader, so whether this is concealment is arguable; the
  scanner has no detector for it either way.

After the run the overlap flaw was fixed (detector hash
`582b3e21...9a02d32`). On the same 24 documents the fixed scanner
reports 19. **That second number is not an outside result**: the fix
was written after seeing these files. The other five misses are
unfixed and now listed as known gaps.

Twenty-four documents from one toolkit is a check, not a benchmark. It
tests whether hidden content is noticed. It does not test the
instruction assessment, because the payload was a neutral sentence.

Reproduce (in an environment with the toolkit installed):

    python scripts/benchmarks/phantomtext/generate.py BASE_DIR OUT_DIR
    python scripts/benchmarks/phantomtext/score.py OUT_DIR

## Concealment map (generated, truth from rendering)

`bench/concealment_map`: one-page PDFs from a grammar of eight
independent choices about how a line of text is drawn. Truth comes from
rendering the page with and without the line; the scanner is not
consulted. Horizon: MuPDF, 72 dpi, one page, the eight listed choices.

| | Pages | Reported when hidden | Clean when visible | Missed | False alarms |
|---|---|---|---|---|---|
| Full product | 3,840 | 3,828 | 10 | 2 | 0 |
| Small scope (at most two choices changed), render check off | 124 | 90 | 5 | 29 | 0 |
| Small scope, render check on | 124 | 116 | 7 | 1 | 0 |

Only 10 of 3,840 pages are visible, so the map says much about misses
and little about false alarms. For false alarms: 313 clean PDFs (300
benchmark originals and 13 fixtures), 9,901 extracted spans, none
reported by the render check.

## PhantomLint test documents (first outside test of the instruction assessment)

Source: `tobycmurray/phantom-lint`, the `tests/` directory at the
repository's head on 24 November 2026: 140 documents its authors label
as carrying a hidden prompt (106 PDF, 34 HTML) and 9 they label clean.
Most are real: résumés and research papers collected with hidden text
in them. None informed any detector or pattern here. The scanner was
run once at commit `38ebd5d` with defaults. A file counts as caught
when the report contains a `concealed_instruction` finding.

| | Caught | Hidden content reported at all |
|---|---|---|
| Real PDFs (89) | 80 | 89 |
| Generated PDFs (17) | 14 | 17 |
| Real HTML pages (24) | 2 | 24 |
| Generated HTML pages (10) | 5 | 5 |
| Clean documents (9) | 0 flagged | |

PDF: 94 of 106 (88.7%), against 87.8% recall on the benchmark the
patterns were developed on. HTML: 7 of 34.

What the misses were:

- **Nine real PDFs: the hidden text was found, then read as harmless.**
  Three kinds of message the assessor had no pattern for: instructions
  to an AI reviewer about what verdict to give and how to write it; a
  run of imitated `[system]` markers followed by "if asked ..., answer
  ..."; and a planted third-party endorsement of the candidate, which
  is not an instruction at all. A fourth cause was mechanical: a span
  reported by two detectors was counted twice, which pushed short
  hidden lines past the short-text rule.
- **Three generated PDFs:** rotated text (two) and one off-page
  variant. No concealment finding carried the text.
- **HTML:** text in the background colour set by a style attribute,
  clipped text, text covered by another element, and a font that draws
  nothing are not detected. The scanner reads HTML without laying it
  out. The real pages are arXiv HTML renderings; their hidden prompts
  were not recovered.
- **Speed:** median 1.1 s per file; two real résumés took 130 s and
  217 s.

Nine clean documents say almost nothing about false alarms.

### After the run

The four causes in the first bullet were fixed. On the same documents
the scanner then catches 102 of 106 PDFs; HTML is unchanged at 7 of 34.
**The second number is not an outside result**: the patterns were
written after reading these files. This collection can no longer serve
as an outside test of the instruction assessment.

Checks that the new patterns did not buy recall with false alarms,
on files they were not written from:

| CrackedPDFs files | Flagged before | Flagged after |
|---|---|---|
| Benign hidden text, train and validation splits (8,837) | not run | 0 |
| Benign hidden text, test split (937) | 0 | 0 |
| Clean originals, test split (937) | 0 | 0 |
| Attacks, test split (937) | 805 | 817 |

The test split in the copy downloaded for this check (dataset revision
`02d7e0be`, `dataset_split == "test"`) has 937 triplets, not the 973
reported in the section above; the earlier run's split file was not
available here. On these 937 the unchanged scanner scores F1 0.924,
and 0.932 after the change.

Reproduce: `scripts/benchmarks/phantomlint_run.py TESTS_DIR results.jsonl`.

## Split-view PDFs (outside test of concealment detection)

Source: `SD957/Split-View-PDF`, the samples published with "What Users
See Is Not What Models Read" (arXiv 2606.15020): 25 minimal PDFs, one
per way a PDF can show a reader one thing and give a parser another
(EG01 to EG25), and 36 longer documents built from the same
constructions. None informed any detector here. The scanner was run
once at commit `c0e872c` with defaults.

The payloads are ordinary claims, not instructions, so the question is
whether the scan reports the divergence at all. A file counts as
reported when it has at least one finding other than
`metadata_anomaly`, `incremental_update` or `pdf_metadata_analyzer`.
That rule was fixed before the run.

| Family | Minimal PDFs reported |
|---|---|
| Hidden text (EG04 to EG14: invisible mode, white, off-page, tiny, zero alpha, clipped, occluded, text-as-clip, zero-height, squeezed, layer off) | 11 of 11 |
| Replacement text (EG01 ToUnicode remap; EG02, EG03 ActualText) | 0 of 3 |
| Reading order (EG15 to EG17) | 0 of 3 |
| Font decoding (EG18 to EG25) | 3 of 8 (EG19, EG22, EG23) |
| **All** | **14 of 25** |

Longer documents: 14 of 25 in the primary set, the same gaps as above;
6 of 11 in the question-answering set, where the clipped (EG09),
occluded (EG10) and squeezed (EG13) variants were **missed although
their minimal versions were caught**. In those files the hidden text is
a short suffix on a visible line.

What this shows:

- Text a reader cannot see is found whatever hides it. Five of the
  eleven were caught by the render check alone, with no detector for
  the specific construction.
- **Text that is replaced rather than hidden is not detected.** A
  reader sees one word and a parser is handed another through
  `/ActualText` or a remapped `/ToUnicode` table. `tounicode_anomaly`
  did not fire on EG01.
- Reading-order and most font-metadata gaps are not detected. The
  paper's own scanner fires on 6.8% of ordinary academic PDFs for the
  font family, so these need care before they are reported at all.
- The benchmark has no clean counterparts, so it says nothing about
  false alarms.

Median 0.01 s per file. Reproduce:
`scripts/benchmarks/splitview_run.py REPO results.jsonl`.

## Reverse CAPTCHA (outside test of invisible-character decoding)

Source: `canonicalmg/reverse-captcha-eval` (arXiv 2603.00164), run once
at commit `c0e872c` through `integrations.check_text`.

Main pack: 30 trivia questions, each carrying a hidden answer in
zero-width characters used as binary digits or in Unicode Tag
characters, under four prompt conditions, plus 30 controls with nothing
hidden.

| | Reported | Hidden text decoded | Read as an instruction |
|---|---|---|---|
| Zero-width binary (120) | 120 | 120 | 30 |
| Unicode Tags (120) | 120 | 120 | 30 |
| Controls (30) | 0 | | 0 |

The 60 read as instructions are the ones whose payload says to ignore
previous instructions. **The other 180 carry "Reply WORD" and were not
read as instructions**, though a hidden order to give a particular
answer is one. They are still reported, as a decoded invisible payload.

Second pack (hidden-message puzzles): zero-width binary decoded in 13
of 13; 20 cases using a made-up mapping of zero-width characters to
letters were reported but, as expected, not decoded; 12 controls not
flagged. Its remaining cases (acrostics, capital letters, comma counts)
hide nothing from a reader and are out of scope; none was reported.

Reproduce: `scripts/benchmarks/reverse_captcha_run.py REPO results.jsonl`.

## Not yet run

OpenRAG-Soc (arXiv 2601.10923): no downloadable copy was found. The
full 3,402-document PhantomLint corpus is not in its repository; only
the test documents above were used. After the fixes above there is
again no untouched outside test of the instruction assessment.

## Multilingual false-alarm check (not a benchmark)

Ten ordinary paragraphs, one per language, nothing hidden.

| | 2.0.1 | Unreleased |
|---|---|---|
| Russian (57 words) | 34 findings, score 0.00 | 0 findings, 1.00 |
| Ukrainian (46 words) | 29 findings, 0.00 | 0, 1.00 |
| Greek (47 words) | 16 findings, 0.00 | 0, 1.00 |
| Persian (52 words) | 1 finding, 0.91 | 0, 1.00 |
| Arabic, Chinese, Japanese, Hindi, Turkish | 0 | 0 |

Ten paragraphs written for the purpose are a smoke test. A measured
false-alarm rate needs a real multilingual corpus.
