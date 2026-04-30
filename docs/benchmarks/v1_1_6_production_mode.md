# v1.1.6 production-mode benchmark

Reproduction harness: `docs/benchmarks/v1_1_6_production_mode.py`.

## Methodology

For each fixture, `ScanService.scan(fixture, mode=...)` is invoked
five times in each mode. Caches are warmed once per mode before
measurement. The two modes are interleaved so any system-level noise
affects both modes equally. P50 is the median of the five timed runs;
P95 is the largest of the five (the standard P95 formula on a 5-sample
set rounds to the max).

The "T1>=0.9" column is the count of Tier 1 findings at confidence
greater than or equal to 0.9 in the final merged report. The
production-mode short-circuit fires the first time this count goes
positive within the dispatch loop.

Hardware: Linux sandbox, Python 3.12.8, single-threaded, no other
load. Run on 2026-04-30.

## Result

| Fixture | Mode | P50 (ms) | P95 (ms) | Findings | T1 >= 0.9 |
|---|---|---:|---:|---:|---:|
| text.homoglyph                  | forensic   |   9.98 |  10.01 |  2 | 1 |
| text.homoglyph                  | production |   9.64 |   9.67 |  2 | 1 |
| text.invisible_render           | forensic   |   4.00 |   4.00 |  1 | 1 |
| text.invisible_render           | production |   3.46 |   3.59 |  1 | 1 |
| text.microscopic_font           | forensic   |   4.12 |   4.11 |  1 | 0 |
| text.microscopic_font           | production |   4.35 |   4.08 |  1 | 0 |
| text.white_on_white             | forensic   |   4.31 |   4.01 |  1 | 1 |
| text.white_on_white             | production |   3.61 |   3.60 |  1 | 1 |
| text.overlapping                | forensic   |   4.08 |   4.14 |  1 | 0 |
| text.overlapping                | production |   4.02 |   4.23 |  1 | 0 |
| object.embedded_javascript      | forensic   |   5.61 |   7.57 |  2 | 1 |
| object.embedded_javascript      | production |   5.92 |   6.46 |  2 | 1 |
| object.embedded_attachment      | forensic   |   3.91 |   3.93 |  1 | 0 |
| object.embedded_attachment      | production |   3.95 |   3.96 |  1 | 0 |
| object.tounicode_cmap           | forensic   |   3.92 |   3.93 |  1 | 1 |
| object.tounicode_cmap           | production |   3.88 |   3.89 |  1 | 1 |
| clean                           | forensic   |   4.74 |   4.75 |  0 | 0 |
| clean                           | production |   4.69 |   4.70 |  0 | 0 |
| **positive_combined**           | **forensic**   | **11.16** | **11.19** | **16** | **5** |
| **positive_combined**           | **production** |  **8.98** |  **9.00** |  **8** | **3** |
| clean_50pg                      | forensic   | 135.92 | 136.14 |  0 | 0 |
| clean_50pg                      | production | 135.51 | 137.34 |  0 | 0 |

## Reading

The headline result is on `positive_combined.pdf`, the multi-mechanism
adversarial fixture that aggregates 16 findings across the corpus in
forensic mode. Production mode short-circuits after the first Tier-1
high-confidence finding lands in the merged report and surfaces only
the eight findings that fired before that point. P50 drops from
11.16 ms to 8.98 ms (20 percent reduction) with the Tier-1 verdict
preserved.

Single-mechanism adversarial fixtures (homoglyph, invisible_render,
white_on_white) get smaller gains in the 3 to 14 percent range. The
short-circuit still fires, but the analyzer that detects the only
Tier-1 mechanism is already early in the cost-class-A bucket, so
there is little to skip.

Fixtures whose only finding is below tier 1 or below the 0.9
confidence threshold (microscopic_font, overlapping, embedded
attachment) cannot trigger the short-circuit; the production-mode
P50 sits within stdev of the forensic-mode P50.

Clean files (clean.pdf, clean_50pg.pdf) cannot trigger the
short-circuit by definition. The two modes run the same set of
analyzers and the P50 difference is within stdev.

## Conclusion

The cost-class-ordered short-circuit pays off most where it
matters: adversarial files with multiple Tier-1 mechanisms in the
combined corpus. Single-mechanism fixtures see modest gains. Clean
files are unaffected. The Tier-1 verdict is preserved across modes
for every fixture in the corpus, pinned by
`tests/test_registry_production_mode.py::test_production_mode_preserves_tier_1_verdict`.
