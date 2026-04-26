"""
End-to-end integration tests — the final guardrail of the Al-Baqarah refactor.

These tests assert the contract the world sees:

  1. ``bayyinah.scan_pdf`` (public Python API) produces byte-identical
     reports to ``bayyinah_v0.scan_pdf`` on every Phase 0 fixture.
  2. The ``bayyinah`` CLI (``cli.main:main``) emits the same output and
     exits with the same code as the library API would suggest.
  3. The public ``__all__`` surface is stable — every advertised
     symbol is importable and has the expected type.
  4. The CLI's --json output is well-formed JSON and contains every
     finding.
  5. Exit codes 0 / 1 / 2 for clean / findings / error are preserved
     byte-for-byte from v0/v0.1 semantics.

This file is the Phase 7 ratchet: a change that breaks any of the
above invariants fails these tests, forcing conscious acknowledgement
before shipping.
"""

from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

import bayyinah_v0
import bayyinah_v0_1
import bayyinah
from bayyinah import (
    BatinObjectAnalyzer,
    Finding,
    IntegrityReport,
    ScanService,
    ZahirTextAnalyzer,
    __version__,
    format_text_report,
    scan_pdf,
)
from cli.main import (
    EXIT_CLEAN,
    EXIT_ERROR,
    EXIT_FINDINGS,
    _build_parser,
    _exit_code_for,
    main as cli_main,
)

from tests.make_test_documents import FIXTURES, FIXTURES_DIR


# ---------------------------------------------------------------------------
# Fixture regeneration (same pattern as the other test modules)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _ensure_fixtures_built() -> None:
    missing = [fx.out_path for fx in FIXTURES.values() if not fx.out_path.exists()]
    if not missing:
        return
    subprocess.run(
        [sys.executable, "-m", "tests.make_test_documents"],
        check=True,
        cwd=str(FIXTURES_DIR.parent.parent),
    )


CLEAN_PDF = FIXTURES_DIR / "clean.pdf"
TEXT_FIXTURE_DIR = FIXTURES_DIR / "text"
OBJECT_FIXTURE_DIR = FIXTURES_DIR / "object"
POSITIVE_COMBINED = FIXTURES_DIR / "positive_combined.pdf"


def _all_phase0_fixtures() -> list[Path]:
    pdfs = [CLEAN_PDF]
    pdfs.extend(sorted(TEXT_FIXTURE_DIR.glob("*.pdf")))
    pdfs.extend(sorted(OBJECT_FIXTURE_DIR.glob("*.pdf")))
    if POSITIVE_COMBINED.exists():
        pdfs.append(POSITIVE_COMBINED)
    return [p for p in pdfs if p.exists()]


# ---------------------------------------------------------------------------
# IndirectObject normalisation — pypdf's repr embeds id(parent), which
# differs across independent reader instances. Parity needs to ignore it.
# ---------------------------------------------------------------------------

_INDIRECT_RE = re.compile(r"IndirectObject\((\d+),\s*(\d+),\s*\d+\)")


def _normalise(s: str) -> str:
    return _INDIRECT_RE.sub(r"IndirectObject(\1, \2, <id>)", s)


def _finding_tuple(f) -> tuple:
    return (
        f.mechanism,
        f.tier,
        round(f.confidence, 6),
        _normalise(f.description),
        _normalise(f.location),
        _normalise(f.surface),
        _normalise(f.concealed),
    )


# ---------------------------------------------------------------------------
# Public API surface — every advertised symbol resolves, is importable,
# and has the expected type.
# ---------------------------------------------------------------------------

class TestPublicSurface:
    def test_version_is_published(self) -> None:
        assert bayyinah.__version__
        assert re.fullmatch(r"\d+\.\d+\.\d+", bayyinah.__version__)

    def test_scan_pdf_is_callable(self) -> None:
        assert callable(bayyinah.scan_pdf)

    def test_format_text_report_is_callable(self) -> None:
        assert callable(bayyinah.format_text_report)

    def test_scan_service_is_exported(self) -> None:
        assert bayyinah.ScanService is ScanService

    def test_integrity_report_is_exported(self) -> None:
        assert bayyinah.IntegrityReport is IntegrityReport

    def test_finding_is_exported(self) -> None:
        assert bayyinah.Finding is Finding

    def test_analyzers_are_exported(self) -> None:
        assert bayyinah.ZahirTextAnalyzer is ZahirTextAnalyzer
        assert bayyinah.BatinObjectAnalyzer is BatinObjectAnalyzer

    def test_all_exports_resolve(self) -> None:
        """Every symbol in __all__ must resolve to a non-None attribute."""
        for name in bayyinah.__all__:
            assert hasattr(bayyinah, name), f"missing: {name}"
            assert getattr(bayyinah, name) is not None

    def test_no_accidental_private_reexport(self) -> None:
        """Nothing in __all__ should be a private-prefixed name."""
        for name in bayyinah.__all__:
            assert not name.startswith("_") or name == "__version__", name


# ---------------------------------------------------------------------------
# Library-API parity — bayyinah.scan_pdf vs bayyinah_v0.scan_pdf
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_scan_pdf_parity_with_v0(pdf_path: Path) -> None:
    """The 0.2 public scan_pdf must emit byte-identical findings to the
    original monolithic v0.scan_pdf. This is the top-level ratchet."""
    ours = bayyinah.scan_pdf(pdf_path)
    theirs = bayyinah_v0.scan_pdf(pdf_path)

    ours_tuples = [_finding_tuple(f) for f in ours.findings]
    theirs_tuples = [_finding_tuple(f) for f in theirs.findings]

    assert ours_tuples == theirs_tuples, (
        f"Parity diverged with v0 on {pdf_path.name}:\n"
        f"  ours:   {ours_tuples}\n"
        f"  v0:     {theirs_tuples}"
    )
    assert abs(ours.integrity_score - theirs.integrity_score) < 1e-9
    assert ours.error == theirs.error
    assert ours.scan_incomplete == theirs.scan_incomplete


@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_scan_pdf_parity_with_v01(pdf_path: Path) -> None:
    """Transitive: bayyinah.scan_pdf == bayyinah_v0_1.scan_pdf too."""
    ours = bayyinah.scan_pdf(pdf_path)
    theirs = bayyinah_v0_1.scan_pdf(pdf_path)

    ours_tuples = [_finding_tuple(f) for f in ours.findings]
    theirs_tuples = [_finding_tuple(f) for f in theirs.findings]

    assert ours_tuples == theirs_tuples
    assert abs(ours.integrity_score - theirs.integrity_score) < 1e-9
    assert ours.error == theirs.error
    assert ours.scan_incomplete == theirs.scan_incomplete


def test_scan_pdf_accepts_string_path() -> None:
    """Library API must accept str — CI scripts pass strings."""
    r = scan_pdf(str(CLEAN_PDF))
    assert r.integrity_score == 1.0


def test_scan_pdf_accepts_path_object() -> None:
    r = scan_pdf(CLEAN_PDF)
    assert r.integrity_score == 1.0


def test_format_text_report_is_byte_identical_to_v01() -> None:
    """The terminal formatter wraps the v0.1 output shape — an
    informational diff here signals a formatter drift."""
    report = scan_pdf(CLEAN_PDF)
    v01_report = bayyinah_v0_1.scan_pdf(CLEAN_PDF)

    ours = format_text_report(report)
    theirs = bayyinah_v0_1.format_text_report(v01_report)

    assert ours == theirs


# ---------------------------------------------------------------------------
# CLI exit code semantics — the stable contract CI pipelines depend on
# ---------------------------------------------------------------------------

class TestCliExitCodeConstants:
    def test_clean_is_zero(self) -> None:
        assert EXIT_CLEAN == 0

    def test_findings_is_one(self) -> None:
        assert EXIT_FINDINGS == 1

    def test_error_is_two(self) -> None:
        assert EXIT_ERROR == 2


class TestCliExitCodeMapping:
    def test_clean_report_yields_zero(self) -> None:
        report = IntegrityReport(file_path="x", integrity_score=1.0)
        assert _exit_code_for(report) == EXIT_CLEAN

    def test_findings_report_yields_one(self) -> None:
        report = IntegrityReport(
            file_path="x",
            integrity_score=0.8,
            findings=[Finding(
                mechanism="javascript",
                tier=1,
                confidence=1.0,
                description="...",
                location="doc",
                surface="...",
                concealed="...",
            )],
        )
        assert _exit_code_for(report) == EXIT_FINDINGS

    def test_error_report_yields_two(self) -> None:
        report = IntegrityReport(
            file_path="x",
            integrity_score=0.0,
            error="File not found: x",
            scan_incomplete=True,
        )
        assert _exit_code_for(report) == EXIT_ERROR

    def test_error_overrides_findings(self) -> None:
        """error + findings → EXIT_ERROR; error is the dominant signal."""
        report = IntegrityReport(
            file_path="x",
            integrity_score=0.5,
            error="Object layer scan error: ...",
            findings=[Finding(
                mechanism="scan_error", tier=3, confidence=0.5,
                description="...", location="document",
                surface="...", concealed="...",
            )],
            scan_incomplete=True,
        )
        assert _exit_code_for(report) == EXIT_ERROR


# ---------------------------------------------------------------------------
# CLI argument parser — introspective tests
# ---------------------------------------------------------------------------

class TestCliParser:
    def test_scan_subcommand_exists(self) -> None:
        parser = _build_parser()
        # argparse does not expose subparsers directly; parsing a known
        # scan invocation is the pragmatic check.
        ns = parser.parse_args(["scan", "tests/fixtures/clean.pdf"])
        assert ns.command == "scan"
        assert ns.file == Path("tests/fixtures/clean.pdf")

    def test_scan_accepts_json_flag(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["scan", "x.pdf", "--json"])
        assert ns.json is True
        assert ns.quiet is False
        assert ns.summary is False

    def test_scan_accepts_quiet_flag(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["scan", "x.pdf", "--quiet"])
        assert ns.quiet is True

    def test_scan_accepts_summary_flag(self) -> None:
        parser = _build_parser()
        ns = parser.parse_args(["scan", "x.pdf", "--summary"])
        assert ns.summary is True

    def test_json_and_quiet_are_mutually_exclusive(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["scan", "x.pdf", "--json", "--quiet"])

    def test_json_and_summary_are_mutually_exclusive(self) -> None:
        parser = _build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["scan", "x.pdf", "--json", "--summary"])

    def test_no_subcommand_is_accepted_by_parser(self) -> None:
        """Parser accepts empty argv — main() is responsible for
        reporting the missing-command error, not the parser."""
        parser = _build_parser()
        ns = parser.parse_args([])
        assert ns.command is None


# ---------------------------------------------------------------------------
# CLI in-process invocation — calling main() directly
# ---------------------------------------------------------------------------

class TestCliInProcess:
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        """Invoke cli.main.main() with stdout/stderr captured."""
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli_main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_clean_fixture_exits_zero(self) -> None:
        code, stdout, _ = self._run(["scan", str(CLEAN_PDF)])
        assert code == EXIT_CLEAN
        assert "Integrity score" in stdout

    def test_findings_fixture_exits_one(self) -> None:
        pdf = TEXT_FIXTURE_DIR / "zero_width.pdf"
        code, stdout, _ = self._run(["scan", str(pdf)])
        assert code == EXIT_FINDINGS
        assert "zero_width_chars" in stdout

    def test_missing_file_exits_two(self, tmp_path: Path) -> None:
        code, stdout, _ = self._run(["scan", str(tmp_path / "ghost.pdf")])
        assert code == EXIT_ERROR
        assert "File not found" in stdout

    def test_unopenable_pdf_exits_two(self, tmp_path: Path) -> None:
        bad = tmp_path / "corrupt.pdf"
        bad.write_bytes(b"not a pdf")
        code, stdout, _ = self._run(["scan", str(bad)])
        assert code == EXIT_ERROR
        assert "Could not open PDF" in stdout

    def test_quiet_flag_suppresses_stdout(self) -> None:
        pdf = TEXT_FIXTURE_DIR / "zero_width.pdf"
        code, stdout, _ = self._run(["scan", str(pdf), "--quiet"])
        assert code == EXIT_FINDINGS
        assert stdout == ""

    def test_summary_flag_emits_single_paragraph(self) -> None:
        pdf = TEXT_FIXTURE_DIR / "zero_width.pdf"
        code, stdout, _ = self._run(["scan", str(pdf), "--summary"])
        assert code == EXIT_FINDINGS
        # summary is a single paragraph; no giant frame decoration.
        assert "=" * 20 not in stdout
        assert "Integrity score" in stdout

    def test_json_flag_emits_parseable_json(self) -> None:
        pdf = TEXT_FIXTURE_DIR / "zero_width.pdf"
        code, stdout, _ = self._run(["scan", str(pdf), "--json"])
        assert code == EXIT_FINDINGS
        data = json.loads(stdout)
        assert data["file_path"].endswith("zero_width.pdf")
        assert isinstance(data["findings"], list)
        assert any(f["mechanism"] == "zero_width_chars" for f in data["findings"])

    def test_no_command_prints_help_and_errors(self) -> None:
        code, _, stderr = self._run([])
        assert code == EXIT_ERROR
        # argparse help text begins with "usage:"
        assert "usage" in stderr.lower()

    def test_version_flag(self) -> None:
        with pytest.raises(SystemExit) as ei:
            self._run(["--version"])
        # argparse --version exits 0 itself
        assert ei.value.code == 0


# ---------------------------------------------------------------------------
# CLI subprocess invocation — exercises the real console-script path
# ---------------------------------------------------------------------------

class TestCliSubprocess:
    """Exercise the CLI as users will actually run it — a separate Python
    process, no shared state with the test runner. ``python -m cli.main``
    is equivalent to the installed ``bayyinah`` console script; the
    ``[project.scripts]`` binding is ``cli.main:main``."""

    _REPO_ROOT = Path(__file__).resolve().parent.parent

    def _invoke(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "cli.main", *args],
            cwd=str(self._REPO_ROOT),
            capture_output=True,
            text=True,
        )

    def test_clean_fixture_yields_zero(self) -> None:
        result = self._invoke("scan", str(CLEAN_PDF))
        assert result.returncode == EXIT_CLEAN
        assert "1.000 / 1.000" in result.stdout

    def test_findings_fixture_yields_one(self) -> None:
        pdf = TEXT_FIXTURE_DIR / "homoglyph.pdf"
        result = self._invoke("scan", str(pdf))
        assert result.returncode == EXIT_FINDINGS
        assert "homoglyph" in result.stdout

    def test_missing_file_yields_two(self, tmp_path: Path) -> None:
        result = self._invoke("scan", str(tmp_path / "ghost.pdf"))
        assert result.returncode == EXIT_ERROR

    def test_json_output_is_valid_json(self) -> None:
        pdf = OBJECT_FIXTURE_DIR / "embedded_javascript.pdf"
        result = self._invoke("scan", str(pdf), "--json")
        assert result.returncode == EXIT_FINDINGS
        data = json.loads(result.stdout)
        mechanisms = {f["mechanism"] for f in data["findings"]}
        assert "javascript" in mechanisms
        assert "openaction" in mechanisms

    def test_quiet_flag_really_is_quiet(self) -> None:
        result = self._invoke("scan", str(CLEAN_PDF), "--quiet")
        assert result.returncode == EXIT_CLEAN
        assert result.stdout == ""

    def test_version_prints_version_and_exits_zero(self) -> None:
        result = self._invoke("--version")
        assert result.returncode == 0
        assert f"bayyinah {__version__}" in result.stdout

    def test_help_contains_scan_subcommand(self) -> None:
        result = self._invoke("--help")
        assert result.returncode == 0
        assert "scan" in result.stdout


# ---------------------------------------------------------------------------
# CLI ↔ library-API parity — both routes produce the same IntegrityReport
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pdf_path",
    _all_phase0_fixtures(),
    ids=[p.name for p in _all_phase0_fixtures()],
)
def test_cli_json_output_matches_library_api(pdf_path: Path) -> None:
    """JSON emitted by the CLI must equal ``report.to_dict()`` of the
    library-API scan on the same fixture."""
    result = subprocess.run(
        [sys.executable, "-m", "cli.main", "scan", str(pdf_path), "--json"],
        cwd=str(Path(__file__).resolve().parent.parent),
        capture_output=True,
        text=True,
    )
    assert result.returncode in (EXIT_CLEAN, EXIT_FINDINGS, EXIT_ERROR)

    cli_report = json.loads(result.stdout)

    lib_report = bayyinah.scan_pdf(pdf_path)
    # JSON round-trips through json.dumps(default=str) — this matches how
    # the CLI serialises.
    lib_report_json = json.loads(
        json.dumps(lib_report.to_dict(), default=str)
    )
    # Finding lists: normalise IndirectObject reprs on both sides before
    # diffing. Must recurse — findings carry nested evidence dicts/lists
    # whose string values also embed IndirectObject reprs.
    def _norm_deep(obj):
        if isinstance(obj, str):
            return _normalise(obj)
        if isinstance(obj, dict):
            return {k: _norm_deep(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_norm_deep(v) for v in obj]
        return obj

    assert _norm_deep(cli_report) == _norm_deep(lib_report_json), (
        f"CLI JSON diverged from library API on {pdf_path.name}"
    )


# ---------------------------------------------------------------------------
# Additive-only isolation — the legacy surface is untouched
# ---------------------------------------------------------------------------

class TestAdditiveIsolation:
    def test_v0_scan_pdf_still_works(self) -> None:
        report = bayyinah_v0.scan_pdf(CLEAN_PDF)
        assert report.integrity_score == 1.0
        assert report.findings == []

    def test_v01_scan_pdf_still_works(self) -> None:
        report = bayyinah_v0_1.scan_pdf(CLEAN_PDF)
        assert report.integrity_score == 1.0
        assert report.findings == []

    def test_v0_main_still_importable(self) -> None:
        """Downstream callers pinning to ``bayyinah_v0.main`` must
        keep working — the CLI rebinding is additive."""
        assert callable(bayyinah_v0.main)

    def test_v01_main_still_importable(self) -> None:
        assert callable(bayyinah_v0_1.main)

    def test_new_scan_service_is_distinct_from_v01(self) -> None:
        assert ScanService is not bayyinah_v0_1.ScanService

    def test_package_scan_pdf_is_distinct_from_v0(self) -> None:
        """bayyinah.scan_pdf is a new function, not a re-export of v0."""
        assert bayyinah.scan_pdf is not bayyinah_v0.scan_pdf
        assert bayyinah.scan_pdf is not bayyinah_v0_1.scan_pdf

    def test_package_does_not_import_v0_or_v01(self) -> None:
        """The ``bayyinah`` package must not depend on the legacy
        modules. This keeps the layered architecture honest."""
        import bayyinah as b
        assert "bayyinah_v0" not in b.__dict__
        assert "bayyinah_v0_1" not in b.__dict__


# ---------------------------------------------------------------------------
# Release-readiness sanity
# ---------------------------------------------------------------------------

class TestReleaseReadiness:
    def test_pyproject_version_matches_package_version(self) -> None:
        """pyproject.toml and bayyinah.__version__ must agree — a
        drift here means a mis-cut release."""
        pyproject = (
            Path(__file__).resolve().parent.parent / "pyproject.toml"
        ).read_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', pyproject, re.MULTILINE)
        assert match is not None
        assert match.group(1) == __version__

    def test_license_file_exists(self) -> None:
        assert (
            Path(__file__).resolve().parent.parent / "LICENSE"
        ).is_file()

    def test_readme_exists(self) -> None:
        assert (
            Path(__file__).resolve().parent.parent / "README.md"
        ).is_file()

    def test_changelog_exists(self) -> None:
        assert (
            Path(__file__).resolve().parent.parent / "CHANGELOG.md"
        ).is_file()

    def test_readme_cites_munafiq_protocol(self) -> None:
        readme = (
            Path(__file__).resolve().parent.parent / "README.md"
        ).read_text()
        assert "10.5281/zenodo.19677111" in readme

    def test_changelog_mentions_current_version(self) -> None:
        changelog = (
            Path(__file__).resolve().parent.parent / "CHANGELOG.md"
        ).read_text()
        assert __version__ in changelog

    def test_license_is_apache_2_0(self) -> None:
        license_text = (
            Path(__file__).resolve().parent.parent / "LICENSE"
        ).read_text()
        assert "Apache License" in license_text
        assert "Version 2.0" in license_text
