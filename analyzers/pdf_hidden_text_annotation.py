"""
Tier 1 detector for hidden /Text annotations carrying concealed text
(v1.1.2, mechanism 06).

PDF annotations occupy their own object space in the document graph.
The PDF specification (ISO 32000-1, section 12.5.3, Table 165)
defines the /F flag bitfield that controls how a viewer renders
each annotation:

    bit 1 (value 1)   - Invisible
    bit 2 (value 2)   - Hidden
    bit 3 (value 4)   - Print
    bit 4 (value 8)   - NoZoom
    bit 5 (value 16)  - NoRotate
    bit 6 (value 32)  - NoView
    bit 7 (value 64)  - ReadOnly
    bit 8 (value 128) - Locked
    bit 9 (value 256) - ToggleNoView
    bit 10 (value 512) - LockedContents

The mechanism keys on three of these bits as evidence that the
annotation has been deliberately suppressed from the reader's view
while remaining live in the document object graph for any AI text-
extractor that walks /Annots:

    Hidden          (bit 2, value 2)
    NoView          (bit 6, value 32)
    LockedContents  (bit 10, value 512)

Note on the v4 prompt's bit accounting. The Day 2 v4 prompt mech 06
spec lists "NoView = bit 4 = value 8" and "LockedContents = bit 7 =
value 64". The PDF specification numbers bits 1-indexed (bit 1 is
the lowest-order bit, value 1; bit n has value 2**(n-1)). Bit 4 is
NoZoom (value 8) and bit 7 is ReadOnly (value 64); NoView is bit 6
(value 32) and LockedContents is bit 10 (value 512). The detector
uses the spec-correct interpretation: mask = 2 | 32 | 512 = 546.
This is documented here so the choice is auditable; the user-facing
behavior (Hidden bit fires on fixture 06) is unchanged because
fixture 06 sets /F 2.

Closes pdf_gauntlet fixture 06_optional_content_group.pdf, whose
filename is historical (the build stage settled on /Text annotation
with /F=2 as the proxy attack rather than an OCG-based concealment).
The fixture's actual content is the hidden /Text annotation case
from REPORT.md row 06.

Reference:
  - docs/adversarial/pdf_gauntlet/REPORT.md row 06
  - docs/scope/v1_1_2_claude_prompt.md section 6.5
  - PDF specification ISO 32000-1, section 12.5.3, Table 165

Tier discipline (per Day 2 prompt section 6.5):

This is a Tier 1 mechanism because every trigger is verifiable from
the file's bytes alone. The annotation has the suppression bit set
AND non-whitespace /Contents text - both observable from a single
walk of /Annots. The signal class parallels mechanism 03
(pdf_off_page_text): structural fact plus recovered concealed text,
no statistical claim, no hidden-state inference.

Classification: ZAHIR. The annotation /F flag and /Contents string
are surface-readable once the parser walks /Annots; the rendering
suppression is a viewer instruction, not a deeper-graph property.
This parallels off_page_text and pdf_off_page_text in zahir.

The detector is a parallel pass alongside the v1.1.1 _scan_annotations
walk in BatinObjectAnalyzer; it does not modify _scan_annotations
or any v1.1.1 analyzer code. It opens its own pypdf reader so a
parse failure in the host analyzer's reader does not silently
suppress the detector.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pypdf

from domain.finding import Finding


# Annotation /F flag bits (per PDF spec ISO 32000-1 Table 165) that
# evidence deliberate suppression of the annotation from the reader's
# view. See module docstring for the complete bit map and the
# accounting note.
_HIDDEN_BIT = 2          # bit 2 - Hidden
_NOVIEW_BIT = 32         # bit 6 - NoView
_LOCKED_CONTENTS_BIT = 512  # bit 10 - LockedContents
_SUPPRESSION_MASK = _HIDDEN_BIT | _NOVIEW_BIT | _LOCKED_CONTENTS_BIT

# Annotation subtypes that carry a /Contents text payload of interest.
# /Link, /Widget, /Highlight, /Underline, /Squiggly, /StrikeOut,
# /Caret, /Ink, /Square, /Circle, /Line, /Polygon, /PolyLine,
# /FileAttachment, /Sound, /Movie, /Screen, /3D, /Redact,
# /Watermark, /TrapNet, /Projection, /RichMedia are out of scope -
# they either carry no text payload or have other v1.1.1 mechanisms
# (e.g. file_attachment_annot for /FileAttachment).
_TEXT_BEARING_SUBTYPES = frozenset({
    "/Text",
    "/FreeText",
    "/Popup",
    "/Stamp",
})

# Maximum length of the /Contents string included in a finding's
# evidence/concealed field. Long payloads are truncated; the full
# value remains in the document for the reviewer to inspect.
_MAX_CONTENTS_PREVIEW = 256


def _flag_int(flag_value: Any) -> int:
    """Coerce pypdf's /F representation (NumberObject, IndirectObject,
    int, float, str) to a plain int. Returns 0 on any failure - a
    flag that cannot be parsed is treated as no-flag-set."""
    try:
        if hasattr(flag_value, "get_object"):
            flag_value = flag_value.get_object()
        return int(flag_value)
    except (TypeError, ValueError):
        return 0


def _set_bits_label(flag_int: int) -> str:
    """Return a human-readable summary of which suppression bits are
    set in the annotation /F flag, e.g. 'Hidden' or 'Hidden+NoView'.
    """
    parts: list[str] = []
    if flag_int & _HIDDEN_BIT:
        parts.append("Hidden")
    if flag_int & _NOVIEW_BIT:
        parts.append("NoView")
    if flag_int & _LOCKED_CONTENTS_BIT:
        parts.append("LockedContents")
    return "+".join(parts) if parts else "(none)"


def detect_pdf_hidden_text_annotation(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for each annotation whose /F flag has
    a suppression bit set AND whose /Contents carries non-whitespace
    text.

    Pure object-graph walk via pypdf. No content-stream parsing, no
    rendering. Defensive: if pypdf cannot open the file at all, the
    detector returns an empty list rather than raising.
    """
    findings: list[Finding] = []
    try:
        reader = pypdf.PdfReader(str(file_path))
    except Exception:
        return findings
    try:
        for page_idx, page in enumerate(reader.pages):
            try:
                annots = page.get("/Annots")
            except Exception:
                continue
            if annots is None:
                continue
            try:
                annots_list = list(annots)
            except Exception:
                continue
            for annot_ref in annots_list:
                try:
                    annot = (
                        annot_ref.get_object()
                        if hasattr(annot_ref, "get_object")
                        else annot_ref
                    )
                    subtype = str(annot.get("/Subtype", "") or "")
                    if subtype not in _TEXT_BEARING_SUBTYPES:
                        continue
                    flag_int = _flag_int(annot.get("/F"))
                    if not (flag_int & _SUPPRESSION_MASK):
                        continue
                    contents_raw = annot.get("/Contents")
                    if contents_raw is None:
                        continue
                    if hasattr(contents_raw, "get_object"):
                        contents_raw = contents_raw.get_object()
                    contents_str = str(contents_raw)
                    if not contents_str.strip():
                        continue
                    preview = contents_str[:_MAX_CONTENTS_PREVIEW]
                    if len(contents_str) > _MAX_CONTENTS_PREVIEW:
                        preview += "..."
                    bits_label = _set_bits_label(flag_int)
                    obj_id = (
                        annot_ref.idnum
                        if hasattr(annot_ref, "idnum") else None
                    )
                    location = (
                        f"page {page_idx + 1}, /Annot object {obj_id}"
                        if obj_id is not None
                        else f"page {page_idx + 1}"
                    )
                    findings.append(Finding(
                        mechanism="pdf_hidden_text_annotation",
                        tier=1,
                        confidence=1.0,
                        description=(
                            f"Annotation {subtype} on page {page_idx + 1} "
                            f"has /F={flag_int} ({bits_label}) and "
                            f"non-whitespace /Contents. The annotation's "
                            f"text is invisible to a human viewing the "
                            f"rendered page but is recovered by any "
                            f"text-extraction pipeline that walks /Annots."
                        ),
                        location=location,
                        surface=f"annotation {subtype} suppressed by /F={flag_int}",
                        concealed=(
                            f"/F={flag_int} ({bits_label}); "
                            f"/Contents={preview!r}"
                        ),
                    ))
                except Exception:
                    continue
    except Exception:
        pass
    return findings


__all__ = ["detect_pdf_hidden_text_annotation"]
