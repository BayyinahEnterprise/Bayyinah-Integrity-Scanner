"""
IntegrityReport — the report object Bayyinah returns for a single scan.

Phase 1 domain port of the dataclass in ``bayyinah_v0.py`` /
``bayyinah_v0_1.py``. Additive-only: ``to_dict`` produces output
byte-identical to v0.1, preserving the parity invariant asserted by
``tests/test_fixtures.py::test_v0_v01_parity``.

Semantic grounding:
    The IntegrityReport is Bayyinah's equivalent of a court record. It
    does not render a moral verdict; it records (a) the observed
    mechanisms of concealment, (b) the continuous integrity score those
    mechanisms produce under the APS weighting, (c) whether the scan
    itself completed cleanly, and (d) a standing disclaimer that the
    reader — not Bayyinah — performs the recognition.

    Al-Baqarah 2:8-10's munafiqun are identified structurally — by the
    gap between what they say and what they carry in their hearts —
    not by assertion. Likewise a Bayyinah report surfaces the gap
    between what a document displays and what it contains, and leaves
    the judgement to the consumer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.config import (
    TIER_LEGEND,
    TOOL_NAME,
    TOOL_VERSION,
    VERDICT_DISCLAIMER,
)
from domain.finding import Finding


@dataclass
class IntegrityReport:
    """The product of a single ``scan_pdf`` call.

    Shape parity with ``bayyinah_v0.IntegrityReport`` /
    ``bayyinah_v0_1.IntegrityReport``: every field those dataclasses
    carry is present here with the same name, default, and serialisation
    behaviour.

    Fields
    ------
    file_path
        Absolute or relative path of the scanned document, stringified.
    integrity_score
        APS-style continuous score in [0.0, 1.0]. 1.0 = no concealment
        observed. Lower = more concealment signal. Scan-incomplete reports
        are clamped at ``SCAN_INCOMPLETE_CLAMP`` (see ``domain.config``).
    findings
        List of ``Finding`` objects emitted by the analyzer pipeline,
        in emission order. Empty list = clean report.
    error
        Free-form error message if the scan failed to complete. ``None``
        on a clean scan.
    scan_incomplete
        ``True`` when the scan did not fully cover the document (error
        raised, or a ``scan_error`` finding was emitted). Consumers MUST
        treat an incomplete scan as inconclusive — absence of findings
        in the uninspected region is not evidence of cleanness.
    """

    file_path: str
    integrity_score: float = 1.0
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    scan_incomplete: bool = False

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the Phase 0 report shape — byte-identical to v0.1.

        Emits exactly the keys v0.1 emits, in the insertion order v0.1
        uses. Nothing from the domain-layer-only ``source_layer`` field
        of individual findings leaks into this output.
        """
        return {
            "tool": TOOL_NAME,
            "version": TOOL_VERSION,
            "file_path": self.file_path,
            "integrity_score": round(self.integrity_score, 3),
            "scan_incomplete": self.scan_incomplete,
            "verdict_disclaimer": VERDICT_DISCLAIMER,
            "tier_legend": TIER_LEGEND,
            "findings": [f.to_dict() for f in self.findings],
            "error": self.error,
        }

    # ------------------------------------------------------------------
    # Convenience accessors (domain-only; not reflected in to_dict)
    # ------------------------------------------------------------------

    @property
    def zahir_findings(self) -> list[Finding]:
        """Findings whose concealment lives in the rendered/text surface."""
        return [f for f in self.findings if f.source_layer == "zahir"]

    @property
    def batin_findings(self) -> list[Finding]:
        """Findings whose concealment lives in the inner object graph."""
        return [f for f in self.findings if f.source_layer == "batin"]


__all__ = ["IntegrityReport"]
