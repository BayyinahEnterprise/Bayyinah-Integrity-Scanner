# Bayyinah scan timing benchmark (v1.1.2)

In-process timings around `bayyinah.scan_file`. Same code path as `POST /scan` minus network round-trip. CPU-only, no GPU, no model inference.

## Methodology

- One cold call per file followed by five warm calls.
- Wall-clock measured around `bayyinah.scan_file` using `time.perf_counter()`.
- Bayyinah package resolved from the repo checkout (not any pip-installed copy in site-packages); the script asserts the import path before benchmarking.
- The 50-page synthesized PDF is regenerated deterministically by the benchmark script (`build_50pg_fixture`) rather than committed, so the repository does not carry a binary that could drift across reportlab versions.

## Results

| File | Size (bytes) | Pages | Cold (ms) | Warm mean (ms) | Warm stdev (ms) |
|---|---:|---:|---:|---:|---:|
| `clean.pdf` | 1,991 | 1 | 43.5 | 5.8 | 0.4 |
| `positive_combined.pdf` | 150,898 | 3 | 18.4 | 13.3 | 0.1 |
| `Bayyinah_Thesis_Paper.pdf` | 150,071 | 17 | 197.9 | 201.4 | 10.6 |
| `Bayyinah_White_Paper.pdf` | 184,336 | 19 | 260.2 | 255.7 | 4.2 |
| `clean_50pg.pdf` | 37,842 | 50 | 189.8 | 195.5 | 8.2 |

## Headline

Every scan completed in under 260 ms warm. The 50-page synthesized PDF scans in ~196 ms warm; the 19-page typeset white paper scans in ~256 ms warm.

Cost scales with structural complexity (content streams, fonts, cross-references), not with raw page count. The 19-page typeset white paper is slower per scan than the 50-page synthesized PDF because the white paper carries embedded fonts and richer content streams. This is expected behavior for a deterministic byte-level scanner.

## Caveats

- **In-process timing, not end-to-end HTTP.** Numbers exclude FastAPI request parsing, multipart upload decode, and network. Production `/scan` adds tens to low-hundreds of milliseconds depending on file size and connection.
- **Single instance, no concurrency test.** Concurrent-scan throughput is on the v1.2 roadmap.
- **Hardware: Linux sandbox, 2 vCPU, 8 GB RAM.** Production Railway free-tier container is comparable in CPU.
- **The 50-page test PDF is synthetic.** A real-world 50-page benchmark on a public document is a planned follow-up.

## Reproduction

```
python docs/benchmarks/scan_benchmark.py
```

Script lives at `docs/benchmarks/scan_benchmark.py`. Requires `pypdf` (or `PyPDF2`) and `reportlab` (only used to generate the 50-page fixture; not a Bayyinah runtime dependency).
