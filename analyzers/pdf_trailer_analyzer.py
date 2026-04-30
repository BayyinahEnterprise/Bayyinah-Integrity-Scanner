"""
Tier 2 detector for non-whitespace bytes after the final PDF
%%EOF marker (v1.1.2, mechanism 05).

The PDF specification (ISO 32000-1 section 7.5.5) places the
final %%EOF marker at the end of a valid PDF file. Bytes after
that final marker are structurally orphan: no parser is required
to read them, no rendered page references them, and no part of
the document object graph reaches them. Adversarial PDFs append
arbitrary content here (text payloads, embedded ZIP archives,
secondary file formats) knowing that text-extraction pipelines
that scan the entire byte stream will surface the trailing region
while a human opening the PDF in a viewer never sees it.

Closes pdf_gauntlet fixture 05_after_eof.pdf.
Reference: docs/adversarial/pdf_gauntlet/REPORT.md row 05.

Tier discipline (per Day 2 prompt section 6.4):

This is a Tier 2 mechanism, not Tier 1. The structural fact
(non-whitespace bytes after the final %%EOF) is verifiable from
the file alone, but the fact alone does not prove concealment:
  - Some PDF generators emit a trailing newline after %%EOF; the
    detector requires non-whitespace content to fire.
  - Incremental-update PDFs contain multiple %%EOF markers in
    series; the detector keys on the FINAL %%EOF only, so an
    incremental-update file with a clean tail does not fire.
  - A non-whitespace trailing region could be a comment, a
    secondary embedded format, an adversarial payload, or
    PDF-generator metadata that fell outside the standard. The
    detector reports the structural fact and lets the reviewer
    perform the recognition.

Promoting to Tier 1 here would require parsing the trailing region
as a specific format (PDF, ZIP, executable) and proving it is
functional. That is v1.3+ research scope; it does not belong in
v1.1.2.

The detector reads raw bytes via the standard library only; no
third-party imports are introduced. This works even on PDFs that
pikepdf or pymupdf cannot parse, because incremental-update
detection should never depend on a successful parse (mirroring the
v1.1.1 BatinObjectAnalyzer._scan_incremental_updates discipline).
"""
from __future__ import annotations

from pathlib import Path

from domain import get_current_content_index
from domain.finding import Finding


# %%EOF token. The PDF specification permits trailing CR or LF
# characters as part of the marker line; the detector locates the
# byte sequence and treats anything after the 5 bytes "%%EOF" as
# the trailing region. A trailing newline is whitespace and the
# whitespace-only check below handles it.
_EOF_TOKEN = b"%%EOF"

# Sample of the trailing region included in the finding's evidence.
# 64 bytes is enough to identify common payloads (HIDDEN_TEXT_*,
# PK\x03\x04 ZIP magic, MZ executable header, %%XPub comments)
# without dumping arbitrarily long blobs into the finding text.
_SAMPLE_BYTES = 64


def _emit_finding(
    last: int,
    trailing_full_len: int,
    trailing_sample: bytes,
    file_size: int,
) -> Finding:
    """Construct the canonical Finding from the located EOF + trailing.

    Both the index path and the legacy self-walk path must produce
    identical Finding shapes; centralising construction here keeps
    them byte-parity-locked.
    """
    sample = trailing_sample[:_SAMPLE_BYTES]
    sample_repr = repr(sample.decode("latin-1", errors="replace"))
    return Finding(
        mechanism="pdf_trailer_analyzer",
        tier=2,
        confidence=1.0,
        description=(
            f"File carries {trailing_full_len} bytes after the final "
            f"%%EOF marker at offset {last}. PDF specification "
            f"places %%EOF at the end of a valid file; bytes beyond "
            f"the final marker are structurally orphan and not part "
            f"of the rendered document. First {min(_SAMPLE_BYTES, trailing_full_len)} "
            f"bytes (Latin-1 repr): {sample_repr}."
        ),
        location=f"byte offset {last + len(_EOF_TOKEN)}",
        surface=f"file size {file_size} bytes; final %%EOF at offset {last}",
        concealed=(
            f"{trailing_full_len} non-whitespace trailing bytes "
            f"(sample: {sample_repr})"
        ),
    )


def detect_pdf_trailer_analyzer(file_path: Path) -> list[Finding]:
    """Return a Tier 2 finding if non-whitespace bytes follow the
    final %%EOF marker; otherwise return an empty list.

    v1.1.4 - reads from the per-scan ContentIndex when one is
    installed (last_eof_offset, trailing_after_last_eof, raw_bytes_len
    populated by populate_from_raw_bytes). Falls back to the
    raw-byte-stream self-walk when no index is available, when the
    raw-bytes read failed during index population, or when the index
    is incomplete. Detection logic and finding construction are
    byte-parity-identical across both paths because the trailing
    region is the same bytes either way.
    """
    findings: list[Finding] = []

    idx = get_current_content_index()
    if (
        idx is not None
        and not idx.build_failed
        and not idx.raw_bytes_read_failed
        and idx.raw_bytes_len > 0
        and idx.last_eof_offset >= -1  # -1 is a valid "no marker" sentinel
    ):
        last = idx.last_eof_offset
        if last == -1:
            return findings
        # The index caps trailing_after_last_eof at 4096 bytes; the
        # full trailing length is recoverable as raw_bytes_len minus
        # the offset past the marker. Compute both so the description
        # cites the full byte count while the sample stays a 64-byte
        # snapshot identical to the legacy self-walk output.
        trailing_full_len = idx.raw_bytes_len - (last + len(_EOF_TOKEN))
        trailing_sample = idx.trailing_after_last_eof
        if trailing_sample.strip() == b"":
            # Whitespace-only trailing region - within spec.
            return findings
        findings.append(_emit_finding(
            last=last,
            trailing_full_len=trailing_full_len,
            trailing_sample=trailing_sample,
            file_size=idx.raw_bytes_len,
        ))
        return findings

    # Fallback: legacy self-walk via raw bytes. Preserved verbatim so
    # direct analyzer-level tests, scans where the index build failed,
    # and pre-migration callers continue to work unchanged.
    try:
        data = Path(file_path).read_bytes()
    except OSError:
        return findings

    last = data.rfind(_EOF_TOKEN)
    if last == -1:
        return findings

    trailing = data[last + len(_EOF_TOKEN):]
    if trailing.strip() == b"":
        return findings

    findings.append(_emit_finding(
        last=last,
        trailing_full_len=len(trailing),
        trailing_sample=trailing,
        file_size=len(data),
    ))
    return findings


__all__ = ["detect_pdf_trailer_analyzer"]
