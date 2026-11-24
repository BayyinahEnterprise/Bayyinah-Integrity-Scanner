"""Total outcomes and disclosures.

Two rules from the program's own papers shape this module.

*Caller-side exhaustiveness* (AX-SH axiom 3, furqan-lint D11): a step
that may fail to produce a result has to say so, and its caller has to
carry every case forward. The instruction assessment therefore returns
one of five named statuses and never "nothing".

*Routing transparency* (the Mughlaq Trap): a correct result built on an
undisclosed inference is a performance of rigor. Every place the
scanner decides not to report something is recorded as a disclosure:
zero-width characters it treated as orthography, invisible runs it
could not decode, hidden text it could not assess.

Disclosures are not findings. They do not change the score and they do
not make a file "flagged"; they say what the scan did.
"""

from __future__ import annotations

import contextvars
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AssessmentStatus(str, Enum):
    NOTHING_HIDDEN = "nothing_hidden"       # no concealed text was recovered
    INSTRUCTION_LIKE = "instruction_like"   # hidden text matches an instruction shape
    NO_MATCH = "no_match"                   # assessed; no shape matched
    NOT_ASSESSED = "not_assessed"           # hidden text present, outside coverage
    FAILED = "failed"                       # the assessment raised


@dataclass(frozen=True)
class InstructionAssessment:
    status: AssessmentStatus
    reason: str
    hidden_chars: int = 0
    scripts_assessed: tuple[str, ...] = ()
    scripts_unassessed: tuple[str, ...] = ()
    families: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    score: int = 0
    experimental_only: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reason": self.reason,
            "hidden_chars": self.hidden_chars,
            "scripts_assessed": list(self.scripts_assessed),
            "scripts_unassessed": list(self.scripts_unassessed),
            "families": list(self.families),
            "evidence": list(self.evidence),
            "experimental_only": self.experimental_only,
        }


@dataclass
class ScanNotes:
    """What the analyzers chose not to report during one scan."""

    exempt_zero_width: int = 0
    exempt_rules: dict[str, int] = field(default_factory=dict)
    undecodable_runs: int = 0
    undecodable_chars: int = 0
    _seen: set = field(default_factory=set, repr=False)
    extra: list = field(default_factory=list)

    def disclosures(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if self.exempt_zero_width:
            rules = ", ".join(f"{k}: {v}" for k, v in sorted(self.exempt_rules.items()))
            out.append({
                "kind": "orthographic_zero_width_not_reported",
                "count": self.exempt_zero_width,
                "detail": (
                    f"{self.exempt_zero_width} zero-width character(s) were "
                    f"treated as required by the writing system ({rules}) and "
                    "not reported. This is a judgment about orthography, not "
                    "a statement that they carry nothing."
                ),
            })
        if self.undecodable_runs:
            out.append({
                "kind": "invisible_run_not_decoded",
                "count": self.undecodable_runs,
                "detail": (
                    f"{self.undecodable_runs} run(s) of invisible characters "
                    f"({self.undecodable_chars} character(s)) did not decode "
                    "under any encoding the scanner knows. Their content is "
                    "unknown, not empty."
                ),
            })
        out.extend(self.extra)
        return out


_NOTES: contextvars.ContextVar[ScanNotes | None] = contextvars.ContextVar(
    "bayyinah_scan_notes", default=None)


@contextmanager
def collect_notes() -> Iterator[ScanNotes]:
    """Collect notes for the duration of one scan (per thread / task)."""
    notes = ScanNotes()
    token = _NOTES.set(notes)
    try:
        yield notes
    finally:
        _NOTES.reset(token)


def current_notes() -> ScanNotes | None:
    return _NOTES.get()


def note_exempt_zero_width(rule: str, count: int, key: object = None) -> None:
    """Record ``count`` exempted characters. ``key`` identifies the text
    so a string examined by two detectors is counted once."""
    notes = _NOTES.get()
    if notes is not None and count:
        if key is not None:
            if (rule, key) in notes._seen:
                return
            notes._seen.add((rule, key))
        notes.exempt_zero_width += count
        notes.exempt_rules[rule] = notes.exempt_rules.get(rule, 0) + count


def note_disclosure(kind: str, count: int, detail: str) -> None:
    """Record any other thing the scan did not do or did not report."""
    notes = _NOTES.get()
    if notes is not None:
        notes.extra.append({"kind": kind, "count": count, "detail": detail})


def note_undecodable_run(chars: int, key: object = None) -> None:
    notes = _NOTES.get()
    if notes is not None:
        if key is not None:
            if ("undecodable", key) in notes._seen:
                return
            notes._seen.add(("undecodable", key))
        notes.undecodable_runs += 1
        notes.undecodable_chars += chars


__all__ = [
    "AssessmentStatus", "InstructionAssessment", "ScanNotes",
    "collect_notes", "current_notes", "note_disclosure", "note_exempt_zero_width", "note_undecodable_run",
]
