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
#
# Cadence (per Bayyinah Engineering Discipline Framework v2.0 section 7.6):
# one frozenset per shipped minor and per shipped patch.
#
# When a release introduces zero __all__ changes, declare the new
# constant as = V_PRIOR_SURFACE rather than copying the names. This
# keeps the file readable while still giving each version boundary an
# explicit constant: future drift will appear in a diff at the named
# version rather than disappearing into an older snapshot.
#
# Capture command:
#   python -c "import bayyinah; print(sorted(set(bayyinah.__all__)))"
#
# Every prior snapshot stays in this file forever. Removing a snapshot
# is a parity break and follows PARITY.md.
#
# Original v1.2.0 snapshot recorded from main at commit 964562e (the
# parity-break release that added scan_complete and coverage to
# to_dict). Recorded 2026-05-02.

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


# v1.2.1 added documented limits enforcement (no surface delta).
# Snapshot is a deliberate alias of V1_2_0_SURFACE so future drift
# at the v1.2.1 boundary is visible in the diff.
V1_2_1_SURFACE: frozenset[str] = V1_2_0_SURFACE


# v1.2.2 added the Claude summarization queue. The queue is internal
# and exposed only via FastAPI endpoints, not via bayyinah.__all__.
# No surface delta. Snapshot is a deliberate alias of V1_2_0_SURFACE.
V1_2_2_SURFACE: frozenset[str] = V1_2_0_SURFACE


# v1.2.3 corrective release (Fraz round 10): no surface delta.
V1_2_3_SURFACE: frozenset[str] = V1_2_0_SURFACE


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


def test_v1_2_1_surface_is_subset_of_current():
    """Every name in the v1.2.1 surface must still be exported."""
    current = _current_surface()
    missing = set(V1_2_1_SURFACE) - current
    assert not missing, (
        f"Additive-only violation: names from v1.2.1 missing in the "
        f"current surface: {sorted(missing)}. If the removal is "
        f"intentional, follow the procedure in PARITY.md. Otherwise "
        f"the offending commit must be reverted."
    )


def test_v1_2_2_surface_is_subset_of_current():
    """Every name in the v1.2.2 surface must still be exported."""
    current = _current_surface()
    missing = set(V1_2_2_SURFACE) - current
    assert not missing, (
        f"Additive-only violation: names from v1.2.2 missing in the "
        f"current surface: {sorted(missing)}. If the removal is "
        f"intentional, follow the procedure in PARITY.md. Otherwise "
        f"the offending commit must be reverted."
    )


def test_v1_2_3_surface_is_subset_of_current():
    """Every name in the v1.2.3 surface must still be exported."""
    current = _current_surface()
    missing = set(V1_2_3_SURFACE) - current
    assert not missing, (
        f"Additive-only violation: names from v1.2.3 missing in the "
        f"current surface: {sorted(missing)}. If the removal is "
        f"intentional, follow the procedure in PARITY.md. Otherwise "
        f"the offending commit must be reverted."
    )
