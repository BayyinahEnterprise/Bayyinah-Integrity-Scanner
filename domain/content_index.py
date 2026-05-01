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


@dataclass(frozen=True)
class FontToUnicodeInfo:
    """One per-page font record carrying its ToUnicode CMap stream bytes.

    Captured by populate_from_pikepdf during the v1.1.7 BatinObjectAnalyzer
    migration. The legacy _scan_tounicode_cmaps walk reads the same
    information from pypdf via per-page Resources/Font/ToUnicode
    resolution; pikepdf's objgen[0] matches pypdf's idnum for the same
    underlying object, so xref-dedup is byte-parity-preserving across
    parsers. The font_key is captured as pikepdf's str(name) which
    matches pypdf's str(name) for /Name objects (verified on fixture
    object/tounicode_cmap.pdf: both report "/Fadv").

    cmap_bytes is the raw ToUnicode stream bytes; the migrated detector
    decodes via the same latin-1 path as the legacy walk so the
    parsed bfchar/bfrange entries are byte-identical.
    """
    page_idx: int
    font_key: str
    xref: int | None
    cmap_bytes: bytes


@dataclass(frozen=True)
class PikepdfAnnotInfo:
    """One annotation record sourced from pikepdf rather than pymupdf.

    Used by ``pdf_hidden_text_annotation`` because pypdf's ``idnum``
    and pikepdf's ``objgen[0]`` agree (verified on fixture 06: both
    report 8 for the hidden /Text annotation), while pymupdf's
    annotation API does not surface that idnum cleanly. Carrying a
    parallel pikepdf-sourced annotation list keeps the migrated
    detector's ``obj_id`` byte-identical with the pre-migration
    pypdf-based output.

    The pymupdf-sourced ``AnnotInfo`` list remains available on
    ``ContentIndex.annotations_by_page``; do not merge the two lists.
    """
    page_idx: int
    subtype: str          # e.g. "/Text", "/FreeText"; matches pypdf's str(/Subtype)
    flags: int            # /F bit field
    contents: str | None  # /Contents string, decoded
    obj_id: int | None    # pikepdf objgen[0]; matches pypdf annot_ref.idnum


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

    # Per-page ToUnicode CMap font records, populated by
    # populate_from_pikepdf during v1.1.7. Keys are page indices in
    # the same order pikepdf yields them. The migrated
    # BatinObjectAnalyzer._scan_tounicode_cmaps walk reads from this
    # mapping when present and falls back to the legacy pypdf walk
    # otherwise.
    fonts_by_page: dict[int, list[FontToUnicodeInfo]] = field(
        default_factory=dict
    )

    # Catalog summary (populated by Phase 3 migration; empty in Phase 1)
    # Keys when populated: "openaction", "aa", "names_javascript",
    #   "names_embedded", "ocproperties", "info_dict", "xmp_stream", "acroform"
    catalog: dict[str, Any] = field(default_factory=dict)

    # Trailer summary (populated by populate_from_raw_bytes during Phase 3
    # when pdf_trailer_analyzer reads from the index instead of doing its
    # own raw-bytes read). ``last_eof_offset`` is the offset of the FINAL
    # %%EOF marker (rfind), or -1 if no marker is present. ``trailing_
    # after_last_eof`` is the bytes that follow the marker, capped at
    # 4096 bytes so the index does not grow unbounded on pathological
    # files; the per-mechanism finding text only cites a 64-byte sample
    # so the cap does not affect byte-parity.
    eof_positions: list[int] = field(default_factory=list)
    last_eof_offset: int = -1
    trailing_after_last_eof: bytes = b""
    raw_bytes_read_failed: bool = False

    # Pikepdf-sourced data populated by populate_from_pikepdf during
    # Phase 3. The catalog dict's "info_dict" key carries /Info as
    # ``dict[str, str]``; "xmp_items" carries the XMP metadata as
    # ``dict[str, str]`` with keys in pikepdf's ``"{namespace}localname"``
    # form. ``page_raw_contents`` carries the raw content stream bytes
    # per page, used by pdf_off_page_text and pdf_metadata_analyzer's
    # rendered-text reconstruction. ``pikepdf_annotations_by_page``
    # carries pikepdf-sourced annotation records so ``obj_id`` matches
    # pypdf's ``idnum`` byte-for-byte.
    page_raw_contents: dict[int, bytes] = field(default_factory=dict)
    pikepdf_annotations_by_page: dict[int, list[PikepdfAnnotInfo]] = field(
        default_factory=dict
    )
    # MediaBoxes sourced from pikepdf (kept separate from page_rects which
    # is populated by from_pymupdf via page.rect). For most PDFs the two
    # agree, but pikepdf's /MediaBox is the byte-parity-correct source
    # for pdf_off_page_text whose existing self-walk reads list(page.MediaBox).
    page_mediaboxes: dict[int, tuple[float, float, float, float]] = field(
        default_factory=dict
    )

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

    # ------------------------------------------------------------------
    # v1.1.4 Phase 3 - additional populate methods
    # ------------------------------------------------------------------
    #
    # These methods extend an already-built ContentIndex with data from
    # sources outside the pymupdf walk. They are called by ScanService's
    # PDF preflight extension after ``from_pymupdf`` returns. Splitting
    # the population across methods keeps each parser's failure isolated:
    # if pikepdf cannot open the file, the pymupdf-sourced spans/drawings
    # are still available; if the raw-bytes read fails, the pikepdf data
    # is still available. Migrated analyzers check the relevant field
    # (e.g. ``page_raw_contents``, ``last_eof_offset``) for presence
    # before reading; missing data triggers the self-walk fallback.

    def populate_from_pikepdf(self, pdf: Any) -> None:
        """Fill catalog["info_dict"], catalog["xmp_items"], page_raw_contents,
        and pikepdf_annotations_by_page from a pikepdf.Pdf instance.

        Per-page failures degrade silently: that page's raw_contents
        and annotations remain absent rather than aborting the whole
        population. The caller is responsible for opening and closing
        the pikepdf handle; this method does neither.
        """
        # /Info dictionary - dict[str, str], keys preserve the leading "/"
        # to match the v1.1.1 detector output. ``pikepdf.Dictionary`` is
        # iterable; ``str(value)`` matches the detector's `str(info[key])`
        # call shape, which is byte-parity-preserving.
        try:
            docinfo = pdf.docinfo
        except Exception:  # noqa: BLE001 - missing /Info is permissible
            docinfo = None
        if docinfo is not None:
            info_dict: dict[str, str] = {}
            try:
                for key in docinfo.keys():
                    try:
                        info_dict[str(key)] = str(docinfo[key])
                    except Exception:  # noqa: BLE001 - per-key degradation
                        continue
            except Exception:  # noqa: BLE001 - per-doc degradation
                pass
            self.catalog["info_dict"] = info_dict

        # XMP metadata - dict[str, str], keys in pikepdf's
        # "{namespace}localname" form to match the v1.1.1 detector's
        # ``str(k)`` call shape.
        # /Names /EmbeddedFiles tree walk - capture leaf names so the
        # v1.1.7 BatinObjectAnalyzer._scan_embedded_files migration can
        # emit findings without re-walking pikepdf. The legacy walk
        # uses pypdf's _walk_names_tree which produces the same leaf
        # name strings as pikepdf's tree walk (verified on fixture
        # object/embedded_attachment.pdf: both yield 'payload.txt').
        # Stored as a list[str] under catalog["embedded_files"] so an
        # empty embedding tree is distinguishable (key present, list
        # empty) from "unable to capture" (key absent, fall through to
        # legacy walk).
        try:
            cat = pdf.Root
            names = cat.get("/Names") if hasattr(cat, "get") else None
        except Exception:  # noqa: BLE001
            names = None
        if names is not None:
            try:
                ef = names.get("/EmbeddedFiles")
            except Exception:  # noqa: BLE001
                ef = None
            if ef is not None:
                embedded: list[str] = []

                # Depth-first pre-order traversal mirroring the legacy
                # _walk_names_tree recursive walk: visit current /Names
                # entries first, then recurse into /Kids in order. The
                # leaf-name iteration order is byte-parity-critical for
                # the migrated _scan_embedded_files finding sequence.
                def _walk(node: Any) -> None:
                    try:
                        ns = (
                            node.get("/Names")
                            if hasattr(node, "get") else None
                        )
                    except Exception:  # noqa: BLE001
                        ns = None
                    if ns:
                        try:
                            seq = list(ns)
                        except Exception:  # noqa: BLE001
                            seq = []
                        for i in range(0, len(seq) - 1, 2):
                            try:
                                embedded.append(str(seq[i]))
                            except Exception:  # noqa: BLE001
                                continue
                    try:
                        kids = (
                            node.get("/Kids")
                            if hasattr(node, "get") else None
                        )
                    except Exception:  # noqa: BLE001
                        kids = None
                    if kids:
                        try:
                            kid_list = list(kids)
                        except Exception:  # noqa: BLE001
                            kid_list = []
                        for kid in kid_list:
                            try:
                                _walk(kid)
                            except Exception:  # noqa: BLE001
                                continue

                try:
                    _walk(ef)
                except Exception:  # noqa: BLE001
                    pass
                self.catalog["embedded_files"] = embedded

        try:
            with pdf.open_metadata() as meta:
                xmp_items: dict[str, str] = {}
                try:
                    for k, v in meta.items():
                        try:
                            xmp_items[str(k)] = str(v)
                        except Exception:  # noqa: BLE001
                            continue
                except Exception:  # noqa: BLE001
                    pass
                self.catalog["xmp_items"] = xmp_items
        except Exception:  # noqa: BLE001 - file may have no XMP
            pass

        # Per-page raw content streams + per-page pikepdf annotation
        # records. Single walk of pdf.pages.
        try:
            pages_iter = list(pdf.pages)
        except Exception:  # noqa: BLE001
            pages_iter = []
        for page_idx, page in enumerate(pages_iter):
            # Raw content stream bytes for pdf_off_page_text and
            # pdf_metadata_analyzer's rendered-text reconstruction.
            try:
                self.page_raw_contents[page_idx] = page.Contents.read_bytes()
            except Exception:  # noqa: BLE001 - per-page degradation
                # Leave the page absent from page_raw_contents; the
                # migrated analyzer's get-or-fallback shape skips it.
                pass

            # MediaBox sourced from pikepdf for pdf_off_page_text
            # byte-parity. The detector's existing self-walk reads
            # ``list(page.MediaBox)`` and casts to float; we capture
            # the same shape.
            try:
                mb = list(page.MediaBox)
                self.page_mediaboxes[page_idx] = (
                    float(mb[0]), float(mb[1]),
                    float(mb[2]), float(mb[3]),
                )
            except Exception:  # noqa: BLE001 - per-page degradation
                pass

            # Pikepdf-sourced annotations. Walk /Annots and capture
            # subtype, /F flags, /Contents, and the indirect-object
            # idnum (pikepdf's objgen[0] matches pypdf's annot_ref.idnum
            # for the same /Annots entry).
            page_annots: list[PikepdfAnnotInfo] = []
            try:
                annots_obj = page.get("/Annots")
            except Exception:  # noqa: BLE001
                annots_obj = None
            if annots_obj is not None:
                try:
                    annots_iter = list(annots_obj)
                except Exception:  # noqa: BLE001
                    annots_iter = []
                for aref in annots_iter:
                    try:
                        # aref is a pikepdf indirect reference; the
                        # objgen attribute exposes the (idnum, gen)
                        # tuple. Resolving the object via aref directly
                        # gives us the underlying dictionary.
                        try:
                            obj_id = int(aref.objgen[0])
                        except (AttributeError, TypeError, IndexError):
                            obj_id = None
                        annot = aref
                        try:
                            subtype = str(annot.get("/Subtype", "") or "")
                        except Exception:  # noqa: BLE001
                            subtype = ""
                        try:
                            flag_raw = annot.get("/F")
                            flags = int(flag_raw) if flag_raw is not None else 0
                        except (TypeError, ValueError):
                            flags = 0
                        try:
                            contents_raw = annot.get("/Contents")
                            contents = (
                                str(contents_raw)
                                if contents_raw is not None else None
                            )
                        except Exception:  # noqa: BLE001
                            contents = None
                        page_annots.append(PikepdfAnnotInfo(
                            page_idx=page_idx,
                            subtype=subtype,
                            flags=flags,
                            contents=contents,
                            obj_id=obj_id,
                        ))
                    except Exception:  # noqa: BLE001 - per-annotation degradation
                        continue
            self.pikepdf_annotations_by_page[page_idx] = page_annots

            # v1.1.7 - per-page font ToUnicode CMap capture for the
            # BatinObjectAnalyzer._scan_tounicode_cmaps migration.
            # Walk Resources/Font and capture each font's ToUnicode
            # stream bytes. Per-font failures degrade silently: the
            # migrated detector treats a missing font_by_page entry
            # the same as the legacy walk treats a per-font exception
            # (continue). xref-dedup is performed by the consumer,
            # not here, because the same font may appear on multiple
            # pages and we capture all occurrences for byte-parity
            # diagnosis.
            page_fonts: list[FontToUnicodeInfo] = []
            try:
                resources = page.get("/Resources")
            except Exception:  # noqa: BLE001
                resources = None
            if resources is not None:
                try:
                    fonts = resources.get("/Font")
                except Exception:  # noqa: BLE001
                    fonts = None
                if fonts is not None:
                    try:
                        font_keys = list(fonts.keys())
                    except Exception:  # noqa: BLE001
                        font_keys = []
                    for font_key in font_keys:
                        try:
                            font = fonts[font_key]
                            try:
                                tu = font.get("/ToUnicode")
                            except Exception:  # noqa: BLE001
                                tu = None
                            if tu is None:
                                continue
                            try:
                                xref = int(tu.objgen[0])
                            except (
                                AttributeError, TypeError, IndexError
                            ):
                                xref = None
                            try:
                                cmap_bytes = bytes(tu.read_bytes())
                            except Exception:  # noqa: BLE001
                                continue
                            page_fonts.append(FontToUnicodeInfo(
                                page_idx=page_idx,
                                font_key=str(font_key),
                                xref=xref,
                                cmap_bytes=cmap_bytes,
                            ))
                        except Exception:  # noqa: BLE001
                            continue
            self.fonts_by_page[page_idx] = page_fonts

    def populate_from_raw_bytes(self, raw: bytes) -> None:
        """Fill eof_positions, last_eof_offset, and trailing_after_last_eof
        from the file's raw byte stream.

        Caps the trailing bytes at 4096 to keep the index size bounded;
        the migrated pdf_trailer_analyzer only reads a 64-byte sample
        from this buffer so the cap does not affect byte-parity. Sets
        ``raw_bytes_read_failed=True`` if the input bytes are unusable
        (length zero is permissible: an empty file has no %%EOF and the
        analyzer fall-through handles that case).
        """
        EOF_TOKEN = b"%%EOF"
        TRAILING_CAP = 4096

        try:
            data_len = len(raw)
        except TypeError:
            self.raw_bytes_read_failed = True
            return

        # Update raw_bytes_len if the caller didn't already populate it
        # via from_pymupdf's raw_bytes_len parameter. The two values
        # should agree; we trust the actual length over any prior
        # estimate.
        self.raw_bytes_len = data_len

        if data_len == 0:
            return

        # Locate every %%EOF marker. The legacy pdf_trailer_analyzer
        # uses only ``rfind`` to find the final marker; ``eof_positions``
        # is also populated for the future incremental_update migration
        # which counts markers. The ``rfind``-style ``last_eof_offset``
        # is the byte-parity-critical value for trailer analyzer output.
        positions: list[int] = []
        idx = -1
        while True:
            nxt = raw.find(EOF_TOKEN, idx + 1)
            if nxt == -1:
                break
            positions.append(nxt)
            idx = nxt
        self.eof_positions = positions

        if positions:
            self.last_eof_offset = positions[-1]
            tail_start = positions[-1] + len(EOF_TOKEN)
            self.trailing_after_last_eof = raw[
                tail_start:tail_start + TRAILING_CAP
            ]
        else:
            self.last_eof_offset = -1
            self.trailing_after_last_eof = b""


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
    "FontToUnicodeInfo",
    "PikepdfAnnotInfo",
    "ContentIndex",
    "get_current_content_index",
    "set_current_content_index",
    "content_index_context",
]
