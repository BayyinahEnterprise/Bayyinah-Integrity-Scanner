"""
Bayyinah CLI — the public command-line surface.

Entry point: ``cli.main:main``. Wired to the ``bayyinah`` console script
via ``[project.scripts]`` in ``pyproject.toml``.

Usage::

    bayyinah scan <file>                    # human-readable report
    bayyinah scan <file> --json             # JSON report
    bayyinah scan <file> --quiet            # exit code only
    bayyinah scan <file> --summary          # one-paragraph summary

Exit codes (preserved from v0/v0.1 so CI pipelines do not break):

    0   scan completed with zero findings (file clean)
    1   scan completed with one or more findings
    2   scan did not complete (file not found, unparseable, etc.)
"""

from __future__ import annotations

from cli.main import main

__all__ = ["main"]
