"""
Domain value objects — pure functions over Finding / IntegrityReport.

These are the two evaluative operations Bayyinah performs on the
evidence it has collected:

    compute_muwazana_score(findings) -> float
        *Muwazana* = weighing. The APS-continuous integrity score.
        1.0 minus the sum of (severity * confidence) across all
        findings, clamped to [0.0, 1.0]. Byte-identical semantics to
        ``bayyinah_v0.compute_integrity_score``.

    tamyiz_verdict(report) -> Verdict
        *Tamyiz* = discrimination / differentiation. A categorical
        label derived from the score, the findings, and the scan-
        completion status. The verdict is a *summary* of the evidence,
        not a moral judgement of the document's author.

Both functions are pure: no I/O, no mutation of their inputs, no global
state read. That is the whole point of calling them "value objects" —
they carry meaning by their return value alone, and they always return
the same thing for the same input.
"""

from __future__ import annotations

from typing import Iterable

from domain.config import (
    SCAN_INCOMPLETE_CLAMP,
    VERDICT_MUGHLAQ,
    VERDICT_MUKHFI,
    VERDICT_MUNAFIQ,
    VERDICT_MUSHTABIH,
    VERDICT_SAHIH,
    Verdict,
)
from domain.finding import Finding
from domain.integrity_report import IntegrityReport


# ---------------------------------------------------------------------------
# Muwazana — the weighing
# ---------------------------------------------------------------------------

def compute_muwazana_score(findings: Iterable[Finding]) -> float:
    """APS-continuous integrity score.

    Semantics identical to ``bayyinah_v0.compute_integrity_score``:

        score = clamp(1.0 - Σ(severity × confidence), 0.0, 1.0)

    Each finding contributes a continuous deduction proportional to
    how much concealment mass it represents (severity) scaled by the
    detector's confidence it fired correctly. The clamp is there
    because a pile of adversarial content can drive the sum above
    1.0 — the score saturates at 0, it does not go negative.

    This function is deliberately separate from the scan-incomplete
    clamp (``SCAN_INCOMPLETE_CLAMP``). Muwazana weighs the findings it
    has; whether those findings are a complete picture is a *tamyiz*
    question and is handled by ``tamyiz_verdict`` and by the scanner's
    post-processing step. A caller that wants the final clamped score
    for an incomplete scan applies the clamp themselves, as the scanner
    does today.

    Pure. Idempotent. No side effects.
    """
    score = 1.0
    for f in findings:
        score -= f.severity * f.confidence
    if score < 0.0:
        return 0.0
    if score > 1.0:
        return 1.0
    return score


# ---------------------------------------------------------------------------
# Tamyiz — the discrimination
# ---------------------------------------------------------------------------

def tamyiz_verdict(report: IntegrityReport) -> Verdict:
    """Categorical verdict derived from an IntegrityReport.

    Decision table (checked top-down - first match wins):

        0. any Tier 0 (routing) finding present
               -> VERDICT_MUGHLAQ (routing in dispute, scan_incomplete
                  semantically though the bytes were read)
        1. scan_incomplete OR error present
               -> VERDICT_MUGHLAQ (closed / withheld)
        2. score == 1.0 AND no findings
               -> VERDICT_SAHIH (sound)
        3. score < 0.3 AND at least one tier-1 finding
               -> VERDICT_MUNAFIQ (severe, verified concealment)
        4. score < 0.7
               -> VERDICT_MUKHFI (concealment detected)
        5. otherwise (0.7 <= score < 1.0, or score == 1.0 with findings
           but all low-severity)
               -> VERDICT_MUSHTABIH (suspicious)

    v1.1.2 - rule 0 (Tier 0 routing floor) is checked first because
    routing transparency is a precondition for every claim downstream.
    A polyglot file that contains genuinely concealed content reports
    BOTH the Tier 0 routing-divergence finding AND any Tier 1/2/3
    concealment findings; the downstream findings are recorded but the
    verdict cannot rise above mughlaq while the routing question is
    open. See docs/adversarial/mughlaq_trap_REPORT.md.

    The classic mughlaq branch (rule 1) is checked next because an
    incomplete scan invalidates every other inference: a document we
    did not fully look at cannot be certified sound, no matter what
    the partial score says.

    The munafiq branch requires BOTH a low score AND a tier-1 finding.
    Tier-1 findings are "verified - unambiguous concealment"; tier-2
    and tier-3 findings are structural or interpretive and can
    accumulate to a low score without meeting the unambiguous-
    concealment bar. This keeps the strongest label from being issued
    on purely circumstantial evidence.

    Pure. Reads from the report; does not mutate it.
    """
    # 0. Tier 0 routing finding: the routing decision itself is in
    # dispute. Verdict floors at mughlaq regardless of any Tier 1/2/3
    # finding's content. This is the v1.1.2 closure of the Mughlaq
    # Trap stress test (2026-04-27): the scanner cannot honestly
    # render a verdict above mughlaq while it cannot honestly state
    # which file kind it just analyzed.
    if any(f.tier == 0 for f in report.findings):
        return VERDICT_MUGHLAQ

    # 1. Incomplete / errored scans are inconclusive. Verdict withheld.
    if report.scan_incomplete or report.error is not None:
        return VERDICT_MUGHLAQ

    score = report.integrity_score
    findings = report.findings

    # 2. Sound: perfect score AND no evidence.
    if score >= 1.0 and not findings:
        return VERDICT_SAHIH

    # 3. Severe concealment: low score AND verified evidence.
    has_tier1 = any(f.tier == 1 for f in findings)
    if score < 0.3 and has_tier1:
        return VERDICT_MUNAFIQ

    # 4. Concealment present but less decisive.
    if score < 0.7:
        return VERDICT_MUKHFI

    # 5. Otherwise: suspicious — some signal, but nothing conclusive.
    return VERDICT_MUSHTABIH


# ---------------------------------------------------------------------------
# Convenience helper — the scan-incomplete clamp
# ---------------------------------------------------------------------------

def apply_scan_incomplete_clamp(score: float, *, scan_incomplete: bool) -> float:
    """Pure function implementing the scan_incomplete score clamp.

    Mirrors the inline logic in ``bayyinah_v0_1.scan_pdf``:

        if scan did not complete cleanly and score > SCAN_INCOMPLETE_CLAMP:
            score = SCAN_INCOMPLETE_CLAMP

    Exists so analyzers and the scan service can apply the clamp
    through one named, documented function instead of re-inlining the
    magic threshold. Additive-only: nothing calls this yet in Phase 1.
    """
    if scan_incomplete and score > SCAN_INCOMPLETE_CLAMP:
        return SCAN_INCOMPLETE_CLAMP
    return score


__all__ = [
    "compute_muwazana_score",
    "tamyiz_verdict",
    "apply_scan_incomplete_clamp",
]
