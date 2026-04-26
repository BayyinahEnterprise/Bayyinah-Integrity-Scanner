"""
PDFClient — the rock from which twelve streams flow (Al-Baqarah 2:60).

    فَقُلْنَا اضْرِب بِّعَصَاكَ الْحَجَرَ ۖ فَانفَجَرَتْ مِنْهُ اثْنَتَا عَشْرَةَ عَيْنًا
    "We said: Strike the rock with your staff — and twelve springs
    gushed forth from it, each tribe knowing its drinking-place."

The architectural reading: one file, many extractors. Every analyzer
drinks from the same rock (the document) through the same client, but
each uses the stream appropriate to its layer — pymupdf's rendering
view for the zahir (visible text), pypdf's object graph for the batin
(catalog, actions, streams). The PDFClient is the rock that produces
both streams on demand, caching so no analyzer re-opens the file.

This is a straight port of ``bayyinah_v0_1.PDFContext`` with three
deltas:
  * Sits under ``infrastructure/`` — parser dependencies are contained
    to this layer; domain and analyzers never import pypdf/pymupdf
    directly once Phase 4+ migrate onto this client.
  * Implements the context-manager protocol (``with PDFClient(path) as
    client: ...``) so callers cannot forget to ``close()``.
  * Narrows the external exception surface: failures to open the file
    wrap the underlying exception in ``PDFParseError`` from the domain
    layer, so callers need only ``except BayyinahError``.

Additive-only. ``bayyinah_v0_1.PDFContext`` is unchanged and still
used by v0.1's own analyzer pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import TracebackType
from typing import Any

from domain.exceptions import PDFParseError


# Parser imports are guarded so that importing this module in a test
# environment without pymupdf / pypdf installed produces a clear error
# at first *use* rather than at first *import*. This mirrors v0's
# defensive import pattern.

try:
    import pymupdf as fitz  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — environment-specific
    try:
        import fitz  # type: ignore[import-not-found]
    except ImportError:
        fitz = None  # type: ignore[assignment]

try:
    import pypdf  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — environment-specific
    pypdf = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# PDFClient
# ---------------------------------------------------------------------------

class PDFClient:
    """Lazily-cached view over a single PDF, shared across analyzers.

    The client opens pymupdf immediately (via the ``fitz`` property) and
    pypdf on request (via ``try_pypdf``). Independence matters: many
    real PDFs open cleanly in one parser and fail in the other, and a
    v0 design decision was that pypdf failures should be *recoverable*
    — the object-layer analyzer records a ``scan_error`` rather than
    tearing down the whole scan.

    Usage as a context manager is strongly recommended::

        with PDFClient(path) as client:
            doc = client.fitz
            reader, err = client.try_pypdf()

    Callers that manage lifecycle manually MUST call ``close()``.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, path: Path) -> None:
        """Bind to a PDF path without opening any parser yet.

        Parser handles are materialised lazily on first access to
        ``.fitz`` or ``.try_pypdf()``. This keeps construction cheap
        (no disk I/O, no parser initialisation) and lets the caller
        decide which parser to exercise — the zahir analyzer uses
        fitz exclusively; the batin analyzer tries both.
        """
        self.path: Path = Path(path)
        self._fitz_doc: Any = None
        self._pypdf_reader: Any = None
        self._pypdf_error: Exception | None = None
        self._raw_bytes: bytes | None = None
        self._closed: bool = False

    # ------------------------------------------------------------------
    # Availability checks — surface clear errors if the parser is missing
    # ------------------------------------------------------------------

    @staticmethod
    def _require_fitz() -> Any:
        """Return the imported ``fitz`` / pymupdf module or raise.

        Called only on first use of the fitz-backed surface. A missing
        parser surfaces as ``PDFParseError`` (plus a stderr hint) so the
        caller's normal ``except BayyinahError`` branch handles it — no
        bare ``ImportError`` propagates past this layer.
        """
        if fitz is None:  # pragma: no cover — environment-specific
            sys.stderr.write(
                "ERROR: pymupdf (or fitz) not installed. "
                "Run: pip install pymupdf\n"
            )
            raise PDFParseError("pymupdf not available")
        return fitz

    @staticmethod
    def _require_pypdf() -> Any:
        """Return the imported ``pypdf`` module or raise ``PDFParseError``.

        Companion to ``_require_fitz``; the two helpers keep parser
        availability errors uniform across both surfaces.
        """
        if pypdf is None:  # pragma: no cover — environment-specific
            sys.stderr.write("ERROR: pypdf not installed. Run: pip install pypdf\n")
            raise PDFParseError("pypdf not available")
        return pypdf

    # ------------------------------------------------------------------
    # pymupdf / fitz surface
    # ------------------------------------------------------------------

    @property
    def fitz(self) -> Any:
        """The fitz (pymupdf) ``Document``.

        Opens on first access; raises ``PDFParseError`` wrapping the
        underlying exception if the file cannot be parsed. The document
        is cached — subsequent accesses return the same object.
        """
        self._raise_if_closed()
        if self._fitz_doc is None:
            fitz_mod = self._require_fitz()
            try:
                self._fitz_doc = fitz_mod.open(str(self.path))
            except Exception as exc:
                raise PDFParseError(
                    f"pymupdf could not open {self.path}: {exc}"
                ) from exc
        return self._fitz_doc

    # ------------------------------------------------------------------
    # pypdf surface — opt-in, failure-aware
    # ------------------------------------------------------------------

    def try_pypdf(self) -> tuple[Any | None, Exception | None]:
        """Return ``(pypdf.PdfReader, None)`` on success or
        ``(None, exception)`` on failure.

        The exception is captured on the first attempt and *replayed*
        on subsequent calls — this is what lets the object-layer
        analyzer surface a single ``scan_error`` finding instead of
        repeatedly retrying a known-bad parse. The semantics exactly
        match ``bayyinah_v0_1.PDFContext.try_pypdf`` (byte-for-byte
        behaviour preserved).
        """
        self._raise_if_closed()
        if self._pypdf_reader is not None:
            return self._pypdf_reader, None
        if self._pypdf_error is not None:
            return None, self._pypdf_error
        pypdf_mod = self._require_pypdf()
        try:
            self._pypdf_reader = pypdf_mod.PdfReader(str(self.path))
            return self._pypdf_reader, None
        except Exception as exc:  # noqa: BLE001 — deliberate: pypdf raises broadly
            self._pypdf_error = exc
            return None, exc

    # ------------------------------------------------------------------
    # Raw bytes
    # ------------------------------------------------------------------

    def raw_bytes(self) -> bytes | None:
        """Whole-file bytes, cached. Returns ``None`` if the file read fails.

        Object-layer analyzers use this for raw-stream unicode scans
        (detecting TAG characters and zero-width characters inside PDF
        content streams that do not surface through the parsers'
        abstract APIs). A read failure degrades gracefully — it is not
        catastrophic to the scan.
        """
        self._raise_if_closed()
        if self._raw_bytes is not None:
            return self._raw_bytes
        try:
            self._raw_bytes = self.path.read_bytes()
        except Exception:  # noqa: BLE001 — filesystem-broad on purpose
            self._raw_bytes = None
        return self._raw_bytes

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Release the pymupdf document. Idempotent and safe to call
        on a client whose ``fitz`` was never touched.
        """
        if self._fitz_doc is not None:
            try:
                self._fitz_doc.close()
            except Exception:  # noqa: BLE001 — close is best-effort
                pass
            self._fitz_doc = None
        self._closed = True

    @property
    def is_closed(self) -> bool:
        """``True`` once ``close()`` has been called (idempotently)."""
        return self._closed

    def _raise_if_closed(self) -> None:
        """Guard every parser-surface access against use-after-close.

        Every public accessor (``fitz``, ``try_pypdf``, ``raw_bytes``)
        calls this first. The error message names the offending path so
        a trace from production tells the reader exactly which client
        was reused past its lifecycle.
        """
        if self._closed:
            raise PDFParseError(
                f"PDFClient({self.path}) is closed — parser handles have "
                "been released. Construct a new client if you need to rescan."
            )

    # ------------------------------------------------------------------
    # Context-manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> "PDFClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"PDFClient(path={str(self.path)!r}, "
            f"closed={self._closed}, "
            f"fitz_open={self._fitz_doc is not None}, "
            f"pypdf_open={self._pypdf_reader is not None})"
        )


__all__ = ["PDFClient"]
