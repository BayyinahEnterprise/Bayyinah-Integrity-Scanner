#!/usr/bin/env python3
"""Build a clean pdfTeX article using \\usepackage{hyperref}, which
causes pdfTeX to emit /OpenAction = {/S: /GoTo, /D: [...]} (a GoTo
action wrapping a destination). This is the shape Bilal's resume
PDF carried in the incident report (Round 12 Bug 1, case 2).

Output: fixture_clean_pdftex_with_hyperref.pdf
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
TEX_SOURCE = r"""\documentclass[11pt]{article}
\usepackage{hyperref}
\hypersetup{pdfstartview={XYZ null null 1.0}}
\title{Round 12 Reproducer (pdfTeX with hyperref)}
\author{Test Author}
\date{}
\begin{document}
\maketitle
\section{Section A}
This document uses hyperref, which causes pdfTeX to emit
/OpenAction with a /GoTo subtype wrapping a destination array.
Per ISO 32000-1 \S12.6.3, /GoTo is navigation, not active
content. Office, file, fluffy ligatures.
\section{Section B}
More content. Quotes ``hello'' and `world'.
\end{document}
"""


def build(output_path: Path) -> None:
    workdir = output_path.parent / "_build_pdftex_hyperref"
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
    out = HERE / "fixture_clean_pdftex_with_hyperref.pdf"
    build(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
