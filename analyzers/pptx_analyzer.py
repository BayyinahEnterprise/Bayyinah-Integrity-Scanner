"""
PptxAnalyzer — Al-Baqarah 2:79 applied to the presentation surface.

    وَيْلٌ لِّلَّذِينَ يَكْتُبُونَ الْكِتَابَ بِأَيْدِيهِمْ ثُمَّ يَقُولُونَ
    هَٰذَا مِنْ عِندِ اللَّهِ لِيَشْتَرُوا بِهِ ثَمَنًا قَلِيلًا ۖ فَوَيْلٌ لَّهُم
    مِّمَّا كَتَبَتْ أَيْدِيهِمْ وَوَيْلٌ لَّهُم مِّمَّا يَكْسِبُونَ
    (Al-Baqarah 2:79)

    "Woe to those who write the book with their own hands, then say,
    'This is from Allah,' in order to exchange it for a small price.
    Woe to them for what their hands have written and woe to them for
    what they earn."

Architectural reading. A presentation is a visual artefact designed to
carry the presenter's authority: the audience sees slides, the presenter
reads notes, and downstream pipelines (search indexers, LLM ingestion
paths, knowledge-base summarisers) extract "all text" from the archive.
Those three readers see three different documents. The PPTX format is
the attack surface that makes the divergence possible, at least seven
places where the surface and the stored content disagree:

  * Zahir (rendered slide body) — the text the audience reads while the
    deck is presented. ``<a:t>`` text runs inside ``ppt/slides/slide*.xml``.
    Shared zahir detectors (zero-width, TAG, bidi, homoglyph, math
    alphanumeric) apply uniformly to every text run across every slide.

  * Batin (archive graph) — parts the audience never sees:
      - ``ppt/vbaProject.bin`` (macros — active code on content-enable).
      - ``ppt/embeddings/*`` (embedded OLE objects / other files).
      - ``ppt/presentation.xml`` declaring slides as ``show="0"`` (hidden
        from presentation, text still in the archive).
      - ``ppt/notesSlides/notesSlide*.xml`` (speaker notes — the highest-
        priority performed-alignment surface in PPTX: visible slides
        appear clean while notes carry prompt injections that every AI
        ingestion pipeline reads).
      - ``ppt/slideMasters/*`` / ``ppt/slideLayouts/*`` (master/layout
        templates that render *behind* every slide using them — a payload
        placed on the master overlays every body slide).
      - ``ppt/commentAuthors.xml`` / ``ppt/comments/*`` /
        ``ppt/revisionInfo.xml`` (revision history).
      - ``ppt/externalLinks/*`` or any ``TargetMode="External"``
        relationship (the archive reaches outside when opened).
      - Action hyperlinks inside shapes: ``<a:hlinkClick>`` /
        ``<a:hlinkMouseOver>`` with ``action="ppaction://..."`` or
        ``action="macro:..."`` — click/hover dispatches out of the
        visible shape caption.
      - ``customXml/*`` parts carrying arbitrary payloads under a part
        type most readers never inspect.

``PptxAnalyzer`` is therefore both a batin witness (structural /
relationship / parts inspection) and a zahir witness (per-run text
concealment). ``source_layer`` is set per-finding; the class default
(``batin``) applies to ``scan_error`` findings emitted by the base
helper.

Supported FileKinds: ``{FileKind.PPTX}``. The router classifies PPTX
files (PK ZIP magic + .pptx extension, or ZIP magic + ppt/presentation.xml
part visible in the head of the archive); this analyzer is the client
the router's dispatch was waiting for.

Additive-only. Nothing in this module is imported by ``bayyinah_v0.py``
or ``bayyinah_v0_1.py``; the PDF pipeline is untouched. The new
mechanisms are registered in ``domain/config.py`` alongside the
existing mechanism catalog — old mechanism names, severities, and
tiers are unchanged.

Reference: Munafiq Protocol §9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import ClassVar, Iterable
from xml.etree import ElementTree as ET

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
    MATH_ALPHANUMERIC_RANGE,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Read limit — 32 MB bounds the footprint of a single PPTX scan. Ample
# for every realistic deck; adversarial ZIP bombs are truncated rather
# than decompressed unbounded. Matches the DocxAnalyzer / XlsxAnalyzer
# bound.
_MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024

# PresentationML namespace — stable since Office 2007. Every .pptx in
# the wild uses this exact string.
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"

# DrawingML namespace — where ``<a:t>`` text runs, ``<a:hlinkClick>``,
# ``<a:hlinkMouseOver>``, etc. live.
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"

# Office Open XML relationships namespace — shared with DOCX / XLSX.
_R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# Customised prompt-injection keyword patterns. The notes-as-injection
# shape is specifically: plain-text instructions aimed at an AI
# ingestion pipeline. These anchors catch the canonical openings without
# firing on ordinary speaker notes. Case-insensitive matching.
_PROMPT_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "Ignore (all / any / the) previous|prior instructions"
    re.compile(
        r"\bignore\s+(?:all\s+|any\s+|the\s+)?"
        r"(?:previous|prior|above|earlier)\s+"
        r"(?:instruction|direction|prompt|command|rule)s?\b",
        re.IGNORECASE,
    ),
    # "System: " or "System prompt:" — common prompt-injection header.
    re.compile(
        r"\b(?:system|assistant|user)\s*:\s*",
        re.IGNORECASE,
    ),
    # "Override (the / your) (instruction|rule|directive)s"
    re.compile(
        r"\boverride\s+(?:the\s+|your\s+)?"
        r"(?:instruction|direction|rule|directive|command|policy)s?\b",
        re.IGNORECASE,
    ),
    # "You are now" / "You are an AI" / "As an AI" — assumption-
    # rewriting openings.
    re.compile(
        r"\b(?:you\s+are\s+now|you\s+are\s+an?\s+AI|as\s+an?\s+AI)\b",
        re.IGNORECASE,
    ),
    # "Forget (everything / your instructions / you were told)"
    re.compile(
        r"\bforget\s+(?:everything|your|all|the)\b",
        re.IGNORECASE,
    ),
)

# Action URI prefixes that indicate a PowerPoint action-dispatch rather
# than a plain hyperlink navigation. ``ppaction://`` is PowerPoint's own
# action-verb scheme (``program``, ``hlink``, ``jump``); ``macro:``
# targets invoke a named macro in the VBA project.
_ACTION_URI_PREFIXES: tuple[str, ...] = (
    "ppaction://",
    "macro:",
    "vbascript:",
)

# Master-part text threshold: below this character count the text run
# is considered trivial template decoration (e.g. "Click to edit Master
# title style") rather than injected content. 16 chars is the smallest
# run that carries enough information to be a meaningful payload.
_MASTER_CONTENT_MIN_LEN: int = 16

# Placeholder text that Office routinely bakes into master/layout parts.
# Text runs with these as their full content (case-insensitive, whitespace
# collapsed) are scaffolding, not content — the mechanism stays silent
# for them.
_MASTER_PLACEHOLDER_TEXTS: frozenset[str] = frozenset({
    "click to edit master title style",
    "click to edit master text style",
    "click to edit master subtitle style",
    "click to edit master footer style",
    "click to edit master date style",
    "click to edit master slide number style",
    "edit master title style",
    "edit master text styles",
    "master title style",
    "master text styles",
    "second level",
    "third level",
    "fourth level",
    "fifth level",
})

# Custom-XML payload threshold: ``customXml/item*.xml`` parts whose
# content is shorter than this are treated as empty shells (the default
# ``<ds:datastoreItem/>`` wrapper). Above this, we surface the part as
# a possible carrier.
_CUSTOM_XML_MIN_LEN: int = 80

_LATIN_RANGES = (
    range(0x0041, 0x005B),  # A-Z
    range(0x0061, 0x007B),  # a-z
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


# ---------------------------------------------------------------------------
# PptxAnalyzer
# ---------------------------------------------------------------------------


class PptxAnalyzer(BaseAnalyzer):
    """Detects structural and embedded concealment in PPTX presentations.

    The analyzer opens the file as a ZIP, inspects the member list and
    the relationships graph for batin-layer concealment (VBA, embedded
    objects, revision history, external links, custom-XML parts), parses
    ``ppt/presentation.xml`` for hidden-slide declarations, walks every
    slide / notes slide / master / layout part for action-hyperlink
    shapes, master-level injected text, and speaker-notes prompt
    patterns, and runs the shared zahir detectors (zero-width / TAG /
    bidi / homoglyph / math-alphanumeric) against every ``<a:t>`` run
    present in slides, notes, masters, and layouts.

    Priority order follows the real-world threat model:

        1. Most dangerous (verified active / embedded content):
           VBA macros, embedded objects.
        2. Most common (structural / template concealment):
           hidden slides, slide-master injection, speaker notes as
           prompt-injection carriers, revision history.
        3. Most subtle (external linkage / dispatch / alternate parts):
           external links, action hyperlinks, custom-XML parts.

    Corrupt / non-ZIP / malformed-XML inputs are converted to a single
    ``scan_error`` finding via ``_scan_error_report`` — consistent with
    the middle-community contract (Al-Baqarah 2:143): one witness
    failing does not silence the others, and the failure itself is a
    signal.
    """

    name: ClassVar[str] = "pptx"
    error_prefix: ClassVar[str] = "PPTX scan error"
    # Class default — ``scan_error`` findings are structural in nature
    # (the inner state was not inspected). Per-finding source_layer is
    # set individually for every zahir / batin detector below.
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.PPTX})

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the PPTX file at ``file_path``."""
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
                f"unexpected failure during PPTX scan: {exc}",
            )
        finally:
            zf.close()

        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Central walk — emits every finding for this deck
    # ------------------------------------------------------------------

    def _scan_zip(
        self, zf: zipfile.ZipFile, file_path: Path,
    ) -> Iterable[Finding]:
        names = zf.namelist()

        # ---- Batin (structural) — priority band 1 ----
        yield from self._detect_vba_macros(names, file_path)
        yield from self._detect_embedded_objects(names, file_path)

        # ---- Batin (structural) — priority band 2 (common) ----
        yield from self._detect_hidden_slides(zf, names, file_path)
        yield from self._detect_revision_history(names, file_path)

        # ---- Batin (structural) — priority band 3 (subtle) ----
        yield from self._detect_external_links(zf, names, file_path)
        yield from self._detect_custom_xml_payloads(zf, names, file_path)

        # ---- Per-part walks: slides, notes, masters, layouts ----
        yield from self._scan_slides(zf, names, file_path)
        yield from self._scan_notes_slides(zf, names, file_path)
        yield from self._scan_slide_masters(zf, names, file_path)
        yield from self._scan_slide_layouts(zf, names, file_path)

    # ------------------------------------------------------------------
    # Batin — VBA macros (priority 1)
    # ------------------------------------------------------------------

    def _detect_vba_macros(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once if a VBA project binary is present anywhere.

        A ``ppt/vbaProject.bin`` entry means the deck ships executable
        macro code. This is PPTX's analogue of PDF ``javascript``,
        ``docx_vba_macros``, and ``xlsx_vba_macros`` — the payload
        activates the moment the user enables content. Presence is
        sufficient.
        """
        vba_entries = [n for n in names if n.endswith("vbaProject.bin")]
        if not vba_entries:
            return
        listing = ", ".join(sorted(vba_entries))
        yield Finding(
            mechanism="pptx_vba_macros",
            tier=TIER["pptx_vba_macros"],
            confidence=1.0,
            description=(
                f"PPTX ships a VBA project binary ({listing}). VBA "
                "macros are active code — they execute when the reader "
                "enables content. A .pptx that carries them has the "
                "same attack surface as a .pptm; the extension alone "
                "does not disclose it."
            ),
            location=f"{file_path}:{listing}",
            surface="(deck appears to be an ordinary .pptx)",
            concealed="embedded VBA macro binary",
            source_layer="batin",
        )

    # ------------------------------------------------------------------
    # Batin — embedded OLE objects / other files (priority 1)
    # ------------------------------------------------------------------

    def _detect_embedded_objects(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once per file under ``ppt/embeddings/``.

        PPTX's analogue of PDF ``embedded_file``, ``docx_embedded_object``,
        and ``xlsx_embedded_object``. An embedded OLE blob can be another
        presentation (with its own macros), a packaged executable, or any
        arbitrary file type the author chose to ride along.
        """
        for entry in names:
            if not entry.startswith("ppt/embeddings/"):
                continue
            # Skip directory entries (ZIP sometimes lists them).
            if entry.endswith("/"):
                continue
            basename = entry.rsplit("/", 1)[-1]
            yield Finding(
                mechanism="pptx_embedded_object",
                tier=TIER["pptx_embedded_object"],
                confidence=1.0,
                description=(
                    f"PPTX embeds {basename!r} under ppt/embeddings/. "
                    "Embedded objects are arbitrary files (OLE, Office "
                    "documents, or packaged binaries) stored inside "
                    "the presentation and accessible to the reader via "
                    "double-click or via programmatic extraction."
                ),
                location=f"{file_path}:{entry}",
                surface="(no inline rendering hint)",
                concealed=f"embedded file {basename!r}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Batin — hidden slides (priority 2)
    # ------------------------------------------------------------------

    def _detect_hidden_slides(
        self, zf: zipfile.ZipFile, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once per slide whose ``show`` attribute is ``"0"``.

        Two places carry the declaration: the ``<p:sldId show="0"/>``
        entry in ``ppt/presentation.xml``'s slide list, and the
        ``<p:sld show="0">`` root attribute on the slide part itself.
        PowerPoint skips ``show="0"`` slides when presenting, but the
        slide part and any associated notes live unchanged in the ZIP
        and are readable by every ingestion pipeline. Parallels
        ``xlsx_hidden_sheet``.
        """
        # Site 1 — presentation.xml's slide list.
        if "ppt/presentation.xml" in names:
            xml_bytes = self._read_bounded(zf, "ppt/presentation.xml")
            if xml_bytes is not None:
                try:
                    root = ET.fromstring(xml_bytes)
                except ET.ParseError:
                    root = None
                if root is not None:
                    for sld_id in root.findall(f".//{{{_P_NS}}}sldId"):
                        if sld_id.get("show", "") != "0":
                            continue
                        sid = sld_id.get("id", "?")
                        rid = sld_id.get(f"{{{_R_NS}}}id", "?")
                        yield Finding(
                            mechanism="pptx_hidden_slide",
                            tier=TIER["pptx_hidden_slide"],
                            confidence=1.0,
                            description=(
                                f"Slide id={sid!r} (rId={rid!r}) is "
                                "declared as show=\"0\" in "
                                "ppt/presentation.xml. PowerPoint skips "
                                "hidden slides during presentation, but "
                                "the slide part and its notes remain in "
                                "the archive."
                            ),
                            location=(
                                f"{file_path}:ppt/presentation.xml:"
                                f"sldId={sid!r}"
                            ),
                            surface=(
                                "(slide hidden from presentation view)"
                            ),
                            concealed=f"slide id={sid!r}",
                            source_layer="batin",
                        )

        # Site 2 — ``<p:sld show="0">`` on slide parts themselves.
        slide_parts = [
            n for n in names
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        ]
        for sp in sorted(slide_parts):
            xml_bytes = self._read_bounded(zf, sp)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError:
                continue
            if root.tag != f"{{{_P_NS}}}sld":
                continue
            if root.get("show", "") != "0":
                continue
            yield Finding(
                mechanism="pptx_hidden_slide",
                tier=TIER["pptx_hidden_slide"],
                confidence=1.0,
                description=(
                    f"Slide part {sp} carries show=\"0\" on the "
                    "<p:sld> root. PowerPoint skips the slide during "
                    "presentation, but the slide's text runs remain in "
                    "the archive."
                ),
                location=f"{file_path}:{sp}",
                surface="(slide hidden from presentation view)",
                concealed=f"slide part {sp}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Batin — revision history (priority 2)
    # ------------------------------------------------------------------

    def _detect_revision_history(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once if any revision-history / comment-history part is present.

        PPTX preserves collaborative state in a small family of parts:
        ``ppt/commentAuthors.xml`` (author registry),
        ``ppt/comments/comment*.xml`` (per-slide comments),
        ``ppt/revisionInfo.xml`` (revision metadata). The final
        presentation view does not display these parts; their content
        is still accessible to any parser that walks the archive.
        Parallels ``docx_revision_history`` and ``xlsx_revision_history``.
        """
        revision_entries = [
            n for n in names
            if (
                n == "ppt/commentAuthors.xml"
                or n.startswith("ppt/comments/")
                or n == "ppt/revisionInfo.xml"
                or n.startswith("ppt/revisions/")
            ) and not n.endswith("/")
        ]
        if not revision_entries:
            return
        listing = ", ".join(sorted(revision_entries))
        yield Finding(
            mechanism="pptx_revision_history",
            tier=TIER["pptx_revision_history"],
            confidence=0.95,
            description=(
                f"PPTX preserves revision / comment history in "
                f"{len(revision_entries)} part(s) ({listing}). The "
                "rendered presentation does not show these parts; their "
                "content is still accessible to any parser that walks "
                "the archive."
            ),
            location=f"{file_path}:ppt/(comments|revisions)/",
            surface="(rendered presentation omits comment/revision parts)",
            concealed=f"{len(revision_entries)} comment/revision part(s)",
            source_layer="batin",
        )

    # ------------------------------------------------------------------
    # Batin — external links (priority 3)
    # ------------------------------------------------------------------

    def _detect_external_links(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Fire on ppt/externalLinks/ parts and TargetMode="External" rels.

        Presentations can reference other workbooks, remote images, or
        external URLs at open time. The references live in two places:
        the ``ppt/externalLinks/`` parts (one per external book) and
        the relationship entries with ``TargetMode="External"`` in the
        ``.rels`` parts across the ZIP. We surface both as the same
        mechanism — a deck that reaches outside itself when opened.
        Parallels ``docx_external_relationship`` and
        ``xlsx_external_link``.
        """
        # External-links parts.
        for entry in names:
            if not entry.startswith("ppt/externalLinks/"):
                continue
            if entry.endswith("/"):
                continue
            basename = entry.rsplit("/", 1)[-1]
            yield Finding(
                mechanism="pptx_external_link",
                tier=TIER["pptx_external_link"],
                confidence=0.9,
                description=(
                    f"PPTX declares an external-link part "
                    f"{basename!r} under ppt/externalLinks/. The deck "
                    "reaches outside itself when opened; common vectors "
                    "include shared-drive references, remote-workbook "
                    "refresh, and cross-document formula evaluation."
                ),
                location=f"{file_path}:{entry}",
                surface="(no visible slide-level indicator)",
                concealed=f"external-link part {basename!r}",
                source_layer="batin",
            )

        # External-mode relationships in any .rels part.
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
                    mechanism="pptx_external_link",
                    tier=TIER["pptx_external_link"],
                    confidence=0.9,
                    description=(
                        f"PPTX declares an external relationship → "
                        f"{target!r} in {rels_entry}. External refs "
                        "cause the deck to reach outside itself when "
                        "opened; common vectors include remote images, "
                        "remote templates, and linked workbooks."
                    ),
                    location=f"{file_path}:{rels_entry}",
                    surface="(no inline slide-level indicator)",
                    concealed=f"external target {target!r}",
                    source_layer="batin",
                )

    # ------------------------------------------------------------------
    # Batin — custom XML payloads (priority 3)
    # ------------------------------------------------------------------

    def _detect_custom_xml_payloads(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Fire on non-trivial ``customXml/*`` parts.

        ``customXml/item*.xml`` is the canonical home for document-data
        binding, but it is also a convenient carrier for arbitrary
        payloads smuggled into an Office archive under a part type most
        readers never inspect. Empty ``<ds:datastoreItem/>`` shells are
        silent; anything substantially larger is surfaced for the
        reader's interpretation (tier 3).
        """
        custom_entries = [
            n for n in names
            if n.startswith("customXml/") and n.endswith(".xml")
            and not n.endswith("/")
        ]
        for entry in sorted(custom_entries):
            data = self._read_bounded(zf, entry)
            if data is None:
                continue
            # Exclude the props schema parts — they are structural
            # metadata, not a payload carrier.
            if entry.endswith("itemProps1.xml") or entry.endswith("itemProps.xml"):
                continue
            if len(data) < _CUSTOM_XML_MIN_LEN:
                continue
            yield Finding(
                mechanism="pptx_custom_xml_payload",
                tier=TIER["pptx_custom_xml_payload"],
                confidence=0.8,
                description=(
                    f"PPTX carries a non-trivial custom-XML part "
                    f"({entry}, {len(data)} bytes). customXml parts are "
                    "legitimate for document-data binding but are also "
                    "a carrier shape for arbitrary payloads; surfaced "
                    "for reader interpretation."
                ),
                location=f"{file_path}:{entry}",
                surface="(custom-XML parts do not render in the deck)",
                concealed=f"custom-XML part of {len(data)} bytes",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Slide walk — per-slide findings + zahir scans on <a:t> runs
    # ------------------------------------------------------------------

    def _scan_slides(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every slide part; emit action-hyperlink + zahir findings."""
        slide_parts = sorted(
            n for n in names
            if n.startswith("ppt/slides/slide") and n.endswith(".xml")
        )
        for sp in slide_parts:
            xml_bytes = self._read_bounded(zf, sp)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError as exc:
                yield Finding(
                    mechanism="scan_error",
                    tier=TIER["scan_error"],
                    confidence=1.0,
                    description=f"Could not parse {sp}: {exc}",
                    location=f"{file_path}:{sp}",
                    surface="(slide body unparsable)",
                    concealed=(
                        "absence of per-run findings cannot be "
                        "taken as cleanness"
                    ),
                    source_layer="batin",
                )
                continue
            yield from self._detect_action_hyperlinks(root, sp, file_path)
            yield from self._scan_text_runs(root, sp, file_path)

    # ------------------------------------------------------------------
    # Notes-slide walk — speaker-notes injection + zahir scans
    # ------------------------------------------------------------------

    def _scan_notes_slides(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every notes-slide part; emit notes-injection + zahir findings.

        Speaker notes are the highest-priority performed-alignment
        surface in PPTX (Al-Baqarah 2:14 — different content for
        different audiences). The audience sees the slide body; the
        presenter reads the notes; an AI ingestion pipeline reads
        *both* and cannot distinguish which is intended for which
        reader.
        """
        notes_parts = sorted(
            n for n in names
            if n.startswith("ppt/notesSlides/notesSlide")
            and n.endswith(".xml")
        )
        for np_ in notes_parts:
            xml_bytes = self._read_bounded(zf, np_)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError as exc:
                yield Finding(
                    mechanism="scan_error",
                    tier=TIER["scan_error"],
                    confidence=1.0,
                    description=f"Could not parse {np_}: {exc}",
                    location=f"{file_path}:{np_}",
                    surface="(notes body unparsable)",
                    concealed=(
                        "absence of per-run findings cannot be "
                        "taken as cleanness"
                    ),
                    source_layer="batin",
                )
                continue
            # Gather all <a:t> text for prompt-injection pattern
            # matching; fire once per notes part that matches.
            texts: list[str] = []
            for t_el in root.iter(f"{{{_A_NS}}}t"):
                value = t_el.text or ""
                if value:
                    texts.append(value)
            joined = " ".join(texts).strip()
            matched_patterns = [
                p.pattern for p in _PROMPT_INJECTION_PATTERNS
                if p.search(joined)
            ]
            if matched_patterns:
                # Truncate the preview for the finding description.
                preview = joined[:200]
                yield Finding(
                    mechanism="pptx_speaker_notes_injection",
                    tier=TIER["pptx_speaker_notes_injection"],
                    confidence=0.85,
                    description=(
                        f"Notes part {np_} contains prompt-injection "
                        "shaped content — speaker notes are invisible "
                        "to the audience during presentation but are "
                        "read by every AI ingestion pipeline that "
                        "extracts \"all text\" from the deck. Matched "
                        f"pattern count: {len(matched_patterns)}. "
                        f"Notes preview: {preview!r}."
                    ),
                    location=f"{file_path}:{np_}",
                    surface=(
                        "(notes hidden from the audience's "
                        "presentation view)"
                    ),
                    concealed=(
                        f"notes carrying prompt-injection shape; "
                        f"preview {preview!r}"
                    ),
                    source_layer="batin",
                )
            # Shared zahir detectors also fire on notes text runs.
            yield from self._scan_text_runs(root, np_, file_path)

    # ------------------------------------------------------------------
    # Slide-master walk — master-injection detection + zahir scans
    # ------------------------------------------------------------------

    def _scan_slide_masters(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every slide-master part; emit master-injection + zahir findings.

        Masters render *behind* every slide using them — a text run
        placed on a master is overlaid onto every body slide that uses
        that master. Legitimate masters carry only placeholder scaffolds
        ("Click to edit Master title style") and branding text; a master
        that carries a substantial non-placeholder text run is the
        suspect shape.
        """
        master_parts = sorted(
            n for n in names
            if n.startswith("ppt/slideMasters/slideMaster")
            and n.endswith(".xml")
        )
        for mp in master_parts:
            xml_bytes = self._read_bounded(zf, mp)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError as exc:
                yield Finding(
                    mechanism="scan_error",
                    tier=TIER["scan_error"],
                    confidence=1.0,
                    description=f"Could not parse {mp}: {exc}",
                    location=f"{file_path}:{mp}",
                    surface="(master body unparsable)",
                    concealed=(
                        "absence of per-run findings cannot be "
                        "taken as cleanness"
                    ),
                    source_layer="batin",
                )
                continue
            yield from self._detect_master_injection(root, mp, file_path)
            yield from self._scan_text_runs(root, mp, file_path)

    # ------------------------------------------------------------------
    # Slide-layout walk — master-injection detection + zahir scans
    # ------------------------------------------------------------------

    def _scan_slide_layouts(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every slide-layout part.

        Slide layouts are an intermediate template layer between the
        slide master and the individual slide. Same suppression shape
        applies: a content-shaped text run on a layout is overlaid onto
        every slide that uses that layout. The master-injection
        detector is reused here.
        """
        layout_parts = sorted(
            n for n in names
            if n.startswith("ppt/slideLayouts/slideLayout")
            and n.endswith(".xml")
        )
        for lp in layout_parts:
            xml_bytes = self._read_bounded(zf, lp)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError as exc:
                yield Finding(
                    mechanism="scan_error",
                    tier=TIER["scan_error"],
                    confidence=1.0,
                    description=f"Could not parse {lp}: {exc}",
                    location=f"{file_path}:{lp}",
                    surface="(layout body unparsable)",
                    concealed=(
                        "absence of per-run findings cannot be "
                        "taken as cleanness"
                    ),
                    source_layer="batin",
                )
                continue
            yield from self._detect_master_injection(root, lp, file_path)
            yield from self._scan_text_runs(root, lp, file_path)

    # ------------------------------------------------------------------
    # Batin — master / layout injection detection
    # ------------------------------------------------------------------

    def _detect_master_injection(
        self, root: ET.Element, part_name: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire when the master/layout part carries non-placeholder content.

        Walks every ``<a:t>`` run in the part; a run whose trimmed text
        is at least ``_MASTER_CONTENT_MIN_LEN`` characters and is not a
        recognised placeholder phrase is flagged. One finding per
        offending run, pinned to the containing part.
        """
        for t_el in root.iter(f"{{{_A_NS}}}t"):
            value = (t_el.text or "").strip()
            if len(value) < _MASTER_CONTENT_MIN_LEN:
                continue
            normalised = " ".join(value.lower().split())
            if normalised in _MASTER_PLACEHOLDER_TEXTS:
                continue
            # Skip runs that are entirely date/footer placeholders.
            if normalised.startswith("click to edit"):
                continue
            preview = value[:200]
            yield Finding(
                mechanism="pptx_slide_master_injection",
                tier=TIER["pptx_slide_master_injection"],
                confidence=0.85,
                description=(
                    f"Master/layout part {part_name} carries a "
                    f"non-placeholder text run ({len(value)} chars). "
                    "Text runs placed on a master or layout render "
                    "behind every slide using it — a content-shaped "
                    "run here overlays every body slide. Preview: "
                    f"{preview!r}."
                ),
                location=f"{file_path}:{part_name}",
                surface=(
                    "(master/layout text overlays every slide using it)"
                ),
                concealed=f"master-level text run: {preview!r}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Batin — action hyperlinks on shapes
    # ------------------------------------------------------------------

    def _detect_action_hyperlinks(
        self, root: ET.Element, part_name: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire on ``<a:hlinkClick>`` / ``<a:hlinkMouseOver>`` with action=.

        PowerPoint shapes can carry an ``<a:hlinkClick>`` /
        ``<a:hlinkMouseOver>`` descendant whose ``action`` attribute
        dispatches an action URI (``ppaction://...``) or a macro
        (``macro:...``). Clicking or hovering the shape invokes the
        action; the shape's rendered caption is the zahir surface, the
        action payload is the batin. Parallels the external-link /
        macro-invocation class with a dispatch twist.
        """
        tags = (
            f"{{{_A_NS}}}hlinkClick",
            f"{{{_A_NS}}}hlinkMouseOver",
        )
        for hl in root.iter():
            if hl.tag not in tags:
                continue
            action = hl.get("action", "")
            if not action:
                continue
            if not any(action.startswith(p) for p in _ACTION_URI_PREFIXES):
                continue
            yield Finding(
                mechanism="pptx_action_hyperlink",
                tier=TIER["pptx_action_hyperlink"],
                confidence=0.9,
                description=(
                    f"Shape in {part_name} declares an action-dispatch "
                    f"hyperlink (action={action!r}). Clicking or "
                    "hovering the shape invokes the action; the "
                    "rendered caption does not disclose the dispatch "
                    "target."
                ),
                location=f"{file_path}:{part_name}",
                surface=(
                    "(shape caption does not disclose the action URI)"
                ),
                concealed=f"action dispatch {action!r}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Zahir — per-run <a:t> text scans (shared)
    # ------------------------------------------------------------------

    def _scan_text_runs(
        self, root: ET.Element, part_name: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every ``<a:t>`` in the part and run zahir detectors.

        All four Office formats (DOCX, XLSX, PPTX) and the raw text
        family share the same zahir-layer contract: every rendered
        text run is inspected for zero-width, TAG, bidi, homoglyph,
        and mathematical-alphanumeric concealment. The per-part
        location string pins the reader to the exact slide / notes /
        master / layout.
        """
        run_index = 0
        for t_el in root.iter(f"{{{_A_NS}}}t"):
            run_index += 1
            value = t_el.text or ""
            if not value:
                continue
            loc = f"{file_path}:{part_name}:t{run_index}"
            yield from self._scan_string(value, loc)

    # ------------------------------------------------------------------
    # Shared zahir-layer string check
    # ------------------------------------------------------------------

    def _scan_string(
        self, value: str, location: str,
    ) -> Iterable[Finding]:
        """Zahir-layer checks applied to a single text value.

        Structured like ``XlsxAnalyzer._scan_string`` / the DOCX / HTML
        equivalents — each mechanism surfaces at most once per call; the
        location already pins the reader to the exact part + run
        coordinates.
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
                    f"run ({codepoints}) — invisible to a human reader, "
                    "preserved by parsers and tokenizers."
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

        # Mathematical-alphanumeric smuggling (Phase 11 detector, applied
        # across every text-bearing format).
        math_chars = [c for c in value if ord(c) in MATH_ALPHANUMERIC_RANGE]
        if math_chars:
            sample = "".join(math_chars[:20])
            yield Finding(
                mechanism="mathematical_alphanumeric",
                tier=TIER["mathematical_alphanumeric"],
                confidence=0.9,
                description=(
                    f"{len(math_chars)} Mathematical Alphanumeric "
                    "Symbol(s) (U+1D400 .. U+1D7FF) in this text run — "
                    "codepoints render as bold/italic/script Latin but "
                    "fall outside ASCII, bypassing naive string filters. "
                    f"Preview: {sample!r}."
                ),
                location=location,
                surface="(letters render as styled Latin but are not ASCII)",
                concealed=f"{len(math_chars)} math-alphanumeric codepoint(s)",
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


__all__ = ["PptxAnalyzer"]
