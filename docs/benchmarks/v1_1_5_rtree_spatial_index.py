"""
v1.1.5 spatial-index benchmark.

Reruns the four-density panel from v1.1.4 to measure the impact of the
overlapping_text spatial pre-filter (uniform grid candidate generator).
P50 over 5 measured runs (preceded by a single warm-up run discarded).

Densities measured:
  - white_paper: 19-page typeset Bayyinah white paper (native text, light)
  - clean_50p:   50-page synthesized native-text PDF (medium density)
  - safety_220p: 220-page international AI safety report (dense, native text)
  - gauntlet_metadata: adversarial fixture (Tier 1 severity-1.0 metadata
    anomaly), measured in forensic mode and production mode for the
    early-return delta.

Outputs Markdown report at docs/benchmarks/v1_1_5_rtree_spatial_index.md.

Run
---
    python3 docs/benchmarks/v1_1_5_rtree_spatial_index.py
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


PANEL = [
    ("white_paper_19p",
     "papers/Bayyinah_White_Paper.pdf",
     "19-page typeset white paper (native text)"),
    ("clean_50p_native",
     "docs/benchmarks/clean_50pg.pdf",
     "50-page synthesized native-text PDF"),
    ("safety_report_220p",
     "/home/user/workspace/international-ai-safety-report-2026_1.pdf",
     "220-page native-text dense report"),
]

GAUNTLET_FIXTURE = (
    "gauntlet_metadata_severity_1",
    "docs/adversarial/pdf_gauntlet/fixtures/04_metadata.pdf",
    "Adversarial Tier 1 severity-1.0 metadata anomaly",
)

RUNS = 5


def time_one(path: str, mode: str | None = None) -> float:
    t0 = time.perf_counter()
    if mode is None:
        bayyinah.scan_file(path)
    else:
        bayyinah.scan_file(path, mode=mode)
    return (time.perf_counter() - t0) * 1000.0


def measure(path: Path, mode: str | None = None) -> dict:
    """One warm-up + RUNS measured iterations. Returns p50/min/max/mean."""
    if not path.exists():
        return {"error": f"not found: {path}"}
    # Warm-up.
    time_one(str(path), mode=mode)
    samples = [time_one(str(path), mode=mode) for _ in range(RUNS)]
    samples_sorted = sorted(samples)
    return {
        "samples_ms": samples,
        "p50_ms": statistics.median(samples),
        "min_ms": min(samples),
        "max_ms": max(samples),
        "mean_ms": statistics.mean(samples),
        "stdev_ms": statistics.stdev(samples) if len(samples) > 1 else 0.0,
    }


def fmt_row(label: str, desc: str, r: dict) -> str:
    if "error" in r:
        return f"| {label} | {desc} | _{r['error']}_ |"
    return (
        f"| {label} | {desc} | "
        f"{r['p50_ms']:.0f} | "
        f"{r['min_ms']:.0f} | "
        f"{r['max_ms']:.0f} | "
        f"{r['mean_ms']:.0f} | "
        f"{r['stdev_ms']:.0f} |"
    )


def main() -> None:
    print(f"bayyinah version: {bayyinah.__version__}")
    print(f"runs per fixture: {RUNS} (plus 1 warm-up)\n")

    panel_results = []
    for label, rel, desc in PANEL:
        path = Path(rel) if not Path(rel).is_absolute() else Path(rel)
        if not path.is_absolute():
            path = _REPO_ROOT / rel
        print(f"-- {label}: {path}")
        r = measure(path)
        if "error" not in r:
            print(f"   p50={r['p50_ms']:.0f}ms  min={r['min_ms']:.0f}ms  "
                  f"max={r['max_ms']:.0f}ms  stdev={r['stdev_ms']:.0f}ms")
        else:
            print(f"   {r['error']}")
        panel_results.append((label, desc, r))

    # Production-mode delta on the gauntlet fixture.
    g_label, g_rel, g_desc = GAUNTLET_FIXTURE
    g_path = _REPO_ROOT / g_rel
    print(f"\n-- {g_label} (forensic mode): {g_path}")
    forensic = measure(g_path, mode="forensic")
    if "error" not in forensic:
        print(f"   p50={forensic['p50_ms']:.0f}ms  "
              f"stdev={forensic['stdev_ms']:.0f}ms")
    print(f"-- {g_label} (production mode): {g_path}")
    production = measure(g_path, mode="production")
    if "error" not in production:
        print(f"   p50={production['p50_ms']:.0f}ms  "
              f"stdev={production['stdev_ms']:.0f}ms")

    # Write report.
    lines = [
        f"# v{bayyinah.__version__} spatial-index benchmark",
        "",
        "Reruns the v1.1.4 four-density panel after the v1.1.5 ",
        "`overlapping_text` spatial pre-filter ships, to measure the ",
        "impact on dense-PDF scan time.",
        "",
        "## Methodology",
        "",
        f"Single-threaded `bayyinah.scan_file` wall-clock measured with "
        f"`time.perf_counter()`. {RUNS} measured runs per fixture preceded "
        "by one discarded warm-up run. Same code path as the `/scan` HTTP "
        "endpoint minus FastAPI request decode and network round-trip.",
        "",
        "## Four-density panel (forensic mode)",
        "",
        "| Fixture | Description | P50 ms | Min ms | Max ms | Mean ms | Stdev ms |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for label, desc, r in panel_results:
        lines.append(fmt_row(label, desc, r))

    lines += [
        "",
        "## Production-mode early return on Tier 1 severity-1.0 finding",
        "",
        f"Fixture: `{g_rel}` ({g_desc})",
        "",
        "| Mode | P50 ms | Min ms | Max ms | Stdev ms |",
        "|---|---:|---:|---:|---:|",
    ]
    if "error" not in forensic:
        lines.append(
            f"| forensic | {forensic['p50_ms']:.0f} | "
            f"{forensic['min_ms']:.0f} | {forensic['max_ms']:.0f} | "
            f"{forensic['stdev_ms']:.0f} |"
        )
    if "error" not in production:
        lines.append(
            f"| production | {production['p50_ms']:.0f} | "
            f"{production['min_ms']:.0f} | {production['max_ms']:.0f} | "
            f"{production['stdev_ms']:.0f} |"
        )
    if "error" not in forensic and "error" not in production:
        delta_pct = 100.0 * (1.0 - production["p50_ms"] / forensic["p50_ms"])
        lines += [
            "",
            f"Production mode returns early on the first Tier 1 severity-1.0 "
            f"finding. P50 reduction: **{delta_pct:.0f}%** "
            f"({forensic['p50_ms']:.0f}ms to {production['p50_ms']:.0f}ms).",
        ]

    lines += [
        "",
        "## Reproduction",
        "",
        "```",
        "python3 docs/benchmarks/v1_1_5_rtree_spatial_index.py",
        "```",
        "",
    ]

    out = _REPO_ROOT / "docs/benchmarks/v1_1_5_rtree_spatial_index.md"
    out.write_text("\n".join(lines))
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
