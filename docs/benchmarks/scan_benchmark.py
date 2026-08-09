"""
Bayyinah /scan timing benchmark. Substantiates per-document scan latency.

Methodology:
  - Cold call: first invocation per file (includes any lazy import warm-up).
  - Warm runs: 5 subsequent invocations per file; report mean and stdev.
  - Wall-clock measured around bayyinah.scan_file (in-process API call,
    same code path as the FastAPI /scan endpoint, which writes the upload
    to a temp file and calls scan_file). Network round-trip excluded.
  - Reports: file, size_bytes, pages, cold_ms, warm_mean_ms, warm_stdev_ms.

Run:
  python scan_benchmark.py
Outputs:
  - prints a markdown table to stdout
  - writes the same table to docs/benchmarks/v1_1_2_scan_timing.md
"""
import os
import statistics
import sys
import time
from pathlib import Path

# Resolve the bayyinah package from the repo checkout, not from any
# pip-installed copy in site-packages. The repo root is two parents up
# from this file: <repo>/docs/benchmarks/scan_benchmark.py.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import bayyinah  # noqa: E402

try:
    from pypdf import PdfReader
except Exception:
    from PyPDF2 import PdfReader  # type: ignore

# Script lives at <repo>/docs/benchmarks/scan_benchmark.py
REPO = _REPO_ROOT
assert Path(bayyinah.__file__).resolve().is_relative_to(REPO), (
    f"bayyinah imported from {bayyinah.__file__} but expected a path under {REPO}."
    " Uninstall any pip-installed bayyinah or run from the repo root."
)

FILES = [
    REPO / "tests/fixtures/clean.pdf",
    REPO / "tests/fixtures/positive_combined.pdf",
    REPO / "papers/Bayyinah_Thesis_Paper.pdf",
    REPO / "papers/Bayyinah_White_Paper.pdf",
    # Synthesized 50-page PDF; produced by build_50pg_fixture() below.
    REPO / "docs/benchmarks/clean_50pg.pdf",
]


def build_50pg_fixture() -> None:
    """Generate a 50-page clean PDF for the page-count benchmark if missing.

    The fixture is synthetic (plain text on letter pages) and is regenerated
    deterministically rather than committed, so the repository does not carry
    a reportlab-produced binary that could drift across reportlab versions.
    """
    target = REPO / "docs/benchmarks/clean_50pg.pdf"
    if target.exists():
        return
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    target.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(target), pagesize=letter)
    body = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 30
    for i in range(50):
        c.setFont("Helvetica", 12)
        c.drawString(72, 720, f"Page {i + 1} of 50 - benchmark filler")
        y = 690
        for line in [body[j:j + 90] for j in range(0, len(body), 90)][:30]:
            c.drawString(72, y, line)
            y -= 14
        c.showPage()
    c.save()


def page_count(p: Path) -> str:
    try:
        return str(len(PdfReader(str(p)).pages))
    except Exception as e:
        return f"err"


def time_scan(p: Path) -> float:
    t0 = time.perf_counter()
    bayyinah.scan_file(str(p))
    return (time.perf_counter() - t0) * 1000.0


def run() -> str:
    build_50pg_fixture()
    rows = []
    for f in FILES:
        if not f.exists():
            print(f"SKIP missing: {f}")
            continue
        size = f.stat().st_size
        pages = page_count(f)
        # Cold
        cold = time_scan(f)
        # Warm
        warms = [time_scan(f) for _ in range(5)]
        rows.append({
            "file": f.name,
            "size": size,
            "pages": pages,
            "cold_ms": cold,
            "warm_mean": statistics.mean(warms),
            "warm_stdev": statistics.stdev(warms) if len(warms) > 1 else 0.0,
        })

    # Markdown table
    lines = []
    lines.append("| File | Size (bytes) | Pages | Cold (ms) | Warm mean (ms) | Warm stdev (ms) |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for r in rows:
        lines.append(
            f"| `{r['file']}` | {r['size']:,} | {r['pages']} | "
            f"{r['cold_ms']:.1f} | {r['warm_mean']:.1f} | {r['warm_stdev']:.1f} |"
        )
    table = "\n".join(lines)
    print(table)
    return table


if __name__ == "__main__":
    print(f"bayyinah version: {bayyinah.__version__}")
    table = run()
    print(f"\nbenchmark complete; report committed at docs/benchmarks/v1_1_2_scan_timing.md")
