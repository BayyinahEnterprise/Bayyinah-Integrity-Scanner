"""
CrossModalCorrelationEngine — the reading of stems together (Al-Baqarah 2:164).

    إِنَّ فِى خَلْقِ ٱلسَّمَـٰوَٰتِ وَٱلْأَرْضِ وَٱخْتِلَـٰفِ ٱلَّيْلِ وَٱلنَّهَارِ … لَءَايَـٰتٍۢ لِّقَوْمٍۢ يَعْقِلُونَ

    "Indeed, in the creation of the heavens and the earth, and the
    alternation of the night and the day... are signs for a people
    who use reason."

The architectural reading: no single stem reveals the full picture.
The verse names the design requirement explicitly — the signs appear
when the separated elements are read together by someone who uses
reason. Phases 23-24 performed the parting (Al-Baqarah 2:50):
VideoAnalyzer and AudioAnalyzer decomposed their containers into
stems and surfaced per-stem findings. Phase 25+ reads those stems
together.

Composition, not duplication
----------------------------

The engine consumes already-scanned :class:`IntegrityReport` s and
emits additional :class:`Finding` s for cross-stem divergence. It
does not reparse files. It does not reimplement detection logic.
Every decision it makes is anchored in findings the upstream
analyzers already produced — the engine's role is to reason
across them.

Rule set (session 1 — two active rules)
---------------------------------------

  * ``cross_stem_inventory``       — meta-finding, always emitted.
    Enumerates every stem the upstream analyzers extracted, every
    mechanism each stem produced, and notes the correlation rules
    applied. Severity zero — informational. The verse's "signs for
    a people who use reason" hinges on being able to *see* what
    was separated; the inventory makes the separation visible.

  * ``cross_stem_undeclared_text`` — subtitle (or audio-lyric) stem
    carries substantive text while the container's metadata stem
    is silent. Al-Baqarah 2:42 applied across stems: the metadata's
    outward declaration (no mention of caption/lyric/text) and the
    subtitle's inner content (actual concealed text) disagree. An
    AI ingestion pipeline reading only metadata would not expect
    textual content to be present, yet the subtitle extractor
    surfaces it.

Future-work rules (reserved names in ``domain/config.py`` comments —
detectors land in subsequent sessions):

  * ``cross_stem_text_inconsistency``
  * ``cross_stem_metadata_clash``
  * ``embedded_media_recursive_scan``
  * ``cross_stem_coordinated_concealment``
  * ``cross_file_media_divergence``

Opt-in invocation (session 1)
-----------------------------

The engine is intentionally *not* wired into ``ScanService`` in this
session — opting in keeps the existing per-fixture mechanism
expectations intact while the rule set is being calibrated. Callers
who want cross-modal analysis invoke the engine explicitly::

    from bayyinah import ScanService, CrossModalCorrelationEngine

    report = ScanService().scan(path)
    correlation_findings = CrossModalCorrelationEngine().correlate(report)
    report.findings.extend(correlation_findings)

A subsequent session may integrate the engine into ``ScanService``
once the rule set has stabilised.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from domain import (
    Finding,
    IntegrityReport,
)
from domain.config import SEVERITY, TIER


# ---------------------------------------------------------------------------
# Rule registration — each rule is a callable (report, stems) -> list[Finding]
# ---------------------------------------------------------------------------

# Keywords that, when present anywhere in a metadata-stem finding's
# surface/concealed/description, count as the container DECLARING that
# textual content exists. Case-insensitive match. Calibrated conservatively
# per Step 7 ("do not specify so many correlation rules that the engine
# fires on everything"): the list is deliberately small, not aspirational.
_METADATA_DECLARES_TEXT: tuple[str, ...] = (
    "caption",
    "subtitle",
    "subtitled",
    "lyric",
    "transcript",
    "dialog",
    "narration",
    "sdh",
    "cc ",   # CC with trailing space — avoids matching "cc" in Cyrillic / homoglyph text
)


@dataclass(frozen=True)
class _StemPartition:
    """Grouping of an IntegrityReport's findings by stem of origin.

    Stems are identified from each finding's ``mechanism`` name.
    The partition is strictly read-only and does not reparse files.
    """

    subtitle: list[Finding]
    lyric: list[Finding]
    metadata: list[Finding]
    embedded: list[Finding]
    container: list[Finding]
    sample: list[Finding]
    inventory: list[Finding]

    @property
    def has_subtitle_or_lyric_content(self) -> bool:
        """True if the report contains at least one substantive
        subtitle or audio-lyric concealment finding.

        Both mechanisms only fire when the upstream analyzer saw
        substantive text in the relevant stem, so their presence is
        positive evidence that text exists.
        """
        return bool(self.subtitle) or bool(self.lyric)

    @property
    def has_metadata_stem_activity(self) -> bool:
        """True if the report contains at least one metadata-stem
        finding (video or audio).
        """
        return bool(self.metadata)


def _partition_findings(report: IntegrityReport) -> _StemPartition:
    """Read-only partition of a report's findings by stem of origin.

    Classification is by mechanism name only — no file access, no
    heuristics beyond the mechanism-to-stem mapping.
    """
    subtitle: list[Finding] = []
    lyric: list[Finding] = []
    metadata: list[Finding] = []
    embedded: list[Finding] = []
    container: list[Finding] = []
    sample: list[Finding] = []
    inventory: list[Finding] = []
    for f in report.findings:
        m = f.mechanism
        if m.startswith("subtitle_"):
            subtitle.append(f)
        elif m in ("audio_lyrics_prompt_injection",):
            lyric.append(f)
        elif "metadata" in m or m in (
            "audio_metadata_identity_anomaly",
            "audio_metadata_injection",
            "audio_high_entropy_metadata",
            "video_metadata_suspicious",
        ):
            metadata.append(f)
        elif m in (
            "video_embedded_attachment",
            "video_frame_stego_candidate",
            "audio_embedded_payload",
        ):
            embedded.append(f)
        elif m in (
            "video_container_anomaly",
            "audio_container_anomaly",
        ):
            container.append(f)
        elif m in ("audio_lsb_stego_candidate",):
            sample.append(f)
        elif m in (
            "video_stream_inventory",
            "audio_stem_inventory",
        ):
            inventory.append(f)
        # Everything else (scan_error, cross-file correlation output,
        # findings from other analyzers) is outside this engine's scope.
    return _StemPartition(
        subtitle=subtitle, lyric=lyric, metadata=metadata,
        embedded=embedded, container=container, sample=sample,
        inventory=inventory,
    )


def _metadata_declares_text(metadata_findings: list[Finding]) -> bool:
    """Check whether any metadata-stem finding mentions a text
    declaration keyword. The heuristic is deliberately narrow — a
    metadata stem that emits a finding referring to "caption" or
    "lyric" is an analyst-declared hint that the container
    acknowledges textual content.
    """
    for f in metadata_findings:
        haystack = " ".join([
            f.description or "",
            f.location or "",
            f.surface or "",
            f.concealed or "",
        ]).lower()
        for keyword in _METADATA_DECLARES_TEXT:
            if keyword in haystack:
                return True
    return False


# ---------------------------------------------------------------------------
# CrossModalCorrelationEngine
# ---------------------------------------------------------------------------

# A rule takes (report, partition) and returns a list of findings
# (possibly empty). Keeping the signature uniform lets later sessions
# extend the rule set without touching the engine class.
_Rule = Callable[[IntegrityReport, _StemPartition], list[Finding]]


def _rule_undeclared_text(
    report: IntegrityReport,
    stems: _StemPartition,
) -> list[Finding]:
    """cross_stem_undeclared_text.

    Fires when a subtitle or audio-lyric stem carries substantive
    concealment findings AND the metadata stem is silent (or its
    findings do not declare that textual content exists).

    The shape: the container's outward declaration (metadata) and its
    inner text (subtitles / lyrics) disagree. An AI pipeline reading
    metadata alone would not expect text; the subtitle extractor will
    still surface the payload.
    """
    if not stems.has_subtitle_or_lyric_content:
        return []

    if stems.has_metadata_stem_activity and _metadata_declares_text(stems.metadata):
        # Metadata DOES declare caption/lyric/text — stems are
        # aligned; rule is silent.
        return []

    # Subtitle / lyric text present; metadata silent or non-declaring.
    text_mechanisms = sorted({
        f.mechanism for f in (stems.subtitle + stems.lyric)
    })
    return [Finding(
        mechanism="cross_stem_undeclared_text",
        tier=TIER["cross_stem_undeclared_text"],
        confidence=0.85,
        severity_override=SEVERITY["cross_stem_undeclared_text"],
        description=(
            "A subtitle / lyric stem carries substantive textual content "
            f"({', '.join(text_mechanisms)}) but the metadata stem is "
            "silent about the file containing text. An AI ingestion "
            "pipeline reading metadata alone would not expect textual "
            "content — cross-stem divergence between the outward "
            "declaration and the inner payload."
        ),
        location=str(report.file_path),
        surface=(
            f"metadata stem findings: "
            f"{len(stems.metadata)}; "
            f"subtitle/lyric findings: "
            f"{len(stems.subtitle) + len(stems.lyric)}"
        ),
        concealed=(
            f"text-bearing mechanisms emitted: {text_mechanisms}"
        ),
    )]


def _rule_inventory(
    report: IntegrityReport,
    stems: _StemPartition,
) -> list[Finding]:
    """cross_stem_inventory — always emitted.

    Informational meta-finding enumerating every stem the upstream
    analyzers surfaced findings on, plus the rules the engine
    considered. The inventory is the visible parting (Al-Baqarah 2:50)
    — without it the reader cannot know what was separated. Severity
    zero; this is a record, not a deduction.
    """
    stem_counts = {
        "subtitle": len(stems.subtitle),
        "lyric": len(stems.lyric),
        "metadata": len(stems.metadata),
        "embedded": len(stems.embedded),
        "container": len(stems.container),
        "sample": len(stems.sample),
        "inventory": len(stems.inventory),
    }
    non_empty = {k: v for k, v in stem_counts.items() if v > 0}
    if not non_empty:
        inventory_line = "(no stem-attributable findings in report)"
    else:
        inventory_line = ", ".join(
            f"{k}={v}" for k, v in sorted(non_empty.items())
        )
    return [Finding(
        mechanism="cross_stem_inventory",
        tier=TIER["cross_stem_inventory"],
        confidence=1.0,
        severity_override=0.0,
        description=(
            "Cross-modal correlation inventory: the engine "
            "enumerated the findings of each stem the upstream "
            "analyzers surfaced, before applying correlation rules."
        ),
        location=str(report.file_path),
        surface=f"stem partition: {inventory_line}",
        concealed=(
            "rules applied: cross_stem_undeclared_text"
        ),
    )]


class CrossModalCorrelationEngine:
    """Post-processor that reads stem-partitioned findings from an
    :class:`IntegrityReport` and emits additional findings for
    cross-stem divergence.

    Session-1 rule set (see module docstring for the full rationale):

      * ``cross_stem_inventory`` — always fires (non-deducting).
      * ``cross_stem_undeclared_text`` — fires when the subtitle or
        audio-lyric stem carries substantive text and the metadata
        stem is silent.

    The engine is stateless, idempotent, and does not mutate its
    input report. Running it twice on the same report produces
    identical output.

    Extensibility
    -------------

    Additional rules register in :attr:`_default_rules`. Each rule
    is a callable that takes the report and its stem partition and
    returns a (possibly empty) list of :class:`Finding`. The
    engine applies each rule in order and concatenates the results.
    """

    _default_rules: tuple[_Rule, ...] = (
        # Inventory last so the rules-applied list it reports is
        # written after any new rules are added above it.
        _rule_undeclared_text,
        _rule_inventory,
    )

    def __init__(self, rules: tuple[_Rule, ...] | None = None) -> None:
        """Create an engine with an optional custom rule tuple.

        Defaults to :attr:`_default_rules`. Tests override this to
        validate individual rules in isolation.
        """
        self._rules: tuple[_Rule, ...] = (
            rules if rules is not None else self._default_rules
        )

    def correlate(self, report: IntegrityReport) -> list[Finding]:
        """Return the engine's findings for ``report``.

        The input report is not mutated. The caller may extend
        ``report.findings`` with the returned list or keep them
        separate. The engine always returns at least the
        ``cross_stem_inventory`` meta-finding.
        """
        stems = _partition_findings(report)
        out: list[Finding] = []
        for rule in self._rules:
            out.extend(rule(report, stems))
        return out


__all__ = [
    "CrossModalCorrelationEngine",
]
