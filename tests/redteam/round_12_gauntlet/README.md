# Round 12 corpus: false-positive incident (LaTeX and LibreOffice)

Corpus seeded for v1.2.4 corrective release. Documents the
calibration bugs surfaced by Bilal's audit-of-self red-team
probe of bayyinah.dev v1.2.3 on 2026-05-06.

## Fixtures

| File | Producer | Pre-fix verdict | Post-fix verdict |
|---|---|---|---|
| fixture_clean_pdftex_article.pdf | pdfTeX | mukhfi (score 0.0) | sahih |
| fixture_clean_pdftex_with_hyperref.pdf | pdfTeX (hyperref) | mukhfi (score 0.0) | sahih |
| fixture_clean_libreoffice_destination_oa.pdf | LibreOffice (synthetic OpenAction) | mushtabih (0.865) | sahih |
| fixture_libreoffice_writer_native.pdf | LibreOffice native | sahih (already clean) | sahih |

## Builders

Each fixture has a deterministic builder. Regenerate with:

```bash
cd tests/redteam/round_12_gauntlet
python3 build_clean_pdftex_article.py
python3 build_clean_pdftex_with_hyperref.py
python3 build_clean_libreoffice_destination_oa.py
python3 build_libreoffice_writer_native.py
```

Builders depend on `pdflatex` and `soffice` being on PATH. CI
skips fixture-regeneration tests when these tools are missing.

## EXPECTED.json

Machine-readable pre-fix and post-fix verdicts. Used by:

- `test_corpus_pre_fix_verdicts.py` (pre-fix passes against
  v1.2.3; inverts after closure commits land).
- `test_corpus_post_fix_verdicts.py` (post-fix passes after
  v1.2.4 fixes).

## Round provenance

See `INCIDENT_v1_2_3_REPORT.md` for the verbatim incident
report dated 2026-05-06.
