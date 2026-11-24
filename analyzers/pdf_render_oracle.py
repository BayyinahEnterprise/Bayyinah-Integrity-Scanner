"""The invariant, checked directly: text a parser extracts must leave a
mark on the rendered page.

Every other PDF text detector names a way of hiding text (render mode 3,
white fill, zero alpha, a clip path, an opaque box drawn on top, a text
matrix scaled to nothing). A list of ways is always one way short. This
module does not ask how. It renders each page twice, once as it is and
once with every text-showing operator removed, and looks at the pixels
under each extracted span. If removing the text changed nothing a reader
could see there, the reader never saw that text, whatever the cause.

Declared horizon
----------------
* Text drawn by the page's own content streams. Text inside form
  XObjects and annotation appearance streams is not removed by the
  stripped render, so it is never reported here (it is not called
  visible either: it is simply outside this check).
* Spans MuPDF's extractor places on the page, plus runs the
  content-stream walker places on the page that MuPDF did not return
  (clipped text). The second kind is tested at an estimated position,
  assuming an unrotated page. Text positioned off the page is the stream
  walker's job (``pdf_stream_concealment``).
* ``MAX_PAGES`` pages per file; later pages are disclosed as unchecked.
* Rendering at 72 dpi in greyscale. A pixel counts as changed when it
  differs by at least ``MIN_PIXEL_DELTA`` of 255, so near-white text on
  white is unseen. Visible-but-illegible text (a 1 pt font) does change
  pixels and is left to the size-based checks.
* Text drawn on top of other text is settled one operator at a time,
  up to ``MAX_OVERLAP_OPS`` operators per file; any beyond that are
  disclosed as unchecked.
* A renderer is one reader. Another viewer may draw a malformed file
  differently; this check speaks for MuPDF.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import Final

MAX_PAGES: Final[int] = 40
MIN_PIXEL_DELTA: Final[int] = 24
MIN_CHANGED_PIXELS: Final[int] = 2
# Where an extracted span sits on top of another, the pixels under it
# change when *all* text is removed whether or not it drew any of them.
# Those spans are settled by removing one text operator at a time.
OVERLAP_SHARE: Final[float] = 0.05
MAX_OVERLAP_OPS: Final[int] = 60
_TEXT_SHOW_OPS: Final[frozenset[str]] = frozenset({"Tj", "TJ", "'", '"'})


@dataclass(frozen=True)
class Span:
    page_index: int
    text: str
    bbox: tuple[float, float, float, float]
    changed_pixels: int

    @property
    def seen(self) -> bool:
        return self.changed_pixels >= MIN_CHANGED_PIXELS


@dataclass(frozen=True)
class OracleResult:
    spans: tuple[Span, ...]
    pages_checked: int
    pages_total: int
    overlap_ops_unchecked: int = 0

    @property
    def unseen(self) -> tuple[Span, ...]:
        return tuple(s for s in self.spans if not s.seen)

    @property
    def seen(self) -> tuple[Span, ...]:
        return tuple(s for s in self.spans if s.seen)


def _without_text(data: bytes, pages: int) -> bytes:
    """A copy of the PDF with every text-showing operator removed from the
    first ``pages`` pages' content streams. Everything else is kept, so
    the graphics state, images and vector art render exactly as before."""
    import pikepdf

    with pikepdf.open(io.BytesIO(data)) as pdf:
        for page in list(pdf.pages)[:pages]:
            kept = [
                (operands, op)
                for operands, op in pikepdf.parse_content_stream(page)
                if str(op) not in _TEXT_SHOW_OPS
            ]
            page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(kept))
        out = io.BytesIO()
        pdf.save(out)
        return out.getvalue()


def _has_glyphs(text: str) -> bool:
    """Whether ``text`` contains anything that is supposed to draw ink.
    Control characters and spaces are extracted as text by some
    producers (tab leaders, layout markers) and never paint."""
    return any(c.isprintable() and not c.isspace() for c in text)


def _changed(a, b, rect) -> int:
    """Pixels in ``rect`` that differ by MIN_PIXEL_DELTA or more between
    two same-size greyscale pixmaps."""
    x0 = max(0, int(rect[0]) - 1)
    y0 = max(0, int(rect[1]) - 1)
    x1 = min(a.width, int(rect[2]) + 2)
    y1 = min(a.height, int(rect[3]) + 2)
    if x1 <= x0 or y1 <= y0:
        return 0
    sa, sb, stride = a.samples, b.samples, a.stride
    n = 0
    for y in range(y0, y1):
        ra = sa[y * stride + x0: y * stride + x1]
        rb = sb[y * stride + x0: y * stride + x1]
        if ra != rb:
            n += sum(1 for p, q in zip(ra, rb) if abs(p - q) >= MIN_PIXEL_DELTA)
    return n


def examine_pdf(file_path: Path | str, max_pages: int = MAX_PAGES) -> OracleResult:
    """Classify every extracted on-page span as seen or unseen."""
    try:
        import pymupdf as fitz
    except ImportError:  # older PyMuPDF
        import fitz

    data = Path(file_path).read_bytes()
    with fitz.open(stream=data, filetype="pdf") as doc:
        total = doc.page_count
        pages = min(total, max_pages)
        with fitz.open(stream=_without_text(data, pages), filetype="pdf") as bare:
            spans: list[Span] = []
            for i in range(pages):
                page = doc[i]
                blocks = page.get_text("dict").get("blocks", [])
                found = [
                    (span["text"], tuple(span["bbox"]))
                    for block in blocks for line in block.get("lines", [])
                    for span in line.get("spans", [])
                    if _has_glyphs(span.get("text", ""))
                ]
                if not found:
                    continue
                pa = page.get_pixmap(colorspace=fitz.csGRAY, alpha=False)
                pb = bare[i].get_pixmap(colorspace=fitz.csGRAY, alpha=False)
                for text, bbox in found:
                    spans.append(Span(i, text, bbox, _changed(pa, pb, bbox)))
            # Second source of spans. An extractor that honours clipping
            # (MuPDF) returns nothing for clipped text; one that does not
            # (pypdf) returns it. Runs the content-stream walker places on
            # the page, which the first extractor did not return, are
            # tested at their estimated position.
            try:
                from analyzers.pdf_content_stream_text import walk_pdf
                runs = [r for r in walk_pdf(Path(file_path))
                        if not r.off_page and _has_glyphs(r.text)
                        and r.page_index < pages]
            except Exception:
                runs = []
            if runs:
                have: dict[int, str] = {}
                for sp in spans:
                    have[sp.page_index] = have.get(sp.page_index, "") + " " + sp.text
                pix: dict[int, tuple] = {}
                for r in runs:
                    if r.text.strip()[:16] in have.get(r.page_index, ""):
                        continue
                    if r.page_index not in pix:
                        pg = doc[r.page_index]
                        pix[r.page_index] = (
                            pg.get_pixmap(colorspace=fitz.csGRAY, alpha=False),
                            bare[r.page_index].get_pixmap(
                                colorspace=fitz.csGRAY, alpha=False),
                            pg.rect.height)
                    pa, pb, height = pix[r.page_index]
                    size = max(r.font_size, 1.0)
                    bbox = (r.x, height - r.y - 0.9 * size,
                            r.x + 0.6 * size * len(r.text), height - r.y + 0.3 * size)
                    spans.append(Span(r.page_index, r.text, bbox,
                                      _changed(pa, pb, bbox)))
            unchecked = _resolve_overlaps(data, doc, spans, pages)
    return OracleResult(tuple(spans), pages, total, unchecked)


_MIN_PROBE: Final[int] = 4


def _same_text(run_text: str, span_text: str) -> bool:
    """Whether a content-stream run and an extracted span are the same
    text: one begins with at least ``_MIN_PROBE`` characters of the
    other. Deliberately strict; an unmatched run changes nothing."""
    a, b = run_text.strip(), span_text.strip()
    if len(a) < _MIN_PROBE or len(b) < _MIN_PROBE:
        return False
    return a.startswith(b[:12]) or b.startswith(a[:12])


def _overlap(a, b) -> float:
    """Intersection area as a share of the smaller box."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0:
        return 0.0
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
    return (w * h) / small if small > 0 else 0.0


def _resolve_overlaps(data: bytes, doc, spans: list, pages: int) -> int:
    """Settle spans that overlap another span: remove one text-showing
    operator at a time and see whether the page changes at all. Spans
    are corrected in place. Returns the number of operators left
    unchecked because of ``MAX_OVERLAP_OPS``."""
    import pikepdf

    try:
        import pymupdf as fitz
    except ImportError:  # older PyMuPDF
        import fitz
    from analyzers.pdf_content_stream_text import walk_page

    by_page: dict[int, list[int]] = {}
    for i, s in enumerate(spans):
        if s.seen:
            by_page.setdefault(s.page_index, []).append(i)
    ambiguous: dict[int, set[int]] = {}
    for page_index, idxs in by_page.items():
        for a in idxs:
            for b in idxs:
                if a < b and _overlap(spans[a].bbox, spans[b].bbox) >= OVERLAP_SHARE:
                    ambiguous.setdefault(page_index, set()).update((a, b))
    if not ambiguous:
        return 0
    unchecked = 0
    budget = MAX_OVERLAP_OPS
    with pikepdf.open(io.BytesIO(data)) as pdf:
        for page_index, idxs in sorted(ambiguous.items()):
            page = pdf.pages[page_index]
            try:
                instructions = list(pikepdf.parse_content_stream(page))
                runs = [r for r in walk_page(page, page_index)
                        if not r.off_page and _has_glyphs(r.text)
                        and 0 <= r.operator_index < len(instructions)
                        and str(instructions[r.operator_index][1]) in _TEXT_SHOW_OPS]
            except Exception:
                continue
            # Only operators whose text belongs to an ambiguous span.
            # A full stop moves one pixel at 72 dpi, so short runs cannot
            # be judged this way and are left as the first pass found them.
            wanted = [r for r in runs
                      if len(r.text.strip()) >= _MIN_PROBE
                      and any(_same_text(r.text, spans[i].text) for i in idxs)]
            base = doc[page_index].get_pixmap(colorspace=fitz.csGRAY, alpha=False)
            whole = (0, 0, base.width, base.height)
            for run in wanted:
                if budget <= 0:
                    unchecked += 1
                    continue
                budget -= 1
                single = pikepdf.new()
                single.pages.append(page)
                kept = [ins for k, ins in enumerate(instructions)
                        if k != run.operator_index]
                single.pages[0].Contents = single.make_stream(
                    pikepdf.unparse_content_stream(kept))
                buf = io.BytesIO()
                single.save(buf)
                single.close()
                with fitz.open(stream=buf.getvalue(), filetype="pdf") as variant:
                    pix = variant[0].get_pixmap(colorspace=fitz.csGRAY, alpha=False)
                if (pix.width, pix.height) != (base.width, base.height):
                    continue
                if _changed(base, pix, whole) >= MIN_CHANGED_PIXELS:
                    continue  # this operator drew something a reader sees
                for i in idxs:
                    if _same_text(run.text, spans[i].text):
                        spans[i] = Span(spans[i].page_index, spans[i].text,
                                        spans[i].bbox, 0)
    return unchecked


def visible_text(file_path: Path | str, max_pages: int = MAX_PAGES) -> str:
    """The text a reader of the rendered pages could see, page by page."""
    result = examine_pdf(file_path, max_pages)
    out: list[str] = []
    for i in range(result.pages_checked):
        lines = [s.text for s in result.spans if s.page_index == i and s.seen]
        out.append("\n".join(lines))
    return "\n\f\n".join(out)


_PREVIEW = 600


def detect_text_not_rendered(file_path: Path | str, existing=()) -> list:
    """``pdf_text_not_rendered`` findings: one per page whose extracted
    text includes spans that leave no mark on the rendered page.

    Spans another finding already quotes are left to that finding, so
    one hidden line is not counted twice. Pages beyond ``MAX_PAGES`` are
    disclosed as unchecked.
    """
    from domain import Finding
    from domain.config import TIER
    from domain.outcomes import note_disclosure

    result = examine_pdf(file_path)
    if result.pages_total > result.pages_checked:
        note_disclosure(
            "pages_not_render_checked",
            result.pages_total - result.pages_checked,
            f"Pages {result.pages_checked + 1} to {result.pages_total} were "
            "not compared against their rendering (page limit). Hidden text "
            "on those pages is caught only by the mechanism-specific checks.",
        )
    if result.overlap_ops_unchecked:
        note_disclosure(
            "overlapping_text_not_fully_checked", result.overlap_ops_unchecked,
            f"{result.overlap_ops_unchecked} text operator(s) drawn over other "
            "text were not individually render-checked (limit reached). Text "
            "hidden on top of visible text may be unreported on those pages.",
        )
    quoted = " ".join(
        f"{getattr(f, 'concealed', '')} {getattr(f, 'description', '')}"
        for f in existing)
    by_page: dict[int, list[Span]] = {}
    for span in result.unseen:
        probe = span.text.strip()[:16]
        if probe and probe in quoted:
            continue
        by_page.setdefault(span.page_index, []).append(span)
    findings = []
    for page_index, spans in sorted(by_page.items()):
        text = " ".join(s.text.strip() for s in spans)
        clipped = text if len(text) <= _PREVIEW else text[:_PREVIEW] + "..."
        findings.append(Finding(
            mechanism="pdf_text_not_rendered",
            tier=TIER["pdf_text_not_rendered"],
            confidence=0.9,
            description=(
                f"{len(spans)} text span(s) on this page are returned by "
                "text extraction but leave no visible mark when the page is "
                "rendered. Removing them changes nothing a reader could see. "
                "The cause is not named because it does not matter: fill "
                "colour, transparency, clipping, an object drawn on top, or "
                "scale all produce the same result."
            ),
            location=f"page {page_index + 1}",
            surface="(nothing rendered at this text's position)",
            concealed=f"recovered text: {clipped!r}",
        ))
    return findings


__all__ = ["MAX_PAGES", "OracleResult", "Span", "detect_text_not_rendered",
           "examine_pdf", "visible_text"]
