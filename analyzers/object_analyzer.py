"""
BatinObjectAnalyzer — the witness for the inner / structural layer
(Al-Baqarah 2:79).

    فَوَيْلٌ لِّلَّذِينَ يَكْتُبُونَ الْكِتَابَ بِأَيْدِيهِمْ ثُمَّ يَقُولُونَ هَٰذَا مِنْ عِندِ اللَّهِ
    لِيَشْتَرُوا بِهِ ثَمَنًا قَلِيلًا

    "So woe to those who write the book with their own hands and then
    say, 'This is from Allah,' in order to sell it for a small price."

The architectural reading: *tahrif* is distortion of the vessel that
carries the text. A document's catalog, its embedded files, its
incremental-update history, its font-level ToUnicode CMaps — these are
the hands that wrote the file. A reader does not see them; an LLM
pulling text from the file does not see them; but they shape what the
file can do on open, what it hides between revisions, and whether the
glyphs a human perceives match the Unicode codepoints a parser
extracts.

BatinObjectAnalyzer reads those hands. It surfaces:

    incremental_update
        Multiple ``%%EOF`` markers — prior revisions live in the same
        file. The default view shows the last revision, but every
        earlier one is still recoverable.

    openaction
        Catalog ``/OpenAction`` — action fired on document open. No
        visible surface indication.

    additional_actions
        Catalog ``/AA`` — actions fired on open, close, save, print.

    javascript
        ``/Names /JavaScript`` name-tree entries OR annotation-level
        ``/A /S /JavaScript`` actions. Executes on open or click.

    hidden_ocg
        Optional Content Groups present in the file but hidden in the
        default view — content hidden from the rendering but still
        extractable by any tool that enumerates all OCGs.

    embedded_file
        Files embedded in the PDF via ``/Names /EmbeddedFiles``.

    file_attachment_annot
        Per-page FileAttachment annotations — another embedding path.

    launch_action
        Annotation ``/A /S /Launch`` — executes a program or opens an
        external file on click.

    metadata_anomaly
        ``/ModDate`` lexicographically precedes ``/CreationDate``.

    tounicode_anomaly
        Font-level ``/ToUnicode`` CMaps whose bfchar / bfrange entries
        map visible glyph CIDs to adversarial Unicode targets
        (zero-width, bidi control, TAG, or Latin homoglyph) — visible
        glyphs render legitimately but extracted text carries payload.

This file is a port of ``bayyinah_v0_1.ObjectLayerAnalyzer``.
Semantics are byte-identical per mechanism: each Finding carries the
same mechanism name, tier, confidence, description, location, surface,
and concealed payload as v0.1 emits. The Phase 0 fixture tests verify
this. Deltas from v0.1 are structural:

  * Consumes ``infrastructure.PDFClient`` (not ``bayyinah_v0_1.PDFContext``)
  * Returns ``domain.IntegrityReport`` (not ``list[Finding]``) via the
    ``analyzers.base.BaseAnalyzer`` contract
  * Emits ``domain.Finding`` objects whose ``source_layer='batin'`` is
    inferred from the mechanism name
  * pypdf-open failures are reported as a v0.1-shape inline scan_error
    finding (mechanism="scan_error", tier=3, confidence=0.5,
    location="document") AND surfaced at report level as
    ``error="Object layer scan error: ..."`` with
    ``scan_incomplete=True`` — preserving v0.1's semantics under the
    new return type.

Additive-only: bayyinah_v0_1.ObjectLayerAnalyzer is unchanged and
still used by v0.1's ScanService. The two analyzers coexist until a
later phase migrates the default pipeline.
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
)
from domain.config import (
    BIDI_CONTROL_CHARS,
    CONFUSABLE_TO_LATIN,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.pdf_client import PDFClient


# ---------------------------------------------------------------------------
# BatinObjectAnalyzer
# ---------------------------------------------------------------------------

class BatinObjectAnalyzer(BaseAnalyzer):
    """Detects concealment at the PDF object / structure (batin) layer.

    Mechanisms emitted (all ``source_layer='batin'``):
        incremental_update, openaction, additional_actions, javascript,
        hidden_ocg, embedded_file, file_attachment_annot, launch_action,
        metadata_anomaly, tounicode_anomaly, scan_error.
    """

    name: ClassVar[str] = "object_layer"
    error_prefix: ClassVar[str] = "Object layer scan error"
    source_layer: ClassVar[SourceLayer] = "batin"

    # ------------------------------------------------------------------
    # Public contract
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:
        """Scan ``file_path`` for batin-layer concealment mechanisms.

        Flow (mirrors v0.1 exactly):
          1. Run the raw-byte ``%%EOF`` scan — works even if pypdf
             cannot open the file, so incremental-update detection
             never depends on a successful parse.
          2. Open pypdf via ``PDFClient.try_pypdf``. If it fails, emit
             a v0.1-shape inline ``scan_error`` finding and return —
             the object walk is skipped but whatever we already found
             in step 1 is preserved.
          3. Otherwise run catalog / metadata / annotation / embedded-
             files / ToUnicode-CMap walks and concatenate findings.
          4. Wrap in an IntegrityReport. When a scan_error was emitted,
             mark ``scan_incomplete=True`` and populate ``error`` with
             the canonical ``"Object layer scan error: ..."`` prefix —
             preserving v0.1's ScanService-level semantics under the
             new return type.
        """
        file_path = Path(file_path)
        client = PDFClient(file_path)
        try:
            findings: list[Finding] = []
            findings.extend(self._scan_incremental_updates(client))

            try:
                reader, err = client.try_pypdf()
            except Exception as exc:  # noqa: BLE001
                # try_pypdf raising (e.g. client already closed) —
                # treat as the canonical open failure.
                reader, err = None, exc

            if err is not None:
                # v0.1-shape inline scan_error — byte-identical to
                # ObjectLayerAnalyzer: confidence 0.5, location
                # "document", description prefix "pypdf could not open".
                findings.append(Finding(
                    mechanism="scan_error",
                    tier=3,
                    confidence=0.5,
                    description=f"pypdf could not open the document: {err}",
                    location="document",
                    surface="(object walk skipped)",
                    concealed=str(err),
                ))
                return IntegrityReport(
                    file_path=str(file_path),
                    integrity_score=compute_muwazana_score(findings),
                    findings=findings,
                    error=f"{self.error_prefix}: {err}",
                    scan_incomplete=True,
                )

            findings.extend(self._scan_catalog(reader))
            findings.extend(self._scan_metadata(reader))
            findings.extend(self._scan_annotations(reader))
            findings.extend(self._scan_embedded_files(reader))
            findings.extend(self._scan_tounicode_cmaps(reader))
            # v1.1.2 Day 2 mechanism 04 - PDF document-metadata
            # concealment via /Info dict and XMP stream. Classifies as
            # batin (object-graph signal independent of the rendered
            # surface) and runs in parallel to the v1.1.1 metadata
            # walk above; does not modify _scan_metadata. Local import
            # to keep the module head untouched. Closes pdf_gauntlet
            # fixture 04_metadata.pdf.
            from analyzers.pdf_metadata_analyzer import detect_pdf_metadata_analyzer
            findings.extend(detect_pdf_metadata_analyzer(file_path))

            return IntegrityReport(
                file_path=str(file_path),
                integrity_score=compute_muwazana_score(findings),
                findings=findings,
            )
        finally:
            client.close()

    # ==================================================================
    # Mechanism 1: incremental updates (raw-byte %%EOF scan)
    # ==================================================================

    def _scan_incremental_updates(self, client: PDFClient) -> list[Finding]:
        """Detect incremental-update trails via raw ``%%EOF`` counts.

        A PDF's byte stream may contain multiple ``%%EOF`` markers
        when the document was saved incrementally — each marker ends a
        revision. Only the final revision is rendered by default, but
        every earlier one is still present in the file and recoverable
        by any parser that chooses to walk them.

        Missing raw bytes (file-read failure) degrades to an empty
        finding list rather than raising. A single ``%%EOF`` is normal
        and emits nothing.
        """
        data = client.raw_bytes()
        if data is None:
            return []
        eof_positions = [m.start() for m in re.finditer(rb"%%EOF", data)]
        if len(eof_positions) <= 1:
            return []
        return [Finding(
            mechanism="incremental_update",
            tier=TIER["incremental_update"],
            confidence=0.7,
            description=(
                f"Document contains {len(eof_positions)} %%EOF markers, indicating "
                f"{len(eof_positions) - 1} incremental update(s). Prior revisions may "
                "contain content not rendered in the current view."
            ),
            location=f"byte offsets {eof_positions}",
            surface="(current rendering shows single version)",
            concealed=f"({len(eof_positions)} document revisions present in file)",
        )]

    # ==================================================================
    # Mechanism 2: catalog walks (/OpenAction, /AA, /Names /JavaScript,
    #                             /OCProperties /D /OFF)
    # ==================================================================

    def _scan_catalog(self, reader: Any) -> list[Finding]:
        """Walk the PDF catalog for action-bearing and visibility-hiding entries.

        Emits findings for four independent catalog surfaces:

          * ``/OpenAction`` — action fired on document open.
          * ``/AA``         — additional actions (open/close/save/print/…).
          * ``/Names /JavaScript`` — JavaScript name-tree presence.
          * ``/OCProperties /D /OFF`` — Optional Content Groups hidden
            in the default view.

        Each surface is wrapped in a defensive ``try``/``except``: a
        malformed catalog entry should not abort the whole walk, and
        the other surfaces still report.
        """
        findings: list[Finding] = []
        try:
            catalog = reader.trailer["/Root"]
        except Exception:
            return findings

        if "/OpenAction" in catalog:
            action = catalog["/OpenAction"]
            findings.append(Finding(
                mechanism="openaction",
                tier=TIER["openaction"],
                confidence=0.9,
                description=(
                    "Document declares /OpenAction — action triggered on document open. "
                    f"Action subtype: {self._describe_action_subtype(action)}."
                ),
                location="catalog /OpenAction",
                surface="(no visible indication on open)",
                concealed=self._safe_str(action)[:500],
            ))

        if "/AA" in catalog:
            findings.append(Finding(
                mechanism="additional_actions",
                tier=TIER["additional_actions"],
                confidence=0.85,
                description=(
                    "Document declares /AA — additional actions triggered by document "
                    "events (open, close, save, print, etc.)."
                ),
                location="catalog /AA",
                surface="(no visible indication)",
                concealed=self._safe_str(catalog["/AA"])[:500],
            ))

        try:
            names = catalog.get("/Names")
            if names is not None:
                names_obj = names.get_object() if hasattr(names, "get_object") else names
                js = names_obj.get("/JavaScript") if hasattr(names_obj, "get") else None
                if js is not None:
                    findings.append(Finding(
                        mechanism="javascript",
                        tier=TIER["javascript"],
                        confidence=0.99,
                        description=(
                            "Document declares a /JavaScript name tree in the catalog. "
                            "JavaScript can execute on open, on user action, or in "
                            "response to form events."
                        ),
                        location="catalog /Names /JavaScript",
                        surface="(no visible indication)",
                        concealed=self._safe_str(js)[:500],
                    ))
        except Exception:
            pass

        try:
            oc = catalog.get("/OCProperties")
            if oc is not None:
                oc_obj = oc.get_object() if hasattr(oc, "get_object") else oc
                d = oc_obj.get("/D") if hasattr(oc_obj, "get") else None
                if d is not None:
                    d_obj = d.get_object() if hasattr(d, "get_object") else d
                    off = d_obj.get("/OFF") if hasattr(d_obj, "get") else None
                    if off:
                        try:
                            n_off = len(off)
                        except TypeError:
                            n_off = 1
                        findings.append(Finding(
                            mechanism="hidden_ocg",
                            tier=TIER["hidden_ocg"],
                            confidence=0.8,
                            description=(
                                f"{n_off} Optional Content Group(s) hidden by default. "
                                "Content present in file but not rendered in default view."
                            ),
                            location="catalog /OCProperties /D /OFF",
                            surface="(layer not shown in default rendering)",
                            concealed=self._safe_str(off)[:300],
                        ))
        except Exception:
            pass

        return findings

    @staticmethod
    def _describe_action_subtype(action: Any) -> str:
        """Return the ``/S`` subtype of a PDF action (``/JavaScript``,
        ``/Launch``, ``/URI``, …) or ``"unknown"`` if unreadable.

        Used to enrich ``openaction`` finding descriptions so the
        reader sees *what kind* of action fires on open, not merely
        that one exists.
        """
        try:
            obj = action.get_object() if hasattr(action, "get_object") else action
            if hasattr(obj, "get"):
                s = obj.get("/S")
                return str(s) if s else "unknown"
        except Exception:
            pass
        return "unknown"

    # ==================================================================
    # Mechanism 3: metadata (/Info /CreationDate vs /ModDate)
    # ==================================================================

    def _scan_metadata(self, reader: Any) -> list[Finding]:
        """Emit ``metadata_anomaly`` when ``/ModDate`` precedes ``/CreationDate``.

        This is a tier-3 signal — an anomaly whose interpretation rests
        with the reader. A modification earlier than creation typically
        indicates either a metadata tamper or a file cloned from a
        template and not re-stamped; the scanner surfaces the gap and
        lets the investigator decide.
        """
        findings: list[Finding] = []
        try:
            info = reader.metadata
        except Exception:
            return findings
        if info is None:
            return findings
        try:
            cd = info.get("/CreationDate")
            md = info.get("/ModDate")
            if cd and md and str(md) < str(cd):
                findings.append(Finding(
                    mechanism="metadata_anomaly",
                    tier=TIER["metadata_anomaly"],
                    confidence=0.6,
                    description="Modification date precedes creation date.",
                    location="/Info",
                    surface=f"(CreationDate: {cd})",
                    concealed=f"(ModDate:      {md})",
                ))
        except Exception:
            pass
        return findings

    # ==================================================================
    # Mechanism 4: annotations (/FileAttachment, /A /S /Launch|JavaScript)
    # ==================================================================

    def _scan_annotations(self, reader: Any) -> list[Finding]:
        """Per-page annotation walk for file-attachments and active actions.

        Emits findings for:

          * ``/Subtype /FileAttachment`` — an embedded file attached
            to a page (payload-carrier, usually invisible beyond a
            small icon).
          * ``/A /S /Launch`` — annotation whose activation launches
            an external application.
          * ``/A /S /JavaScript`` — annotation whose activation runs
            JavaScript.

        Malformed annotations are skipped rather than fatal — one bad
        annotation should not blind the scan to the rest.
        """
        findings: list[Finding] = []
        for page_idx, page in enumerate(reader.pages):
            try:
                annots = page.get("/Annots")
            except Exception:
                continue
            if annots is None:
                continue
            try:
                annots_list = list(annots)
            except Exception:
                continue
            for annot_ref in annots_list:
                try:
                    annot = (annot_ref.get_object()
                             if hasattr(annot_ref, "get_object") else annot_ref)
                    subtype = str(annot.get("/Subtype", "") or "")
                    if subtype == "/FileAttachment":
                        fs = annot.get("/FS")
                        findings.append(Finding(
                            mechanism="file_attachment_annot",
                            tier=TIER["file_attachment_annot"],
                            confidence=0.95,
                            description=(
                                "File-attachment annotation contains an embedded file."
                            ),
                            location=f"page {page_idx + 1}",
                            surface="(attachment icon or nothing visible)",
                            concealed=self._safe_str(fs)[:300],
                        ))
                    a = annot.get("/A") if hasattr(annot, "get") else None
                    if a is not None:
                        a_obj = a.get_object() if hasattr(a, "get_object") else a
                        s_type = (str(a_obj.get("/S", "") or "")
                                  if hasattr(a_obj, "get") else "")
                        if s_type == "/Launch":
                            findings.append(Finding(
                                mechanism="launch_action",
                                tier=TIER["launch_action"],
                                confidence=0.95,
                                description=(
                                    "Annotation triggers /Launch action — can execute "
                                    "a program or open an external file."
                                ),
                                location=f"page {page_idx + 1}",
                                surface="(click target appears normal)",
                                concealed=self._safe_str(a_obj)[:400],
                            ))
                        elif s_type == "/JavaScript":
                            findings.append(Finding(
                                mechanism="javascript",
                                tier=TIER["javascript"],
                                confidence=0.99,
                                description="Annotation triggers JavaScript action.",
                                location=f"page {page_idx + 1}",
                                surface="(click target appears normal)",
                                concealed=self._safe_str(a_obj)[:500],
                            ))
                except Exception:
                    continue
        return findings

    # ==================================================================
    # Mechanism 5: embedded files (/Names /EmbeddedFiles)
    # ==================================================================

    def _scan_embedded_files(self, reader: Any) -> list[Finding]:
        """Walk ``catalog /Names /EmbeddedFiles`` and report every embedded file.

        Embedded files are present in the document body but have no
        automatic visual surface — a reader typically sees them only if
        a FileAttachment annotation exposes them. The tree walk uses
        ``_walk_names_tree`` to descend both flat ``/Names`` arrays and
        nested ``/Kids`` structures uniformly.
        """
        findings: list[Finding] = []
        try:
            catalog = reader.trailer["/Root"]
            names = catalog.get("/Names")
            if names is None:
                return findings
            names_obj = names.get_object() if hasattr(names, "get_object") else names
            ef = names_obj.get("/EmbeddedFiles") if hasattr(names_obj, "get") else None
            if ef is None:
                return findings
            for name, fspec in self._walk_names_tree(ef):
                findings.append(Finding(
                    mechanism="embedded_file",
                    tier=TIER["embedded_file"],
                    confidence=0.95,
                    description=f"Embedded file '{name}' present in document.",
                    location="catalog /Names /EmbeddedFiles",
                    surface="(no visible indication unless annotation present)",
                    concealed=f"embedded file: {name}",
                ))
        except Exception:
            pass
        return findings

    # ==================================================================
    # Mechanism 6: ToUnicode CMap anomalies
    # ==================================================================

    def _scan_tounicode_cmaps(self, reader: Any) -> list[Finding]:
        """Inspect every page's font resources for adversarial ``/ToUnicode`` CMaps.

        A font's ``/ToUnicode`` CMap tells a text extractor what Unicode
        codepoint each glyph-ID decodes to. An attacker can set up a
        legitimate-looking rendered glyph (e.g. the Latin letter 'a')
        but map its CID to a zero-width character, bidi control, TAG
        character, or a homoglyph — so that what the reader sees and
        what the extractor reads diverge at the font-table level.

        Xref de-duplication keeps shared fonts from being reported
        multiple times across pages. Any individual font-parse error
        is swallowed so one malformed font does not hide the rest.
        """
        findings: list[Finding] = []
        seen_xrefs: set[int] = set()
        for page_idx, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if resources is None:
                    continue
                res_obj = (resources.get_object()
                           if hasattr(resources, "get_object") else resources)
                fonts = res_obj.get("/Font") if hasattr(res_obj, "get") else None
                if fonts is None:
                    continue
                fonts_obj = (fonts.get_object()
                             if hasattr(fonts, "get_object") else fonts)
            except Exception:
                continue
            try:
                font_keys = list(fonts_obj.keys())
            except Exception:
                continue
            for font_key in font_keys:
                try:
                    font_ref = fonts_obj[font_key]
                    font = (font_ref.get_object()
                            if hasattr(font_ref, "get_object") else font_ref)
                    to_unicode = (font.get("/ToUnicode")
                                  if hasattr(font, "get") else None)
                    if to_unicode is None:
                        continue
                    tu = (to_unicode.get_object()
                          if hasattr(to_unicode, "get_object") else to_unicode)
                    xref = getattr(to_unicode, "idnum", None)
                    if xref is not None:
                        if xref in seen_xrefs:
                            continue
                        seen_xrefs.add(xref)
                    try:
                        cmap_bytes = tu.get_data()
                    except Exception:
                        continue
                    cmap_text = cmap_bytes.decode("latin-1", errors="ignore")
                    anomalies = self._parse_tounicode_cmap(cmap_text)
                    if anomalies:
                        previews = anomalies[:6]
                        findings.append(Finding(
                            mechanism="tounicode_anomaly",
                            tier=TIER["tounicode_anomaly"],
                            confidence=0.9,
                            description=(
                                f"Font {font_key!s} on page {page_idx + 1} carries a "
                                f"ToUnicode CMap with {len(anomalies)} entr(y/ies) that "
                                "map visible glyph CIDs to adversarial Unicode targets "
                                "(zero-width, bidi control, TAG, or Latin homoglyph). "
                                "Visible text and extracted text will diverge."
                            ),
                            location=(
                                f"page {page_idx + 1}, font {font_key!s}, /ToUnicode"
                            ),
                            surface="(rendered glyphs look legitimate)",
                            concealed="; ".join(previews)[:400],
                        ))
                except Exception:
                    continue
        return findings

    @staticmethod
    def _parse_tounicode_cmap(cmap_text: str) -> list[str]:
        """Walk a ToUnicode CMap's bfchar/bfrange blocks and return a
        list of human-readable descriptions of each entry whose target
        Unicode is adversarial (zero-width, bidi, TAG, homoglyph)."""
        def hex_to_text(h: str) -> str:
            h = re.sub(r"\s+", "", h)
            if not h or len(h) % 2 != 0:
                return ""
            try:
                data = bytes.fromhex(h)
            except ValueError:
                return ""
            try:
                return data.decode("utf-16-be", errors="replace")
            except Exception:
                return ""

        def is_anomalous(text: str) -> tuple[bool, str]:
            for c in text:
                if c in ZERO_WIDTH_CHARS:
                    return True, f"zero-width U+{ord(c):04X}"
                if c in BIDI_CONTROL_CHARS:
                    return True, f"bidi U+{ord(c):04X}"
                if ord(c) in TAG_CHAR_RANGE:
                    return True, f"TAG U+{ord(c):06X}"
                if c in CONFUSABLE_TO_LATIN:
                    return True, (
                        f"homoglyph U+{ord(c):04X} (looks like "
                        f"'{CONFUSABLE_TO_LATIN[c]}')"
                    )
            return False, ""

        anomalies: list[str] = []

        for m in re.finditer(
            r"beginbfchar(.*?)endbfchar", cmap_text, re.DOTALL,
        ):
            block = m.group(1)
            for entry in re.finditer(
                r"<\s*([0-9A-Fa-f]+)\s*>\s*<\s*([0-9A-Fa-f]+)\s*>", block,
            ):
                src_hex, tgt_hex = entry.group(1), entry.group(2)
                tgt_text = hex_to_text(tgt_hex)
                bad, reason = is_anomalous(tgt_text)
                if bad:
                    anomalies.append(
                        f"CID<{src_hex}> → {tgt_text!r}  [{reason}]"
                    )

        for m in re.finditer(
            r"beginbfrange(.*?)endbfrange", cmap_text, re.DOTALL,
        ):
            block = m.group(1)
            for entry in re.finditer(
                r"<\s*([0-9A-Fa-f]+)\s*>\s*<\s*([0-9A-Fa-f]+)\s*>\s*"
                r"(<\s*[0-9A-Fa-f]+\s*>|\[[^\]]*\])",
                block,
            ):
                src_lo_hex, src_hi_hex, tgt_part = (
                    entry.group(1), entry.group(2), entry.group(3),
                )
                if tgt_part.startswith("<"):
                    tgt_text = hex_to_text(tgt_part.strip("<> \t\n\r"))
                    bad, reason = is_anomalous(tgt_text)
                    if bad:
                        anomalies.append(
                            f"CIDs<{src_lo_hex}>-<{src_hi_hex}> start→ {tgt_text!r}  "
                            f"[{reason}]"
                        )
                else:
                    for tm in re.finditer(r"<\s*([0-9A-Fa-f]+)\s*>", tgt_part):
                        tgt_text = hex_to_text(tm.group(1))
                        bad, reason = is_anomalous(tgt_text)
                        if bad:
                            anomalies.append(
                                f"CIDs<{src_lo_hex}>-<{src_hi_hex}> entry→ "
                                f"{tgt_text!r}  [{reason}]"
                            )
        return anomalies

    # ==================================================================
    # Shared helpers
    # ==================================================================

    def _walk_names_tree(self, node: Any) -> list[tuple[str, Any]]:
        """Walk a PDF Names tree and collect ``(name, value)`` pairs
        from its leaves. Used by the /EmbeddedFiles walk."""
        out: list[tuple[str, Any]] = []
        try:
            obj = node.get_object() if hasattr(node, "get_object") else node
            if hasattr(obj, "get"):
                ns = obj.get("/Names")
                if ns:
                    seq = list(ns)
                    for i in range(0, len(seq) - 1, 2):
                        out.append((str(seq[i]), seq[i + 1]))
                kids = obj.get("/Kids")
                if kids:
                    for kid in kids:
                        out.extend(self._walk_names_tree(kid))
        except Exception:
            pass
        return out

    @staticmethod
    def _safe_str(obj: Any) -> str:
        """``str(obj)``, falling back to ``repr(obj)`` if that raises —
        pypdf's indirect-object wrappers occasionally need this."""
        try:
            return str(obj)
        except Exception:
            return repr(obj)


__all__ = ["BatinObjectAnalyzer"]
