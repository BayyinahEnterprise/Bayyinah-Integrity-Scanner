"""
Finding — the atomic unit of Bayyinah's evidence surface.

A Finding records one observed concealment mechanism: what was hidden,
where it was hidden, how confident Bayyinah is that the hiding is real,
and the inversion-recovery pair (what the surface showed vs. what the
document actually carried).

This is the Phase 1 domain port of the Finding dataclass that lives in
``bayyinah_v0.py`` and ``bayyinah_v0_1.py``. The port is additive-only:
the public ``to_dict`` output is byte-identical to v0.1.

The one new field — ``source_layer: Literal['zahir', 'batin']`` — carries
the methodological distinction from Al-Baqarah 2:8-10 and Munafiq Protocol
§9: whether a concealment mechanism manifests in the surface a human
reader perceives (zahir) or in the document's inner object graph that
only a parser sees (batin). ``source_layer`` is deliberately excluded
from ``to_dict`` so the serialised report remains byte-identical to
v0.1; it is available to analyzers and to value-object functions that
need to reason about *where* a mechanism lives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from domain.config import (
    BATIN_MECHANISMS,
    DEFAULT_SEVERITY,
    ROUTING_MECHANISMS,
    SEVERITY,
    ZAHIR_MECHANISMS,
    SourceLayer,
)
from domain.exceptions import InvalidFindingError

# v1.1.2 - Tier 0 routing findings carry a five-key disclosure schema
# in their `evidence` field. The schema is the contract a reviewer
# inspects to verify what the scanner decided about routing. Every key
# is required; missing keys are a structural defect, not a benign
# omission. See docs/scope/v1_1_2_framework_report.md section 3.0.
ROUTING_DISCLOSURE_KEYS: frozenset[str] = frozenset({
    "claimed_format",
    "inferred_format",
    "routing_decision",
    "bytes_sampled",
    "analyzer_invoked",
})


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _infer_source_layer(mechanism: str) -> SourceLayer:
    """Derive source_layer from the mechanism name.

    Zahir mechanisms manifest in the text/rendering surface; batin
    mechanisms live in the inner object graph. v1.1.2 routing
    mechanisms (the Tier 0 layer) classify as 'zahir' because the
    routing decision is observable from the file's surface (filename
    plus first bytes); they sit before any analyzer in the call graph
    and do not inspect the document's inner object graph. For unknown
    mechanism names we default to 'batin' - concealment we don't yet
    have a name for is structurally suspicious by nature, and the
    report consumer should see that classification, not silently lose
    it.
    """
    if mechanism in ZAHIR_MECHANISMS:
        return "zahir"
    if mechanism in BATIN_MECHANISMS:
        return "batin"
    if mechanism in ROUTING_MECHANISMS:
        return "zahir"
    return "batin"


# ---------------------------------------------------------------------------
# Finding
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single observed concealment mechanism with inversion recovery.

    Shape parity with ``bayyinah_v0.Finding`` / ``bayyinah_v0_1.Finding``:
    every field those dataclasses carry is present here with the same
    name, default, and serialisation behaviour. The only addition is
    ``source_layer``, which is excluded from ``to_dict``.

    Fields
    ------
    mechanism
        Short stable identifier for the concealment mechanism, e.g.
        'zero_width_chars', 'javascript', 'tounicode_anomaly'.
    tier
        Validity tier 1/2/3 — see ``TIER_LEGEND`` in ``domain.config``.
    confidence
        [0.0, 1.0] — how confident the detector is the mechanism is real
        (not a false positive).
    description
        Human-readable explanation of what was observed.
    location
        Where in the document the mechanism was found (e.g. "page 2,
        span 4", "catalog /OpenAction"). Free-form string.
    surface
        What the reader would see at that location (the zahir side of
        the inversion-recovery pair).
    concealed
        What the document actually carries there (the batin side).
    severity_override
        Optional per-finding severity, bypassing the ``SEVERITY`` table.
        Used when the detector has context-specific reason to weight a
        finding differently (e.g. a scan_error finding contributes zero).
    source_layer
        'zahir' or 'batin' — which concealment locus the mechanism lives
        in. Internal-only; excluded from ``to_dict``. Defaults are inferred
        from the mechanism name via ``_infer_source_layer``.
    """

    mechanism: str
    tier: int
    confidence: float
    description: str
    location: str
    surface: str = ""
    concealed: str = ""
    severity_override: float | None = None
    # source_layer defaults to a sentinel so __post_init__ can detect
    # "caller did not supply one" vs. "caller explicitly passed 'zahir'".
    # When the sentinel is seen we infer from the mechanism name.
    source_layer: SourceLayer = field(default="")  # type: ignore[assignment]
    # v1.1.2 - structured disclosure dict for Tier 0 routing findings.
    # Optional and excluded from to_dict() when None to preserve byte-
    # parity with v0/v0.1 for every existing analyzer that does not set
    # it. Tier 0 findings MUST set evidence, and the dict MUST contain
    # every key in ROUTING_DISCLOSURE_KEYS (validated in __post_init__).
    evidence: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        # ------ mechanism ------
        if not isinstance(self.mechanism, str) or not self.mechanism:
            raise InvalidFindingError(
                f"Finding.mechanism must be a non-empty string, got {self.mechanism!r}"
            )

        # ------ tier ------
        # v1.1.2 widens the validator to admit Tier 0 (routing
        # transparency) alongside the existing 1/2/3 concealment tiers.
        # See domain.config.TIER_LEGEND.
        if self.tier not in (0, 1, 2, 3):
            raise InvalidFindingError(
                f"Finding.tier must be 0, 1, 2, or 3 - got {self.tier!r}"
            )

        # ------ confidence ------
        if not isinstance(self.confidence, (int, float)):
            raise InvalidFindingError(
                f"Finding.confidence must be numeric, got {type(self.confidence).__name__}"
            )
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise InvalidFindingError(
                f"Finding.confidence must lie in [0.0, 1.0] — got {self.confidence}"
            )

        # ------ severity_override ------
        if self.severity_override is not None:
            if not isinstance(self.severity_override, (int, float)):
                raise InvalidFindingError(
                    "Finding.severity_override must be numeric or None"
                )
            if not (0.0 <= float(self.severity_override) <= 1.0):
                raise InvalidFindingError(
                    f"Finding.severity_override must lie in [0.0, 1.0] — "
                    f"got {self.severity_override}"
                )

        # ------ source_layer ------
        if self.source_layer == "":  # sentinel -> infer
            self.source_layer = _infer_source_layer(self.mechanism)
        elif self.source_layer not in ("zahir", "batin"):
            raise InvalidFindingError(
                f"Finding.source_layer must be 'zahir' or 'batin' — "
                f"got {self.source_layer!r}"
            )

        # ------ evidence (Tier 0 disclosure schema, v1.1.2) ------
        # Tier 0 routing findings MUST carry a complete five-key
        # disclosure schema in `evidence`. Missing keys are a structural
        # defect (the user is owed exactly those five facts about the
        # routing decision); a benign Tier 0 finding without evidence
        # would itself be the Process 3 surface this layer was added to
        # close. See ROUTING_DISCLOSURE_KEYS at the top of this module.
        # Concealment-tier findings (1, 2, 3) do not require evidence;
        # if they do supply it, it must be a dict.
        if self.evidence is not None and not isinstance(self.evidence, dict):
            raise InvalidFindingError(
                f"Finding.evidence must be a dict or None - "
                f"got {type(self.evidence).__name__}"
            )
        if self.tier == 0:
            if self.evidence is None:
                raise InvalidFindingError(
                    "Finding.tier == 0 requires a complete disclosure-"
                    f"schema dict in evidence; got None. Required keys: "
                    f"{sorted(ROUTING_DISCLOSURE_KEYS)}"
                )
            missing = ROUTING_DISCLOSURE_KEYS - set(self.evidence.keys())
            if missing:
                raise InvalidFindingError(
                    f"Tier 0 finding missing required disclosure keys: "
                    f"{sorted(missing)}. Required: "
                    f"{sorted(ROUTING_DISCLOSURE_KEYS)}; "
                    f"supplied: {sorted(self.evidence.keys())}"
                )

    # ------------------------------------------------------------------
    # Derived / serialisation surface
    # ------------------------------------------------------------------

    @property
    def severity(self) -> float:
        """APS-weight contribution for this finding.

        Respects ``severity_override`` when supplied; otherwise reads
        from the ``SEVERITY`` table; otherwise falls back to
        ``DEFAULT_SEVERITY`` (mirrors v0.1 behaviour exactly).
        """
        if self.severity_override is not None:
            return float(self.severity_override)
        return SEVERITY.get(self.mechanism, DEFAULT_SEVERITY)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to the Phase 0 report shape - byte-identical to v0.1
        for every existing zahir/batin mechanism.

        ``source_layer`` is deliberately NOT emitted. Exposing it would
        break the v0/v0.1 parity invariant asserted by
        ``tests/test_fixtures.py::test_v0_v01_parity``. It is available
        to in-process callers via attribute access only.

        v1.1.2 - ``evidence`` is emitted only when present (Tier 0
        routing findings carry it; existing zahir/batin mechanisms do
        not). The conditional include preserves the v0/v0.1 byte-parity
        invariant - PDF analyzers never set evidence, so their dict
        shape is unchanged. Tier 0 is new and has no parity contract.
        """
        out: dict[str, Any] = {
            "mechanism": self.mechanism,
            "tier": self.tier,
            "confidence": round(self.confidence, 3),
            "severity": self.severity,
            "description": self.description,
            "location": self.location,
            "inversion_recovery": {
                "surface": self.surface,
                "concealed": self.concealed,
            },
        }
        if self.evidence is not None:
            out["evidence"] = dict(self.evidence)
        return out


__all__ = ["Finding", "ROUTING_DISCLOSURE_KEYS"]
