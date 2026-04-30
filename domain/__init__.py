"""
Bayyinah domain layer.

Pure data types and pure operations. No I/O, no parser dependencies,
no global state. This package is the language in which the rest of
Bayyinah describes what it found — analyzers build ``Finding`` objects,
the scan service assembles them into an ``IntegrityReport``, the
reporting layer reads the report and renders it.

Phase 1 of the Al-Baqarah refactor. Additive-only: the legacy
``bayyinah_v0`` and ``bayyinah_v0_1`` modules continue to define their
own internal Finding / IntegrityReport shapes until later phases
migrate the analyzers onto this domain contract.
"""

from __future__ import annotations

from domain.config import (
    BATIN_MECHANISMS,
    CONFUSABLE_TO_LATIN,
    DEFAULT_LIMITS,
    MECHANISM_REGISTRY,
    ROUTING_MECHANISMS,
    SEVERITY,
    ScanLimits,
    TIER,
    TIER_LEGEND,
    TOOL_NAME,
    TOOL_VERSION,
    VERDICT_DISCLAIMER,
    VERDICT_MUGHLAQ,
    VERDICT_MUKHFI,
    VERDICT_MUNAFIQ,
    VERDICT_MUSHTABIH,
    VERDICT_SAHIH,
    ZAHIR_MECHANISMS,
    SourceLayer,
    Verdict,
    get_current_limits,
    limits_context,
    set_current_limits,
)
from domain.exceptions import (
    BayyinahError,
    InvalidFindingError,
    PDFParseError,
    ScanError,
)
from domain.content_index import (
    AnnotInfo,
    ContentIndex,
    DrawingInfo,
    FontInfo,
    PikepdfAnnotInfo,
    SpanInfo,
    content_index_context,
    get_current_content_index,
    set_current_content_index,
)
from domain.cost_classes import CostClass, MECHANISM_COST_CLASS, cost_class
from domain.finding import Finding, ROUTING_DISCLOSURE_KEYS
from domain.integrity_report import IntegrityReport
from domain.value_objects import (
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
    tamyiz_verdict,
)

__all__ = [
    # Dataclasses
    "Finding",
    "IntegrityReport",
    # Pure functions
    "compute_muwazana_score",
    "tamyiz_verdict",
    "apply_scan_incomplete_clamp",
    # Exceptions
    "BayyinahError",
    "InvalidFindingError",
    "PDFParseError",
    "ScanError",
    # Config — most frequently imported members
    "MECHANISM_REGISTRY",
    "SEVERITY",
    "TIER",
    "TIER_LEGEND",
    "VERDICT_DISCLAIMER",
    "TOOL_NAME",
    "TOOL_VERSION",
    "ZAHIR_MECHANISMS",
    "BATIN_MECHANISMS",
    "ROUTING_MECHANISMS",
    "ROUTING_DISCLOSURE_KEYS",
    "CONFUSABLE_TO_LATIN",
    "SourceLayer",
    "Verdict",
    "VERDICT_SAHIH",
    "VERDICT_MUSHTABIH",
    "VERDICT_MUKHFI",
    "VERDICT_MUNAFIQ",
    "VERDICT_MUGHLAQ",
    # Phase 21 — configurable safety limits.
    "ScanLimits",
    "DEFAULT_LIMITS",
    "get_current_limits",
    "set_current_limits",
    "limits_context",
    # v1.1.4 — content index + cost-class taxonomy
    "ContentIndex",
    "SpanInfo",
    "FontInfo",
    "AnnotInfo",
    "PikepdfAnnotInfo",
    "DrawingInfo",
    "get_current_content_index",
    "set_current_content_index",
    "content_index_context",
    "CostClass",
    "MECHANISM_COST_CLASS",
    "cost_class",
]
