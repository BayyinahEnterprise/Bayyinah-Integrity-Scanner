"""Truth by execution: render the page with and without the payload.

``visible``     removing the payload changes pixels a reader could notice,
                and the changed area is tall enough to be glyphs
``sub_legible`` it changes pixels, but the mark is under ``MIN_GLYPH_PX``
                tall: ink is there, words are not
``invisible``   it changes nothing

Independent of the scanner: the truth comes from the generator leaving
the payload out, not from any analysis of the file's operators.

Horizon: MuPDF at 72 dpi, greyscale, one reader. A pixel counts as
changed at a difference of ``MIN_DELTA`` of 255 or more.
"""

from __future__ import annotations

try:
    import pymupdf as fitz
except ImportError:
    import fitz

MIN_DELTA = 24
MIN_PIXELS = 2
MIN_GLYPH_PX = 4


def _render(path: str):
    with fitz.open(path) as doc:
        return doc[0].get_pixmap(colorspace=fitz.csGRAY, alpha=False)


def truth(with_path: str, without_path: str) -> str:
    a, b = _render(with_path), _render(without_path)
    sa, sb, stride = a.samples, b.samples, a.stride
    rows = []
    for y in range(a.height):
        ra, rb = sa[y * stride:(y + 1) * stride], sb[y * stride:(y + 1) * stride]
        if ra != rb:
            n = sum(1 for p, q in zip(ra, rb) if abs(p - q) >= MIN_DELTA)
            if n:
                rows.append((y, n))
    if sum(n for _, n in rows) < MIN_PIXELS:
        return "invisible"
    height = rows[-1][0] - rows[0][0] + 1
    return "visible" if height >= MIN_GLYPH_PX else "sub_legible"


def machine_reads(path: str, mark: str) -> bool:
    """Whether a text extractor hands the payload to a model. Two
    extractors, because they disagree about off-page text."""
    from pypdf import PdfReader
    try:
        if mark in (PdfReader(path).pages[0].extract_text() or ""):
            return True
    except Exception:
        pass
    with fitz.open(path) as doc:
        return mark in doc[0].get_text()
