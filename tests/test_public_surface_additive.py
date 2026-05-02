"""Verify bayyinah's public surface is additive-only.

Records the public API at each minor (and where notable, patch)
version. Every prior snapshot must be a subset of the current
surface. If a name must be removed, follow the PARITY.md procedure
(file an issue tagged parity-break, cross-reference from
CHANGELOG.md, retain the prior name as a deprecation shim for at
least one minor version, update this test to reflect the deliberate
break).

This test closes the East-West asymmetry identified in the round-3
external audit: Furqan-the-language enforces additive-only at the
.fqn boundary via src/furqan/checker/additive.py; Bayyinah-the-
Python-package now enforces it at the bayyinah.__all__ boundary
here.
"""
from __future__ import annotations

import bayyinah


def _current_surface() -> set[str]:
    """The current public surface of the bayyinah package."""
    if hasattr(bayyinah, "__all__"):
        return set(bayyinah.__all__)
    return {n for n in dir(bayyinah) if not n.startswith("_")}


# ---------------------------------------------------------------------------
# Recorded snapshots (chronological, oldest first)
# ---------------------------------------------------------------------------
# Snapshot recorded from v1.2.0 main at commit 964562e (the parity-break
# release that added scan_complete and coverage to to_dict). Recorded
# 2026-05-02 at the start of v1.2.1 work.
#
# Procedure for adding a new snapshot when a new minor/patch ships:
#   python -c "import bayyinah; print(sorted(set(bayyinah.__all__)))"
# Paste the result as a new V_X_Y_Z_SURFACE constant. Every prior
# snapshot stays in this file forever.

V1_2_0_SURFACE: frozenset[str] = frozenset({
    # 58 names captured from bayyinah.__all__ at commit 964562e.
    "AnalyzerRegistrationError",
    "AnalyzerRegistry",
    "AudioAnalyzer",
    "BaseAnalyzer",
    "BatinObjectAnalyzer",
    "BayyinahError",
    "CrossModalCorrelationEngine",
    "CsvAnalyzer",
    "DEFAULT_LIMITS",
    "DocxAnalyzer",
    "EmlAnalyzer",
    "FallbackAnalyzer",
    "FileKind",
    "FileRouter",
    "FileTypeDetection",
    "Finding",
    "HtmlAnalyzer",
    "IntegrityReport",
    "InvalidFindingError",
    "JsonReportFormatter",
    "MECHANISM_REGISTRY",
    "PDFClient",
    "PDFParseError",
    "PlainLanguageFormatter",
    "PptxAnalyzer",
    "ReportFormatter",
    "ScanError",
    "ScanLimits",
    "ScanService",
    "SourceLayer",
    "TOOL_NAME",
    "TOOL_VERSION",
    "TerminalReportFormatter",
    "UnknownFileType",
    "UnsupportedFileType",
    "VERDICT_DISCLAIMER",
    "VERDICT_MUGHLAQ",
    "VERDICT_MUKHFI",
    "VERDICT_MUNAFIQ",
    "VERDICT_MUSHTABIH",
    "VERDICT_SAHIH",
    "Verdict",
    "VideoAnalyzer",
    "XlsxAnalyzer",
    "ZahirTextAnalyzer",
    "__version__",
    "apply_scan_incomplete_clamp",
    "compute_muwazana_score",
    "default_pdf_registry",
    "default_registry",
    "format_text_report",
    "get_current_limits",
    "limits_context",
    "plain_language_summary",
    "scan_file",
    "scan_pdf",
    "set_current_limits",
    "tamyiz_verdict",
})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_current_surface_is_not_empty():
    """Sanity check: the surface should have at least 50 names."""
    current = _current_surface()
    assert len(current) >= 50, (
        f"Public surface unexpectedly small: {len(current)} names. "
        f"Expected at least 50."
    )


def test_v1_2_0_surface_is_subset_of_current():
    """Every name in the v1.2.0 surface must still be exported."""
    current = _current_surface()
    missing = set(V1_2_0_SURFACE) - current
    assert not missing, (
        f"Additive-only violation: names from v1.2.0 missing in the "
        f"current surface: {sorted(missing)}. If the removal is "
        f"intentional, follow the procedure in PARITY.md. Otherwise "
        f"the offending commit must be reverted."
    )
