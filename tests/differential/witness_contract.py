"""
DifferentialWitness contract (v1.8.0).

Defines the abstract base class every external-witness implementation
must satisfy, plus the WitnessFinding and WitnessDivergence
dataclasses used by differential pair tests.

Per docs/differential_testing.md §2: the contract is intentionally
minimal so that witnesses with very different internal designs
(structural inspectors like pdfid, rule-based matchers like yara,
signature-based scanners like clamav) can all conform.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class WitnessFinding:
    """One observation by an external witness.

    Fields:
        witness_name: stable identifier of the witness tool
                      (e.g. "pdfid").
        finding_key: the witness's mechanism / rule / signature name.
                     Witnesses use their own vocabulary; mapping to
                     Bayyinah's mechanism names is the pair test's
                     responsibility, not the witness's.
        location: optional structural reference (page / object id /
                  byte offset). Empty string when not applicable.
    """

    witness_name: str
    finding_key: str
    location: str


@dataclass(frozen=True)
class WitnessDivergence:
    """A divergence between Bayyinah and an external witness on one
    fixture.

    Fields:
        fixture: file path of the fixture under inspection.
        kind: one of "solo_bayyinah", "solo_witness", "distinct_locus"
              per docs/differential_testing.md §2.2.
        bayyinah_finding_key: Bayyinah mechanism name when applicable;
                              empty string for solo_witness.
        witness_finding_key: external witness mechanism when
                             applicable; empty string for solo_bayyinah.
        location: structural reference when known; empty string
                  otherwise.
    """

    fixture: str
    kind: str
    bayyinah_finding_key: str
    witness_finding_key: str
    location: str

    _VALID_KINDS = ("solo_bayyinah", "solo_witness", "distinct_locus")

    def __post_init__(self) -> None:
        if self.kind not in self._VALID_KINDS:
            raise ValueError(
                f"WitnessDivergence kind must be one of "
                f"{self._VALID_KINDS}; got {self.kind!r}"
            )


class DifferentialWitness(ABC):
    """Abstract base for an external-witness implementation.

    A subclass MUST implement ``witness_name`` and ``observe``. A
    subclass MAY override ``is_available`` if availability depends on
    more than just module-import success (e.g. system-daemon
    reachability for clamd).
    """

    @property
    @abstractmethod
    def witness_name(self) -> str:
        """The stable identifier of this witness tool."""
        raise NotImplementedError

    @abstractmethod
    def observe(self, path: Path) -> List[WitnessFinding]:
        """Run the witness against ``path`` and return its findings.

        Implementations MUST return a list (possibly empty). Raising
        an exception is an error in the witness, not a divergence.
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        """Return True iff the witness can run in the current env.

        Default: True. Override to add module-import or daemon-
        reachability checks.
        """
        return True

    @property
    def install_hint(self) -> str:
        """Human-readable install instruction for when is_available
        returns False. Override in subclasses with the tool-specific
        hint."""
        return "(no install hint provided by witness subclass)"


__all__ = [
    "DifferentialWitness",
    "WitnessFinding",
    "WitnessDivergence",
]
