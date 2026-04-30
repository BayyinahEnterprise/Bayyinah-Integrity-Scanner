# Bayyinah single-threaded throughput benchmark (v1.1.2)

## Headline

On a 28-PDF corpus drawn from the repository fixtures, sequential scanning completes the full corpus in **0.56 seconds** with a per-file mean of **20.0 ms** (median 4.5 ms, stdev 57.5 ms, p95 224.4 ms, max 249.9 ms).

## Single-threaded extrapolation

| Documents | Estimated wall-clock |
|---:|---:|
| 100 | 2.0 s |
| 1,000 | 20.0 s |
| 10,000 | 3.3 min |

Extrapolation multiplies the measured per-file mean by N. This is honest about what is measured (per-file cost on the existing corpus) and what is extrapolated (volume scaling under sequential execution).

## Multi-page subset extrapolation

The full corpus mean is dragged down by 24 of 28 fixtures being trivially small (under 100 KB single-page test files). For a realistic 1,000 multi-page native-text PDFs workload (e.g., a government agency batch of 50-page filings), the right per-file figure is the multi-page subset.

Multi-page subset: 4 files at >= 100 KB, mean **115.4 ms** per file, max 249.9 ms.

| Documents (multi-page) | Estimated wall-clock single-threaded |
|---:|---:|
| 100 | 11.5 s |
| 1,000 | 1.9 min |
| 10,000 | 19.2 min |

This is the figure to cite when answering "how long for 1,000 50-page PDFs single-threaded?" The multi-page subset includes the 19-page Bayyinah white paper, the 17-page thesis, and the 50-page synthesized fixture, which together approximate a 50-page native-text workload at the upper end. Production-corpus benchmarking on a representative agency sample remains a 24-hour follow-up given a fixture set.

## How this answers the 1,000-document agency question

With production deployment as a worker pool (Level 2 benchmark), throughput scales with cores because the analyzer is stateless. At a single-threaded rate of ~115 ms per 50-page native-text file:

- 1 worker:  ~1.9 min for 1,000 files
- 8 workers: ~0.2 min for 1,000 files (linear-scaling assumption)
- 32 workers: ~0.1 min for 1,000 files (linear-scaling assumption)

The 8-worker and 32-worker rows are extrapolations from the single-threaded measurement times architectural linearity. Empirical confirmation requires the Level 2 worker-pool benchmark.

## Methodology

- Corpus: every PDF in the repository excluding generated benchmark artifacts (28 files).
- One full warm-up pass over the corpus to amortize one-time import and module-load costs, followed by one measured pass.
- Wall-clock measured around `bayyinah.scan_file` using `time.perf_counter()`. Same code path as `POST /scan` minus network round-trip.
- Bayyinah package resolved from the repo checkout (asserted before benchmarking) to avoid picking up any pip-installed copy.

## What this benchmark does NOT prove

- **Concurrent throughput.** This is single-threaded. Linear speedup with cores is the architectural claim, validated separately by the Level 2 worker-pool benchmark.
- **End-to-end HTTP latency.** Numbers exclude FastAPI request parsing, multipart upload decode, and network.
- **Production hardware.** Sandbox is 2 vCPU, 8 GB RAM. Production scaling depends on hosting tier.
- **Realistic agency document distribution.** This corpus skews small; a real corpus would have more multi-page native-text files. An agency-corpus benchmark is a 24-hour follow-up given a fixture set.

## Reproduction

```
python docs/benchmarks/throughput_single_threaded.py
```
