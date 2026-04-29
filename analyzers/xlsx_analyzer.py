"""
XlsxAnalyzer — Al-Baqarah 2:79 applied to the spreadsheet surface.

    وَيْلٌ لِّلَّذِينَ يَكْتُبُونَ الْكِتَابَ بِأَيْدِيهِمْ ثُمَّ يَقُولُونَ
    هَٰذَا مِنْ عِندِ اللَّهِ لِيَشْتَرُوا بِهِ ثَمَنًا قَلِيلًا ۖ فَوَيْلٌ لَّهُم
    مِّمَّا كَتَبَتْ أَيْدِيهِمْ وَوَيْلٌ لَّهُم مِّمَّا يَكْسِبُونَ
    (Al-Baqarah 2:79)

    "Woe to those who write the book with their own hands, then say,
    'This is from Allah,' in order to exchange it for a small price.
    Woe to them for what their hands have written and woe to them for
    what they earn."

Architectural reading. A spreadsheet is the most numerically
trustworthy-looking surface a document can wear: rows of values, a
few headers, a sum here and there. The format carries at least six
places where the surface and the stored content can disagree:

  * Zahir (rendered grid) — the cells an auditor sees in Excel after
    the workbook opens. Hidden rows and columns disappear from the
    grid but their values remain in the sheet stream and in the shared
    strings table; every downstream data pipeline (pandas, CSV export,
    LLM ingestion) reads them unchanged.

  * Batin (workbook graph) — parts the auditor never sees: the VBA
    project binary (``xl/vbaProject.bin``), embedded OLE objects
    (``xl/embeddings/*``), revision history parts (``xl/revisions/*``),
    external-workbook links (``xl/externalLinks/*`` plus
    ``TargetMode="External"`` relationships), hidden worksheets
    declared as ``state="hidden"`` or ``state="veryHidden"`` in
    workbook.xml, and custom formulas inside ``<dataValidations>``
    blocks that can indirect through ``INDIRECT``, ``HYPERLINK``, or
    an external-name reference.

``XlsxAnalyzer`` is therefore both a batin witness (structural /
relationship / parts inspection) and a zahir witness (per-cell text
concealment). ``source_layer`` is set per-finding; the class default
(``batin``) applies to ``scan_error`` findings emitted by the base
helper.

Supported FileKinds: ``{FileKind.XLSX}``. The router classifies XLSX
files (PK ZIP magic + .xlsx extension, or ZIP magic + xl/workbook.xml
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
from analyzers.xlsx_white_text import detect_xlsx_white_text
from analyzers.xlsx_microscopic_font import detect_xlsx_microscopic_font
from analyzers.xlsx_defined_name_payload import detect_xlsx_defined_name_payload
from analyzers.xlsx_comment_payload import detect_xlsx_comment_payload
from analyzers.xlsx_metadata_payload import detect_xlsx_metadata_payload
from analyzers.xlsx_csv_injection_formula import detect_xlsx_csv_injection_formula
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

# Read limit — 32 MB bounds the footprint of a single XLSX scan. Ample
# for every realistic workbook; adversarial ZIP bombs are truncated
# rather than decompressed unbounded. Matches the DocxAnalyzer bound.
_MAX_UNCOMPRESSED_BYTES = 32 * 1024 * 1024

# The SpreadsheetML namespace URI for workbook / worksheet parts. Stable
# since Office 2007; every .xlsx in the wild uses this exact string.
_S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

# The Office Open XML relationships namespace — shared with DOCX.
_R_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

# Formula functions that indirectly reference other names, URLs, or
# external workbooks. Their presence inside a data-validation formula
# is the specific payload-carrier shape the
# ``xlsx_data_validation_formula`` mechanism targets: a validation
# rule that calls ``INDIRECT("[external.xlsx]Sheet1!A1")`` is not
# validating input, it is pulling in content from elsewhere.
_SUSPICIOUS_FORMULA_FUNCS: frozenset[str] = frozenset({
    "INDIRECT",
    "HYPERLINK",
    "WEBSERVICE",
    "IMPORTRANGE",
    "IMPORTXML",
    "IMPORTHTML",
    "IMPORTDATA",
})

_LATIN_RANGES = (
    range(0x0041, 0x005B),  # A-Z
    range(0x0061, 0x007B),  # a-z
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


# ---------------------------------------------------------------------------
# XlsxAnalyzer
# ---------------------------------------------------------------------------


class XlsxAnalyzer(BaseAnalyzer):
    """Detects structural and embedded concealment in XLSX workbooks.

    The analyzer opens the file as a ZIP, inspects the member list and
    the relationships graph for batin-layer concealment (VBA, embedded
    objects, revision history, external links), parses
    ``xl/workbook.xml`` for hidden-sheet declarations and external-link
    relationships, walks every worksheet for hidden rows/columns and
    data-validation formulas, and runs the shared zahir detectors
    (zero-width / TAG / bidi / homoglyph) against every cell text
    present in ``xl/sharedStrings.xml`` and inline ``<is><t>`` elements
    inside the sheets themselves.

    Priority order follows real-world threat prevalence:

        1. Most dangerous (verified active / embedded content):
           VBA macros, embedded objects.
        2. Most common (structural concealment of prior/hidden state):
           revision history, hidden sheets, hidden rows/columns.
        3. Most subtle (external linkage, formula-carrier shapes):
           external links, data-validation formulas.

    Corrupt / non-ZIP / malformed-XML inputs are converted to a single
    ``scan_error`` finding via ``_scan_error_report`` — consistent with
    the middle-community contract (Al-Baqarah 2:143): one witness
    failing does not silence the others, and the failure itself is a
    signal.
    """

    name: ClassVar[str] = "xlsx"
    error_prefix: ClassVar[str] = "XLSX scan error"
    # Class default — ``scan_error`` findings are structural in nature
    # (the inner state was not inspected). Per-finding source_layer is
    # set individually for every zahir / batin detector below.
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.XLSX})

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the XLSX file at ``file_path``."""
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
                f"unexpected failure during XLSX scan: {exc}",
            )
        finally:
            zf.close()

        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Central walk — emits every finding for this workbook
    # ------------------------------------------------------------------

    def _scan_zip(
        self, zf: zipfile.ZipFile, file_path: Path,
    ) -> Iterable[Finding]:
        names = zf.namelist()

        # ---- Batin (structural) — priority band 1 ----
        yield from self._detect_vba_macros(names, file_path)
        yield from self._detect_embedded_objects(names, file_path)

        # ---- Batin (structural) — priority band 2 (common) ----
        yield from self._detect_revision_history(names, file_path)
        yield from self._detect_hidden_sheets(zf, names, file_path)

        # ---- Batin (structural) — priority band 3 (subtle) ----
        yield from self._detect_external_links(zf, names, file_path)

        # ---- Zahir (rendered grid) + per-sheet batin + per-cell zahir ----
        yield from self._scan_worksheets(zf, names, file_path)

        # ---- Zahir — per-cell scans over shared strings ----
        yield from self._scan_shared_strings(zf, names, file_path)

        # ---- v1.1.2 payload detectors ----
        yield from detect_xlsx_white_text(file_path)
        yield from detect_xlsx_microscopic_font(file_path)
        yield from detect_xlsx_csv_injection_formula(file_path)
        yield from detect_xlsx_defined_name_payload(file_path)
        yield from detect_xlsx_comment_payload(file_path)
        yield from detect_xlsx_metadata_payload(file_path)

    # ------------------------------------------------------------------
    # Batin — VBA macros (priority 1)
    # ------------------------------------------------------------------

    def _detect_vba_macros(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once if a VBA project binary is present anywhere.

        An ``xl/vbaProject.bin`` entry means the workbook ships
        executable macro code. This is XLSX's analogue of PDF
        ``javascript`` and ``docx_vba_macros`` — the payload activates
        the moment the user enables content. Presence is sufficient.
        """
        vba_entries = [n for n in names if n.endswith("vbaProject.bin")]
        if not vba_entries:
            return
        listing = ", ".join(sorted(vba_entries))
        yield Finding(
            mechanism="xlsx_vba_macros",
            tier=TIER["xlsx_vba_macros"],
            confidence=1.0,
            description=(
                f"XLSX ships a VBA project binary ({listing}). "
                "VBA macros are active code — they execute when the "
                "reader enables content. A .xlsx that carries them has "
                "the same attack surface as a .xlsm; the extension "
                "alone does not disclose it."
            ),
            location=f"{file_path}:{listing}",
            surface="(workbook appears to be an ordinary .xlsx)",
            concealed="embedded VBA macro binary",
            source_layer="batin",
        )

    # ------------------------------------------------------------------
    # Batin — embedded OLE objects / other files (priority 1)
    # ------------------------------------------------------------------

    def _detect_embedded_objects(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once per file under ``xl/embeddings/``.

        XLSX's analogue of PDF ``embedded_file`` and
        ``docx_embedded_object``. An embedded OLE blob can be another
        workbook (with its own macros), a packaged executable, or any
        arbitrary file type the author chose to ride along.
        """
        for entry in names:
            if not entry.startswith("xl/embeddings/"):
                continue
            # Skip directory entries (ZIP sometimes lists them).
            if entry.endswith("/"):
                continue
            basename = entry.rsplit("/", 1)[-1]
            yield Finding(
                mechanism="xlsx_embedded_object",
                tier=TIER["xlsx_embedded_object"],
                confidence=1.0,
                description=(
                    f"XLSX embeds {basename!r} under xl/embeddings/. "
                    "Embedded objects are arbitrary files (OLE, Office "
                    "documents, or packaged binaries) stored inside "
                    "the workbook and accessible to the reader via "
                    "double-click or via programmatic extraction."
                ),
                location=f"{file_path}:{entry}",
                surface="(no inline rendering hint)",
                concealed=f"embedded file {basename!r}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Batin — revision history (priority 2)
    # ------------------------------------------------------------------

    def _detect_revision_history(
        self, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once if any entry under ``xl/revisions/`` is present.

        Shared-workbook tracked changes are preserved in ``xl/revisions/``
        parts (``revisionHeaders.xml`` plus one or more ``revisionLog*.xml``
        files). The final rendered view shows the accepted state; the
        prior revision is still accessible to any parser that walks the
        revisions parts. XLSX's analogue of PDF ``incremental_update``
        and ``docx_revision_history``.
        """
        revision_entries = [
            n for n in names
            if n.startswith("xl/revisions/") and not n.endswith("/")
        ]
        if not revision_entries:
            return
        listing = ", ".join(sorted(revision_entries))
        yield Finding(
            mechanism="xlsx_revision_history",
            tier=TIER["xlsx_revision_history"],
            confidence=0.95,
            description=(
                f"XLSX preserves shared-workbook revision history in "
                f"{len(revision_entries)} part(s) under xl/revisions/ "
                f"({listing}). The rendered view only shows the "
                "accepted state; prior revisions are accessible to any "
                "parser that walks the revisions parts."
            ),
            location=f"{file_path}:xl/revisions/",
            surface="(rendered workbook shows accepted state only)",
            concealed=f"{len(revision_entries)} revision part(s)",
            source_layer="batin",
        )

    # ------------------------------------------------------------------
    # Batin — hidden sheets (priority 2)
    # ------------------------------------------------------------------

    def _detect_hidden_sheets(
        self, zf: zipfile.ZipFile, names: list[str], file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once per ``<sheet>`` whose ``state`` is hidden or veryHidden.

        ``xl/workbook.xml`` declares every worksheet as a ``<sheet>``
        element. A ``state="hidden"`` sheet is not listed in the Excel
        tab bar; a ``state="veryHidden"`` sheet can only be reached
        through the VBA IDE. Both carry full cell data inside their
        respective ``xl/worksheets/sheet*.xml`` files — every data
        pipeline reads them normally.
        """
        if "xl/workbook.xml" not in names:
            return
        xml_bytes = self._read_bounded(zf, "xl/workbook.xml")
        if xml_bytes is None:
            return
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError:
            return
        for sheet in root.findall(f".//{{{_S_NS}}}sheet"):
            state = sheet.get("state", "")
            if state not in ("hidden", "veryHidden"):
                continue
            sheet_name = sheet.get("name", "<unnamed>")
            sheet_id = sheet.get("sheetId", "?")
            if state == "veryHidden":
                state_note = (
                    "veryHidden sheets are only reachable through "
                    "the VBA IDE — the tab bar does not list them "
                    "and the Unhide dialog does not offer them."
                )
            else:
                state_note = (
                    "Hidden sheets are not listed in the tab bar, "
                    "but the sheet part still carries full cell data."
                )
            yield Finding(
                mechanism="xlsx_hidden_sheet",
                tier=TIER["xlsx_hidden_sheet"],
                confidence=1.0,
                description=(
                    f"Worksheet {sheet_name!r} (sheetId={sheet_id}) is "
                    f"declared as state={state!r} in xl/workbook.xml. "
                    f"{state_note}"
                ),
                location=f"{file_path}:xl/workbook.xml:sheet={sheet_name!r}",
                surface=f"(sheet hidden from tab bar as state={state!r})",
                concealed=f"worksheet {sheet_name!r} with state={state!r}",
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
        """Fire on xl/externalLinks/ parts and TargetMode="External" rels.

        Workbooks can reference other workbooks on disk or across the
        network at open time. The references live in two places: the
        ``xl/externalLinks/`` parts (one per external workbook) and
        the relationship entries with ``TargetMode="External"`` in the
        ``.rels`` parts. We surface both as the same mechanism because
        they serve the same adversarial purpose — a workbook that
        reaches outside itself when opened. Parallels
        ``docx_external_relationship``.
        """
        # External-links parts.
        for entry in names:
            if not entry.startswith("xl/externalLinks/"):
                continue
            if entry.endswith("/"):
                continue
            basename = entry.rsplit("/", 1)[-1]
            yield Finding(
                mechanism="xlsx_external_link",
                tier=TIER["xlsx_external_link"],
                confidence=0.9,
                description=(
                    f"XLSX declares an external-workbook link via "
                    f"{basename!r} under xl/externalLinks/. The "
                    "workbook reaches outside itself when opened; "
                    "common vectors include shared-drive references, "
                    "remote-workbook refresh, and cross-workbook "
                    "formula evaluation."
                ),
                location=f"{file_path}:{entry}",
                surface="(no visible cell-level indicator)",
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
                    mechanism="xlsx_external_link",
                    tier=TIER["xlsx_external_link"],
                    confidence=0.9,
                    description=(
                        f"XLSX declares an external relationship → "
                        f"{target!r} in {rels_entry}. External refs "
                        "cause the workbook to reach outside itself "
                        "when opened; common vectors include remote "
                        "images, remote templates, and linked "
                        "workbooks."
                    ),
                    location=f"{file_path}:{rels_entry}",
                    surface="(no inline cell-level indicator)",
                    concealed=f"external target {target!r}",
                    source_layer="batin",
                )

    # ------------------------------------------------------------------
    # Per-sheet walk — hidden rows/cols, data validation, cell text
    # ------------------------------------------------------------------

    def _scan_worksheets(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every worksheet and emit per-sheet findings."""
        sheet_parts = sorted(
            n for n in names
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )
        for sheet_part in sheet_parts:
            xml_bytes = self._read_bounded(zf, sheet_part)
            if xml_bytes is None:
                continue
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError as exc:
                yield Finding(
                    mechanism="scan_error",
                    tier=TIER["scan_error"],
                    confidence=1.0,
                    description=(
                        f"Could not parse {sheet_part}: {exc}"
                    ),
                    location=f"{file_path}:{sheet_part}",
                    surface="(sheet body unparsable)",
                    concealed=(
                        "absence of per-cell findings cannot be "
                        "taken as cleanness"
                    ),
                    source_layer="batin",
                )
                continue
            yield from self._detect_hidden_rows_cols(
                root, sheet_part, file_path,
            )
            yield from self._detect_data_validation(
                root, sheet_part, file_path,
            )
            yield from self._scan_inline_cell_text(
                root, sheet_part, file_path,
            )

    # ------------------------------------------------------------------
    # Zahir — hidden rows / hidden columns
    # ------------------------------------------------------------------

    def _detect_hidden_rows_cols(
        self, root: ET.Element, sheet_part: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once per sheet on any ``<row hidden="1"/>`` or ``<col hidden="1"/>``.

        Hidden rows and columns are removed from the rendered grid but
        preserve their values inside the sheet stream and the shared
        strings table. Every CSV exporter, every ``pandas.read_excel``
        call, and every LLM ingesting the workbook sees them unchanged
        — the classic performed-alignment shape at the spreadsheet
        surface.
        """
        hidden_rows: list[str] = []
        for row in root.findall(f".//{{{_S_NS}}}row"):
            if row.get("hidden") == "1":
                hidden_rows.append(row.get("r", "?"))

        hidden_cols: list[tuple[str, str]] = []
        for col in root.findall(f".//{{{_S_NS}}}col"):
            if col.get("hidden") == "1":
                hidden_cols.append(
                    (col.get("min", "?"), col.get("max", "?")),
                )

        if not hidden_rows and not hidden_cols:
            return

        row_summary = (
            f"rows: {', '.join(hidden_rows)}"
            if hidden_rows else ""
        )
        col_summary = (
            "cols: " + ", ".join(
                f"{mn}..{mx}" if mn != mx else mn
                for mn, mx in hidden_cols
            )
            if hidden_cols else ""
        )
        summary_parts = [p for p in (row_summary, col_summary) if p]
        summary = "; ".join(summary_parts)

        yield Finding(
            mechanism="xlsx_hidden_row_column",
            tier=TIER["xlsx_hidden_row_column"],
            confidence=1.0,
            description=(
                f"Sheet part {sheet_part} marks "
                f"{len(hidden_rows)} row(s) and {len(hidden_cols)} "
                f"column-range(s) as hidden ({summary}). The hidden "
                "cells are removed from the rendered grid but their "
                "values remain in the sheet stream — every "
                "downstream data pipeline reads them unchanged."
            ),
            location=f"{file_path}:{sheet_part}",
            surface="(hidden rows/columns not shown in rendered grid)",
            concealed=summary,
            source_layer="zahir",
        )

    # ------------------------------------------------------------------
    # Batin — data-validation formulas with carrier-shape functions
    # ------------------------------------------------------------------

    def _detect_data_validation(
        self, root: ET.Element, sheet_part: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire on ``<dataValidation>`` blocks with suspicious formulas.

        Data validation is a legitimate feature — a drop-down list or
        numeric range check — but its ``<formula1>`` / ``<formula2>``
        children can carry arbitrary Excel expressions. A formula that
        calls ``INDIRECT``, ``HYPERLINK``, ``WEBSERVICE``, or one of
        the Google-Sheets-compatible ``IMPORT*`` functions is not
        validating input: it is pulling in content from elsewhere.

        We only surface validation blocks whose formulas match the
        carrier-shape regex; a plain ``<formula1>3</formula1>`` for a
        numeric-range rule is silent.
        """
        pattern = re.compile(
            r"\b(" + "|".join(_SUSPICIOUS_FORMULA_FUNCS) + r")\s*\(",
            re.IGNORECASE,
        )
        for dv in root.findall(f".//{{{_S_NS}}}dataValidation"):
            sqref = dv.get("sqref", "?")
            type_ = dv.get("type", "")
            matched_formulas: list[str] = []
            for f_el in dv.findall(f"{{{_S_NS}}}formula1") + \
                    dv.findall(f"{{{_S_NS}}}formula2"):
                formula_text = (f_el.text or "").strip()
                if not formula_text:
                    continue
                if pattern.search(formula_text):
                    # Truncate long formulas for the preview.
                    preview = formula_text[:200]
                    matched_formulas.append(preview)
            if not matched_formulas:
                continue
            preview = " | ".join(matched_formulas)
            yield Finding(
                mechanism="xlsx_data_validation_formula",
                tier=TIER["xlsx_data_validation_formula"],
                confidence=0.85,
                description=(
                    f"Data-validation rule on {sqref!r} "
                    f"(type={type_!r}) in {sheet_part} carries a "
                    "formula that invokes one of INDIRECT, HYPERLINK, "
                    "WEBSERVICE, or IMPORT* — functions that reach "
                    "outside the validation's declared scope. "
                    f"Formula: {preview!r}."
                ),
                location=(
                    f"{file_path}:{sheet_part}:dataValidation={sqref!r}"
                ),
                surface=f"(validation on {sqref!r})",
                concealed=f"formula {preview!r}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Zahir — inline cell text (``<is><t>…</t></is>``) per-cell zahir scan
    # ------------------------------------------------------------------

    def _scan_inline_cell_text(
        self, root: ET.Element, sheet_part: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every inline ``<t>`` in the sheet and run zahir detectors.

        XLSX stores cell text in two places: the shared strings table
        (``xl/sharedStrings.xml``, handled separately) and inline
        ``<is><t>…</t></is>`` elements inside the sheet when the cell
        has ``t="inlineStr"``. Both are reader-visible on screen and
        both can carry zero-width / TAG / bidi / homoglyph payloads.
        """
        # The sheet's data cells live under worksheet/sheetData/row/c.
        # Each ``<c>`` with ``t="inlineStr"`` has an ``<is>/<t>`` child.
        for c in root.findall(f".//{{{_S_NS}}}c"):
            if c.get("t") != "inlineStr":
                continue
            cell_ref = c.get("r", "?")
            for t_el in c.findall(f".//{{{_S_NS}}}t"):
                value = t_el.text or ""
                if not value:
                    continue
                loc = f"{file_path}:{sheet_part}:{cell_ref}"
                yield from self._scan_string(value, loc)

    # ------------------------------------------------------------------
    # Zahir — shared strings per-cell scan
    # ------------------------------------------------------------------

    def _scan_shared_strings(
        self,
        zf: zipfile.ZipFile,
        names: list[str],
        file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every entry in ``xl/sharedStrings.xml`` and emit zahir findings.

        The shared strings table is the primary text store in a
        workbook: every non-inline string cell references an entry in
        this table by index. Cells that point at the same entry all
        display the same text — a single concealment payload in this
        table can be referenced from many cells.
        """
        if "xl/sharedStrings.xml" not in names:
            return
        xml_bytes = self._read_bounded(zf, "xl/sharedStrings.xml")
        if xml_bytes is None:
            return
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            yield Finding(
                mechanism="scan_error",
                tier=TIER["scan_error"],
                confidence=1.0,
                description=(
                    f"Could not parse xl/sharedStrings.xml: {exc}"
                ),
                location=f"{file_path}:xl/sharedStrings.xml",
                surface="(shared-strings table unparsable)",
                concealed=(
                    "absence of per-cell findings cannot be "
                    "taken as cleanness"
                ),
                source_layer="zahir",
            )
            return
        # Each <si> (shared-string item) holds one or more <t> children
        # (plain text runs) or <r><t> children (rich-text runs). We
        # enumerate every <t> descendant and scan its value.
        si_index = 0
        for si in root.findall(f"{{{_S_NS}}}si"):
            si_index += 1
            for t_el in si.iter(f"{{{_S_NS}}}t"):
                value = t_el.text or ""
                if not value:
                    continue
                loc = (
                    f"{file_path}:xl/sharedStrings.xml:"
                    f"si{si_index}"
                )
                yield from self._scan_string(value, loc)

    # ------------------------------------------------------------------
    # Shared zahir-layer string check
    # ------------------------------------------------------------------

    def _scan_string(
        self, value: str, location: str,
    ) -> Iterable[Finding]:
        """Zahir-layer checks applied to a single text value.

        Structured like ``DocxAnalyzer._scan_string`` — each mechanism
        surfaces at most once per call; the location already pins the
        reader to the exact sheet/cell or shared-string coordinates.
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
                    f"{len(zw)} zero-width character(s) in this cell "
                    f"text ({codepoints}) — invisible to a human "
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
                    "cell text. TAG codepoints are invisible to human "
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
                    f"cell text ({codepoints}) — reorders display "
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


__all__ = ["XlsxAnalyzer"]
