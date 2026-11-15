"""Last step of every scan: assess hidden text, disclose, split the score.

Kept out of ``ScanService.scan`` so both dispatch paths (PDF and
non-PDF) end the same way, and so the whole step is switched off in one
place when a scan must reproduce the v0.1 report exactly.
"""

from __future__ import annotations

from pathlib import Path

from analyzers.concealed_instruction import (
    assess_report, finding_from_assessment, legacy_parity_mode,
)
from domain import IntegrityReport, compute_muwazana_score
from domain.outcomes import AssessmentStatus, InstructionAssessment, ScanNotes


def score_axes(report: IntegrityReport) -> dict:
    """The scalar score, split.

    ``surface``    concealment in what is rendered or extracted as text
    ``structure``  concealment in the file's inner objects
    ``coverage``   1.0 when every analyzer covered its scope, else 0.0

    A consumer that triages on the single score cannot tell a default
    navigation action from hidden text; these axes keep them apart. The
    single score is unchanged.
    """
    return {
        "surface": round(compute_muwazana_score(report.zahir_findings), 3),
        "structure": round(compute_muwazana_score(report.batin_findings), 3),
        "coverage": 0.0 if report.scan_incomplete else 1.0,
    }


def finalize_report(
    report: IntegrityReport, file_path: Path, notes: ScanNotes | None,
    *, is_pdf: bool,
) -> IntegrityReport:
    if legacy_parity_mode():
        return report
    assessment = assess_report(report.findings, file_path, is_pdf=is_pdf)
    finding = finding_from_assessment(assessment, file_path)
    if finding is not None:
        report.findings.append(finding)
        report.integrity_score = compute_muwazana_score(report.findings)
    disclosures = notes.disclosures() if notes is not None else []
    undecoded = notes.undecodable_runs if notes is not None else 0
    if undecoded and assessment.status in (
            AssessmentStatus.NOTHING_HIDDEN, AssessmentStatus.NO_MATCH):
        assessment = InstructionAssessment(
            AssessmentStatus.NOT_ASSESSED,
            f"{undecoded} run(s) of invisible characters could not be "
            "decoded, so their content was not assessed.",
            hidden_chars=assessment.hidden_chars,
            scripts_assessed=assessment.scripts_assessed,
            scripts_unassessed=assessment.scripts_unassessed,
        )
    if assessment.status is not AssessmentStatus.NOTHING_HIDDEN:
        report.instruction_assessment = assessment.to_dict()
    report.disclosures = disclosures
    report.score_axes = score_axes(report)
    seals = [d for d in disclosures if d["kind"] == "fatima_signed_seal"]
    if seals:
        report.score_axes["seal"] = seals[0]["detail"].split(" Key ")[0]
    return report


__all__ = ["finalize_report", "score_axes"]
