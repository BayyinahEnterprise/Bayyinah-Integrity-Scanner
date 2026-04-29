"""
DocxAnalyzer — both witnesses at once for Office Open XML documents.

    قَالُوا إِنَّمَا نَحْنُ مُصْلِحُونَ أَلَا إِنَّهُمْ هُمُ الْمُفْسِدُونَ
    وَلَـٰكِن لَّا يَشْعُرُونَ
    (Al-Baqarah 2:11-12)

    "They say, 'We are but reformers.' Unquestionably, it is they who
    are the corrupters, but they perceive it not."

Architectural reading. A Word document (.docx) is a *double* surface
— just like a JSON file, but with more places for concealment to
live:

  * Zahir (rendered text) — the paragraphs a reader sees in Word,
    encoded as ``<w:t>`` elements inside ``word/document.xml``. The
    same zero-width / TAG-block / bidi / homoglyph concealment vectors
    that apply to plain text apply here, plus one DOCX-specific shape:
    a run marked with ``<w:vanish/>`` is rendered as zero-width but
    still lives in the document's text stream — every downstream
    indexer, LLM, or search crawler reads it.

  * Batin (object graph) — the ZIP container carries parts the reader
    never sees: VBA macros (``word/vbaProject.bin``), embedded OLE
    objects (``word/embeddings/*``), altChunk parts pulling in foreign
    content, external relationships reaching out of the document at
    render time, and tracked-changes metadata that preserves edit
    history in the final file.

``DocxAnalyzer`` is therefore both a batin witness (structural /
relationship inspection) and a zahir witness (per-run text-layer
concealment). ``source_layer`` is set per-finding; the class default
(``batin``) applies to ``scan_error`` findings emitted by the base
helper.

Supported FileKinds: ``{FileKind.DOCX}``. The router already classifies
DOCX files (PK ZIP magic + .docx extension); this analyzer is the
client the router's dispatch was waiting for.

Additive-only. Nothing in this module is imported by ``bayyinah_v0.py``
or ``bayyinah_v0_1.py``; the PDF pipeline is untouched. The new
mechanisms are registered in ``domain/config.py`` alongside the
existing mechanism catalog — old mechanism names, severities, and
tiers are unchanged.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import ClassVar, Iterable
from xml.etree import ElementTree as ET

from analyzers.base import BaseAnalyzer
from analyzers.docx_white_text import detect_docx_white_text
from analyzers.docx_microscopic_font import detect_docx_microscopic_font
from analyzers.docx_metadata_payload import detect_docx_metadata_payload
from analyzers.docx_comment_payload import detect_docx_comment_payload
from analyzers.docx_header_footer_payload import detect_docx_header_footer_payload
from analyzers.docx_orphan_footnote import detect_docx_orphan_footnote
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
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Read limit — 32 MB bounds the footprint of a single DOCX scan. Ample
# for every realistic document; adversarial ZIP bombs are truncated
# rather than decompressed unbounded.
_MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024

# The DOCX namespace URI for the WordprocessingML content. Stable since
# Office 2007; every .docx in the wild uses this exact string.
_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# The Office Open XML relationships namespace.
_R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# Namespace prefix map used by ElementTree find/findall calls.
_NAMESPACES = {"w": _W_NS, "r": _R_NS}

_LATIN_RANGES = (
    range(0x0041, 0x005B),  # A-Z
    range(0x0061, 0x007B),  # a-z
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


# ---------------------------------------------------------------------------
# DocxAnalyzer
# ---------------------------------------------------------------------------


class DocxAnalyzer(BaseAnalyzer):
    """Detects structural and embedded concealment in DOCX files.

    The analyzer opens the file as a ZIP, inspects the member list and
    the relationships graph for batin-layer concealment (VBA, embedded
    objects, altChunks, external refs, revision history), then parses
    ``word/document.xml`` for zahir-layer concealment at per-run
    granularity (zero-width / TAG / bidi / homoglyph, plus DOCX-specific
    vanish-marked hidden runs).

    Corrupt / non-ZIP / malformed-XML inputs are converted to a single
    ``scan_error`` finding via ``_scan_error_report`` — consistent with
    the middle-community contract (Al-Baqarah 2:143): one witness
    failing does not silence the others, and the failure itself is a
    signal.
    """

    name: ClassVar[str] = "docx"
    error_prefix: ClassVar[str] = "DOCX scan error"
    # Class default — ``scan_error`` findings are structural in nature
    # (the inner state was not inspected). Per-finding source_layer is
    # set individually for every zahir / batin detector below.
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.DOCX})

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the DOCX file at ``file_path``."""
        try:
            zf = zipfile.ZipFile(file_path, "r")
        except (zipfile.BadZipFile, OSError) as exc:
            return self._scan_error_report(
                file_path,
                f"could not open as ZIP: {exc}",
            )

        try:
            findings = list(self._scan_zip(zf, file_path))
        except Exception as exc:  # noqa: BLE001 — deliberately broad
            return self._scan_error_report(
                file_path,
                f"unexpected failure during DOCX scan: {exc}",
            )
        finally:
            zf.close()

        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Central walk — emits every finding for this document
    # ------------------------------------------------------------------

    def _scan_zip(
        self, zf: zipfile.ZipFile, file_path: Path,
    ) -> Iterable[Finding]:
        names = zf.namelist()

        # ---- Batin (structural) ----
        yield from self._detect_vba_macros(names, file_path)
        yield from self._detect_embedded_objects(names, file_path)
        yield from self._detect_alt_chunks(names, zf, file_path)
        yield from self._detect_external_relationships(names, zf, file_path)

        # ---- v1.1.2 hidden-text payload detectors (zahir + batin) ----
        # Each detector opens the file independently as a ZipFile so it
        # can be reused outside the orchestrator (mirrors the PDF
        # v1.1.2 pattern). Cheap relative to the parse work already
        # done in this module; ZIP central-directory reads are O(1).
        yield from detect_docx_white_text(file_path)
        yield from detect_docx_microscopic_font(file_path)
        yield from detect_docx_header_footer_payload(file_path)
        yield from detect_docx_metadata_payload(file_path)
        yield from detect_docx_comment_payload(file_path)
        yield from detect_docx_orphan_footnote(file_path)

        # ---- Zahir (rendered text) + revision history (batin) ----
        # Both signals come from document.xml: we parse once and split
        # the findings by source layer at emission time.
        if "word/document.xml" in names:
            xml_bytes = self._read_bounded(zf, "word/document.xml")
            if xml_bytes is not None:
                try:
                    root = ET.fromstring(xml_bytes)
                except ET.ParseError as exc:
                    yield Finding(
                        mechanism="scan_error",
                        tier=TIER["scan_error"],
                        confidence=1.0,
                        description=(
                            f"Could not parse word/document.xml: {exc}"
                        ),
                        location=f"{file_path}:word/document.xml",
                        surface="(document body unparsable)",
                        concealed=(
                            "absence of zahir findings cannot be "
                            "taken as cleanness"
                        ),
                        source_layer="batin",
                    )
                else:
                    yield from self._detect_hidden_text(root, file_path)
                    yield from self._detect_revision_history(root, file_path)
                    yield from self._scan_text_runs(root, file_path)

    # ------------------------------------------------------------------
    # Batin — VBA macros
    # ------------------------------------------------------------------

    def _detect_vba_macros(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once if a VBA project binary is present anywhere.

        A ``vbaProject.bin`` entry means the document ships executable
        macro code. This is DOCX's analogue of PDF ``javascript`` — the
        payload activates the moment the user allows content.
        """
        vba_entries = [n for n in names if n.endswith("vbaProject.bin")]
        if not vba_entries:
            return
        listing = ", ".join(sorted(vba_entries))
        yield Finding(
            mechanism="docx_vba_macros",
            tier=TIER["docx_vba_macros"],
            confidence=1.0,
            description=(
                f"DOCX ships a VBA project binary ({listing}). "
                "VBA macros are active code — they execute when the "
                "reader enables content. A .docx that carries them has "
                "the same attack surface as a .docm; the extension "
                "alone does not disclose it."
            ),
            location=f"{file_path}:{listing}",
            surface="(document appears to be an ordinary .docx)",
            concealed="embedded VBA macro binary",
            source_layer="batin",
        )

    # ------------------------------------------------------------------
    # Batin — embedded OLE objects / other files
    # ------------------------------------------------------------------

    def _detect_embedded_objects(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once per file under ``word/embeddings/``.

        DOCX's analogue of PDF ``embedded_file``. An embedded OLE blob
        can be an Excel workbook (potentially with its own macros), a
        packaged executable, or any arbitrary file type the author
        chose to ride along.
        """
        for entry in names:
            if not entry.startswith("word/embeddings/"):
                continue
            # Skip directory entries (ZIP sometimes lists them).
            if entry.endswith("/"):
                continue
            basename = entry.rsplit("/", 1)[-1]
            yield Finding(
                mechanism="docx_embedded_object",
                tier=TIER["docx_embedded_object"],
                confidence=1.0,
                description=(
                    f"DOCX embeds {basename!r} under word/embeddings/. "
                    "Embedded objects are arbitrary files (OLE, Office "
                    "documents, or packaged binaries) stored inside "
                    "the document and accessible to the reader via "
                    "double-click or via programmatic extraction."
                ),
                location=f"{file_path}:{entry}",
                surface="(no inline rendering hint)",
                concealed=f"embedded file {basename!r}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Batin — altChunk parts (foreign-content injection)
    # ------------------------------------------------------------------

    def _detect_alt_chunks(
        self,
        names: list[str],
        zf: zipfile.ZipFile,
        file_path: Path,
    ) -> Iterable[Finding]:
        """Fire if a relationship declares an AltChunk target.

        altChunk inserts the contents of another document (HTML, MHT,
        DOCX, XML) at render time. It is the DOCX mechanism closest to
        SVG's ``<use xlink:href=...>`` or ``<iframe>`` in HTML: a
        pointer from the main body to a wholly separate payload, whose
        origin is disjoint from the document's own text stream.
        """
        # The altChunk relationship type string is stable across all
        # modern OOXML versions.
        alt_chunk_type = (
            "http://schemas.openxmlformats.org/officeDocument/2006/"
            "relationships/aFChunk"
        )
        rels_entries = [n for n in names if n.endswith(".rels")]
        seen_targets: list[tuple[str, str]] = []  # (rels entry, target)

        for rels_entry in rels_entries:
            xml_bytes = self._read_bounded(zf, rels_entry)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError:
                continue
            for rel in root.findall(f"{{{_R_NS}}}Relationship"):
                rel_type = rel.get("Type", "")
                target = rel.get("Target", "")
                if rel_type == alt_chunk_type:
                    seen_targets.append((rels_entry, target))

        for rels_entry, target in seen_targets:
            yield Finding(
                mechanism="docx_alt_chunk",
                tier=TIER["docx_alt_chunk"],
                confidence=0.95,
                description=(
                    f"DOCX declares an altChunk relationship → "
                    f"{target!r} in {rels_entry}. altChunk inserts "
                    "the content of another document at render time; "
                    "the inserted content is outside the main body's "
                    "text stream and may not be visible in a casual "
                    "review of document.xml."
                ),
                location=f"{file_path}:{rels_entry}",
                surface="(no paragraph-level indicator)",
                concealed=f"altChunk target {target!r}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Batin — external relationships
    # ------------------------------------------------------------------

    def _detect_external_relationships(
        self,
        names: list[str],
        zf: zipfile.ZipFile,
        file_path: Path,
    ) -> Iterable[Finding]:
        """Fire per relationship with ``TargetMode="External"``.

        External relationships make the document reach outside itself
        when opened — remote images (tracking beacons), remote
        stylesheets, remote templates. Parallels
        ``svg_external_reference``.
        """
        rels_entries = [n for n in names if n.endswith(".rels")]
        for rels_entry in rels_entries:
            xml_bytes = self._read_bounded(zf, rels_entry)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError:
                continue
            for rel in root.findall(f"{{{_R_NS}}}Relationship"):
                mode = rel.get("TargetMode", "")
                target = rel.get("Target", "")
                if mode != "External":
                    continue
                yield Finding(
                    mechanism="docx_external_relationship",
                    tier=TIER["docx_external_relationship"],
                    confidence=0.9,
                    description=(
                        f"DOCX declares an external relationship → "
                        f"{target!r} in {rels_entry}. External refs "
                        "cause the document to reach outside itself "
                        "when opened; common vectors include remote "
                        "images, remote templates, and tracking "
                        "beacons."
                    ),
                    location=f"{file_path}:{rels_entry}",
                    surface="(no inline rendering indicator)",
                    concealed=f"external target {target!r}",
                    source_layer="batin",
                )

    # ------------------------------------------------------------------
    # Batin — revision history
    # ------------------------------------------------------------------

    def _detect_revision_history(
        self, root: ET.Element, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once if ``<w:ins>`` or ``<w:del>`` appears anywhere.

        Tracked changes preserve edit history. The final rendered view
        shows the accepted-or-rejected state; the prior revision is
        not visible to a reader who merely opens the document. DOCX's
        analogue of PDF ``incremental_update``.
        """
        ins_nodes = root.findall(f".//{{{_W_NS}}}ins")
        del_nodes = root.findall(f".//{{{_W_NS}}}del")
        if not ins_nodes and not del_nodes:
            return
        yield Finding(
            mechanism="docx_revision_history",
            tier=TIER["docx_revision_history"],
            confidence=0.95,
            description=(
                f"DOCX preserves {len(ins_nodes)} inserted and "
                f"{len(del_nodes)} deleted revision(s) inside "
                "document.xml. The rendered view only shows the "
                "accepted state; prior content is accessible to any "
                "parser that walks w:ins / w:del elements."
            ),
            location=f"{file_path}:word/document.xml",
            surface="(rendered document shows accepted state only)",
            concealed=(
                f"{len(ins_nodes)} inserted / {len(del_nodes)} "
                "deleted revision element(s)"
            ),
            source_layer="batin",
        )

    # ------------------------------------------------------------------
    # Zahir — hidden text via <w:vanish/>
    # ------------------------------------------------------------------

    def _detect_hidden_text(
        self, root: ET.Element, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once per run whose run-properties contain ``<w:vanish/>``.

        Word renders ``<w:vanish/>`` runs as zero-width on screen, but
        the text remains in the document's codepoint stream — every
        downstream indexer, LLM ingesting the docx text, or search
        crawler reads it.
        """
        vanish_tag = f"{{{_W_NS}}}vanish"
        rpr_tag = f"{{{_W_NS}}}rPr"
        r_tag = f"{{{_W_NS}}}r"
        t_tag = f"{{{_W_NS}}}t"

        run_index = 0
        for run in root.iter(r_tag):
            run_index += 1
            rpr = run.find(rpr_tag)
            if rpr is None or rpr.find(vanish_tag) is None:
                continue
            text_pieces = [
                (t.text or "") for t in run.findall(t_tag)
            ]
            hidden_text = "".join(text_pieces)
            if not hidden_text:
                # A vanish-marked run with no text is harmless — skip.
                continue
            preview = hidden_text[:120]
            yield Finding(
                mechanism="docx_hidden_text",
                tier=TIER["docx_hidden_text"],
                confidence=1.0,
                description=(
                    f"Run #{run_index} in word/document.xml carries "
                    "<w:vanish/> in its run-properties, suppressing "
                    "it from the rendered page while leaving the "
                    "text in the document's stream for indexers and "
                    f"LLMs. Preview: {preview!r}."
                ),
                location=f"{file_path}:word/document.xml:run{run_index}",
                surface="(rendered as zero-width)",
                concealed=f"hidden run text {preview!r}",
                source_layer="zahir",
            )

    # ------------------------------------------------------------------
    # Zahir — per-run zero-width / TAG / bidi / homoglyph scans
    # ------------------------------------------------------------------

    def _scan_text_runs(
        self, root: ET.Element, file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every ``<w:t>`` element and run the zahir detectors.

        Each ``<w:t>`` is the text content of one run; the per-run
        granularity lets the finding's ``location`` point a reader to
        the exact paragraph and run.
        """
        t_tag = f"{{{_W_NS}}}t"
        p_tag = f"{{{_W_NS}}}p"

        # Build a paragraph index so each text finding can be located by
        # paragraph number. We iterate over paragraphs and run-index
        # within — stable across Word versions, since the ordering in
        # document.xml matches the on-page reading order.
        paragraph_index = 0
        for paragraph in root.iter(p_tag):
            paragraph_index += 1
            run_index_in_para = 0
            for text_el in paragraph.iter(t_tag):
                run_index_in_para += 1
                value = text_el.text or ""
                if not value:
                    continue
                loc = (
                    f"{file_path}:word/document.xml:"
                    f"p{paragraph_index}:t{run_index_in_para}"
                )
                yield from self._scan_string(value, loc)

    def _scan_string(
        self, value: str, location: str,
    ) -> Iterable[Finding]:
        """Zahir-layer checks applied to a single run's text value.

        Structured like ``JsonAnalyzer._scan_string_value`` — each
        mechanism surfaces at most once per run; the location already
        pins the reader to the exact paragraph/run coordinates.
        """
        # Zero-width.
        zw = [c for c in value if c in ZERO_WIDTH_CHARS]
        if zw:
            codepoints = ", ".join(sorted({f"U+{ord(c):04X}" for c in zw}))
            yield Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.9,
                description=(
                    f"{len(zw)} zero-width character(s) in this text "
                    f"run ({codepoints}) — invisible to a human "
                    "reader, preserved by parsers and tokenizers."
                ),
                location=location,
                surface="(no visible indication)",
                concealed=f"{len(zw)} zero-width codepoint(s)",
                source_layer="zahir",
            )

        # TAG block.
        tags = [c for c in value if ord(c) in TAG_CHAR_RANGE]
        if tags:
            shadow = "".join(
                chr(ord(c) - 0xE0000) if 0x20 <= ord(c) - 0xE0000 <= 0x7E
                else "?"
                for c in tags
            )
            yield Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=1.0,
                description=(
                    f"{len(tags)} Unicode TAG character(s) in this "
                    "text run. TAG codepoints are invisible to human "
                    "readers and decodable by LLMs — a documented "
                    "prompt-injection smuggling vector. Decoded "
                    f"shadow: {shadow!r}."
                ),
                location=location,
                surface="(no visible indication)",
                concealed=f"TAG payload ({len(tags)} codepoints)",
                source_layer="zahir",
            )

        # Bidi-control.
        bidi = [c for c in value if c in BIDI_CONTROL_CHARS]
        if bidi:
            codepoints = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in bidi})
            )
            yield Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(bidi)} bidi-control character(s) in this "
                    f"text run ({codepoints}) — reorders display "
                    "without changing the codepoint stream."
                ),
                location=location,
                surface="(reordered display)",
                concealed=f"{len(bidi)} bidi-override codepoint(s)",
                source_layer="zahir",
            )

        # Homoglyph — word-level mix of Latin + confusable.
        for word in value.split():
            if len(word) < 2:
                continue
            confusables = [c for c in word if c in CONFUSABLE_TO_LATIN]
            latin_letters = [c for c in word if _is_latin_letter(c)]
            if not confusables:
                continue
            if not (latin_letters or len(confusables) >= 2):
                continue
            recovered = "".join(
                CONFUSABLE_TO_LATIN.get(c, c) for c in word
            )
            cp_info = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in confusables})
            )
            yield Finding(
                mechanism="homoglyph",
                tier=TIER["homoglyph"],
                confidence=0.85,
                description=(
                    f"Word mixes Latin letters with {len(confusables)} "
                    f"confusable codepoint(s) ({cp_info}) — visually "
                    f"impersonates {recovered!r}."
                ),
                location=location,
                surface=word,
                concealed=f"appears identical to {recovered!r}",
                source_layer="zahir",
            )

    # ------------------------------------------------------------------
    # Bounded ZIP read helper
    # ------------------------------------------------------------------

    def _read_bounded(
        self, zf: zipfile.ZipFile, name: str,
    ) -> bytes | None:
        """Read ``name`` from the ZIP, bounded by _MAX_UNCOMPRESSED_BYTES.

        Returns ``None`` if the entry is missing or unreadable. The
        size check reads the ZipInfo's declared uncompressed size
        before extracting, so a ZIP bomb never materialises more than
        a few ZipInfo records before we bail.
        """
        try:
            info = zf.getinfo(name)
        except KeyError:
            return None
        if info.file_size > _MAX_UNCOMPRESSED_BYTES:
            return None
        try:
            with zf.open(info) as fh:
                return fh.read(_MAX_UNCOMPRESSED_BYTES)
        except (zipfile.BadZipFile, OSError, RuntimeError):
            return None


__all__ = ["DocxAnalyzer"]
