"""
ContentIndex - walk the document once, share the result across mechanisms.

The v1.1.4 cost-taxonomy redesign rests on a single principle: the
expensive parsing cost (pymupdf get_text("dict"), per-page drawing
enumeration, annotation walks) is paid ONCE per scan, not once per
mechanism. Every PDF mechanism that previously walked the document
independently now reads from a shared per-scan ContentIndex.

The index is per-scan, not per-corpus:
  - Built at the start of a PDF scan from the pymupdf document.
  - Consumed by analyzers and per-mechanism detectors.
  - Discarded at the end. The next scan builds a fresh index.

The index is not persisted, not cached across calls, and not shared
between concurrent scans. Each scan owns its own index.

The index covers the high-cost class B paths first:
  - Text spans per page (eliminates repeated get_text("dict") calls)
  - Per-page drawings (eliminates repeated get_drawings() calls)
  - Annotations per page (eliminates repeated /Annots walks)
  - Page rectangles (off-page-text check)

The index intentionally does NOT cover:
  - Raw content streams (read via page.read_contents() in the few
    mechanisms that need them; this is lower-volume and the index
    would balloon with stream data).
  - The PDF catalog (pikepdf handle, separate concern; class A
    mechanisms can read from it directly during the catalog migration
    in Phase 3).

Backward compatibility:
  - Analyzers gain an optional ``content_index`` parameter on scan().
  - Analyzers that have been migrated read from the index when
    available; they fall back to self-walking the document when the
    index is None.
  - This lets the migration ship per-mechanism without breaking
    byte-parity on the existing test suite.

Failure mode:
  - If the index builder hits a parsing error, ``build_failed=True``
    is set on the resulting index and analyzers fall back to their
    self-walk path. This preserves the existing scan_error reporting
    shape without forcing every analyzer to re-implement defensive
    parsing around the index.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


# ---------------------------------------------------------------------------
# Per-element record types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SpanInfo:
    """One text span extracted from one page.

    Mirrors the fields ZahirTextAnalyzer reads from
    ``page.get_text("dict")[blocks][lines][spans]``. Frozen so the
    span list can be safely shared across mechanisms without anyone
    accidentally mutating it.
    """
    page_idx: int
    bbox: tuple[float, float, float, float]    # x0, y0, x1, y1
    text: str
    font_name: str
    font_size: float
    color: int                                  # sRGB packed integer
    flags: int                                  # bold/italic/etc per pymupdf


@dataclass(frozen=True)
class DrawingInfo:
    """One drawing record from a page (rect + fill colour).

    Captured for the white-on-white background check in
    ZahirTextAnalyzer._check_color. Only the subset of drawing
    properties the existing detector actually reads is recorded;
    everything else from page.get_drawings() is dropped.
    """
    page_idx: int
    rect: tuple[float, float, float, float] | None  # x0, y0, x1, y1
    fill: tuple[float, float, float] | None         # r, g, b 0..1; None if no fill


@dataclass(frozen=True)
class AnnotInfo:
    """One annotation from one page.

    Captures the fields pdf_hidden_text_annotation reads: the /F
    suppression flags and the /Contents string. Annotation type and
    rectangle are included for future migrations.
    """
    page_idx: int
    annot_type: str
    bbox: tuple[float, float, float, float]
    flags: int                                  # /F bit field
    contents: str | None
    uri: str | None


@dataclass(frozen=True)
class FontInfo:
    """One font record from the document's font table.

    Currently a thin shape; tounicode_anomaly migration will populate
    the cmap entries when that mechanism is migrated to read from the
    index.
    """
    font_id: str
    encoding: str | None


# ---------------------------------------------------------------------------
# ContentIndex
# ---------------------------------------------------------------------------

@dataclass
class ContentIndex:
    """Per-document structural index, built once per scan.

    Built by ``ContentIndex.from_pymupdf(doc, file_path)`` at the top
    of the PDF scan path in ScanService. Passed to every PDF analyzer
    via the optional ``content_index`` keyword on ``scan()``. Mechanisms
    that have been migrated read from the index instead of re-walking
    the document.
    """

    # Identification and shape
    file_path: str = ""
    page_count: int = 0
    raw_bytes_len: int = 0

    # Per-page content (the expensive part, now shared)
    spans: list[SpanInfo] = field(default_factory=list)
    spans_by_page: dict[int, list[SpanInfo]] = field(default_factory=dict)

    # Per-page drawings (for white-on-white background check)
    drawings_by_page: dict[int, list[DrawingInfo]] = field(default_factory=dict)

    # Annotations
    annotations: list[AnnotInfo] = field(default_factory=list)
    annotations_by_page: dict[int, list[AnnotInfo]] = field(default_factory=dict)

    # Page geometry (for off-page-text check)
    page_rects: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)

    # Font table (for tounicode and font-related checks; populated on demand)
    fonts: dict[str, FontInfo] = field(default_factory=dict)

    # Catalog summary (populated by Phase 3 migration; empty in Phase 1)
    # Keys when populated: "openaction", "aa", "names_javascript",
    #   "names_embedded", "ocproperties", "info_dict", "xmp_stream", "acroform"
    catalog: dict[str, Any] = field(default_factory=dict)

    # Trailer summary (populated when Phase 3 migrates pdf_trailer_analyzer)
    eof_positions: list[int] = field(default_factory=list)

    # Failure flag: True when the index could not be fully built.
    # Analyzers that read from the index check this and fall back to
    # their self-walk path when set, preserving the existing defensive
    # scan_error semantics.
    build_failed: bool = False
    build_error: str | None = None

    # ------------------------------------------------------------------
    # Builders
    # ------------------------------------------------------------------

    @classmethod
    def from_pymupdf(
        cls,
        doc: Any,
        file_path: str,
        raw_bytes_len: int = 0,
    ) -> "ContentIndex":
        """Build the index from a pymupdf Document in a single walk.

        One pass through every page. Per-page failures degrade
        gracefully: that page's spans/drawings/annotations are empty
        rather than aborting the whole index. Top-level failures set
        ``build_failed=True`` and the analyzers fall back to their
        self-walk path.
        """
        try:
            page_count = len(doc)
        except Exception as exc:  # noqa: BLE001 - degradation, not abort
            idx = cls(file_path=file_path, raw_bytes_len=raw_bytes_len)
            idx.build_failed = True
            idx.build_error = f"page_count: {exc}"
            return idx

        idx = cls(
            file_path=file_path,
            page_count=page_count,
            raw_bytes_len=raw_bytes_len,
        )

        for page_idx in range(page_count):
            try:
                page = doc[page_idx]
            except Exception:  # noqa: BLE001
                # Per-page failure: leave the page's lists empty.
                idx.spans_by_page[page_idx] = []
                idx.drawings_by_page[page_idx] = []
                idx.annotations_by_page[page_idx] = []
                continue

            # Page rectangle for off-page-text checks.
            try:
                rect = page.rect
                idx.page_rects[page_idx] = (
                    float(rect.x0), float(rect.y0),
                    float(rect.x1), float(rect.y1),
                )
            except Exception:  # noqa: BLE001
                idx.page_rects[page_idx] = (0.0, 0.0, 0.0, 0.0)

            # Spans: the load-bearing extraction. Single get_text("dict")
            # call per page, replacing the two calls today (one in
            # _scan_spans, one in _scan_overlapping_spans).
            page_spans: list[SpanInfo] = []
            try:
                page_dict = page.get_text("dict")
                for block in page_dict.get("blocks", []):
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            text = span.get("text", "") or ""
                            bbox_raw = span.get("bbox", (0.0, 0.0, 0.0, 0.0))
                            try:
                                bbox = (
                                    float(bbox_raw[0]), float(bbox_raw[1]),
                                    float(bbox_raw[2]), float(bbox_raw[3]),
                                )
                            except (TypeError, ValueError, IndexError):
                                bbox = (0.0, 0.0, 0.0, 0.0)
                            si = SpanInfo(
                                page_idx=page_idx,
                                bbox=bbox,
                                text=text,
                                font_name=str(span.get("font", "") or ""),
                                font_size=float(span.get("size", 0.0) or 0.0),
                                color=int(span.get("color", 0) or 0),
                                flags=int(span.get("flags", 0) or 0),
                            )
                            page_spans.append(si)
                            idx.spans.append(si)
            except Exception:  # noqa: BLE001
                # Page-level extraction failed; leave empty.
                pass
            idx.spans_by_page[page_idx] = page_spans

            # Per-page drawings for white-on-white background detection.
            page_drawings: list[DrawingInfo] = []
            try:
                for d in page.get_drawings() or []:
                    fill_raw = d.get("fill")
                    if fill_raw is not None:
                        try:
                            if len(fill_raw) >= 3:
                                fill = (
                                    float(fill_raw[0]),
                                    float(fill_raw[1]),
                                    float(fill_raw[2]),
                                )
                            else:
                                fill = None
                        except (TypeError, ValueError):
                            fill = None
                    else:
                        fill = None

                    rect_raw = d.get("rect")
                    rect_tuple: tuple[float, float, float, float] | None = None
                    if rect_raw is not None:
                        try:
                            rect_tuple = (
                                float(rect_raw.x0), float(rect_raw.y0),
                                float(rect_raw.x1), float(rect_raw.y1),
                            )
                        except AttributeError:
                            try:
                                rect_tuple = (
                                    float(rect_raw[0]), float(rect_raw[1]),
                                    float(rect_raw[2]), float(rect_raw[3]),
                                )
                            except (TypeError, ValueError, IndexError):
                                rect_tuple = None

                    page_drawings.append(DrawingInfo(
                        page_idx=page_idx,
                        rect=rect_tuple,
                        fill=fill,
                    ))
            except Exception:  # noqa: BLE001
                pass
            idx.drawings_by_page[page_idx] = page_drawings

            # Annotations for /F-flag concealment checks.
            page_annots: list[AnnotInfo] = []
            try:
                annots = page.annots()
                if annots:
                    for annot in annots:
                        try:
                            annot_type = str(annot.type) if annot.type else ""
                            try:
                                rect = annot.rect
                                bbox = (
                                    float(rect.x0), float(rect.y0),
                                    float(rect.x1), float(rect.y1),
                                )
                            except Exception:  # noqa: BLE001
                                bbox = (0.0, 0.0, 0.0, 0.0)
                            try:
                                flags = int(annot.flags or 0)
                            except Exception:  # noqa: BLE001
                                flags = 0
                            try:
                                info = annot.info or {}
                                contents = info.get("content", None)
                                uri = info.get("uri", None)
                            except Exception:  # noqa: BLE001
                                contents = None
                                uri = None
                            ai = AnnotInfo(
                                page_idx=page_idx,
                                annot_type=annot_type,
                                bbox=bbox,
                                flags=flags,
                                contents=contents,
                                uri=uri,
                            )
                            page_annots.append(ai)
                            idx.annotations.append(ai)
                        except Exception:  # noqa: BLE001
                            continue
            except Exception:  # noqa: BLE001
                pass
            idx.annotations_by_page[page_idx] = page_annots

        return idx


# ---------------------------------------------------------------------------
# Thread-local context (mirrors the limits_context pattern in domain/config.py)
# ---------------------------------------------------------------------------
#
# Analyzers reach the active ContentIndex via ``get_current_content_index()``
# rather than through a new keyword on ``BaseAnalyzer.scan()``. This keeps
# the migration backward-compatible across every existing analyzer (PDF and
# non-PDF) without widening the abstract contract that 50+ analyzers
# implement. ScanService installs the index with ``content_index_context``
# at the top of the PDF dispatch path; analyzers that have been migrated
# read the contextvar and fall through to their self-walk path when the
# return value is None (the default outside a context manager).
#
# Thread-local storage isolates concurrent scans the same way ``_limits_state``
# does for ``ScanLimits``. Test patterns of the form
# ``with content_index_context(idx): analyzer.scan(p)`` work naturally
# under pytest's per-test scope without any per-test cleanup.

_index_state = threading.local()


def get_current_content_index() -> "ContentIndex | None":
    """Return the ContentIndex in effect for the current scan, if any.

    Outside a ``content_index_context`` block (and outside an active
    ScanService dispatch), returns ``None`` so analyzers fall back to
    their self-walk path. This makes the index migration purely
    additive: an analyzer that does not call this function continues
    to behave exactly as it did before.
    """
    return getattr(_index_state, "current", None)


def set_current_content_index(index: "ContentIndex | None") -> None:
    """Install ``index`` as the current scan's ContentIndex.

    Prefer ``content_index_context`` for temporary overrides; use this
    setter only for long-lived contexts (CLI startup, test fixture
    setup).
    """
    _index_state.current = index


@contextmanager
def content_index_context(index: "ContentIndex | None") -> Iterator[None]:
    """Install ``index`` for the duration of the with-block.

    On entry, replaces any previously-installed index. On exit (or
    exception), restores whatever was installed before. Concurrent
    scans on different threads do not see each other's indexes
    because ``_index_state`` is a ``threading.local``.
    """
    prior = getattr(_index_state, "current", None)
    _index_state.current = index
    try:
        yield
    finally:
        _index_state.current = prior


__all__ = [
    "SpanInfo",
    "DrawingInfo",
    "AnnotInfo",
    "FontInfo",
    "ContentIndex",
    "get_current_content_index",
    "set_current_content_index",
    "content_index_context",
]
