"""
Tier 1 detector for off-page text in PDFs (v1.1.2, mechanism 03).

Catches text-positioning operators (Tm) whose origin coordinate falls
outside the page's MediaBox. The text exists in the content stream
and is extracted by every PDF text extractor an LLM ingestion pipeline
uses, but is invisible to a human reading the rendered page. The
v1.1.1 _check_offpage in text_analyzer.py would fire correctly if it
received the off-page span, but PyMuPDF's get_text('dict') silently
drops spans whose origin is outside the page rectangle, so the check
has nothing to evaluate. This mechanism reads the raw content stream
via pikepdf to bypass that drop and surface the structural fact:
bytes are present, rendering is gone.

Closes pdf_gauntlet fixture 03_off_page.pdf. Reference:
docs/adversarial/pdf_gauntlet/REPORT.md row 03.

Tier discipline: this is Tier 1 because the divergence is unambiguous
from the file alone. The Tm origin's device-space coordinate is a
deterministic function of the bytes; no statistical claim, no
heuristic threshold beyond a 1-pt floating-point margin. If the
fixture's signal ever required a confidence band (e.g., partial
glyph extents, CTM-rotated text), demote to Tier 2 in the same
commit and update REPORT.md to match.

The detector is a parallel pass alongside the v1.1.1 zahir text
walk; it does not modify _check_offpage or any v1.1.1 analyzer code.
The classification is zahir (not batin): the Tm origin coordinate
is observable from the rendered surface's text-positioning operators
with no hidden-state inference, paralleling the existing zahir
off_page_text mechanism.
"""
from __future__ import annotations

import re
from pathlib import Path

import pikepdf

from domain.finding import Finding


# A Tm operator inside a content stream: six numbers followed by
# the literal token "Tm". The last two numbers (groups 5 and 6) are
# the e and f translation components of the text matrix; combined
# with the CTM they give the device-space text origin. For a page
# whose CTM is identity (the common case, including the fixture's
# explicit "1 0 0 1 0 0 cm"), e and f ARE the device-space origin.
# This pattern matches well-formed Tm operations; pathological
# whitespace or comments inside the operator parameters are not in
# scope (the fixture uses canonical PDF generation).
_TM_PATTERN = re.compile(
    rb'(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+'
    rb'(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+'
    rb'(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s+Tm\b'
)

# Capture the literal text drawn by the Tj/TJ operators that follow a
# Tm (within the same BT/ET text object). The off-page Tm has positioned
# the cursor outside MediaBox; the subsequent Tj literal IS the payload
# the file carries but the rendered page does not show. Surfacing those
# bytes in inversion_recovery.concealed lets a reviewer read the hidden
# text directly, paralleling pdf_hidden_text_annotation's /Contents
# preview rather than only naming the structural pointer.
#
# We extract until the next Tm (cursor moves elsewhere) or ET (text
# object closes); whichever comes first bounds the off-page run. Hex
# strings (<...>Tj) are not decoded; the v1.1.2 fixture uses literal
# strings, and hex decoding requires font-encoding awareness that is
# out of scope for a Tier 1 byte-level analyzer.
_TJ_LITERAL = re.compile(rb'\(((?:[^()\\]|\\.)*)\)\s*Tj')
_TJ_ARRAY = re.compile(rb'\[([^\]]*)\]\s*TJ')
_TJ_INNER = re.compile(rb'\(((?:[^()\\]|\\.)*)\)')
_TEXT_BOUNDARY = re.compile(rb'\bTm\b|\bET\b')
_OFF_PAGE_TEXT_PREVIEW_LIMIT = 240  # chars; bounds inversion_recovery output


def _recover_off_page_text(content: bytes, start: int) -> str:
    """Read literal text the off-page Tm positions for, until the
    next Tm or ET. Returns a stripped UTF-8 (latin-1 fallback) string.
    """
    boundary = _TEXT_BOUNDARY.search(content, pos=start)
    end = boundary.start() if boundary else len(content)
    region = content[start:end]
    chunks: list[str] = []
    for m in _TJ_LITERAL.finditer(region):
        chunks.append(m.group(1).decode('latin-1', errors='replace'))
    for m in _TJ_ARRAY.finditer(region):
        for sub in _TJ_INNER.finditer(m.group(1)):
            chunks.append(sub.group(1).decode('latin-1', errors='replace'))
    text = ''.join(chunks).strip()
    if len(text) > _OFF_PAGE_TEXT_PREVIEW_LIMIT:
        text = text[:_OFF_PAGE_TEXT_PREVIEW_LIMIT] + '...'
    return text

# Margin around MediaBox edges. A Tm origin within 1 point of an
# edge stays on-page (font ascent/descent can pull a glyph
# fractionally over an edge in legitimate typesetting). 1 pt is
# conservative; the fixture's off-page Tm at y=-200 is 200 pt below
# the bottom edge, far beyond any tolerance.
_MARGIN = 1.0


def detect_pdf_off_page_text(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for each Tm origin outside MediaBox."""
    findings: list[Finding] = []
    try:
        pdf = pikepdf.open(str(file_path))
    except Exception:
        return findings
    try:
        for page_idx, page in enumerate(pdf.pages):
            try:
                mb = list(page.MediaBox)
                x0, y0, x1, y1 = (
                    float(mb[0]), float(mb[1]), float(mb[2]), float(mb[3])
                )
                content = page.Contents.read_bytes()
            except Exception:
                continue
            for m in _TM_PATTERN.finditer(content):
                e = float(m.group(5))
                f_ = float(m.group(6))
                if (
                    e < x0 - _MARGIN or e > x1 + _MARGIN
                    or f_ < y0 - _MARGIN or f_ > y1 + _MARGIN
                ):
                    recovered = _recover_off_page_text(content, m.end())
                    if recovered:
                        concealed = (
                            f"Tm origin ({e}, {f_}); "
                            f"recovered text: {recovered!r}"
                        )
                    else:
                        # Tm fired but no following literal in the
                        # same text object (e.g., off-page positioning
                        # used for cursor manipulation only). Keep
                        # the structural pointer so the verdict floor
                        # still trips and reviewers see the geometry.
                        concealed = f"Tm origin ({e}, {f_})"
                    findings.append(Finding(
                        mechanism="pdf_off_page_text",
                        tier=1,
                        confidence=1.0,
                        description=(
                            f"Text-matrix origin ({e}, {f_}) at content-"
                            f"stream offset {m.start()} positions a Tj/"
                            f"TJ-subsequent glyph run outside page "
                            f"MediaBox [{x0}, {y0}, {x1}, {y1}]. The "
                            f"bytes are present in the file; no "
                            f"rendering of the page shows them."
                        ),
                        location=f"page {page_idx + 1}",
                        surface=f"page MediaBox [{x0}, {y0}, {x1}, {y1}]",
                        concealed=concealed,
                    ))
    finally:
        pdf.close()
    return findings


__all__ = ["detect_pdf_off_page_text"]
