"""
ZahirTextAnalyzer — the witness for the outward layer (Al-Baqarah 2:9-10).

    يُخَادِعُونَ اللَّهَ وَالَّذِينَ آمَنُوا وَمَا يَخْدَعُونَ إِلَّا أَنفُسَهُمْ وَمَا يَشْعُرُونَ
    فِي قُلُوبِهِم مَّرَضٌ فَزَادَهُمُ اللَّهُ مَرَضًا

    "They seek to deceive Allah and those who believe, but they deceive
    no one except themselves, and they perceive it not. In their hearts
    is a disease, and Allah has increased their disease."

The architectural reading: the munafiq's tongue says one thing and his
heart carries another. The zahir layer is the tongue of the document —
the rendered text, the characters the extractor pulls, the positions
the renderer paints. The ZahirTextAnalyzer reads that tongue.

It asks, for each page and each span: does what the reader perceives
match what the text layer carries? If the bytes encode a payload that
the rendering swallows — zero-width punctuation between every letter,
Unicode TAG characters below ASCII, a render-mode-3 "invisible" stanza,
a microscopic font no eye can read, a white glyph on a white page, a
later-drawn span overlaying an earlier one with different words — then
the gap between what is *shown* and what is *contained* is a zahir
concealment. This analyzer surfaces each such gap, attributes it to
its page and bounding box, and records the inversion-recovery pair.

This file is a port of ``bayyinah_v0_1.TextLayerAnalyzer``. Semantics
are byte-identical per mechanism (findings carry the same mechanism
names, tiers, confidence, descriptions, surface/concealed pairs) — the
Phase 0 fixture tests verify this. The deltas from v0.1 are structural:

  * Consumes ``infrastructure.PDFClient`` (not ``bayyinah_v0_1.PDFContext``)
  * Returns ``domain.IntegrityReport`` (not ``list[Finding]``) via the
    ``analyzers.base.BaseAnalyzer`` contract
  * Emits ``domain.Finding`` objects whose ``source_layer='zahir'`` is
    inferred from the mechanism name
  * A top-level parser failure yields a ``scan_error`` report via the
    inherited ``_scan_error_report`` helper, preserving v0.1's
    "Text layer scan error: <msg>" wording

Additive-only: bayyinah_v0_1.TextLayerAnalyzer is unchanged and still
used by v0.1's ScanService. The two analyzers coexist until a later
phase migrates the default pipeline.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, ClassVar

from analyzers.base import BaseAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    compute_muwazana_score,
    get_current_content_index,
)
from domain.config import (
    BACKGROUND_LUMINANCE_WHITE,
    BIDI_CONTROL_CHARS,
    COLOR_CONTRAST_THRESHOLD,
    CONFUSABLE_TO_LATIN,
    INVISIBLE_RENDER_MODE,
    MICROSCOPIC_FONT_THRESHOLD,
    SPAN_OVERLAP_THRESHOLD,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from domain.exceptions import PDFParseError
from infrastructure.pdf_client import PDFClient


# ---------------------------------------------------------------------------
# v1.1.4 — _RectShim: tuple-backed stand-in for a pymupdf Rect.
#
# Exposes ``.x0`` / ``.y0`` / ``.x1`` / ``.y1`` plus tuple unpacking and
# integer indexing, so existing helpers that read ``page_rect.x0`` or
# ``rect.x0, rect.y0, rect.x1, rect.y1`` work unchanged on rectangle
# data extracted from the ContentIndex (where rectangles are stored as
# plain float tuples for hashability and serialization).
# ---------------------------------------------------------------------------

class _RectShim:
    """Minimal stand-in for ``pymupdf.Rect`` over a 4-tuple.

    Lets existing detection code that branches on ``rect.x0`` style
    attribute access work without a type check when the rectangle
    came from the index instead of from a live pymupdf page.
    """
    __slots__ = ("x0", "y0", "x1", "y1")

    def __init__(self, x0: float, y0: float, x1: float, y1: float) -> None:
        self.x0 = x0
        self.y0 = y0
        self.x1 = x1
        self.y1 = y1

    def __iter__(self):  # pragma: no cover - covered via _check_offpage path
        yield self.x0
        yield self.y0
        yield self.x1
        yield self.y1

    def __getitem__(self, idx: int) -> float:  # pragma: no cover
        return (self.x0, self.y0, self.x1, self.y1)[idx]


# ---------------------------------------------------------------------------
# v1.1.5 spatial pre-filter for overlapping_text.
#
# The naive overlapping-spans scan is O(n^2) IoU calls over every pair
# of spans on a page. On dense documents (220-page reports with ~100
# spans per page) this dominates the per-document cost.
#
# This helper buckets spans into a uniform grid sized to the median
# span width and height. A pair of spans whose bounding boxes overlap
# by any positive area must occupy at least one common cell, so
# limiting candidate pairs to co-cellular spans cannot drop a true
# positive. The IoU predicate downstream re-checks each candidate;
# false positives in candidate generation are filtered there. The
# observable behaviour of `_scan_overlapping_spans` is unchanged.
#
# Implementation choice: stdlib only. The wider scanner refuses to
# pull in libspatialindex (rtree) for the same attack-surface reason
# the rest of the dependency block is kept minimal. A uniform grid
# matches an R-tree's asymptotic complexity on roughly uniformly
# sized boxes (text spans on a page) and ships in pure Python.
# ---------------------------------------------------------------------------

def _overlapping_pair_candidates(
    spans: list[tuple[tuple[float, float, float, float], str]],
):
    """Yield (i, j) index pairs that may overlap by IoU >= threshold.

    The grid cell size is the median span width / height (floored at
    1.0 to defend against degenerate page layouts). Each span is
    indexed under every cell its bounding box touches; pairs are
    enumerated per cell and de-duplicated across cells. The caller is
    expected to confirm each candidate with the IoU predicate.

    On a page with n spans this generates O(n) work to build the grid
    plus work proportional to the number of overlapping cell
    occupants, which on a real document is dominated by the small
    constant of glyphs that share neighborhoods rather than by n^2.
    """
    n = len(spans)
    if n < 2:
        return

    # Pick cell size from median span dimensions. Median is robust to
    # the occasional very wide or very tall span (table cells, headers).
    widths = sorted(b[2] - b[0] for b, _ in spans)
    heights = sorted(b[3] - b[1] for b, _ in spans)
    cell_w = max(widths[n // 2], 1.0)
    cell_h = max(heights[n // 2], 1.0)

    grid: dict[tuple[int, int], list[int]] = {}
    for i, (b, _) in enumerate(spans):
        gx_lo = int(b[0] // cell_w)
        gx_hi = int(b[2] // cell_w)
        gy_lo = int(b[1] // cell_h)
        gy_hi = int(b[3] // cell_h)
        for gx in range(gx_lo, gx_hi + 1):
            for gy in range(gy_lo, gy_hi + 1):
                grid.setdefault((gx, gy), []).append(i)

    seen: set[tuple[int, int]] = set()
    for occupants in grid.values():
        if len(occupants) < 2:
            continue
        m = len(occupants)
        for ii in range(m):
            for jj in range(ii + 1, m):
                a = occupants[ii]
                b = occupants[jj]
                if a > b:
                    a, b = b, a
                key = (a, b)
                if key in seen:
                    continue
                seen.add(key)
                yield key


# ---------------------------------------------------------------------------
# ZahirTextAnalyzer
# ---------------------------------------------------------------------------

class ZahirTextAnalyzer(BaseAnalyzer):
    """Detects concealment at the rendered-text (zahir) layer of a PDF.

    Mechanisms emitted (all ``source_layer='zahir'``):

        invisible_render_mode
            Content-stream ``3 Tr`` operator — glyphs advanced but not
            painted. Concealed text is recovered from ``Tj`` / ``TJ``
            operators inside the invisible region.

        white_on_white_text
            Span whose fill colour matches page-background luminance,
            with no dark fill drawn behind it.

        microscopic_font
            Span whose font size is below the sub-visual threshold.

        off_page_text
            Span positioned outside the page MediaBox.

        zero_width_chars / bidi_control / tag_chars
            Unicode smuggling vectors. Emitted from both the span-text
            view (what the extractor returns) and the raw content
            stream (literal and hex strings, including /ActualText).
            Per-page de-duplication is done inside ``scan``.

        overlapping_text
            Two spans with the same page whose bounding boxes share
            at least ``SPAN_OVERLAP_THRESHOLD`` IoU and whose text
            differs — later-drawn occludes the earlier visually while
            both survive in the text layer.

        homoglyph
            Word containing non-Latin codepoints that visually
            impersonate Latin letters, where the word also contains
            plain Latin or has ≥2 confusables.
    """

    name: ClassVar[str] = "text_layer"
    error_prefix: ClassVar[str] = "Text layer scan error"
    source_layer: ClassVar[SourceLayer] = "zahir"

    # ------------------------------------------------------------------
    # Public contract
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:
        """Scan ``file_path`` for zahir-layer concealment mechanisms.

        Flow:
          1. Open a PDFClient on ``file_path``; if pymupdf cannot parse,
             emit a scan_error report (tier 3, non-deducting) and mark
             scan_incomplete. This preserves v0.1's treatment of
             unreadable PDFs at the text-layer layer of abstraction.
          2. Iterate pages. Per page, run render-mode, span-level,
             raw-unicode, and overlapping-span scans. Per-page failures
             are swallowed (they degrade that page's coverage, not the
             whole scan) — the same defensive behaviour v0.1 has.
          3. Assemble findings into an IntegrityReport; recompute the
             per-analyzer score via ``compute_muwazana_score`` (advisory
             at this level — the registry recomputes at merge time).
        """
        file_path = Path(file_path)

        client = PDFClient(file_path)
        try:
            try:
                doc = client.fitz
            except PDFParseError as exc:
                # Parser couldn't open the file. Emit the canonical
                # scan_error report — non-deducting, scan_incomplete=True.
                return self._scan_error_report(file_path, str(exc))

            findings: list[Finding] = []
            for page_idx in range(len(doc)):
                page = doc[page_idx]
                # Each helper is responsible for its own defensive
                # try/except — a per-page parser failure must not
                # abort the whole scan. This mirrors v0.1's behaviour
                # exactly; the failure becomes "no findings for this
                # helper on this page", not a scan_error.
                findings.extend(self._scan_render_modes(page, page_idx))
                span_findings = self._scan_spans(page, page_idx)
                findings.extend(span_findings)
                # Raw-stream unicode scan de-duplicates against span-
                # level hits so the same ZWSP/bidi/tag payload is not
                # double-reported for the same page.
                span_unicode_mechs = {
                    f.mechanism for f in span_findings
                    if f.mechanism in (
                        "zero_width_chars", "bidi_control", "tag_chars",
                    )
                }
                findings.extend(
                    self._scan_raw_unicode(page, page_idx, span_unicode_mechs)
                )
                findings.extend(self._scan_overlapping_spans(page, page_idx))

            # v1.1.2 Day 2 mechanism 03 - parallel pass to off_page_text
            # that reads the raw PDF content stream via pikepdf instead
            # of relying on PyMuPDF's get_text('dict'), which silently
            # drops spans whose origin is outside the page rectangle.
            # Classifies as zahir alongside off_page_text: the structural
            # signal (Tm origin coordinate vs. MediaBox) is observable
            # from the content stream's text-rendering operators with
            # no hidden-state inference. Local import to keep the
            # module head untouched; the detector opens its own
            # pikepdf handle and is independent of the pymupdf doc
            # used above. Closes pdf_gauntlet fixture 03_off_page.pdf.
            from analyzers.pdf_off_page_text import detect_pdf_off_page_text
            findings.extend(detect_pdf_off_page_text(file_path))

            report = IntegrityReport(
                file_path=str(file_path),
                integrity_score=compute_muwazana_score(findings),
                findings=findings,
            )
            return report
        finally:
            client.close()

    # ==================================================================
    # Mechanism 1: invisible render mode (content-stream 3 Tr)
    # ==================================================================

    def _scan_render_modes(self, page: Any, page_idx: int) -> list[Finding]:
        """Detect text rendered with PDF render mode 3 (invisible).

        Walks the content stream, tracks the current ``Tr`` (text
        rendering mode) operator, and emits an ``invisible_render_mode``
        finding for every ``Tj`` / ``TJ`` operand drawn while mode 3 is
        active. Mode 3 means "neither fill nor stroke" — the glyphs are
        present in the text layer but invisible on the rendered page.

        Page-parse failures degrade silently (return empty) rather than
        aborting the whole scan — consistent with every other page-level
        helper in this analyzer.
        """
        findings: list[Finding] = []
        try:
            raw = page.read_contents()
            if not raw:
                return findings
            stream = raw.decode("latin-1", errors="ignore")
        except Exception:  # noqa: BLE001 — page-parse failure is degradation, not abort
            return findings

        # Strip literal strings so a "(3 Tr)" inside a legitimate string
        # literal does not false-positive. Hex strings are stripped too.
        stripped = self._strip_literal_strings(stream)
        tr_matches = list(re.finditer(r"(?<![A-Za-z0-9_])(\d+)\s+Tr\b", stripped))
        if not tr_matches:
            return findings

        # Build the sequence of regions by render mode. Mode 0 is the
        # default; each Tr operator switches mode from *that point on*.
        regions: list[tuple[int, int, int]] = []
        mode = 0
        mode_start = 0
        for m in tr_matches:
            new_mode = int(m.group(1))
            regions.append((mode_start, m.start(), mode))
            mode = new_mode
            mode_start = m.end()
        regions.append((mode_start, len(stripped), mode))

        invisible_regions = [
            (s, e) for (s, e, m) in regions
            if m == INVISIBLE_RENDER_MODE and e > s
        ]
        if not invisible_regions:
            return findings

        for (start, end) in invisible_regions:
            segment = stream[start:end]
            concealed = self._extract_tj_strings(segment)
            if concealed:
                concealed_preview = concealed[:500]
                findings.append(Finding(
                    mechanism="invisible_render_mode",
                    tier=TIER["invisible_render_mode"],
                    confidence=0.95,
                    description=(
                        f"Text rendered with render mode 3 (invisible). "
                        f"{len(concealed)} character(s) of hidden text extracted."
                    ),
                    location=f"page {page_idx + 1}",
                    surface="(nothing visible at this location)",
                    concealed=concealed_preview,
                ))
            else:
                # Capability-only variant: render-mode-3 armed but no
                # text drawn (OCR-noise false-positive reducer). Down-
                # tier to 3, low confidence, zero severity override.
                findings.append(Finding(
                    mechanism="invisible_render_mode",
                    tier=3,
                    confidence=0.6,
                    description=(
                        "Content stream activates text render mode 3 (invisible) "
                        "but no text-drawing operators were found in the region. "
                        "Concealment capability present without payload."
                    ),
                    location=f"page {page_idx + 1}",
                    surface="(nothing visible)",
                    concealed="(capability only; no text drawn)",
                    severity_override=0.05,
                ))
        return findings

    # ------------------------------------------------------------------
    # Content-stream string helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_literal_strings(s: str) -> str:
        """Replace every ``(...)`` literal and every ``<...>`` hex string
        with spaces, preserving offsets. Escaped parens inside literals
        are handled correctly.
        """
        out = list(s)
        n = len(s)
        i = 0
        while i < n:
            c = s[i]
            if c == "(":
                depth = 1
                j = i + 1
                while j < n and depth > 0:
                    if s[j] == "\\" and j + 1 < n:
                        j += 2
                        continue
                    if s[j] == "(":
                        depth += 1
                    elif s[j] == ")":
                        depth -= 1
                    j += 1
                for k in range(i, min(j, n)):
                    out[k] = " "
                i = j
            elif c == "<":
                j = i + 1
                while j < n and s[j] != ">":
                    j += 1
                for k in range(i, min(j + 1, n)):
                    out[k] = " "
                i = j + 1
            else:
                i += 1
        return "".join(out)

    @classmethod
    def _extract_tj_strings(cls, segment: str) -> str:
        """Pull concealed text out of ``(...) Tj`` and ``[...] TJ``
        operators inside an invisible-render-mode region."""
        pieces: list[str] = []
        for m in re.finditer(r"\((.*?)(?<!\\)\)\s*Tj", segment, re.DOTALL):
            pieces.append(cls._decode_pdf_literal(m.group(1)))
        for m in re.finditer(r"\[(.*?)\]\s*TJ", segment, re.DOTALL):
            arr = m.group(1)
            for lit in re.finditer(r"\((.*?)(?<!\\)\)", arr, re.DOTALL):
                pieces.append(cls._decode_pdf_literal(lit.group(1)))
        return "".join(pieces)

    @staticmethod
    def _decode_pdf_literal(s: str) -> str:
        """Decode a PDF string literal, handling octal and standard escapes."""
        s = re.sub(
            r"\\([0-7]{1,3})",
            lambda m: chr(int(m.group(1), 8)),
            s,
        )
        s = (
            s.replace(r"\n", "\n")
             .replace(r"\r", "\r")
             .replace(r"\t", "\t")
             .replace(r"\b", "\b")
             .replace(r"\f", "\f")
             .replace(r"\(", "(")
             .replace(r"\)", ")")
             .replace(r"\\", "\\")
        )
        return s

    @staticmethod
    def _decode_hex_text(hex_blob: str, prefer_utf16be: bool = False) -> str:
        """Decode a ``<...>`` hex string. UTF-16BE preferred when the
        blob looks like one (BOM or caller signals /ActualText)."""
        h = re.sub(r"\s+", "", hex_blob)
        if not h:
            return ""
        if len(h) % 2 != 0:
            h += "0"
        try:
            data = bytes.fromhex(h)
        except ValueError:
            return ""
        if len(data) >= 2 and data[:2] == b"\xfe\xff" and len(data) % 2 == 0:
            try:
                return data[2:].decode("utf-16-be", errors="replace")
            except Exception:  # noqa: BLE001
                pass
        if prefer_utf16be and len(data) >= 2 and len(data) % 2 == 0:
            try:
                return data.decode("utf-16-be", errors="replace")
            except Exception:  # noqa: BLE001
                pass
        return data.decode("latin-1", errors="ignore")

    # ==================================================================
    # Mechanism 2: overlapping / stacked text spans
    # ==================================================================

    def _scan_overlapping_spans(self, page: Any, page_idx: int) -> list[Finding]:
        """Detect text spans whose bounding boxes overlap past the
        configured threshold but whose text content differs.

        A later-drawn span visually occludes the earlier one; both
        survive in the text layer. The concealment model: what a reader
        sees (top span) and what a text extractor reads (both spans)
        diverge. IoU (intersection-over-union) above
        ``SPAN_OVERLAP_THRESHOLD`` is the trigger.

        v1.1.4 — reads spans from the per-scan ContentIndex when one is
        installed, eliminating the second ``page.get_text("dict")`` call
        that previously fired on every PDF page (the first being in
        ``_scan_spans``). Falls back to the self-walk path when no index
        is available. Detection logic is unchanged.
        """
        # v1.1.4 — prefer the per-scan content index. Avoids the
        # repeated get_text("dict") call this method historically made
        # in addition to the one _scan_spans makes on the same page.
        idx = get_current_content_index()
        spans: list[tuple[tuple[float, float, float, float], str]] = []

        if (
            idx is not None
            and not idx.build_failed
            and page_idx in idx.spans_by_page
        ):
            for si in idx.spans_by_page[page_idx]:
                text = (si.text or "").strip()
                if not text:
                    continue
                bbox = si.bbox
                if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) <= 0:
                    continue
                spans.append((bbox, text))
        else:
            try:
                page_dict = page.get_text("dict")
            except Exception:  # noqa: BLE001
                return []
            for block in page_dict.get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = (span.get("text") or "").strip()
                        if not text:
                            continue
                        bbox = tuple(span.get("bbox", (0, 0, 0, 0)))
                        if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) <= 0:
                            continue
                        spans.append((bbox, text))

        if len(spans) < 2:
            return []

        # v1.1.5 spatial pre-filter. The naive scan was O(n^2) IoU calls
        # over every span pair on a page. _overlapping_pair_candidates
        # buckets spans into a uniform grid sized to the median span
        # dimensions; only spans sharing at least one cell are emitted
        # as candidate pairs. The IoU predicate below is unchanged, so
        # any pair the naive loop would have surfaced (IoU >= threshold)
        # is still surfaced: a pair whose bounding boxes intersect by
        # any positive area must share at least one grid cell. False
        # positives in candidate generation are filtered by the
        # existing IoU check.
        findings: list[Finding] = []
        seen_pairs: set[tuple[int, int]] = set()
        for i, j in _overlapping_pair_candidates(spans):
            b1, t1 = spans[i]
            b2, t2 = spans[j]
            iou = self._bbox_iou(b1, b2)
            if iou < SPAN_OVERLAP_THRESHOLD:
                continue
            if t1 == t2:
                continue
            pair_key = (id(t1) & 0xFFFF, id(t2) & 0xFFFF)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            findings.append(Finding(
                mechanism="overlapping_text",
                tier=TIER["overlapping_text"],
                confidence=0.75,
                description=(
                    f"Two text spans share {iou:.0%} of their bounding-box area "
                    "but contain different text. The later-drawn span "
                    "occludes the other visually; both survive in the text layer."
                ),
                location=f"page {page_idx + 1}, bbox {b1}",
                surface=t2[:200],
                concealed=t1[:200],
            ))
        return findings

    @staticmethod
    def _bbox_iou(a: tuple, b: tuple) -> float:
        """Bounding-box intersection-over-union."""
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        ox0, oy0 = max(ax0, bx0), max(ay0, by0)
        ox1, oy1 = min(ax1, bx1), min(ay1, by1)
        if ox1 <= ox0 or oy1 <= oy0:
            return 0.0
        inter = (ox1 - ox0) * (oy1 - oy0)
        area_a = max((ax1 - ax0) * (ay1 - ay0), 1e-9)
        area_b = max((bx1 - bx0) * (by1 - by0), 1e-9)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    # ==================================================================
    # Mechanism 3: raw-stream Unicode smuggling
    # ==================================================================

    def _scan_raw_unicode(
        self,
        page: Any,
        page_idx: int,
        skip_mechs: set[str] | None = None,
    ) -> list[Finding]:
        """Inspect the raw content stream for zero-width / bidi / TAG
        characters in ``/ActualText``, ``Tj``, and ``TJ`` operands.

        ``skip_mechs`` lists mechanism names that the span-level pass
        already emitted for this page — those are suppressed here to
        prevent double-reporting.
        """
        skip = skip_mechs or set()
        try:
            raw = page.read_contents()
            if not raw:
                return []
        except Exception:  # noqa: BLE001
            return []

        stream = raw.decode("latin-1", errors="ignore")

        zw_hits: list[tuple[str, str]] = []
        bidi_hits: list[tuple[str, str]] = []
        tag_hits: list[tuple[str, str]] = []

        def accumulate(decoded: str, source_label: str) -> None:
            """Triage a decoded stream fragment into zero-width / bidi /
            TAG-character buckets. Each bucket collects a ``(context,
            codepoints)`` pair per hit so the caller can emit one
            finding per bucket with representative evidence attached.
            """
            zw = [c for c in decoded if c in ZERO_WIDTH_CHARS]
            if zw:
                visible = decoded
                for c in ZERO_WIDTH_CHARS:
                    visible = visible.replace(c, "")
                zw_hits.append((
                    f"{source_label}: {visible[:120]}",
                    " | ".join(f"U+{ord(c):04X}" for c in zw[:24]) +
                    (" ..." if len(zw) > 24 else ""),
                ))
            bidi = [c for c in decoded if c in BIDI_CONTROL_CHARS]
            if bidi:
                bidi_hits.append((
                    f"{source_label}: {decoded[:120]}",
                    " | ".join(f"U+{ord(c):04X}" for c in bidi[:24]) +
                    (" ..." if len(bidi) > 24 else ""),
                ))
            tag = [c for c in decoded if ord(c) in TAG_CHAR_RANGE]
            if tag:
                decoded_ascii = "".join(
                    chr(ord(c) - 0xE0000) for c in tag
                    if 0xE0020 <= ord(c) <= 0xE007E
                )
                visible = re.sub(r"[\U000E0000-\U000E007F]", "", decoded)
                tag_hits.append((
                    f"{source_label}: {visible[:120]}",
                    " | ".join(f"U+{ord(c):06X}" for c in tag[:12]) +
                    (" ..." if len(tag) > 12 else "") +
                    (f"  decoded: {decoded_ascii!r}" if decoded_ascii else ""),
                ))

        # /ActualText literal
        for m in re.finditer(
            r"/ActualText\s*\((.*?)(?<!\\)\)", stream, re.DOTALL,
        ):
            body = self._decode_pdf_literal(m.group(1))
            accumulate(body, "/ActualText literal")
            try:
                body_utf8 = body.encode("latin-1").decode("utf-8")
                if body_utf8 != body:
                    accumulate(body_utf8, "/ActualText literal (utf-8)")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # /ActualText hex (UTF-16BE per PDF spec)
        for m in re.finditer(
            r"/ActualText\s*<([0-9A-Fa-f\s]+)>", stream,
        ):
            decoded = self._decode_hex_text(m.group(1), prefer_utf16be=True)
            if decoded:
                accumulate(decoded, "/ActualText hex")

        # Bare Tj / TJ hex strings
        for m in re.finditer(
            r"<([0-9A-Fa-f\s]+)>\s*T[jJ]", stream,
        ):
            decoded = self._decode_hex_text(m.group(1), prefer_utf16be=False)
            if decoded:
                accumulate(decoded, "hex text string")

        # TJ arrays — both hex fragments and literal fragments
        for m in re.finditer(r"\[(.*?)\]\s*TJ", stream, re.DOTALL):
            arr = m.group(1)
            for hm in re.finditer(r"<([0-9A-Fa-f\s]+)>", arr):
                decoded = self._decode_hex_text(hm.group(1), prefer_utf16be=False)
                if decoded:
                    accumulate(decoded, "TJ hex fragment")
            for lm in re.finditer(r"\((.*?)(?<!\\)\)", arr, re.DOTALL):
                body = self._decode_pdf_literal(lm.group(1))
                accumulate(body, "TJ literal fragment")
                try:
                    body_utf8 = body.encode("latin-1").decode("utf-8")
                    if body_utf8 != body:
                        accumulate(body_utf8, "TJ literal (utf-8)")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass

        # Bare Tj literal strings
        for m in re.finditer(
            r"\((.*?)(?<!\\)\)\s*Tj", stream, re.DOTALL,
        ):
            body = self._decode_pdf_literal(m.group(1))
            accumulate(body, "Tj literal")
            try:
                body_utf8 = body.encode("latin-1").decode("utf-8")
                if body_utf8 != body:
                    accumulate(body_utf8, "Tj literal (utf-8)")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        findings: list[Finding] = []
        if zw_hits and "zero_width_chars" not in skip:
            visible = "; ".join(v for v, _ in zw_hits)[:280]
            concealed = "; ".join(c for _, c in zw_hits)[:280]
            findings.append(Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.85,
                description=(
                    f"{len(zw_hits)} content-stream region(s) contain zero-width "
                    "character(s). These are not rendered but are preserved "
                    "through conforming text extraction."
                ),
                location=f"page {page_idx + 1}, raw content stream",
                surface=visible,
                concealed=concealed,
            ))
        if bidi_hits and "bidi_control" not in skip:
            visible = "; ".join(v for v, _ in bidi_hits)[:280]
            concealed = "; ".join(c for _, c in bidi_hits)[:280]
            findings.append(Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(bidi_hits)} content-stream region(s) contain "
                    "bidirectional control character(s). These can reorder "
                    "displayed text without changing its underlying byte order."
                ),
                location=f"page {page_idx + 1}, raw content stream",
                surface=visible,
                concealed=concealed,
            ))
        if tag_hits and "tag_chars" not in skip:
            visible = "; ".join(v for v, _ in tag_hits)[:280]
            concealed = "; ".join(c for _, c in tag_hits)[:280]
            findings.append(Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=0.99,
                description=(
                    f"{len(tag_hits)} content-stream region(s) contain Unicode "
                    "TAG character(s) (U+E0000-U+E007F). TAG characters do not "
                    "render but carry ASCII payloads preserved through text "
                    "extraction — a known prompt-injection vector."
                ),
                location=f"page {page_idx + 1}, raw content stream",
                surface=visible,
                concealed=concealed,
            ))
        return findings

    # ==================================================================
    # Mechanism 4: per-span physical / colour / unicode checks
    # ==================================================================

    def _scan_spans(self, page: Any, page_idx: int) -> list[Finding]:
        """Per-span pass: colour, size, position, and per-span Unicode.

        For each text span on the page this dispatches to four
        independent checks — ``_check_color`` (white-on-white),
        ``_check_size`` (microscopic font), ``_check_offpage`` (outside
        MediaBox), and ``_check_unicode`` (zero-width / bidi / TAG /
        homoglyph). The checks are independent so any combination can
        fire on a single span without mutual interference.

        v1.1.4 — reads spans from the per-scan ContentIndex when one is
        installed (built once by ScanService at the top of the PDF
        dispatch path). Falls back to ``page.get_text("dict")`` and
        ``page.get_drawings()`` self-walk when no index is available
        (tests that call this analyzer directly outside ScanService,
        or scans where the index build failed). Detection logic and
        finding construction are unchanged across the two paths.
        """
        findings: list[Finding] = []

        # v1.1.4 — prefer the per-scan content index when available.
        # When the index is present and built successfully, use its
        # pre-walked spans and drawings for this page. This eliminates
        # the per-mechanism page.get_text("dict") and page.get_drawings()
        # calls that dominate the cost on dense PDFs.
        idx = get_current_content_index()
        use_index = (
            idx is not None
            and not idx.build_failed
            and page_idx in idx.spans_by_page
        )

        if use_index:
            page_spans_idx = idx.spans_by_page[page_idx]
            page_drawings_idx = idx.drawings_by_page.get(page_idx, [])
            page_rect_tuple = idx.page_rects.get(page_idx)
            # Synthesize a minimal page-rect-shaped object so the
            # existing _check_offpage helper can read .x0/.x1/.y0/.y1
            # without branching on whether it received a real
            # pymupdf Rect or a tuple.
            page_rect = (
                _RectShim(*page_rect_tuple)
                if page_rect_tuple
                else page.rect
            )
            # Re-shape DrawingInfo into the dict form _has_dark_fill_behind
            # already understands (fill list of floats + rect-like object).
            page_fills = [
                {
                    "fill": list(d.fill),
                    "rect": _RectShim(*d.rect) if d.rect else None,
                }
                for d in page_drawings_idx
                if d.fill is not None and d.rect is not None
            ]
            for si in page_spans_idx:
                text = si.text
                if not text:
                    continue
                bbox = si.bbox
                findings.extend(self._check_color(
                    text, si.color, bbox, page_idx, page_fills,
                ))
                findings.extend(self._check_size(
                    text, si.font_size, bbox, page_idx,
                ))
                findings.extend(self._check_offpage(
                    text, bbox, page_rect, page_idx,
                ))
                findings.extend(self._check_unicode(text, bbox, page_idx))
            return findings

        # Fallback: legacy self-walk path. Preserved verbatim for
        # backward compatibility with direct analyzer-level tests and
        # for the index-build-failed degradation case.
        try:
            page_dict = page.get_text("dict")
        except Exception:  # noqa: BLE001
            return findings

        try:
            page_fills = [
                d for d in page.get_drawings()
                if d.get("fill") is not None
            ]
        except Exception:  # noqa: BLE001
            page_fills = []

        page_rect = page.rect
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text:
                        continue
                    color_int = span.get("color", 0) or 0
                    size = float(span.get("size", 0.0) or 0.0)
                    bbox = tuple(span.get("bbox", (0, 0, 0, 0)))

                    findings.extend(self._check_color(
                        text, color_int, bbox, page_idx, page_fills,
                    ))
                    findings.extend(self._check_size(text, size, bbox, page_idx))
                    findings.extend(self._check_offpage(
                        text, bbox, page_rect, page_idx,
                    ))
                    findings.extend(self._check_unicode(text, bbox, page_idx))
        return findings

    # ------------------------------------------------------------------
    # Colour / size / off-page checks
    # ------------------------------------------------------------------

    @staticmethod
    def _unpack_color(color_int: int) -> tuple[float, float, float]:
        """pymupdf packs span colour as an integer 0xRRGGBB."""
        r = ((color_int >> 16) & 0xFF) / 255.0
        g = ((color_int >> 8) & 0xFF) / 255.0
        b = (color_int & 0xFF) / 255.0
        return r, g, b

    @classmethod
    def _check_color(
        cls,
        text: str,
        color_int: int,
        bbox: tuple,
        page_idx: int,
        page_fills: list[Any] | None = None,
    ) -> list[Finding]:
        """Emit ``white_on_white_text`` when a span's colour matches the
        page background and no dark fill sits behind it.

        Luminance is computed on the unpacked RGB; the background check
        uses ``_has_dark_fill_behind`` to suppress legitimate
        white-on-dark renderings (e.g. a white title drawn over a dark
        rectangle).
        """
        r, g, b = cls._unpack_color(color_int)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if lum < (BACKGROUND_LUMINANCE_WHITE - COLOR_CONTRAST_THRESHOLD):
            return []
        if page_fills and cls._has_dark_fill_behind(bbox, page_fills):
            return []
        return [Finding(
            mechanism="white_on_white_text",
            tier=TIER["white_on_white_text"],
            confidence=0.9,
            description=(
                f"Text color RGB({r:.2f}, {g:.2f}, {b:.2f}) matches page "
                f"background luminance (delta {BACKGROUND_LUMINANCE_WHITE - lum:.3f}), "
                "and no coloured fill is drawn behind the span."
            ),
            location=f"page {page_idx + 1}, bbox {bbox}",
            surface="(indistinguishable from page background)",
            concealed=text[:300],
        )]

    @staticmethod
    def _has_dark_fill_behind(bbox: tuple, page_fills: list[Any]) -> bool:
        """True if any dark-luminance fill drawn at ``bbox`` covers more
        than half the span — legitimate white-on-dark rendering."""
        x0, y0, x1, y1 = bbox
        bbox_area = max((x1 - x0) * (y1 - y0), 1e-6)
        for d in page_fills:
            fill = d.get("fill")
            if fill is None:
                continue
            try:
                if len(fill) >= 3:
                    fr, fg, fb = float(fill[0]), float(fill[1]), float(fill[2])
                else:
                    continue
            except (ValueError, TypeError):
                continue
            flum = 0.2126 * fr + 0.7152 * fg + 0.0722 * fb
            if flum >= (BACKGROUND_LUMINANCE_WHITE - COLOR_CONTRAST_THRESHOLD):
                continue
            rect = d.get("rect")
            if rect is None:
                continue
            try:
                dx0, dy0, dx1, dy1 = rect.x0, rect.y0, rect.x1, rect.y1
            except AttributeError:
                try:
                    dx0, dy0, dx1, dy1 = rect
                except (ValueError, TypeError):
                    continue
            ox0, oy0 = max(dx0, x0), max(dy0, y0)
            ox1, oy1 = min(dx1, x1), min(dy1, y1)
            if ox1 > ox0 and oy1 > oy0:
                overlap = (ox1 - ox0) * (oy1 - oy0)
                if overlap / bbox_area > 0.5:
                    return True
        return False

    @staticmethod
    def _check_size(text: str, size: float, bbox: tuple, page_idx: int) -> list[Finding]:
        """Emit ``microscopic_font`` when the span's font size is below
        the human-readability threshold (``MICROSCOPIC_FONT_THRESHOLD``).

        Size 0 is skipped — pymupdf sometimes reports zero for spans
        the extractor cannot measure confidently, and that is not the
        same signal as deliberately-tiny rendering.
        """
        if 0 < size < MICROSCOPIC_FONT_THRESHOLD:
            return [Finding(
                mechanism="microscopic_font",
                tier=TIER["microscopic_font"],
                confidence=0.8,
                description=(
                    f"Font size {size:.3f}pt is below human-readable threshold "
                    f"({MICROSCOPIC_FONT_THRESHOLD}pt)."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=f"(effectively invisible at {size:.3f}pt)",
                concealed=text[:300],
            )]
        return []

    @staticmethod
    def _check_offpage(
        text: str, bbox: tuple, page_rect: Any, page_idx: int,
    ) -> list[Finding]:
        """Emit ``off_page_text`` when a span's bbox falls entirely
        outside the page MediaBox (plus a 1-point tolerance).

        Text drawn outside the visible page region is present in the
        text layer (and parsed by any extractor) but never rendered —
        the classic zahir/batin divergence at the layout level.
        """
        x0, y0, x1, y1 = bbox
        margin = 1.0
        off = (x1 < page_rect.x0 - margin or
               x0 > page_rect.x1 + margin or
               y1 < page_rect.y0 - margin or
               y0 > page_rect.y1 + margin)
        if off:
            return [Finding(
                mechanism="off_page_text",
                tier=TIER["off_page_text"],
                confidence=0.9,
                description=(
                    f"Span positioned outside page MediaBox "
                    f"(page rect: {tuple(page_rect)})."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface="(outside visible page region)",
                concealed=text[:300],
            )]
        return []

    # ------------------------------------------------------------------
    # Per-span Unicode + homoglyph checks
    # ------------------------------------------------------------------

    @classmethod
    def _check_unicode(cls, text: str, bbox: tuple, page_idx: int) -> list[Finding]:
        """Per-span Unicode-concealment pass.

        Looks for four independent signals inside a single span's text:

          * Zero-width characters (ZWSP, ZWNJ, ZWJ, WJ, BOM, …).
          * Bidirectional control characters (LRE/RLE/PDF/LRO/RLO/FSI/…).
          * Unicode TAG characters (U+E0000–U+E007F).
          * Mixed-script homoglyph substitution within a run of letters.

        Each signal emits its own finding if present; one span can
        therefore produce up to four findings if multiple concealment
        techniques are stacked.
        """
        findings: list[Finding] = []
        zw = [c for c in text if c in ZERO_WIDTH_CHARS]
        if zw:
            visible = text
            for c in ZERO_WIDTH_CHARS:
                visible = visible.replace(c, "")
            findings.append(Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.8,
                description=f"{len(zw)} zero-width character(s) embedded in visible text.",
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=visible[:200],
                concealed=" | ".join(f"U+{ord(c):04X}" for c in zw),
            ))
        bidi = [c for c in text if c in BIDI_CONTROL_CHARS]
        if bidi:
            findings.append(Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.85,
                description=(
                    f"{len(bidi)} bidirectional control character(s) found. These can "
                    "reorder display without changing underlying text."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=text[:200],
                concealed=" | ".join(f"U+{ord(c):04X}" for c in bidi),
            ))
        tag = [c for c in text if ord(c) in TAG_CHAR_RANGE]
        if tag:
            decoded_ascii = "".join(
                chr(ord(c) - 0xE0000) for c in tag if 0xE0020 <= ord(c) <= 0xE007E
            )
            findings.append(Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=0.99,
                description=(
                    f"{len(tag)} Unicode TAG character(s) (U+E0000-U+E007F) found. "
                    "TAG characters are not rendered but carry ASCII payloads invisible "
                    "to human readers — a known prompt-injection vector."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=re.sub(r"[\U000E0000-\U000E007F]", "", text)[:200],
                concealed=(
                    " | ".join(f"U+{ord(c):06X}" for c in tag[:12]) +
                    (" ..." if len(tag) > 12 else "") +
                    (f"  decoded: {decoded_ascii!r}" if decoded_ascii else "")
                ),
            ))
        findings.extend(cls._check_homoglyphs(text, bbox, page_idx))
        return findings

    @staticmethod
    def _check_homoglyphs(text: str, bbox: tuple, page_idx: int) -> list[Finding]:
        """Words with non-Latin lookalike characters alongside plain
        Latin (or ≥2 confusables on their own). Stricter than a raw
        "any confusable present" test so single-language non-Latin
        words don't false-positive."""
        if not text.strip():
            return []
        hits: list[tuple[str, list[tuple[str, str]]]] = []
        for word in re.split(r"\s+", text):
            if not word:
                continue
            confusables_in_word = [
                (c, CONFUSABLE_TO_LATIN[c]) for c in word
                if c in CONFUSABLE_TO_LATIN
            ]
            if not confusables_in_word:
                continue
            has_plain_latin = any(
                ("a" <= c.lower() <= "z") for c in word
            )
            if has_plain_latin or len(confusables_in_word) >= 2:
                hits.append((word, confusables_in_word))
        if not hits:
            return []
        surface_preview = "; ".join(w for w, _ in hits[:6])[:220]
        concealed_detail = "; ".join(
            f"{w!r}: " + ", ".join(
                f"U+{ord(c):04X}(looks like '{latin}')"
                for c, latin in pairs[:4]
            )
            for w, pairs in hits[:6]
        )[:320]
        return [Finding(
            mechanism="homoglyph",
            tier=TIER["homoglyph"],
            confidence=0.8,
            description=(
                f"{len(hits)} word(s) contain characters from non-Latin Unicode "
                "blocks that visually impersonate Latin letters (Cyrillic/Greek/"
                "Armenian/Cherokee/fullwidth/mathematical). Common in "
                "phishing spoofs and prompt-injection label swaps."
            ),
            location=f"page {page_idx + 1}, bbox {bbox}",
            surface=surface_preview,
            concealed=concealed_detail,
        )]


__all__ = ["ZahirTextAnalyzer"]
