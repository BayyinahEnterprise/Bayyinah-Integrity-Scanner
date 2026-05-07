#!/usr/bin/env python3
"""Build a clean pdfTeX-produced article PDF (Round 12 fixture).

Reproduces Bug 2 (tounicode_anomaly false positive on Computer
Modern fonts) when scanned with v1.2.3. Post-fix, the producer-
signature suppression in v1.2.4 keeps this fixture clean.

Determinism: SOURCE_DATE_EPOCH=0 strips the build timestamp.
The output is byte-stable across runs given the same TeX
distribution.

Output: clean_pdftex_article.pdf
"""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
TEX_SOURCE = r"""\documentclass[11pt]{article}
\title{Round 12 Reproducer (clean pdfTeX article)}
\author{Test Author}
\date{}
\begin{document}
\maketitle
This is a Round 12 corpus fixture. It uses Computer Modern fonts,
which emit ToUnicode CMaps the v1.2.3 heuristic flagged as
adversarial. The v1.2.4 fix suppresses this on TeX-stack
producers. Ligatures: office, file, fluffy. Quotes: ``hello''
and `world'. Math: $\alpha + \beta = \gamma$.
\end{document}
"""


def build(output_path: Path) -> None:
    workdir = output_path.parent / "_build_pdftex_article"
    workdir.mkdir(parents=True, exist_ok=True)
    tex_path = workdir / "article.tex"
    tex_path.write_text(TEX_SOURCE)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = "0"
    for _ in range(2):
        subprocess.run(
            ["pdflatex", "-interaction=nonstopmode", "article.tex"],
            cwd=workdir, env=env, check=True, capture_output=True,
        )
    (workdir / "article.pdf").rename(output_path)
    for ext in (".tex", ".aux", ".log", ".out"):
        for f in workdir.glob(f"*{ext}"):
            f.unlink(missing_ok=True)
    workdir.rmdir()


if __name__ == "__main__":
    out = HERE / "fixture_clean_pdftex_article.pdf"
    build(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
