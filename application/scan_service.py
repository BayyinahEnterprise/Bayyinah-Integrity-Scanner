"""
ScanService — the orchestrator that makes no distinction between witnesses
(Al-Baqarah 2:285).

    لَا نُفَرِّقُ بَيْنَ أَحَدٍ مِّن رُّسُلِهِۦ
    "We make no distinction between any of His messengers."

The architectural reading: the orchestrator treats every analyzer's
findings equally. No analyzer's output is privileged, reweighted, or
silenced. The service composes them in registration order, recomputes
one APS-continuous score over the merged list, and clamps that score
to SCAN_INCOMPLETE_CLAMP (0.5) whenever any witness reports incomplete
coverage — the single integrity guarantee the reader can rely on.

This file is a structural port of ``bayyinah_v0_1.ScanService`` onto
the Phase 2+ contracts:

  * Analyzers are dispatched via ``analyzers.AnalyzerRegistry`` (not a
    raw ``list[BaseAnalyzer]``).
  * The file is opened via ``infrastructure.PDFClient`` (not the legacy
    ``bayyinah_v0_1.PDFContext``) and routed via
    ``infrastructure.FileRouter``.
  * The return type is ``domain.IntegrityReport``.

Byte-identical parity with ``bayyinah_v0_1.scan_pdf`` is preserved on
every Phase 0 fixture:

    1. Missing file  → error="File not found: <path>", score=0.0,
                       scan_incomplete=True, no findings.
    2. pymupdf-open
       failure       → error="Could not open PDF: <pymupdf-message>",
                       score=0.0, scan_incomplete=True, no findings.
    3. Happy path    → analyzers run in registration order
                       (Text → Object). Findings concatenated in order.
                       Score = clamp(1.0 - Σ(sev × conf), 0, 1),
                       clamped to 0.5 iff scan_incomplete.
    4. Per-analyzer
       errors        → joined with "; " at the top-level report.error.

The pymupdf-open error message is extracted from ``PDFParseError.__cause__``
— ``PDFClient`` wraps the underlying exception with its own prefix
(``"pymupdf could not open ..."``), and v0.1 uses the raw pymupdf
message. Unwrapping the cause restores v0.1's exact error string, which
is what the parity harness compares against.

Additive-only: nothing in this module is imported by ``bayyinah_v0``
or ``bayyinah_v0_1``. They continue to use their own
``ScanService`` / ``scan_pdf`` surface; the two pipelines coexist
until a later phase migrates the CLI onto this one.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from analyzers import (
    AnalyzerRegistry,
    AudioAnalyzer,
    BatinObjectAnalyzer,
    CorrelationEngine,
    CsvAnalyzer,
    DocxAnalyzer,
    EmlAnalyzer,
    FallbackAnalyzer,
    HtmlAnalyzer,
    ImageAnalyzer,
    JsonAnalyzer,
    PptxAnalyzer,
    SvgAnalyzer,
    TextFileAnalyzer,
    VideoAnalyzer,
    XlsxAnalyzer,
    ZahirTextAnalyzer,
)
from domain import (
    DEFAULT_LIMITS,
    Finding,
    IntegrityReport,
    PDFParseError,
    ScanLimits,
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
    limits_context,
)
from infrastructure import FileKind, FileRouter, PDFClient


# ---------------------------------------------------------------------------
# Default registry factory
# ---------------------------------------------------------------------------

def default_pdf_registry() -> AnalyzerRegistry:
    """Build the shipped default registry for PDF scanning.

    Registration order is deliberately ``ZahirTextAnalyzer`` first,
    ``BatinObjectAnalyzer`` second — which mirrors v0/v0.1's
    ``DEFAULT_PDF_ANALYZERS`` list. The registry preserves registration
    order when composing findings, so the merged ``IntegrityReport``
    carries text-layer findings before object-layer findings: the exact
    order ``bayyinah_v0_1.scan_pdf`` produces.

    This is a factory (not a module-level singleton) because tests
    frequently want independent registries they can clear, reorder, or
    swap. Handing back a fresh registry per call keeps parallel test
    runs from colliding.
    """
    registry = AnalyzerRegistry()
    registry.register(ZahirTextAnalyzer)
    registry.register(BatinObjectAnalyzer)
    return registry


def default_registry() -> AnalyzerRegistry:
    """Build the shipped default registry for the full multi-format scanner.

    Phase 9 extension — registers every shipping analyzer:

        ZahirTextAnalyzer      (supports PDF)
        BatinObjectAnalyzer    (supports PDF)
        TextFileAnalyzer       (supports MARKDOWN, CODE, plus any raw
                                text-family kind that is decoded bytes)
        JsonAnalyzer           (supports JSON)

    Registration order is fixed so PDF scans reduce to exactly the same
    set and ordering as ``default_pdf_registry()`` — the two text / JSON
    analyzers never fire on a PDF (their ``supported_kinds`` excludes
    ``FileKind.PDF``), so the merged report for any PDF input is
    byte-identical whether the caller uses ``default_pdf_registry()`` or
    ``default_registry()``. The Phase 9 integration tests verify this.

    The ``ScanService`` default switches to this factory so non-PDF
    files are handled transparently without the caller having to know
    the dispatch rules.
    """
    registry = AnalyzerRegistry()
    registry.register(ZahirTextAnalyzer)
    registry.register(BatinObjectAnalyzer)
    registry.register(TextFileAnalyzer)
    registry.register(JsonAnalyzer)
    # Phase 10 — raster image + SVG. Both declare disjoint
    # ``supported_kinds`` from the earlier analyzers, so PDF parity is
    # preserved: neither fires on a PDF, on a Markdown file, or on
    # JSON.
    registry.register(ImageAnalyzer)
    registry.register(SvgAnalyzer)
    # Phase 15 — DOCX. ``supported_kinds = {FileKind.DOCX}`` keeps this
    # analyzer disjoint from every earlier registration, so PDF, text,
    # JSON, and image parity are all preserved.
    registry.register(DocxAnalyzer)
    # Phase 16 — HTML. ``supported_kinds = {FileKind.HTML}`` keeps this
    # analyzer disjoint from every earlier registration; PDF, text,
    # JSON, image, and DOCX parity are all preserved. HTML files
    # previously fell through to ``TextFileAnalyzer`` (which still
    # accepts them as decoded text); both witnesses now compose per
    # Al-Baqarah 2:143 — the middle community of witnesses gives the
    # honest reading of a format that literally mixes zahir (visible
    # DOM text) with batin (scripts, data attributes, external
    # references). Al-Baqarah 2:42: do not mix truth with falsehood.
    registry.register(HtmlAnalyzer)
    # Phase 17 — XLSX. ``supported_kinds = {FileKind.XLSX}`` keeps this
    # analyzer disjoint from every earlier registration; PDF, text,
    # JSON, image, DOCX, and HTML parity are all preserved. Al-Baqarah
    # 2:79: "Woe to those who write the book with their own hands,
    # then say, 'This is from Allah,' in order to exchange it for a
    # small price." The verse describes the spreadsheet attack surface
    # exactly — structured, numerical, trustworthy-looking data
    # written with hidden macros, embedded objects, revision history,
    # and concealed payloads, then presented as clean input.
    registry.register(XlsxAnalyzer)
    # Phase 18 — PPTX. ``supported_kinds = {FileKind.PPTX}`` keeps this
    # analyzer disjoint from every earlier registration; PDF, text,
    # JSON, image, DOCX, HTML, and XLSX parity are all preserved.
    # Al-Baqarah 2:79 extended to the presentation surface; Al-Baqarah
    # 2:14: "When they meet those who believe, they say, 'We believe,'
    # but when they are alone with their devils, they say, 'Indeed, we
    # are with you'." A presentation ships three audiences at once —
    # the room that watches the slides, the presenter who reads the
    # notes, and the AI ingestion pipeline that reads both — and the
    # format lets those readers see three different documents.
    registry.register(PptxAnalyzer)
    # Phase 19 — EML. ``supported_kinds = {FileKind.EML}`` keeps this
    # analyzer disjoint from every earlier registration; PDF, text,
    # JSON, image, DOCX, HTML, XLSX, and PPTX parity are all preserved.
    # Al-Baqarah 2:42: "And do not mix the truth with falsehood, nor
    # conceal the truth while you know it." Email is the canonical
    # adversarial surface — the rendered HTML body the human reads can
    # diverge from the text/plain part the automated reader sees;
    # display names can impersonate trusted brands; RFC 2047
    # encoded-word subjects can smuggle payloads; CRLF injection can
    # forge headers; and attachments can carry executables, macros, or
    # nested .eml payloads that recurse into the same integrity
    # discipline through ``default_registry()``.
    registry.register(EmlAnalyzer)
    # Phase 20 — CSV / TSV / delimited data.
    # ``supported_kinds = {FileKind.CSV}`` keeps this analyzer disjoint
    # from every earlier registration; PDF, text, JSON, image, DOCX,
    # HTML, XLSX, PPTX, and EML parity are all preserved. Al-Baqarah
    # 2:42: "And do not mix the truth with falsehood, nor conceal the
    # truth while you know it." Delimited-data files are the format
    # where the human reader and the automated parser most literally
    # disagree — the spreadsheet-app reader sees rendered cells, the
    # text-editor reader sees raw formula source, and downstream data
    # pipelines silently skip comment rows, pad ragged columns, or
    # truncate at null bytes. CsvAnalyzer surfaces those divergences.
    registry.register(CsvAnalyzer)
    # Phase 21 — the universal witness of last resort.
    # ``supported_kinds = {FileKind.UNKNOWN}`` keeps this analyzer disjoint
    # from every earlier registration; PDF, text, JSON, image, DOCX, HTML,
    # XLSX, PPTX, EML, and CSV parity are all preserved — none of those
    # formats ever classify as UNKNOWN. The fallback analyzer fires
    # exclusively on files the router leaves unclassified, emitting an
    # ``unknown_format`` finding with the metadata (magic bytes,
    # extension, size, head preview) a forensics reader needs to begin
    # their own classification. Without this witness, unidentified
    # files would slip through as silent-clean — the exact failure mode
    # the Munafiq Protocol exists to prevent. Al-Baqarah 2:143.
    registry.register(FallbackAnalyzer)
    # Phase 24 — video containers (MP4 / MOV / WEBM / MKV).
    # ``supported_kinds = {VIDEO_MP4, VIDEO_MOV, VIDEO_WEBM, VIDEO_MKV}``
    # keeps this analyzer disjoint from every earlier registration; PDF,
    # text, JSON, image, DOCX, HTML, XLSX, PPTX, EML, CSV, and UNKNOWN
    # parity are all preserved — no existing format ever classifies as
    # a video kind. Al-Baqarah 2:19-20: the rainstorm's darker layers
    # (subtitle stems, metadata atoms, attachments, cover art) carry
    # concealment while the lightning of playback holds attention.
    # VideoAnalyzer reuses ZahirTextAnalyzer's codepoint primitives on
    # subtitle text and ImageAnalyzer's LSB / trailing-data detectors
    # on cover-art images, composing rather than duplicating.
    registry.register(VideoAnalyzer)
    # Phase 24 — audio containers (MP3 / WAV / FLAC / M4A / OGG).
    # ``supported_kinds = {AUDIO_MP3, AUDIO_WAV, AUDIO_FLAC, AUDIO_M4A,
    # AUDIO_OGG}`` keeps this analyzer disjoint from every earlier
    # registration; PDF, text, JSON, image, DOCX, HTML, XLSX, PPTX, EML,
    # CSV, UNKNOWN, and video parity are all preserved — no existing
    # format ever classifies as an audio kind. Al-Baqarah 2:93:
    # "Take what We have given you with determination and listen" —
    # the verse commands inspection with determination, to part the
    # layers and listen to every stem so no hidden payload deceives
    # artificial systems, mankind, or jinnkind. AudioAnalyzer reuses
    # ZahirTextAnalyzer's codepoint primitives on metadata text,
    # ImageAnalyzer on embedded pictures, and stdlib statistics on
    # WAV/FLAC PCM samples. Composition, not duplication — the same
    # discipline Phase 23 video applied to subtitle tracks.
    registry.register(AudioAnalyzer)
    return registry


# ---------------------------------------------------------------------------
# ScanService
# ---------------------------------------------------------------------------

class ScanService:
    """Orchestrate a full scan of one PDF through the registered analyzers.

    Construction::

        ScanService()                                   # default registry
        ScanService(registry=my_registry)               # custom analyzers
        ScanService(file_router=MyFileRouter())         # custom routing

    The service is stateless across ``scan`` calls. It holds references
    to a registry and a file router but mutates neither — callers may
    safely share one ``ScanService`` across threads that do not share
    a registry mutation path.

    The public method is ``scan(file_path) -> IntegrityReport``. It
    reproduces v0.1's ``scan_pdf`` semantics byte-for-byte on every
    Phase 0 fixture; the Phase 6 parity harness asserts this across the
    full fixture corpus.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        registry: AnalyzerRegistry | None = None,
        file_router: FileRouter | None = None,
        correlation_engine: CorrelationEngine | None = None,
        limits: ScanLimits | None = None,
    ) -> None:
        """Construct a ScanService.

        Parameters
        ----------
        registry
            Analyzer registry to dispatch to. Defaults to
            ``default_registry()`` — the shipped multi-format pipeline
            (PDF text/object + text-file + JSON analyzers). For any PDF
            input this reduces to exactly the same two analyzers firing
            in the same order as ``default_pdf_registry()``; the PDF
            parity harness verifies this.
        file_router
            File-type detector used to classify the input before
            dispatching. Defaults to a fresh ``FileRouter``. Phase 9
            activates this — the detected ``FileKind`` drives analyzer
            selection via the registry's ``kind`` filter and decides
            whether pymupdf preflight is applicable.
        correlation_engine
            Phase 12 cross-modal correlation composer. Applied to the
            non-PDF dispatch path as a post-analysis pass: emits
            ``coordinated_concealment`` findings when the same hidden
            payload appears in multiple carrier layers. The PDF path
            deliberately does NOT invoke correlation — byte-identical
            parity with v0/v0.1 requires that PDF reports be unchanged
            by Phase 12 additions. Defaults to a fresh
            ``CorrelationEngine``; callers may pass ``None`` explicitly
            (via the class attribute) to opt out entirely.
        limits
            Phase 21 configurable safety ceilings. A frozen
            ``ScanLimits`` instance declaring max file size, max
            recursion depth, max CSV rows, max field length, and max
            EML attachments. Defaults to ``DEFAULT_LIMITS`` — the
            shipped ceilings, sized to cover every legitimate document
            while preventing pathological inputs from exhausting the
            scanner host's memory. The limits are installed in a
            thread-local context for the duration of each ``scan()``
            call, so analyzers that read ``get_current_limits()``
            respect the per-scan configuration without the contract
            widening to thread the limits through every signature.
        """
        self.registry: AnalyzerRegistry = registry or default_registry()
        self.file_router: FileRouter = file_router or FileRouter()
        self.correlation_engine: CorrelationEngine = (
            correlation_engine or CorrelationEngine()
        )
        self.limits: ScanLimits = limits if limits is not None else DEFAULT_LIMITS

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(
        self,
        file_path: Path | str | None = None,
        *,
        pdf_path: Path | str | None = None,
    ) -> IntegrityReport:
        """Produce one merged IntegrityReport for ``file_path``.

        Control flow (byte-identical to ``bayyinah_v0_1.ScanService.scan``
        for every Phase 0 fixture):

            1. Coerce to ``Path``.
            2. Short-circuit if the file does not exist. Score = 0.0,
               error = ``"File not found: <path>"``,
               ``scan_incomplete = True``, no findings.
            3. Pre-flight pymupdf via ``PDFClient.fitz``. On failure,
               short-circuit with score = 0.0,
               error = ``"Could not open PDF: <pymupdf-message>"``,
               ``scan_incomplete = True``, no findings. The pymupdf
               message is recovered from ``PDFParseError.__cause__`` so
               the error string matches v0.1 exactly (v0.1 calls
               ``fitz.open`` directly and lets the raw exception
               surface).
            4. Dispatch to the registry. The registry instantiates every
               registered analyzer, composes their reports, applies the
               ``scan_incomplete`` clamp, and returns one merged
               ``IntegrityReport``. We recompute the final score and
               clamp at this layer for defence-in-depth — the assertion
               is that the registry already did it correctly, and we
               verify in tests that the two paths agree.

        The ``file_router`` reference is retained for multi-kind
        dispatch in later phases; in Phase 6 it does not branch scan
        behaviour — routing to the right analyzer set is the caller's
        responsibility via the ``registry`` argument. Using the default
        registry on a non-PDF file produces whatever each analyzer's
        error path would produce, which for the text and object
        analyzers is a ``scan_error`` + incomplete scan — the honest
        signal that the file is out of scope.

        Backward compatibility
        ----------------------
        Prior to 1.0 the parameter was spelled ``pdf_path``. It is
        still accepted as a deprecated keyword alias: callers writing
        ``svc.scan(pdf_path=p)`` continue to work but receive a
        ``DeprecationWarning``. Positional callers are unaffected.
        Passing both ``file_path`` and ``pdf_path`` is an error.
        """
        if pdf_path is not None:
            if file_path is not None:
                raise TypeError(
                    "ScanService.scan() received both 'file_path' and "
                    "'pdf_path'; 'pdf_path' is a deprecated alias — "
                    "use only 'file_path'."
                )
            import warnings
            warnings.warn(
                "ScanService.scan(pdf_path=...) is a deprecated alias "
                "since 1.0.0; use file_path=... (or the positional "
                "argument). The pdf_path keyword will be removed in a "
                "future release.",
                DeprecationWarning,
                stacklevel=2,
            )
            file_path = pdf_path
        if file_path is None:
            raise TypeError(
                "ScanService.scan() missing required argument: 'file_path'"
            )
        file_path = Path(file_path)

        # ------------------------------------------------------------------
        # Phase 21 — wrap the entire scan in the limits context so every
        # analyzer that reads ``get_current_limits()`` sees THIS
        # ScanService's configured ceilings for the duration of this
        # call, and then the prior context is restored. This keeps
        # concurrent scans with different limits isolated.
        # ------------------------------------------------------------------
        with limits_context(self.limits):
            return self._scan_inner(file_path)

    def _scan_inner(self, file_path: Path) -> IntegrityReport:
        """Body of ``scan``, invoked inside the limits context.

        Factored out so ``scan`` can own the limits wrapper without
        nesting the entire control flow under an extra indentation
        level. All the original ``scan`` semantics live here.
        """
        # ------------------------------------------------------------------
        # 1. Missing file — short-circuit identically to v0.1.
        # ------------------------------------------------------------------
        if not file_path.exists():
            report = IntegrityReport(
                file_path=str(file_path),
                integrity_score=0.0,
            )
            report.error = f"File not found: {file_path}"
            report.scan_incomplete = True
            return report

        # ------------------------------------------------------------------
        # Phase 21 — universal pre-flight: enforce max_file_size_bytes
        # before any analyzer runs. This is the one ceiling that applies
        # to every file type, so it lives at the orchestrator level
        # rather than in each analyzer. A file past the ceiling gets a
        # single ``scan_limited`` finding, ``scan_incomplete=True``, and
        # the 0.5 clamp — honest about what was not inspected. The
        # analyzer set is not invoked at all (the point of a size limit
        # is not to start the expensive work).
        #
        # Deliberately comes AFTER the existence check so a missing
        # file's "File not found" error is preserved byte-identically
        # for v0.1 parity.
        # ------------------------------------------------------------------
        try:
            size_bytes = file_path.stat().st_size
        except OSError:
            size_bytes = -1  # stat failure falls through to PDF legacy path
        if 0 <= self.limits.max_file_size_bytes < size_bytes:
            finding = Finding(
                mechanism="scan_limited",
                tier=3,
                confidence=1.0,
                description=(
                    f"file size {size_bytes} bytes exceeds configured "
                    f"max_file_size_bytes="
                    f"{self.limits.max_file_size_bytes}; no analyzer ran"
                ),
                location=str(file_path),
                surface=f"file size {size_bytes} bytes",
                concealed=(
                    "(file exceeded max_file_size_bytes pre-flight; "
                    "contents not inspected)"
                ),
                source_layer="batin",
            )
            report = IntegrityReport(
                file_path=str(file_path),
                integrity_score=compute_muwazana_score([finding]),
                findings=[finding],
                error=None,
            )
            report.scan_incomplete = True
            report.integrity_score = apply_scan_incomplete_clamp(
                report.integrity_score,
                scan_incomplete=True,
            )
            return report

        # ------------------------------------------------------------------
        # Phase 9 — classify the file. The branch taken below depends on
        # this: PDFs go through the pymupdf pre-flight path (byte-identical
        # to v0.1); every other kind skips pre-flight and dispatches the
        # matching non-PDF analyzers via the registry's kind filter.
        #
        # Detection is deliberately best-effort: if FileRouter raises an
        # OSError mid-read we fall back to PDF semantics — the pymupdf
        # preflight will then produce the expected "Could not open PDF"
        # error. That keeps the PDF path robust against router bugs.
        # ------------------------------------------------------------------
        try:
            detection = self.file_router.detect(file_path)
            detected_kind = detection.kind
        except OSError:
            detected_kind = FileKind.PDF  # fall-through to legacy path
            detection = None

        # ------------------------------------------------------------------
        # 2. Non-PDF dispatch. Every non-PDF, non-UNKNOWN kind routes
        #    directly to the registry with a kind filter — pymupdf
        #    pre-flight is a PDF concern, not a universal one.
        #
        #    Phase 21 change: UNKNOWN files now dispatch through the
        #    registry (reaching FallbackAnalyzer), rather than
        #    short-circuiting with an error. This closes the silent-
        #    clean failure mode: a file we could not classify no longer
        #    slips through — it surfaces as ``unknown_format`` with
        #    the magic-byte / extension / head-preview metadata a
        #    forensics reader needs. The prior "Unknown file type"
        #    error behaviour is preserved only when the caller uses a
        #    custom registry that does not include FallbackAnalyzer
        #    (in which case the UNKNOWN kind filter matches zero
        #    analyzers and the merged report surfaces with no findings
        #    — we detect that case explicitly and restore the old
        #    error for additive compatibility).
        #
        #    Exception: a .pdf extension on UNKNOWN content falls
        #    through to the pymupdf preflight path. v0.1 treated every
        #    path the caller handed it as PDF, so a garbage file named
        #    .pdf surfaces as "Could not open PDF: ..." — we preserve
        #    that exact string for byte-identical parity on that edge
        #    case.
        # ------------------------------------------------------------------
        if detected_kind is FileKind.UNKNOWN:
            if file_path.suffix.lower() == ".pdf":
                # Honour the extension — let pymupdf's own error surface
                # so v0.1 parity is preserved byte-for-byte.
                detected_kind = FileKind.PDF
            else:
                # Does the registry have a fallback? If not, preserve
                # the prior "Unknown file type" error so custom
                # registries that explicitly don't want the fallback
                # behaviour keep the old semantics — additive.
                has_fallback = any(
                    FileKind.UNKNOWN in cls.supported_kinds
                    for cls in self.registry.classes()
                )
                if not has_fallback:
                    report = IntegrityReport(
                        file_path=str(file_path),
                        integrity_score=0.0,
                    )
                    reason = (
                        detection.reason if detection is not None else
                        "could not classify"
                    )
                    report.error = f"Unknown file type: {reason}"
                    report.scan_incomplete = True
                    return report

        if detected_kind is not FileKind.PDF:
            merged = self.registry.scan_all(file_path, kind=detected_kind)
            # Surface the router's extension_mismatch signal. A polyglot
            # file (e.g. a .json whose bytes are a PNG) is adversarial
            # before a single analyzer runs; we record it as a tier-2
            # structural finding on the merged report.
            if detection.extension_mismatch:
                merged.findings.insert(0, Finding(
                    mechanism="extension_mismatch",
                    tier=2,
                    confidence=1.0,
                    description=(
                        f"File extension suggests one type but content "
                        f"bytes are {detected_kind.value!r}: "
                        f"{detection.reason}"
                    ),
                    location=str(file_path),
                    surface=f"extension .{file_path.suffix.lstrip('.')}",
                    concealed=f"actual content: {detected_kind.value}",
                    source_layer="batin",
                ))
                merged.integrity_score = compute_muwazana_score(
                    merged.findings,
                )
            # Phase 12 — intra-file cross-modal correlation. Only fires
            # on the non-PDF dispatch path; PDF parity with v0/v0.1 is
            # therefore unaffected. Correlation findings are appended
            # to the list (post-analyzer ordering) and the integrity
            # score is recomputed over the extended set.
            correlation_findings = self.correlation_engine.intra_file_correlate(
                merged.findings, file_path,
            )
            if correlation_findings:
                merged.findings.extend(correlation_findings)
                merged.integrity_score = compute_muwazana_score(
                    merged.findings,
                )
            # Defence-in-depth clamp, same as PDF path.
            has_scan_error = any(
                f.mechanism == "scan_error" for f in merged.findings
            )
            if merged.error is not None or has_scan_error:
                merged.scan_incomplete = True
            merged.integrity_score = apply_scan_incomplete_clamp(
                merged.integrity_score,
                scan_incomplete=merged.scan_incomplete,
            )
            return merged

        # ------------------------------------------------------------------
        # 3. PDF pre-flight — short-circuit identically to v0.1.
        #
        # v0.1 does: `ctx = PDFContext(file_path); _ = ctx.fitz`, catching
        # every exception and surfacing it as ``Could not open PDF: <e>``.
        # PDFClient wraps the pymupdf exception in PDFParseError with
        # its own prefix, so we unwrap via __cause__ to recover v0.1's
        # exact error text. If __cause__ is absent (e.g. pymupdf itself
        # raised a PDFParseError we did not wrap), fall back to the
        # PDFParseError string — still informative, still honest about
        # the failure.
        # ------------------------------------------------------------------
        preflight_error: Exception | None = None
        client = PDFClient(file_path)
        try:
            try:
                _ = client.fitz
            except PDFParseError as exc:
                preflight_error = exc.__cause__ or exc
            except Exception as exc:  # noqa: BLE001 — mirror v0.1 bare except
                preflight_error = exc
        finally:
            client.close()

        if preflight_error is not None:
            report = IntegrityReport(
                file_path=str(file_path),
                integrity_score=0.0,
            )
            report.error = f"Could not open PDF: {preflight_error}"
            report.scan_incomplete = True
            return report

        # ------------------------------------------------------------------
        # 4. Happy path — dispatch to the registry with a PDF kind filter.
        #
        # The ``kind=FileKind.PDF`` filter is load-bearing only when the
        # registry contains non-PDF analyzers (the Phase 9 default). With
        # ``default_pdf_registry()`` (every analyzer PDF-scoped), the
        # filter is a no-op and the call reduces byte-for-byte to v0.1's
        # `scan_all(file_path)`. The Phase 0 parity harness asserts this.
        # ------------------------------------------------------------------
        merged = self.registry.scan_all(file_path, kind=FileKind.PDF)

        # Defence-in-depth: re-assert the invariants. If an older
        # registry in a custom setup forgets the clamp, we enforce it
        # here without reshaping anything else about the report.
        has_scan_error = any(
            f.mechanism == "scan_error" for f in merged.findings
        )
        if merged.error is not None or has_scan_error:
            merged.scan_incomplete = True
        merged.integrity_score = apply_scan_incomplete_clamp(
            merged.integrity_score,
            scan_incomplete=merged.scan_incomplete,
        )
        return merged

    # ------------------------------------------------------------------
    # Phase 12 — batch scan + cross-file correlation
    # ------------------------------------------------------------------

    def scan_batch(
        self,
        paths: Iterable[Path],
    ) -> "BatchScanResult":
        """Scan a batch of files and correlate payloads across them.

        Runs ``scan(path)`` on every entry in ``paths``, preserving
        input order, and returns a ``BatchScanResult`` that carries

          * ``reports`` — one ``IntegrityReport`` per input path, in
            input order. Each report is byte-for-byte identical to what
            a single ``scan(path)`` would return for that path; batching
            does not alter per-file findings.
          * ``cross_file_findings`` — a list of
            ``cross_format_payload_match`` findings for every payload
            that appeared in two or more files in the batch. Empty when
            no correlation fires.

        Cross-file correlation runs after every per-file scan completes.
        It does NOT mutate the per-file reports — batch callers who want
        to see the correlation findings inspect
        ``result.cross_file_findings`` directly. This keeps the single-
        file API byte-identical for callers who do not use batching.

        PDF reports are excluded from cross-file correlation: their
        findings never carry correlatable payloads (PDF analyzers emit
        summary-shaped concealed fields, not literal payload previews),
        and excluding them by kind guarantees PDF parity is preserved
        even when PDFs are scanned alongside other formats in a batch.
        """
        reports: list[IntegrityReport] = []
        scans_for_correlation: list[tuple[Path, list]] = []
        for raw_path in paths:
            path = Path(raw_path)
            report = self.scan(path)
            reports.append(report)
            # Guard: exclude reports for files we determine are PDFs so
            # the cross-file correlation never rolls up PDF findings
            # into its payload buckets. We re-detect rather than relying
            # on a "was this a PDF" flag on the report — the router is
            # the single source of truth for file kind.
            try:
                detection = self.file_router.detect(path)
                is_pdf = detection.kind is FileKind.PDF
            except OSError:
                is_pdf = path.suffix.lower() == ".pdf"
            if not is_pdf:
                scans_for_correlation.append((path, report.findings))

        cross_file_findings = self.correlation_engine.cross_file_correlate(
            scans_for_correlation,
        )
        return BatchScanResult(
            reports=reports,
            cross_file_findings=cross_file_findings,
        )

    # ------------------------------------------------------------------
    # Dunders
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        analyzer_names = ", ".join(self.registry.names())
        return (
            f"ScanService(registry=[{analyzer_names}], "
            f"file_router={type(self.file_router).__name__})"
        )


# ---------------------------------------------------------------------------
# BatchScanResult
# ---------------------------------------------------------------------------


from dataclasses import dataclass, field


@dataclass
class BatchScanResult:
    """The output of ``ScanService.scan_batch``.

    Pairs the per-file reports (unchanged from what a single-file
    ``scan`` would produce) with any cross-file correlation findings the
    batch surfaces. Callers who just want per-file scans read
    ``reports``; callers running coordination audits inspect
    ``cross_file_findings``.

    The properties and helpers on this dataclass are read-only views —
    they compute their answers from the underlying ``reports`` and
    ``cross_file_findings`` lists each time they are called. Mutating
    those lists after construction is supported and the views will
    reflect the current state.
    """
    reports: list[IntegrityReport]
    cross_file_findings: list = field(default_factory=list)

    # ------------------------------------------------------------------
    # Phase 13 — reporting helpers
    # ------------------------------------------------------------------
    #
    # These helpers exist because batch callers repeatedly needed the same
    # roll-ups: "did correlation fire at all?", "how many files does the
    # batch cover?", "which files are actually implicated in the cross-
    # file match?". Computing them from ``reports`` + ``cross_file_findings``
    # one-off is trivial but error-prone (the location field is a
    # semicolon-joined string — easy to forget to split it). Surfacing
    # them as named properties makes the intent of the caller's code
    # legible and keeps the splitting logic in one place.

    @property
    def has_cross_file_correlation(self) -> bool:
        """``True`` when any ``cross_format_payload_match`` fired.

        The most common batch question: "did the correlator find
        anything coordinated across these files?". Callers typically
        branch on this before inspecting ``cross_file_findings`` in
        detail.
        """
        return len(self.cross_file_findings) > 0

    @property
    def cross_file_finding_count(self) -> int:
        """Number of cross-file correlation findings emitted.

        One ``cross_format_payload_match`` finding per unique payload
        that appeared in ``CORRELATION_MIN_FILES`` or more files — so
        this counts distinct coordinated *payloads*, not distinct files
        involved. For that, use ``involved_files``.
        """
        return len(self.cross_file_findings)

    @property
    def files_scanned(self) -> int:
        """Total number of files this batch processed.

        Equal to ``len(self.reports)``. Kept as a named property so
        summary-reporting code reads naturally.
        """
        return len(self.reports)

    @property
    def involved_files(self) -> list[str]:
        """Sorted unique file paths implicated in any cross-file finding.

        Every ``cross_format_payload_match`` finding's ``location`` is a
        ``"; "``-joined list of the paths whose findings share the
        coordinated payload. This property parses those back into a
        flat, sorted, de-duplicated list — the set of files a reader
        should actually look at when investigating a batch-level
        coordination signal.

        Returns an empty list when ``cross_file_findings`` is empty or
        when none of the findings carry a parseable location.
        """
        seen: set[str] = set()
        for finding in self.cross_file_findings:
            location = getattr(finding, "location", "") or ""
            for entry in location.split("; "):
                entry = entry.strip()
                if entry:
                    seen.add(entry)
        return sorted(seen)

    @property
    def total_per_file_findings(self) -> int:
        """Sum of finding counts across every per-file report.

        Does NOT include ``cross_file_findings``; those are a batch-
        level overlay. Use ``total_findings`` if you want the grand
        total including both.
        """
        return sum(len(r.findings) for r in self.reports)

    @property
    def total_findings(self) -> int:
        """Per-file findings plus cross-file correlation findings."""
        return self.total_per_file_findings + self.cross_file_finding_count

    @property
    def any_scan_incomplete(self) -> bool:
        """``True`` when any report in the batch was marked incomplete.

        A batch with even one ``scan_incomplete`` report should be
        treated as tentative by downstream auditors — the clean-looking
        reports next to an incomplete one may be hiding the same
        failure mode.
        """
        return any(r.scan_incomplete for r in self.reports)

    def reports_by_path(self) -> dict[str, IntegrityReport]:
        """Dict view keyed by ``str(file_path)`` → ``IntegrityReport``.

        Handy when a caller holds the batch result and wants random
        access by path (e.g. cross-referencing against another source of
        truth). If the same path appears twice in the input, the later
        report wins — consistent with Python's dict-insertion order.
        """
        return {r.file_path: r for r in self.reports}


__all__ = [
    "ScanService",
    "default_pdf_registry",
    "default_registry",
    "BatchScanResult",
]
