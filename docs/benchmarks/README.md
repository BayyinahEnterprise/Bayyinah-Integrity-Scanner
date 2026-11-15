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

Median scan time per file: 30 ms (four worker processes, one laptop-class
machine; not a controlled timing).

### What this number does and does not show

- **In-distribution.** The English instruction patterns were developed
  on a 1,500-triplet sample of this benchmark's training split. The
  score shows fit to this benchmark's style of attack.
- **Labels are not used.** The benchmark wraps messages in tags. They
  are stripped before assessment; deleting every label changed 0 of
  1,946 verdicts.
- **The test split has been scored four times.** Between the first and
  third runs a truncation bug was fixed and the acrostic reader added,
  both developed on training files. The fourth run changed wiring only
  (the assessment moved into the scan report) and reproduced the third
  exactly. No pattern or threshold was changed in response to a test
  result.
- **Where it misses.** Acrostic messages 40 of 80; one-character-per-
  operator messages 52 of 66; about 8% of the rest through phrasing the
  patterns do not anticipate.

### Reproduce

    python scripts/benchmarks/crackedpdfs_run.py  PDF_ROOT test_meta.csv results.jsonl
    python scripts/benchmarks/crackedpdfs_score.py results.jsonl

`test_meta.csv` is the test-split rows of the dataset's metadata with a
`file_path` column relative to `PDF_ROOT`.

## Not yet run

PhantomLint corpus (arXiv 2508.17884), PhantomText (arXiv 2507.05093),
OpenRAG-Soc (arXiv 2601.10923). None of these informed any pattern in
the scanner, so they are the honest test of the claim above. Until one
is run, there is no out-of-distribution number to report.

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
