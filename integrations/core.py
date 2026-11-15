"""Framework-free entry points for pipelines.

Two questions a pipeline asks before it hands content to a model:

``check_file(path)``  Is anything hidden in this file?
``check_text(text)``  Is anything hidden in this string?

Use ``check_file`` whenever the original file exists. Text extracted
from a PDF or an Office file has already lost the difference between
what a reader could see and what they could not: white text, off-page
text and hidden runs come out of the extractor looking like ordinary
sentences. ``check_text`` can only find what survives in the characters
themselves (invisible characters, direction controls, lookalike
letters, terminal escapes).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_MEMORY = Path("<text>")


@dataclass(frozen=True)
class Verdict:
    """Outcome of one check, in a shape that serialises cleanly."""

    flagged: bool
    instruction_like: bool
    integrity_score: float
    mechanisms: tuple[str, ...]
    findings: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    scan_incomplete: bool = False
    source: str = ""
    # "instruction_like", "no_match", "not_assessed", "failed", or None
    # when the scan recovered no hidden text. "no_match" and
    # "not_assessed" are not "safe"; see domain/outcomes.py.
    assessment_status: str | None = None
    assessment_reason: str = ""
    disclosures: tuple[dict[str, Any], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "flagged": self.flagged,
            "instruction_like": self.instruction_like,
            "integrity_score": self.integrity_score,
            "mechanisms": list(self.mechanisms),
            "findings": list(self.findings),
            "scan_incomplete": self.scan_incomplete,
            "source": self.source,
            "assessment_status": self.assessment_status,
            "assessment_reason": self.assessment_reason,
            "disclosures": list(self.disclosures),
        }


def _finding_dict(f) -> dict[str, Any]:
    return {
        "mechanism": f.mechanism,
        "tier": f.tier,
        "confidence": f.confidence,
        "description": f.description,
        "location": f.location,
    }


def _verdict(findings, score: float, incomplete: bool, source: str,
             assessment: dict | None = None, disclosures=()) -> Verdict:
    mechs = tuple(dict.fromkeys(f.mechanism for f in findings))
    return Verdict(
        assessment_status=(assessment or {}).get("status"),
        assessment_reason=(assessment or {}).get("reason", ""),
        disclosures=tuple(disclosures),
        flagged=bool(findings),
        instruction_like="concealed_instruction" in mechs,
        integrity_score=round(float(score), 4),
        mechanisms=mechs,
        findings=tuple(_finding_dict(f) for f in findings),
        scan_incomplete=incomplete,
        source=source,
    )


def check_file(path: str | Path) -> Verdict:
    """Scan a file of any supported format."""
    from bayyinah import scan_file

    report = scan_file(Path(path))
    return _verdict(report.findings, report.integrity_score,
                    bool(report.scan_incomplete), str(path),
                    report.instruction_assessment, report.disclosures)


def check_text(text: str, source: str = "<text>") -> Verdict:
    """Scan a string in memory. See the module note on what this can see."""
    from analyzers.text_file_analyzer import TextFileAnalyzer
    from application.finalize import finalize_report
    from domain import IntegrityReport, compute_muwazana_score
    from domain.outcomes import collect_notes

    with collect_notes() as notes:
        findings = list(TextFileAnalyzer()._scan_text(text, Path(source)))
        report = IntegrityReport(
            file_path=source, findings=findings,
            integrity_score=compute_muwazana_score(findings))
        finalize_report(report, Path(source), notes, is_pdf=False)
    return _verdict(report.findings, report.integrity_score, False, source,
                    report.instruction_assessment, report.disclosures)


__all__ = ["Verdict", "check_file", "check_text"]
