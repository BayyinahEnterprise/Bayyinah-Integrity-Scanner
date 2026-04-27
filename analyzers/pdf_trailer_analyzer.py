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


def detect_pdf_trailer_analyzer(file_path: Path) -> list[Finding]:
    """Return a Tier 2 finding if non-whitespace bytes follow the
    final %%EOF marker; otherwise return an empty list.

    Pure byte scan. No PDF parser invoked.
    """
    findings: list[Finding] = []
    try:
        data = Path(file_path).read_bytes()
    except OSError:
        return findings

    # Locate the FINAL %%EOF marker. PDFs with incremental updates
    # carry multiple %%EOF markers; only the bytes after the last
    # one are structurally orphan.
    last = data.rfind(_EOF_TOKEN)
    if last == -1:
        # No %%EOF at all - that is a separate parse-level problem
        # already surfaced by pymupdf/pypdf scan_error paths. Tier 2
        # trailing-bytes detection has nothing to say about it.
        return findings

    trailing = data[last + len(_EOF_TOKEN):]
    # Whitespace-only trailing regions are within spec: many PDF
    # generators end the file with a newline. Strip and check.
    if trailing.strip() == b"":
        return findings

    sample = trailing[:_SAMPLE_BYTES]
    # ASCII-decode the sample for the description; non-printable
    # bytes are passed through as escape sequences via the repr()
    # path so the finding stays printable in any UTF-8 console.
    sample_repr = repr(sample.decode("latin-1", errors="replace"))
    findings.append(Finding(
        mechanism="pdf_trailer_analyzer",
        tier=2,
        confidence=1.0,
        description=(
            f"File carries {len(trailing)} bytes after the final "
            f"%%EOF marker at offset {last}. PDF specification "
            f"places %%EOF at the end of a valid file; bytes beyond "
            f"the final marker are structurally orphan and not part "
            f"of the rendered document. First {min(_SAMPLE_BYTES, len(trailing))} "
            f"bytes (Latin-1 repr): {sample_repr}."
        ),
        location=f"byte offset {last + len(_EOF_TOKEN)}",
        surface=f"file size {len(data)} bytes; final %%EOF at offset {last}",
        concealed=(
            f"{len(trailing)} non-whitespace trailing bytes "
            f"(sample: {sample_repr})"
        ),
    ))
    return findings


__all__ = ["detect_pdf_trailer_analyzer"]
