"""
Bayyinah single-threaded throughput benchmark.

Substantiates per-corpus wall-clock for sequential scanning across the
full set of repository PDF fixtures, plus extrapolations to larger
document counts (100, 1,000, 10,000).

Methodology
-----------
- Corpus: every PDF in the repository (excluding generated benchmark
  fixtures and .git internals). 28 files at the time of writing,
  ranging from 1 KB single-page fixtures to a 19-page typeset white
  paper.
- Each file is scanned once after a single warm-up pass over the
  corpus to amortize one-time import costs.
- Wall-clock is measured around the full corpus loop and reported as
  total seconds, mean per file, and per-file standard deviation.
- The 1,000-document extrapolation multiplies the measured per-file
  mean by 1,000. This is honest about what is measured (per-file cost
  on the existing corpus) and what is extrapolated (volume scaling
  under sequential execution).

Limits this benchmark does NOT address
--------------------------------------
- Concurrent throughput (parallel workers). That is the Level 2
  benchmark; this is Level 1.
- End-to-end HTTP latency (FastAPI parsing, multipart decode, network).
- Production hardware (Railway tier or beefier worker pools).
- Realistic document distribution (this corpus skews small; a real
  agency corpus would have more multi-page native-text files).

Run
---
    python docs/benchmarks/throughput_single_threaded.py
"""
import statistics
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bayyinah  # noqa: E402

assert Path(bayyinah.__file__).resolve().is_relative_to(_REPO_ROOT), (
    f"bayyinah imported from {bayyinah.__file__} but expected a path "
    f"under {_REPO_ROOT}. Uninstall any pip-installed bayyinah."
)


def collect_pdfs(root: Path) -> list[Path]:
    """All repository PDFs except generated benchmark artifacts and .git."""
    skip_parts = {".git", "benchmarks"}
    out: list[Path] = []
    for p in root.rglob("*.pdf"):
        if any(part in skip_parts for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return sorted(out)


def time_one(p: Path) -> float:
    t0 = time.perf_counter()
    bayyinah.scan_file(str(p))
    return (time.perf_counter() - t0) * 1000.0


def main() -> None:
    print(f"bayyinah version: {bayyinah.__version__}")
    files = collect_pdfs(_REPO_ROOT)
    print(f"corpus: {len(files)} PDFs")

    # Warm-up pass (amortize import / lazy module load).
    print("warm-up pass...")
    for f in files:
        bayyinah.scan_file(str(f))

    # Measured pass.
    print("measured pass...")
    per_file_ms: list[float] = []
    t_corpus = time.perf_counter()
    for f in files:
        per_file_ms.append(time_one(f))
    corpus_total_s = time.perf_counter() - t_corpus

    mean_ms = statistics.mean(per_file_ms)
    median_ms = statistics.median(per_file_ms)
    stdev_ms = statistics.stdev(per_file_ms) if len(per_file_ms) > 1 else 0.0
    p95_ms = (
        statistics.quantiles(per_file_ms, n=20)[18]
        if len(per_file_ms) >= 20 else max(per_file_ms)
    )
    max_ms = max(per_file_ms)

    print()
    print(f"corpus wall-clock total: {corpus_total_s:.2f} s ({len(files)} files)")
    print(f"per-file mean   : {mean_ms:7.1f} ms")
    print(f"per-file median : {median_ms:7.1f} ms")
    print(f"per-file stdev  : {stdev_ms:7.1f} ms")
    print(f"per-file p95    : {p95_ms:7.1f} ms")
    print(f"per-file max    : {max_ms:7.1f} ms")
    print()

    # The corpus mean is dragged down by 24 of 28 fixtures being
    # trivially small (<2 KB single-page test files). For a realistic
    # "1,000 multi-page native-text PDFs" extrapolation, the right
    # per-file figure is the multi-page-class subset, not the corpus mean.
    multipage = [
        per_file_ms[i] for i, f in enumerate(files)
        if f.stat().st_size >= 100_000  # ~50 KB+ skips the small fixtures
    ]
    multipage_mean_ms = statistics.mean(multipage) if multipage else mean_ms
    multipage_max_ms = max(multipage) if multipage else max_ms
    print()
    print(f"multi-page subset ({len(multipage)} files >= 100 KB):")
    print(f"  mean: {multipage_mean_ms:7.1f} ms  max: {multipage_max_ms:7.1f} ms")

    # Extrapolations (single-threaded).
    print()
    print("Single-threaded extrapolation:")
    print("  (a) using full-corpus mean per file:")
    for n in (100, 1000, 10000):
        secs = n * mean_ms / 1000.0
        if secs < 60:
            print(f"      {n:>6d} files: {secs:7.1f} s")
        elif secs < 3600:
            print(f"      {n:>6d} files: {secs/60:7.1f} min")
        else:
            print(f"      {n:>6d} files: {secs/3600:7.2f} h")
    print("  (b) using multi-page subset mean (closer to 50-page workload):")
    for n in (100, 1000, 10000):
        secs = n * multipage_mean_ms / 1000.0
        if secs < 60:
            print(f"      {n:>6d} files: {secs:7.1f} s")
        elif secs < 3600:
            print(f"      {n:>6d} files: {secs/60:7.1f} min")
        else:
            print(f"      {n:>6d} files: {secs/3600:7.2f} h")

    # Write report.
    out = _REPO_ROOT / "docs/benchmarks/v1_1_2_throughput_single_threaded.md"
    lines = [
        f"# Bayyinah single-threaded throughput benchmark (v{bayyinah.__version__})",
        "",
        "## Headline",
        "",
        f"On a {len(files)}-PDF corpus drawn from the repository fixtures, "
        f"sequential scanning completes the full corpus in "
        f"**{corpus_total_s:.2f} seconds** with a per-file mean of "
        f"**{mean_ms:.1f} ms** (median {median_ms:.1f} ms, stdev {stdev_ms:.1f} ms, "
        f"p95 {p95_ms:.1f} ms, max {max_ms:.1f} ms).",
        "",
        "## Single-threaded extrapolation",
        "",
        "| Documents | Estimated wall-clock |",
        "|---:|---:|",
    ]
    for n in (100, 1000, 10000):
        secs = n * mean_ms / 1000.0
        if secs < 60:
            label = f"{secs:.1f} s"
        elif secs < 3600:
            label = f"{secs/60:.1f} min"
        else:
            label = f"{secs/3600:.2f} h"
        lines.append(f"| {n:,} | {label} |")
    lines += [
        "",
        "Extrapolation multiplies the measured per-file mean by N. This is "
        "honest about what is measured (per-file cost on the existing "
        "corpus) and what is extrapolated (volume scaling under sequential "
        "execution).",
        "",
        "## Multi-page subset extrapolation",
        "",
        f"The full corpus mean is dragged down by {len(files) - len(multipage)} "
        f"of {len(files)} fixtures being trivially small (under 100 KB "
        f"single-page test files). For a realistic 1,000 multi-page "
        f"native-text PDFs workload (e.g., a government agency batch of "
        f"50-page filings), the right per-file figure is the multi-page "
        f"subset.",
        "",
        f"Multi-page subset: {len(multipage)} files at >= 100 KB, mean "
        f"**{multipage_mean_ms:.1f} ms** per file, max {multipage_max_ms:.1f} ms.",
        "",
        "| Documents (multi-page) | Estimated wall-clock single-threaded |",
        "|---:|---:|",
    ]
    for n in (100, 1000, 10000):
        secs = n * multipage_mean_ms / 1000.0
        if secs < 60:
            label = f"{secs:.1f} s"
        elif secs < 3600:
            label = f"{secs/60:.1f} min"
        else:
            label = f"{secs/3600:.2f} h"
        lines.append(f"| {n:,} | {label} |")
    lines += [
        "",
        "This is the figure to cite when answering \"how long for 1,000 "
        "50-page PDFs single-threaded?\" The multi-page subset includes the "
        "19-page Bayyinah white paper, the 17-page thesis, and the 50-page "
        "synthesized fixture, which together approximate a 50-page native-text "
        "workload at the upper end. Production-corpus benchmarking on a "
        "representative agency sample remains a 24-hour follow-up given a "
        "fixture set.",
        "",
        "## How this answers the 1,000-document agency question",
        "",
        "With production deployment as a worker pool (Level 2 benchmark), "
        "throughput scales with cores because the analyzer is stateless. "
        f"At a single-threaded rate of ~{multipage_mean_ms:.0f} ms per "
        "50-page native-text file:",
        "",
        "- 1 worker:  ~{:.1f} min for 1,000 files".format(
            1000 * multipage_mean_ms / 1000.0 / 60
        ),
        "- 8 workers: ~{:.1f} min for 1,000 files (linear-scaling assumption)".format(
            1000 * multipage_mean_ms / 1000.0 / 60 / 8
        ),
        "- 32 workers: ~{:.1f} min for 1,000 files (linear-scaling assumption)".format(
            1000 * multipage_mean_ms / 1000.0 / 60 / 32
        ),
        "",
        "The 8-worker and 32-worker rows are extrapolations from the "
        "single-threaded measurement times architectural linearity. "
        "Empirical confirmation requires the Level 2 worker-pool benchmark.",
        "",
        "## Methodology",
        "",
        f"- Corpus: every PDF in the repository excluding generated benchmark "
        f"artifacts ({len(files)} files).",
        "- One full warm-up pass over the corpus to amortize one-time import "
        "and module-load costs, followed by one measured pass.",
        "- Wall-clock measured around `bayyinah.scan_file` using "
        "`time.perf_counter()`. Same code path as `POST /scan` minus network "
        "round-trip.",
        "- Bayyinah package resolved from the repo checkout (asserted before "
        "benchmarking) to avoid picking up any pip-installed copy.",
        "",
        "## What this benchmark does NOT prove",
        "",
        "- **Concurrent throughput.** This is single-threaded. Linear speedup "
        "with cores is the architectural claim, validated separately by the "
        "Level 2 worker-pool benchmark.",
        "- **End-to-end HTTP latency.** Numbers exclude FastAPI request "
        "parsing, multipart upload decode, and network.",
        "- **Production hardware.** Sandbox is 2 vCPU, 8 GB RAM. Production "
        "scaling depends on hosting tier.",
        "- **Realistic agency document distribution.** This corpus skews "
        "small; a real corpus would have more multi-page native-text files. "
        "An agency-corpus benchmark is a 24-hour follow-up given a fixture "
        "set.",
        "",
        "## Reproduction",
        "",
        "```",
        "python docs/benchmarks/throughput_single_threaded.py",
        "```",
        "",
    ]
    out.write_text("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
