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

## Not yet run

PhantomLint corpus (arXiv 2508.17884) and OpenRAG-Soc (arXiv
2601.10923): no downloadable copy was found from this workspace. No
outside test of the instruction assessment exists yet.

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
