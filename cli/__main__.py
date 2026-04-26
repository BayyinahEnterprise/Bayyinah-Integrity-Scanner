"""
Enable ``python -m cli`` as an alternative invocation of the Bayyinah CLI.

The canonical entry point is the ``bayyinah`` console script registered
via ``pyproject.toml`` ([project.scripts]). This ``__main__`` module is
an additive convenience: it lets developers run the CLI directly from a
source checkout without first installing the package.

    # After ``pip install bayyinah``:
    bayyinah scan document.pdf

    # From a source checkout (no install required):
    python -m cli scan document.pdf

Both paths resolve to ``cli.main.main``; the exit code contract (0/1/2)
is identical.
"""

from __future__ import annotations

import sys

from cli.main import main


if __name__ == "__main__":
    sys.exit(main())
