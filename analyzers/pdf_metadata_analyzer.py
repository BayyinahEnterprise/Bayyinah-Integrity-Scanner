"""
Tier 1 detector for PDF document-metadata concealment (v1.1.2,
mechanism 04).

PDF document metadata - the /Info dictionary in the trailer and the
XMP stream attached to the document catalog - carries text that AI
extraction pipelines ingest as document content but that no rendered
page displays. Adversarial use places directive text or hidden
payloads in metadata fields, knowing that downstream LLMs read the
metadata while a human reader sees only the visible page.

Closes pdf_gauntlet fixture 04_metadata.pdf, which carries the
HIDDEN_TEXT_PAYLOAD in /Info /Keywords, /Info /Subject, and XMP
dc:description.

Reference: docs/adversarial/pdf_gauntlet/REPORT.md row 04.

Tier discipline (per Day 2 prompt section 6.3):

This is a Tier 1 mechanism because every trigger below is verifiable
from the file's bytes alone with no semantic claim. The four
triggers are:

  (a) length: a field's UTF-8 byte length exceeds 512 (a reasonable
      ceiling for legitimate metadata; longer values are structurally
      anomalous regardless of content);
  (b) bidi: presence of bidirectional override codepoints
      (U+202A through U+202E, U+2066 through U+2069);
  (c) zero-width: presence of U+200B ZWSP, U+200C ZWNJ, U+200D ZWJ,
      or U+FEFF BOM;
  (d) divergence: the field's text is not present in the rendered
      page text. Restricted to the three content-summary fields
      where divergence with the visible surface is the structural
      concern (/Keywords, XMP dc:description, XMP pdf:Keywords).
      /Title, /Author, /Subject, /Creator are excluded because
      legitimate values in those fields may not appear verbatim on
      rendered pages (titles abbreviate, authors are credited
      differently, subjects summarize abstractly).

Semantic signals (imperative-mode vocabulary, prompt-shaped phrasing,
directive markers) are explicitly out of scope for this Tier 1
mechanism. Such signals are queued for v1.3+ as the future Tier 3
sub-mechanism pdf_metadata_directive_phrasing.

Cow Episode discipline (Day 2 prompt section 6.3): only dc:, pdf:,
and xmp: namespaces are inspected. The fixture exercises dc: and
pdf:; xmp: is included as the standard core. Other XMP namespaces
(x:, photoshop:, exif:, etc.) are not in scope for v1.1.2.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

import pikepdf

from domain.finding import Finding


_FIELD_LENGTH_LIMIT = 512  # bytes (UTF-8); per Day 2 prompt section 6.3

# Bidirectional-override codepoints, named by explicit escape. The
# detector for adversarial bidi runs must not itself contain invisible
# bidi runs in its source - readers reviewing this file in any editor
# see the codepoint number, not a glyph that re-orders surrounding
# code. U+202A through U+202E are the legacy embedding/override
# controls; U+2066 through U+2069 are the Unicode 6.3 isolate
# controls. The set is closed; future additions to the bidi class are
# tracked at https://www.unicode.org/Public/UCD/latest/ucd/Bidirectional/.
_BIDI_CHARS = frozenset({
    "‪",  # LEFT-TO-RIGHT EMBEDDING
    "‫",  # RIGHT-TO-LEFT EMBEDDING
    "‬",  # POP DIRECTIONAL FORMATTING
    "‭",  # LEFT-TO-RIGHT OVERRIDE
    "‮",  # RIGHT-TO-LEFT OVERRIDE
    "⁦",  # LEFT-TO-RIGHT ISOLATE
    "⁧",  # RIGHT-TO-LEFT ISOLATE
    "⁨",  # FIRST STRONG ISOLATE
    "⁩",  # POP DIRECTIONAL ISOLATE
})

# Zero-width codepoints. Same source-review reasoning as the bidi set.
_ZERO_WIDTH_CHARS = frozenset({
    "​",  # ZERO WIDTH SPACE
    "‌",  # ZERO WIDTH NON-JOINER
    "‍",  # ZERO WIDTH JOINER
    "﻿",  # ZERO WIDTH NO-BREAK SPACE / BOM
})

_MIN_DIVERGENCE_LENGTH = 16  # Floor on metadata text considered for the
# divergence trigger; shorter values are too noisy to evaluate against
# rendered text (legitimate short tags need not appear verbatim on a
# page). The fixture's payload is 55 chars, well above this floor.

# /Info keys whose divergence with rendered text is structurally
# suspicious. /Title, /Author, /Subject, /Creator, /Producer,
# /Trapped, /CreationDate, /ModDate are excluded for the reasons
# described in the module docstring.
_DIVERGENCE_INFO_KEYS = frozenset({"/Keywords"})

# XMP property local names (without namespace) whose divergence with
# rendered text is structurally suspicious. dc:description (a richer
# variant of /Subject typically used to carry directive content
# payloads) and pdf:Keywords (XMP analogue of /Info /Keywords).
_DIVERGENCE_XMP_LOCAL_NAMES = frozenset({"description", "Keywords"})

# XMP namespaces inspected. Other namespaces are out of v1.1.2 scope
# per the Cow Episode discipline; they queue as future-work entries
# in REPORT.md.
_XMP_DC_NS = "{http://purl.org/dc/elements/1.1/}"
_XMP_PDF_NS = "{http://ns.adobe.com/pdf/1.3/}"
_XMP_XMP_NS = "{http://ns.adobe.com/xap/1.0/}"
_XMP_NAMESPACES = (_XMP_DC_NS, _XMP_PDF_NS, _XMP_XMP_NS)


# Regexes for extracting Tj / TJ literal text operands from a content
# stream. Best-effort; the goal is "rendered text the metadata can be
# checked against," not perfect text reconstruction. Hex strings
# (``<...>`` Tj) are not decoded; the divergence trigger is permissive
# (a metadata payload is concealed only if it does NOT appear in the
# extracted text, so missing some legitimate text causes false
# positives only if the metadata happens to mirror exactly that
# extracted-vs-actual gap; that risk is bounded by _MIN_DIVERGENCE_LENGTH).
_TJ_LITERAL = re.compile(rb"\(((?:[^()\\]|\\.)*)\)\s*Tj")
_TJ_INNER = re.compile(rb"\(((?:[^()\\]|\\.)*)\)")


def _extract_rendered_text(pdf: pikepdf.Pdf) -> str:
    chunks: list[str] = []
    for page in pdf.pages:
        try:
            cs = page.Contents.read_bytes()
        except Exception:
            continue
        for m in _TJ_LITERAL.finditer(cs):
            chunks.append(m.group(1).decode("latin-1", errors="replace"))
        # TJ operands appear as ``[ (text) num (text) num ] TJ``; the
        # inner literals share the same Tj-style escaping. Capture them
        # all so a TJ-rendered passage is searchable.
        for m in re.finditer(rb"\[([^\]]*)\]\s*TJ", cs):
            for sub in _TJ_INNER.finditer(m.group(1)):
                chunks.append(sub.group(1).decode("latin-1", errors="replace"))
    return "\n".join(chunks)


def _check_field(
    field_label: str,
    value: str,
    rendered: str,
    divergence_eligible: bool,
) -> Iterable[Finding]:
    if value is None:
        return []
    out: list[Finding] = []
    encoded_len = len(value.encode("utf-8", errors="replace"))
    # (a) length
    if encoded_len > _FIELD_LENGTH_LIMIT:
        out.append(Finding(
            mechanism="pdf_metadata_analyzer",
            tier=1,
            confidence=1.0,
            description=(
                f"Metadata field {field_label} carries {encoded_len} "
                f"UTF-8 bytes, exceeding the {_FIELD_LENGTH_LIMIT}-byte "
                f"per-field limit. Long metadata is structurally "
                f"anomalous regardless of content."
            ),
            location=field_label,
            surface=f"metadata field {field_label}",
            concealed=f"length {encoded_len} bytes",
        ))
    # (b) bidi
    bidi = sorted({c for c in value if c in _BIDI_CHARS})
    if bidi:
        out.append(Finding(
            mechanism="pdf_metadata_analyzer",
            tier=1,
            confidence=1.0,
            description=(
                f"Metadata field {field_label} contains "
                f"bidirectional-override codepoints "
                f"({', '.join('U+%04X' % ord(c) for c in bidi)}) that "
                f"reorder rendered glyphs vs. the underlying byte order."
            ),
            location=field_label,
            surface=f"metadata field {field_label}",
            concealed=f"bidi codepoints: {[hex(ord(c)) for c in bidi]}",
        ))
    # (c) zero-width
    zw = sorted({c for c in value if c in _ZERO_WIDTH_CHARS})
    if zw:
        out.append(Finding(
            mechanism="pdf_metadata_analyzer",
            tier=1,
            confidence=1.0,
            description=(
                f"Metadata field {field_label} contains zero-width "
                f"codepoints "
                f"({', '.join('U+%04X' % ord(c) for c in zw)}) that "
                f"are invisible in any renderer but present in the bytes."
            ),
            location=field_label,
            surface=f"metadata field {field_label}",
            concealed=f"zero-width codepoints: {[hex(ord(c)) for c in zw]}",
        ))
    # (d) divergence
    if divergence_eligible:
        stripped = value.strip()
        if len(stripped) >= _MIN_DIVERGENCE_LENGTH and stripped not in rendered:
            out.append(Finding(
                mechanism="pdf_metadata_analyzer",
                tier=1,
                confidence=1.0,
                description=(
                    f"Metadata field {field_label} carries text "
                    f"({len(stripped)} chars) that does not appear in "
                    f"any rendered page. Content-summary fields whose "
                    f"text diverges from the visible surface are "
                    f"structurally anomalous: an LLM reading the "
                    f"metadata sees content the human reader cannot."
                ),
                location=field_label,
                surface=f"metadata field {field_label}",
                concealed=f"text not present in any rendered page",
            ))
    return out


def detect_pdf_metadata_analyzer(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for /Info dictionary or XMP metadata
    fields exhibiting structural anomalies.
    """
    findings: list[Finding] = []
    try:
        pdf = pikepdf.open(str(file_path))
    except Exception:
        return findings
    try:
        rendered = _extract_rendered_text(pdf)
        # /Info dictionary
        try:
            info = pdf.docinfo
        except Exception:
            info = None
        if info is not None:
            for key in info.keys():
                k = str(key)
                v = str(info[key])
                findings.extend(_check_field(
                    f"/Info {k}",
                    v,
                    rendered,
                    divergence_eligible=k in _DIVERGENCE_INFO_KEYS,
                ))
        # XMP metadata
        try:
            with pdf.open_metadata() as meta:
                for k, v in meta.items():
                    sk = str(k)
                    if not any(sk.startswith(ns) for ns in _XMP_NAMESPACES):
                        continue
                    sv = str(v)
                    local = sk.rsplit("}", 1)[-1] if "}" in sk else sk
                    findings.extend(_check_field(
                        f"XMP {sk}",
                        sv,
                        rendered,
                        divergence_eligible=(
                            local in _DIVERGENCE_XMP_LOCAL_NAMES
                        ),
                    ))
        except Exception:
            pass
    finally:
        pdf.close()
    return findings


__all__ = ["detect_pdf_metadata_analyzer"]
