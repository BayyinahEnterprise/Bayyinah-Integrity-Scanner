"""
Phase 22 polish-pass tests (1.0 pre-release).

Covers the three additive-only surfaces introduced in the polish pass:

  1. The ``legacy`` conceptual-alias package, which re-exports the
     frozen reference modules without copying or shadowing them.
  2. The ``ScanService.scan(pdf_path=...)`` backward-compatibility
     keyword alias, which emits a ``DeprecationWarning`` but continues
     to function identically to the canonical ``file_path`` kwarg.
  3. ``python -m cli`` as an alternative invocation of the CLI
     ``main`` function (the canonical entry point is the ``bayyinah``
     console script).

All three are additive — no existing public surface is changed.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import warnings
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. legacy/ conceptual-alias package
# ---------------------------------------------------------------------------

def test_legacy_package_importable():
    """``from legacy import bayyinah_v0, bayyinah_v0_1`` resolves."""
    import legacy
    assert hasattr(legacy, "bayyinah_v0")
    assert hasattr(legacy, "bayyinah_v0_1")


def test_legacy_alias_resolves_to_top_level_module_objects():
    """The alias must be the *same module object* as the top-level import,
    not a copy. This is load-bearing: the md5-fingerprint CI check
    verifies one file on disk; any copy would break that invariant.
    """
    import legacy
    import bayyinah_v0
    import bayyinah_v0_1
    assert legacy.bayyinah_v0 is bayyinah_v0
    assert legacy.bayyinah_v0_1 is bayyinah_v0_1


def test_legacy_alias_scan_pdf_parity():
    """``legacy.bayyinah_v0.scan_pdf`` is literally ``bayyinah_v0.scan_pdf``.

    We do not re-assert byte-identical parity here (that is tested
    exhaustively in test_integration.py). We only assert the alias
    resolves to the same function object.
    """
    import legacy
    import bayyinah_v0
    import bayyinah_v0_1
    assert legacy.bayyinah_v0.scan_pdf is bayyinah_v0.scan_pdf
    assert legacy.bayyinah_v0_1.scan_pdf is bayyinah_v0_1.scan_pdf


def test_legacy_module_dunder_all():
    """Keep ``__all__`` in sync with what the package actually exports."""
    import legacy
    assert set(legacy.__all__) == {"bayyinah_v0", "bayyinah_v0_1"}


# ---------------------------------------------------------------------------
# 2. ScanService.scan(pdf_path=...) backward-compat alias
# ---------------------------------------------------------------------------

@pytest.fixture
def clean_pdf() -> Path:
    """A byte-clean PDF fixture — zero findings, integrity 1.0."""
    p = Path("tests/fixtures/clean.pdf")
    if not p.exists():
        pytest.skip(f"fixture not generated: {p} — run tests/make_test_documents.py")
    return p


def test_scan_positional_still_works(clean_pdf: Path):
    """Positional callers must continue to work unchanged."""
    from bayyinah import ScanService
    report = ScanService().scan(clean_pdf)
    assert report.error is None or report.error == ""
    assert report.integrity_score == 1.0


def test_scan_file_path_kwarg(clean_pdf: Path):
    """The canonical keyword ``file_path=`` works cleanly."""
    from bayyinah import ScanService
    report = ScanService().scan(file_path=clean_pdf)
    assert report.integrity_score == 1.0


def test_scan_pdf_path_kwarg_still_accepted(clean_pdf: Path):
    """Deprecated ``pdf_path=`` keyword must still function identically."""
    from bayyinah import ScanService
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        report = ScanService().scan(pdf_path=clean_pdf)
    assert report.integrity_score == 1.0
    # Exactly one DeprecationWarning emitted, and it names the offending kwarg.
    dep = [w for w in recorded if issubclass(w.category, DeprecationWarning)]
    assert len(dep) == 1
    assert "pdf_path" in str(dep[0].message)


def test_scan_pdf_path_and_file_path_both_raises(clean_pdf: Path):
    """Passing both the new and old kwarg is a TypeError — explicit refusal
    rather than silently preferring one over the other."""
    from bayyinah import ScanService
    with pytest.raises(TypeError, match="both 'file_path' and 'pdf_path'"):
        ScanService().scan(file_path=clean_pdf, pdf_path=clean_pdf)


def test_scan_missing_argument_raises():
    """Calling scan() with neither positional nor keyword must raise."""
    from bayyinah import ScanService
    with pytest.raises(TypeError, match="missing required argument"):
        ScanService().scan()


def test_scan_deprecation_warning_is_actionable(clean_pdf: Path):
    """The DeprecationWarning must include the remediation hint."""
    from bayyinah import ScanService
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        ScanService().scan(pdf_path=clean_pdf)
    (dep,) = [w for w in recorded if issubclass(w.category, DeprecationWarning)]
    msg = str(dep.message)
    assert "file_path" in msg
    assert "1.0.0" in msg


# ---------------------------------------------------------------------------
# 3. `python -m cli` invocation
# ---------------------------------------------------------------------------

def test_python_m_cli_version():
    """``python -m cli --version`` prints a recognisable version string."""
    result = subprocess.run(
        [sys.executable, "-m", "cli", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "bayyinah" in result.stdout.lower() or "bayyinah" in result.stderr.lower()


def test_python_m_cli_help_mentions_scan():
    """``python -m cli --help`` lists the ``scan`` subcommand."""
    result = subprocess.run(
        [sys.executable, "-m", "cli", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "scan" in result.stdout
