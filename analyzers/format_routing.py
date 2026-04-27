"""
Tier 0 - format-routing transparency layer (v1.1.2).

Bayyinah's per-format analyzers all assume one structural fact: the
file the analyzer was handed actually is the kind of file the analyzer
expects. The 42-fixture per-format gauntlet probes whether each
analyzer catches concealment within its own format. It does NOT probe
whether the routing decision that put the file in front of that
analyzer was honest.

The 2026-04-27 Mughlaq Trap stress test showed that v1.1.1 silently
trusts magic bytes over the user's declared extension. A real
adversarial PDF renamed to ``.docx`` was routed to the PDF analyzer
without any disclosure; the user received a Tier-1 ``mukhfi`` verdict
on a file they had labelled as Word. The verdict was structurally
correct for the bytes the scanner saw - and structurally dishonest
about the file the user uploaded.

This module is the Tier 0 layer that fixes that gap. It runs before
any per-format analyzer, inspects the routing decision the
``FileRouter`` already made, and emits a single ``Finding`` whenever
that decision was itself in dispute. The finding floors the verdict
at ``mughlaq`` via the rule added to ``domain.value_objects.tamyiz_verdict``;
downstream Tier-1/2/3 findings are still recorded but cannot raise
the verdict above ``mughlaq`` while the routing question is open.

Trigger conditions (any one fires the Tier 0 finding):

  T0a - extension-implied format diverges from magic-byte-implied
        format. Reuses ``FileTypeDetection.extension_mismatch`` from
        the existing router. Catches V1 polyglot, V2 spoofed.
  T0b - extension-implied format is recognised but the magic bytes
        are absent / ambiguous / unrecognised, AND no analyzer is
        registered for the bytes. Catches V3 empty PDF, generic
        unknown-magic UNKNOWN routes.
  T0c - file size is below the content-depth floor required for any
        verified analyzer to produce a meaningful verdict. Catches
        V5 unanalyzed-text (a 4-byte ``.txt`` is structurally
        insufficient to warrant a sahih verdict), and the truncated.pdf
        fixture (PDF header without %%EOF, below the smallest PDF
        body).
  T0d - ZIP container internal-path divergence. The OOXML family
        (DOCX/XLSX/PPTX) shares ``PK\\x03\\x04`` magic; the router
        disambiguates on extension. A ``.xlsx`` whose ZIP head
        declares ``word/document.xml`` (a DOCX marker) is routed to
        the XLSX analyzer dishonestly. Catches V5_05 docx_as_xlsx.

The disclosure schema (every Tier 0 finding's ``evidence`` field)
carries five required keys:

  claimed_format    - the extension the user uploaded with
  inferred_format   - the format the magic-byte sniff identified
  routing_decision  - which path the scanner took
                      ("trusted_magic_bytes" / "trusted_extension"
                       / "below_content_depth_floor"
                       / "no_analyzer_in_registry"
                       / "ooxml_internal_path_divergence")
  bytes_sampled     - how many leading bytes were inspected
  analyzer_invoked  - the analyzer that ran, or None if no analyzer
                      could honestly be selected

The schema is enforced at ``Finding`` construction time
(``ROUTING_DISCLOSURE_KEYS`` in ``domain.finding``); a Tier 0 finding
that omits any key will fail to construct rather than silently emit
incomplete disclosure.

References:
  - docs/adversarial/mughlaq_trap_REPORT.md  (the 2026-04-27 stress test)
  - docs/scope/v1_1_2_framework_report.md    (section 3.0)
  - docs/scope/v1_1_2_claude_prompt.md       (section 3.1)
  - docs/scope/ADR-001-v1_2_scope.md         (depth-before-scope rule)

  > "Wa la talbisu al-haqqa bil-batil wa taktumu al-haqqa wa antum
  > ta'lamun." (Al-Baqarah 2:42)
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from domain.finding import Finding, ROUTING_DISCLOSURE_KEYS
from infrastructure.file_router import (
    FileKind,
    FileRouter,
    FileTypeDetection,
)


# ---------------------------------------------------------------------------
# Tunable thresholds
# ---------------------------------------------------------------------------

# Files smaller than this many bytes cannot honestly carry a verified
# concealment verdict regardless of extension. Below this floor any
# analyzer that returns a clean result is overconfident: it has not
# inspected enough content to justify the claim. The choice of 16
# bytes is small enough to admit single-line CSV/JSON/EML and very
# short clean code files, large enough to exclude V3 (4 bytes), V5
# (4 bytes), and the truncated PDF header fixture.
_CONTENT_DEPTH_FLOOR: Final[int] = 16

# Bytes the FileRouter samples for magic-byte / content sniffing.
# Mirrors ``FileRouter.HEAD_BYTES``. Reproduced here as a constant so
# the disclosure schema's ``bytes_sampled`` value is honest about how
# much the router actually looked at.
_HEAD_BYTES_SAMPLED: Final[int] = FileRouter.HEAD_BYTES

# OOXML internal-path markers. Each declared OOXML family has exactly
# one canonical part name visible in the local file header table near
# the head of the archive. A ``.xlsx`` whose head shows
# ``word/document.xml`` is structurally a renamed DOCX; a ``.docx``
# whose head shows ``ppt/presentation.xml`` is structurally a renamed
# PPTX; etc. The router today trusts the extension; this layer
# disagrees and discloses the disagreement.
_OOXML_MARKERS: Final[dict[FileKind, bytes]] = {
    FileKind.DOCX: b"word/document.xml",
    FileKind.XLSX: b"xl/workbook.xml",
    FileKind.PPTX: b"ppt/presentation.xml",
}


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

def detect_format_routing_divergence(
    path: Path,
    detection: FileTypeDetection,
    file_size: int,
    head: bytes | None = None,
) -> Finding | None:
    """Return a Tier 0 ``format_routing_divergence`` finding if any of the
    four trigger conditions fires; otherwise return ``None``.

    Pure. No I/O when ``head`` is supplied; reads the file head once
    when ``head`` is ``None`` AND OOXML internal-path inspection is
    needed. The caller (``ScanService``) supplies ``head`` so the
    detector and the router share a single bounded read.

    Parameters
    ----------
    path
        The user-uploaded path (the filename / extension is what the
        user "claimed"; the bytes are what the scanner inferred).
    detection
        The result of ``FileRouter.detect(path)``. Carries
        ``extension_mismatch`` directly; this detector reuses that
        flag for trigger T0a rather than re-inferring it.
    file_size
        The byte length of the file. Used by trigger T0c to compare
        against the content-depth floor.
    head
        Optional pre-read first ``HEAD_BYTES`` of the file. When
        supplied, the OOXML internal-path inspection (trigger T0d)
        runs without a second open(); when ``None``, the inspection
        is skipped (T0d is best-effort under the no-extra-IO contract).

    Returns
    -------
    Finding | None
        Exactly zero or one Tier 0 finding. Multiple trigger conditions
        cannot fire on one file - the conditions are checked in order
        of specificity (extension mismatch first, content-depth floor
        next, unknown second-to-last, OOXML internal path last).
    """
    ext = path.suffix.lower().lstrip(".")
    bytes_sampled = min(_HEAD_BYTES_SAMPLED, file_size)

    # ------------------------------------------------------------------
    # T0a - extension says one thing, magic-byte detection says another.
    # ------------------------------------------------------------------
    if detection.extension_mismatch:
        return Finding(
            mechanism="format_routing_divergence",
            tier=0,
            confidence=1.0,
            description=(
                f"Extension '.{ext}' diverges from magic-byte detection "
                f"'{detection.kind.value}'. Analysis was routed by magic "
                f"bytes; verdict is floored at mughlaq because the "
                f"scanner cannot honestly resolve which file kind the "
                f"user intended to upload."
            ),
            location=path.name,
            surface=f"extension .{ext}",
            concealed=f"detected: {detection.kind.value}",
            evidence={
                "claimed_format": ext or "(none)",
                "inferred_format": detection.kind.value,
                "routing_decision": "trusted_magic_bytes",
                "bytes_sampled": bytes_sampled,
                "analyzer_invoked": detection.kind.value,
            },
        )

    # ------------------------------------------------------------------
    # T0c - file too small for any honest verdict. Checked before T0b
    # so a 4-byte file with .pdf extension does not slip through as
    # plain UNKNOWN; the content-depth claim is the more specific
    # disclosure.
    # ------------------------------------------------------------------
    if file_size < _CONTENT_DEPTH_FLOOR:
        return Finding(
            mechanism="format_routing_divergence",
            tier=0,
            confidence=1.0,
            description=(
                f"File is {file_size} bytes - below the {_CONTENT_DEPTH_FLOOR}-"
                f"byte content-depth floor required for any verified "
                f"analyzer to produce a meaningful verdict. Verdict is "
                f"floored at mughlaq because absence of findings here "
                f"is not evidence of soundness."
            ),
            location=path.name,
            surface=f"file size {file_size} bytes",
            concealed="content insufficient for verification",
            evidence={
                "claimed_format": ext or "(none)",
                "inferred_format": detection.kind.value,
                "routing_decision": "below_content_depth_floor",
                "bytes_sampled": bytes_sampled,
                "analyzer_invoked": None,
            },
        )

    # ------------------------------------------------------------------
    # T0b - magic bytes unrecognised AND no analyzer for the extension.
    # ``FileKind.UNKNOWN`` is the router's honest "I do not know what
    # this is" return; every supported format has a non-UNKNOWN kind.
    # When the router says UNKNOWN we know there is no analyzer to
    # invoke and the verdict cannot honestly be sahih.
    # ------------------------------------------------------------------
    if detection.kind is FileKind.UNKNOWN:
        return Finding(
            mechanism="format_routing_divergence",
            tier=0,
            confidence=1.0,
            description=(
                f"File extension '.{ext or '(none)'}' has no recognised "
                f"magic-byte signature and no verified analyzer applies. "
                f"Verdict is floored at mughlaq because no analyzer ran."
            ),
            location=path.name,
            surface=f"extension .{ext or '(none)'}",
            concealed="no recognised format signature",
            evidence={
                "claimed_format": ext or "(none)",
                "inferred_format": "unknown",
                "routing_decision": "no_analyzer_in_registry",
                "bytes_sampled": bytes_sampled,
                "analyzer_invoked": None,
            },
        )

    # ------------------------------------------------------------------
    # T0d - OOXML internal-path divergence.
    # Both DOCX and XLSX and PPTX share the ZIP magic ``PK\x03\x04``.
    # The router disambiguates by extension first; when the extension
    # is one of the OOXML kinds, the router trusts it. A reviewer who
    # opens the ZIP and finds the wrong canonical part name is owed
    # the disclosure that the routing decision did not match the
    # internal structure.
    # ------------------------------------------------------------------
    if head is not None and detection.kind in _OOXML_MARKERS:
        if head.startswith(b"PK\x03\x04"):
            expected_marker = _OOXML_MARKERS[detection.kind]
            for other_kind, other_marker in _OOXML_MARKERS.items():
                if other_kind is detection.kind:
                    continue
                if other_marker in head and expected_marker not in head:
                    return Finding(
                        mechanism="format_routing_divergence",
                        tier=0,
                        confidence=1.0,
                        description=(
                            f"Routed as {detection.kind.value} on extension "
                            f"'.{ext}', but the ZIP head declares "
                            f"{other_kind.value!r}'s canonical part "
                            f"({other_marker.decode('ascii')!r}) and "
                            f"omits {detection.kind.value!r}'s "
                            f"({expected_marker.decode('ascii')!r}). "
                            f"OOXML family routing is in dispute; verdict "
                            f"floors at mughlaq."
                        ),
                        location=path.name,
                        surface=f"extension .{ext}",
                        concealed=(
                            f"ZIP internal path indicates "
                            f"{other_kind.value}"
                        ),
                        evidence={
                            "claimed_format": ext,
                            "inferred_format": other_kind.value,
                            "routing_decision": "ooxml_internal_path_divergence",
                            "bytes_sampled": bytes_sampled,
                            "analyzer_invoked": detection.kind.value,
                        },
                    )

    return None


__all__ = [
    "detect_format_routing_divergence",
    "ROUTING_DISCLOSURE_KEYS",
]
