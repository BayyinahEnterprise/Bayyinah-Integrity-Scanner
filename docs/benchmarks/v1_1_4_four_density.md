# v1.1.4 four-density benchmark

## Methodology

Single-threaded `bayyinah.scan_file` wall-clock measured with `time.perf_counter()`. 5 measured runs per fixture preceded by one discarded warm-up run. Same code path as the `/scan` HTTP endpoint minus FastAPI request decode and network round-trip. Hardware: 2 vCPU sandbox, 8 GB RAM.

## Four-density panel (forensic mode)

| Fixture | Description | P50 ms | Min ms | Max ms | Mean ms | Stdev ms |
|---|---|---:|---:|---:|---:|---:|
| white_paper_19p | 19-page typeset white paper (native text) | 232 | 221 | 263 | 236 | 16 |
| clean_50p_native | 50-page synthesized native-text PDF | 143 | 140 | 166 | 146 | 11 |
| safety_report_220p | 220-page native-text dense report | 15335 | 14985 | 15875 | 15415 | 335 |

## Comparison with v1.1.2 baseline

The v1.1.4 content-index port (Phases 0 to 4) folds in five PDF analyzers that previously each opened their own pikepdf or pymupdf handle. Comparing against the v1.1.2 baselines on the two fixtures with prior measurements:

| Fixture | v1.1.2 P50 | v1.1.4 P50 | Reduction |
|---|---:|---:|---:|
| white_paper_19p (synthesized 19-page) | 277 ms | 226 ms | 18% |
| NIST 48-page native text | 3,605 ms | 2,448 ms | 32% |

The 19-page run on the published Bayyinah white paper measures 232 ms in this run (within stdev of the documented 226 ms Phase 3+4 result). The 32% reduction on the 48-page NIST native-text fixture is the structural win from page-dict caching landing on a non-trivial document where the migrated detectors have actual work to do.

## Production-mode early return on Tier 1 severity-1.0 finding

Fixture: `docs/adversarial/pdf_gauntlet/fixtures/04_metadata.pdf` (adversarial Tier 1 severity-1.0 metadata anomaly).

| Mode | P50 ms | Min ms | Max ms | Stdev ms |
|---|---:|---:|---:|---:|
| forensic | 4 | 4 | 4 | 0 |
| production | 4 | 4 | 4 | 0 |

The gauntlet fixtures are intentionally minimal (under 2 KB) to isolate one mechanism per file, so the wall-clock cost of every analyzer running to completion is already at the floor of the measurement. The production-mode short-circuit in v1.1.4 lands at the report-emission boundary: when any Tier 1 finding fires at confidence at least 0.9, the merged report is returned without the cold-path explanation pass. The visible delta on these tiny fixtures is below measurement noise. Cost-class-ordered early termination inside the registry, where production mode would skip Class B analyzers once a Tier 1 hit is seen, is queued for v1.1.5 once the registry supports class-A-first dispatch (see `application/scan_service.py` docstring under "v1.1.4 - mode parameter").

What is established by v1.1.4:

- The `mode` kwarg is wired end-to-end (`bayyinah.scan_file(..., mode=...)` and `POST /scan?mode=production`) with input validation that returns 400 on unknown values.
- Forensic mode is byte-identical to pre-v1.1.4 behaviour; the entire 1,719-test suite passes unchanged with `mode="forensic"` as the default.
- Production mode returns the same merged report shape on these fixtures. End-to-end production-mode test coverage at the API and scan-service boundary is queued alongside the v1.1.5 cost-class-ordered early termination work.

## Reproduction

```
python3 docs/benchmarks/v1_1_4_four_density.py
```
