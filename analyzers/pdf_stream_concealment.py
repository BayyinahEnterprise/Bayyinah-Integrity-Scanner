"""
Concealed-text detector built on the content-stream walker.

Adds two things the span-based checks cannot see:

1. Off-page text positioned with any operator (``Td``, ``TD``, ``T*``,
   ``'``, ``"``, ``Tm``, or a ``cm`` transform), not only ``Tm``. Emitted as
   the existing ``pdf_off_page_text`` mechanism (Tier 1), one finding per
   page, with the recovered text joined in reading order. Pages already
   reported by the ``Tm``-only detector are skipped by the caller.

2. Sub-legible text: on-page text whose effective size is at least the
   Tier 1 microscopic threshold (1.0 pt) but below ``SUBLEGIBLE_FONT_PT``.
   Text this small cannot be read on screen or in print without
   magnification, yet every text extractor returns it. Emitted as the
   existing ``microscopic_font`` mechanism at Tier 2 (structural; context
   may justify), because legitimate microprint and scaled-down vector
   figures do occur. Text below 1.0 pt stays with the existing Tier 1 check.

No new mechanism names are introduced, so the registry is unchanged.

Found by running the scanner against the CrackedPDFs benchmark
(arXiv:2607.19396), where it missed text placed with ``Td`` at
(10000, 10000) and all text at 1.2 pt and 2.0 pt.
"""
from __future__ import annotations

from pathlib import Path

from analyzers.pdf_content_stream_text import TextRun, join_runs, walk_pdf
from domain.config import MICROSCOPIC_FONT_THRESHOLD
from domain.finding import Finding

# Upper bound of the sub-legible band, in points. 2.5 pt is under 0.9 mm of
# glyph height; body text is rarely set below 5 pt.
SUBLEGIBLE_FONT_PT = 2.5
_PREVIEW_LIMIT = 600


def _preview(text: str) -> str:
    return text if len(text) <= _PREVIEW_LIMIT else text[:_PREVIEW_LIMIT] + "..."


def detect_pdf_stream_concealment(
    file_path: Path, skip_off_page_pages: frozenset[int] = frozenset(),
) -> list[Finding]:
    """Return off-page and sub-legible text findings for a PDF.

    ``skip_off_page_pages`` holds zero-based page indices for which another
    detector has already reported off-page text.
    """
    runs = walk_pdf(file_path)
    by_page: dict[int, list[TextRun]] = {}
    for r in runs:
        by_page.setdefault(r.page_index, []).append(r)

    findings: list[Finding] = []
    for page_idx in sorted(by_page):
        page_runs = by_page[page_idx]
        off = [r for r in page_runs if r.off_page and r.text.strip()]
        if off and page_idx not in skip_off_page_pages:
            xs = [r.x for r in off]; ys = [r.y for r in off]
            findings.append(Finding(
                mechanism="pdf_off_page_text",
                tier=1,
                confidence=1.0,
                description=(
                    f"{len(off)} text run(s) are positioned outside the page "
                    f"MediaBox (origins from ({min(xs):.1f}, {min(ys):.1f}) to "
                    f"({max(xs):.1f}, {max(ys):.1f})). The bytes are present in "
                    f"the content stream and are returned by text extractors; "
                    f"no rendering of the page shows them."
                ),
                location=f"page {page_idx + 1}",
                surface="(outside the visible page)",
                concealed=f"recovered text: {_preview(join_runs(off))!r}",
            ))
        small = [
            r for r in page_runs
            if not r.off_page and r.render_mode != 3 and r.text.strip()
            and MICROSCOPIC_FONT_THRESHOLD <= r.font_size < SUBLEGIBLE_FONT_PT
        ]
        if small:
            sizes = sorted({round(r.font_size, 2) for r in small})
            findings.append(Finding(
                mechanism="microscopic_font",
                tier=2,
                confidence=0.6,
                description=(
                    f"{len(small)} text run(s) are set at {sizes[0]}-{sizes[-1]} pt, "
                    f"below the {SUBLEGIBLE_FONT_PT} pt legibility floor but at or "
                    f"above the {MICROSCOPIC_FONT_THRESHOLD} pt Tier 1 threshold. "
                    f"Unreadable without magnification; returned in full by text "
                    f"extractors. Legitimate microprint and scaled figures can "
                    f"produce this."
                ),
                location=f"page {page_idx + 1}",
                surface=f"(sub-legible at {sizes[0]}-{sizes[-1]} pt)",
                concealed=f"recovered text: {_preview(join_runs(small))!r}",
            ))
    return findings


def concealed_stream_text(file_path: Path) -> str:
    """Full text of every run a reader cannot see (off-page, invisible render
    mode, or below the legibility floor), joined in content-stream order.

    Findings carry a bounded preview for display; an assessment of what the
    hidden text says needs all of it, so this reads the file again.
    """
    hidden = [
        r for r in walk_pdf(file_path)
        if r.text.strip() and (r.off_page or r.render_mode == 3 or 0 < r.font_size < SUBLEGIBLE_FONT_PT)
    ]
    return join_runs(hidden)


def assess_pdf(file_path: Path, findings=()):
    """Second-stage assessment for a PDF: is the concealed text instruction-like?

    Combines the complete stream-level concealed text with the concealed text
    carried by ``findings`` (white-on-white spans and other mechanisms the
    stream walk does not classify). Returns an ``Assessment``. Interpretive
    (Tier 3); see analyzers/concealed_instruction.py for what it can miss.
    """
    from analyzers.concealed_instruction import (
        assess, assess_acrostic, concealed_text_of,
    )
    stream_text = concealed_stream_text(file_path)
    other = concealed_text_of(
        f for f in findings
        if getattr(f, "mechanism", None) not in ("pdf_off_page_text", "microscopic_font", "invisible_render_mode")
    )
    text = (stream_text + " " + other).strip()
    direct = assess(text)
    if direct.instruction_like:
        return direct
    hidden = assess_acrostic(stream_text)
    return hidden if hidden.instruction_like else direct


__all__ = ["detect_pdf_stream_concealment", "concealed_stream_text", "assess_pdf", "SUBLEGIBLE_FONT_PT"]
