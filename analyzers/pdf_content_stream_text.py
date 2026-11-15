"""
Content-stream text walker for PDFs.

Reads each page's content stream operator by operator (via pikepdf) and
reports every text-showing operation together with the state that decides
whether a human can see it:

  * device-space origin   (CTM x text line matrix)  -> on or off the page
  * effective font size   (Tf size x matrix scale)   -> legible or not
  * text render mode      (Tr)                       -> painted or not

Why this exists. PyMuPDF's ``get_text("dict")`` omits spans positioned far
outside the page, so any check that relies on extracted spans never sees
them. Other extractors commonly used in LLM ingestion (pypdf, for one)
return that text. Walking the operators directly closes the gap without
depending on any one extractor's clipping behaviour. The earlier
``pdf_off_page_text`` detector reads only ``Tm`` operators; text moved with
``Td``/``TD``/``T*`` (the more common way to position a line) was missed.

This module only reports facts about the bytes. It does not decide intent.

Limits, stated plainly:
  * Glyph advance after a show operator is not tracked (it needs font
    metrics), so the origin reported for a second ``Tj`` on the same line
    is the line origin. Off-page and size judgements are unaffected.
  * Hex strings and CID-keyed fonts are decoded as latin-1 best effort;
    recovered text for such fonts may be unreadable. The structural fact
    (text present, where, at what size) is still reported.
  * Text drawn inside Form XObjects (``Do``) is not followed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pikepdf

Matrix = tuple[float, float, float, float, float, float]
_IDENTITY: Matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

# A text origin within this many points of a MediaBox edge counts as on-page.
OFF_PAGE_MARGIN_PT = 1.0


def _mul(m: Matrix, n: Matrix) -> Matrix:
    """Return m x n (apply m first, then n), PDF row-vector convention."""
    a, b, c, d, e, f = m
    g, h, i, j, k, l = n
    return (a * g + b * i, a * h + b * j,
            c * g + d * i, c * h + d * j,
            e * g + f * i + k, e * h + f * j + l)


def _scale(m: Matrix) -> float:
    """Uniform scale factor of a matrix (square root of |determinant|)."""
    return math.sqrt(abs(m[0] * m[3] - m[1] * m[2]))


@dataclass(frozen=True)
class TextRun:
    page_index: int
    text: str
    x: float
    y: float
    font_size: float          # effective size in points, after matrix scaling
    render_mode: int
    off_page: bool
    operator_index: int


def _num(x) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _text_of(operand) -> str:
    """Best-effort text from a Tj operand or one element of a TJ array."""
    try:
        raw = bytes(operand)
    except Exception:
        return ""
    if raw[:2] in (b"\xfe\xff", b"\xff\xfe"):
        try:
            return raw.decode("utf-16")
        except Exception:
            pass
    return raw.decode("latin-1", errors="replace")


def _page_streams(page) -> bytes | None:
    try:
        contents = page.obj.get("/Contents")
        if contents is None:
            return None
        if isinstance(contents, pikepdf.Array):
            return b"\n".join(s.read_bytes() for s in contents)
        return contents.read_bytes()
    except Exception:
        return None


def walk_page(page, page_index: int) -> Iterator[TextRun]:
    """Yield a TextRun for every text-showing operator on one page."""
    try:
        mb = [float(v) for v in page.MediaBox]
        x0, y0, x1, y1 = min(mb[0], mb[2]), min(mb[1], mb[3]), max(mb[0], mb[2]), max(mb[1], mb[3])
    except Exception:
        return
    try:
        instructions = pikepdf.parse_content_stream(page)
    except Exception:
        return

    ctm: Matrix = _IDENTITY
    stack: list[tuple[Matrix, int]] = []
    tm: Matrix = _IDENTITY       # text matrix
    tlm: Matrix = _IDENTITY      # text line matrix
    size = 0.0
    leading = 0.0
    render = 0

    def emit(text: str, idx: int) -> TextRun | None:
        if not text:
            return None
        dev = _mul(tm, ctm)
        ox, oy = dev[4], dev[5]
        off = (ox < x0 - OFF_PAGE_MARGIN_PT or ox > x1 + OFF_PAGE_MARGIN_PT
               or oy < y0 - OFF_PAGE_MARGIN_PT or oy > y1 + OFF_PAGE_MARGIN_PT)
        return TextRun(page_index, text, ox, oy, abs(size) * _scale(dev), render, off, idx)

    def next_line(tx: float, ty: float) -> None:
        nonlocal tm, tlm
        tlm = _mul((1.0, 0.0, 0.0, 1.0, tx, ty), tlm)
        tm = tlm

    for idx, ins in enumerate(instructions):
        try:
            op = str(ins.operator)
            a = ins.operands
        except Exception:
            continue
        if op == "q":
            stack.append((ctm, render))
        elif op == "Q":
            if stack:
                ctm, render = stack.pop()
        elif op == "cm" and len(a) == 6:
            ctm = _mul(tuple(_num(v) for v in a), ctm)  # type: ignore[arg-type]
        elif op == "BT":
            tm = tlm = _IDENTITY
        elif op == "Tf" and len(a) == 2:
            size = _num(a[1])
        elif op == "TL" and a:
            leading = _num(a[0])
        elif op == "Tr" and a:
            render = int(_num(a[0]))
        elif op == "Tm" and len(a) == 6:
            tm = tlm = tuple(_num(v) for v in a)  # type: ignore[assignment]
        elif op == "Td" and len(a) == 2:
            next_line(_num(a[0]), _num(a[1]))
        elif op == "TD" and len(a) == 2:
            leading = -_num(a[1])
            next_line(_num(a[0]), _num(a[1]))
        elif op == "T*":
            next_line(0.0, -leading)
        elif op == "Tj" and a:
            r = emit(_text_of(a[0]), idx)
            if r:
                yield r
        elif op == "TJ" and a:
            try:
                parts = [_text_of(e) for e in a[0] if isinstance(e, (pikepdf.String, bytes))]
            except Exception:
                parts = []
            r = emit("".join(parts), idx)
            if r:
                yield r
        elif op in ("'", '"') and a:
            next_line(0.0, -leading)
            r = emit(_text_of(a[-1]), idx)
            if r:
                yield r


def walk_pdf(file_path: Path | str) -> list[TextRun]:
    """Return every text run in the document. Empty list if unreadable."""
    runs: list[TextRun] = []
    try:
        pdf = pikepdf.open(str(file_path))
    except Exception:
        return runs
    try:
        for i, page in enumerate(pdf.pages):
            runs.extend(walk_page(page, i))
    finally:
        pdf.close()
    return runs


def join_runs(runs: list[TextRun]) -> str:
    """Join consecutive runs into readable text.

    A message split one glyph per operator ("I", "g", "n", ...) is joined
    without separators; a single space run inside such a sequence is kept as
    the word break. All other runs are joined with one space.
    """
    pieces: list[str] = []
    glyph_chain = False
    for r in runs:
        t = r.text
        if len(t) == 1:
            if glyph_chain and pieces:
                pieces[-1] += t
            else:
                pieces.append(t)
            glyph_chain = True
        else:
            pieces.append(t)
            glyph_chain = False
    return " ".join(p.strip() for p in pieces if p.strip())


__all__ = ["TextRun", "walk_page", "walk_pdf", "join_runs", "OFF_PAGE_MARGIN_PT"]
