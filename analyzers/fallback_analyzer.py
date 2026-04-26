"""
FallbackAnalyzer — the universal witness for unknown file types
(Al-Baqarah 2:143).

    وَكَذَٰلِكَ جَعَلْنَاكُمْ أُمَّةً وَسَطًا لِّتَكُونُوا شُهَدَاءَ عَلَى النَّاسِ
    "And thus We have made you a middle community, that you might be
    witnesses over the people."

The architectural reading (Phase 21): every scanner needs a witness of
last resort. Without one, a file whose bytes no magic prefix recognised
and whose extension no map entry covered would either produce an
explicit "Unknown file type" scan_error (honest but unactionable) or,
worse, slip through the format-specific registry as silent-clean (the
failure mode the Munafiq Protocol exists to prevent: a file we could
not identify being reported as score 1.0 with zero findings). The
fallback analyzer is the middle-community witness that closes that
gap — for any file Bayyinah could not classify, it emits an
``unknown_format`` finding carrying the metadata a forensics reader
needs to begin their own classification:

    * magic_bytes_hex    — first 16 bytes of the file, hex-encoded.
                            The "magic prefix" a reader would consult
                            against the PRONOM / libmagic registry.
    * extension          — the declared extension (or ``"(none)"``).
    * size_bytes         — full file size in bytes.
    * head_preview_hex   — first 512 bytes hex-encoded. Enough for a
                            reader to spot a container header, a
                            proprietary-format signature, or text
                            shaped like a known format.
    * head_preview_ascii — first 512 bytes rendered as printable ASCII
                            (non-printables replaced with ``.``). Gives
                            the human reader a quick visual read of
                            whether the file is text-shaped or binary.

The finding is tier 3 (interpretive) and severity 0.0 (non-deducting,
parallel to ``scan_error``), but the analyzer marks the scan
incomplete — the 0.5 ``SCAN_INCOMPLETE_CLAMP`` then applies. "Absence
of findings in a file we could not identify is not evidence of
cleanness." Al-Baqarah 2:42, applied to format classification: do not
mix truth ("we scanned this file") with falsehood ("we scanned it and
it was clean") when the truth is "we did not recognise it at all".

Reference: Munafiq Protocol §9 — performed-alignment detection at the
input layer. DOI: 10.5281/zenodo.19677111
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

from analyzers.base import BaseAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
    get_current_limits,
)
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

# How many head bytes to include in the finding's preview. 512 is enough
# for a human reader to recognise most format signatures (ELF, Mach-O,
# proprietary binary headers, embedded compression containers, the first
# few lines of text-shaped payloads) without bloating the finding body
# past what a report renderer wants to show.
_HEAD_PREVIEW_BYTES: int = 512

# Magic-byte prefix length included in the finding. 16 bytes covers
# every format signature in common use today (the longest in the PRONOM
# registry today is 12 bytes), with room for a future format that
# extends the pattern.
_MAGIC_PREFIX_BYTES: int = 16


# ---------------------------------------------------------------------------
# FallbackAnalyzer
# ---------------------------------------------------------------------------


class FallbackAnalyzer(BaseAnalyzer):
    """Emit ``unknown_format`` for any file the router could not classify.

    Conforms to the standard ``BaseAnalyzer`` contract: returns its own
    ``IntegrityReport`` with ``scan_incomplete=True``, so the
    ``AnalyzerRegistry.scan_all`` merge propagates the flag and the
    final score is clamped to ``SCAN_INCOMPLETE_CLAMP`` (0.5).

    Declares ``supported_kinds = {FileKind.UNKNOWN}`` so it fires only
    on the UNKNOWN dispatch path. This is how the registry keeps it
    disjoint from every other analyzer — it never runs on a PDF, DOCX,
    or any other identified kind, so PDF parity and every earlier
    phase's parity are all preserved by construction.
    """

    name: ClassVar[str] = "fallback"
    error_prefix: ClassVar[str] = "Fallback scan error"
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.UNKNOWN})

    # ------------------------------------------------------------------
    # Scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:
        """Emit one ``unknown_format`` finding describing the file.

        Control flow:

            1. Short-circuit ``FileNotFoundError`` into a ``scan_error``
               via the base-class helper — matches every other
               analyzer's missing-file semantics.
            2. Respect the configured ``max_file_size_bytes`` limit:
               if the file is oversized, emit a ``scan_limited``
               finding instead of loading the head-preview bytes. This
               keeps the fallback analyzer itself from being a DoS
               vector on pathologically-large inputs.
            3. Read the first ``_HEAD_PREVIEW_BYTES`` bytes. Compute
               the magic-byte prefix, printable-ASCII preview, and
               file size.
            4. Emit one ``unknown_format`` finding carrying all four
               metadata fields in the ``description`` (so CLI / JSON
               renderers surface them without custom rendering).
            5. Return a report with ``scan_incomplete=True``.
        """
        path = Path(file_path)

        # Step 1 — missing file.
        if not path.exists():
            return self._scan_error_report(
                path,
                f"File not found: {path}",
            )

        # Step 2 — size ceiling.
        limits = get_current_limits()
        try:
            size_bytes = path.stat().st_size
        except OSError as exc:
            return self._scan_error_report(
                path,
                f"Could not stat file: {exc}",
            )

        if size_bytes > limits.max_file_size_bytes:
            return self._scan_limited_report(
                path,
                (
                    f"file size {size_bytes} bytes exceeds configured "
                    f"max_file_size_bytes={limits.max_file_size_bytes}; "
                    "head preview not sampled"
                ),
                size_bytes=size_bytes,
            )

        # Step 3 — read the head preview.
        try:
            with path.open("rb") as fh:
                head = fh.read(_HEAD_PREVIEW_BYTES)
        except OSError as exc:
            return self._scan_error_report(
                path,
                f"Could not read file: {exc}",
            )

        magic_prefix = head[:_MAGIC_PREFIX_BYTES]
        magic_bytes_hex = magic_prefix.hex()
        head_preview_hex = head.hex()
        head_preview_ascii = _printable_ascii_preview(head)
        extension = path.suffix or "(none)"

        # Step 4 — compose the finding.
        description = (
            "File could not be classified by magic bytes or extension; "
            "no format-specific analyzer ran. Forensic metadata: "
            f"extension={extension!r}, size_bytes={size_bytes}, "
            f"magic_bytes_hex={magic_bytes_hex!r}, "
            f"head_preview_bytes={len(head)}"
        )

        finding = Finding(
            mechanism="unknown_format",
            tier=3,
            confidence=1.0,
            description=description,
            location=str(path),
            surface=(
                f"declared extension {extension!r}; "
                f"file size {size_bytes} bytes"
            ),
            concealed=(
                f"magic bytes {magic_bytes_hex!r}; "
                f"head preview ASCII: {head_preview_ascii!r}; "
                f"head preview hex: {head_preview_hex!r}"
            ),
            source_layer=self.source_layer,
        )

        # Step 5 — return scan-incomplete so the clamp applies.
        return IntegrityReport(
            file_path=str(path),
            integrity_score=apply_scan_incomplete_clamp(
                compute_muwazana_score([finding]),
                scan_incomplete=True,
            ),
            findings=[finding],
            error=None,
            scan_incomplete=True,
        )

    # ------------------------------------------------------------------
    # Scan-limited helper
    # ------------------------------------------------------------------

    def _scan_limited_report(
        self,
        path: Path,
        message: str,
        *,
        size_bytes: int,
    ) -> IntegrityReport:
        """Emit a ``scan_limited`` finding and a scan-incomplete report.

        Parallels ``BaseAnalyzer._scan_error_report`` in shape — tier 3,
        severity 0.0 (via the SEVERITY table), confidence 1.0. The
        finding carries the declared size in its ``concealed`` field so
        a reader can see exactly what ceiling was hit.
        """
        finding = Finding(
            mechanism="scan_limited",
            tier=3,
            confidence=1.0,
            description=message,
            location=str(path),
            surface=f"file size {size_bytes} bytes",
            concealed=(
                "(file exceeded max_file_size_bytes; "
                "head preview not inspected)"
            ),
            source_layer=self.source_layer,
        )
        return IntegrityReport(
            file_path=str(path),
            integrity_score=apply_scan_incomplete_clamp(
                compute_muwazana_score([finding]),
                scan_incomplete=True,
            ),
            findings=[finding],
            error=None,
            scan_incomplete=True,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _printable_ascii_preview(data: bytes) -> str:
    """Render ``data`` as printable ASCII, replacing non-printables with ``.``.

    The convention borrows from hexdump ``-C``: every byte in the
    printable-ASCII range (0x20-0x7E) is passed through; everything
    else becomes ``.``. The result is a single-line preview the
    terminal report formatter can render without escaping concerns.
    """
    return "".join(
        chr(b) if 0x20 <= b <= 0x7E else "." for b in data
    )


__all__ = ["FallbackAnalyzer"]
