# v1.1.5 spatial-index benchmark

Reruns the v1.1.4 four-density panel after the v1.1.5 
`overlapping_text` spatial pre-filter ships, to measure the 
impact on dense-PDF scan time.

## Methodology

Single-threaded `bayyinah.scan_file` wall-clock measured with `time.perf_counter()`. 5 measured runs per fixture preceded by one discarded warm-up run. Same code path as the `/scan` HTTP endpoint minus FastAPI request decode and network round-trip.

## Four-density panel (forensic mode)

| Fixture | Description | P50 ms | Min ms | Max ms | Mean ms | Stdev ms |
|---|---|---:|---:|---:|---:|---:|
| white_paper_19p | 19-page typeset white paper (native text) | 210 | 207 | 217 | 211 | 4 |
| clean_50p_native | 50-page synthesized native-text PDF | 136 | 135 | 153 | 139 | 8 |
| safety_report_220p | 220-page native-text dense report | 13788 | 13721 | 13968 | 13815 | 94 |

## Production-mode early return on Tier 1 severity-1.0 finding

Fixture: `docs/adversarial/pdf_gauntlet/fixtures/04_metadata.pdf` (Adversarial Tier 1 severity-1.0 metadata anomaly)

| Mode | P50 ms | Min ms | Max ms | Stdev ms |
|---|---:|---:|---:|---:|
| forensic | 4 | 4 | 5 | 0 |
| production | 4 | 4 | 4 | 0 |

Production mode returns early on the first Tier 1 severity-1.0 finding. P50 reduction: **11%** (4ms to 4ms).

## Reproduction

```
python3 docs/benchmarks/v1_1_5_rtree_spatial_index.py
```
