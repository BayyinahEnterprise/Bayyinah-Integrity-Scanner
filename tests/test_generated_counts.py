"""The README's mechanism counts are generated from the registry."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_readme_counts_match_the_registry() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "generate_counts.py")],
        capture_output=True, text=True, cwd=ROOT)
    assert result.returncode == 0, result.stdout
