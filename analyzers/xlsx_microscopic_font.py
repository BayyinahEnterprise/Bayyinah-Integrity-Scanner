"""
Tier 2 detector for microscopic-font cell text in XLSX (v1.1.2).

OOXML spreadsheet cells reference a font record via the cellXfs ->
fontId chain in ``xl/styles.xml``; the font carries
``<sz val="N"/>`` where ``N`` is the size in points (unlike DOCX
which uses half-points). A cell with ``sz <= 4`` (4.0pt and below)
renders too small to read but its text is preserved verbatim in
the cell's inline-string or shared-string and read by every
downstream extractor.

Mirrors the PDF analyzer's ``microscopic_font`` and the DOCX
``docx_microscopic_font``. Closes xlsx_gauntlet fixture
02_microscopic_font.xlsx.

Tier discipline: Tier 2 structural rather than Tier 1 verified.
``sz`` is byte-deterministic, but legitimate uses of small sizes
exist (footnote-style annotations, accessibility audit markers,
certain typesetting tricks). The body of dangerous-and-legitimate
patterns at small sizes is broader than the body of dangerous-and-
legitimate patterns at near-white color, so this detector stays one
tier below the white-text detector.

The threshold is ``sz <= 4`` (4.0pt and below). Real-world
typography clusters at 8pt and above for body text; 4pt and below
is well outside any legitimate rendering envelope. Anything between
4 and 8pt is treated as small-but-readable and not flagged.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from analyzers.xlsx_styles_resolver import (
    load_styles_from_zip,
    resolve_cell_font,
)
from domain.finding import Finding


_S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_S_C = f"{{{_S_NS}}}c"
_S_IS = f"{{{_S_NS}}}is"
_S_T = f"{{{_S_NS}}}t"

_MICROSCOPIC_PT_THRESHOLD = 4.0
_PREVIEW_LIMIT = 240


def _cell_text(cell: ET.Element) -> str:
    is_el = cell.find(_S_IS)
    if is_el is None:
        return ""
    chunks: list[str] = []
    for t in is_el.iter(_S_T):
        if t.text:
            chunks.append(t.text)
    return "".join(chunks).strip()


def detect_xlsx_microscopic_font(file_path: Path) -> list[Finding]:
    """Return Tier 2 findings for cells whose resolved font size is
    at or below the microscopic threshold of 4.0pt.
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            fonts, cell_xfs = load_styles_from_zip(zf)
            if not fonts or not cell_xfs:
                return findings
            sheet_parts = sorted(
                n for n in zf.namelist()
                if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
            )
            for sheet_part in sheet_parts:
                try:
                    xml_bytes = zf.read(sheet_part)
                except KeyError:
                    continue
                try:
                    root = ET.fromstring(xml_bytes)
                except ET.ParseError:
                    continue
                for cell in root.iter(_S_C):
                    s_attr = cell.get("s")
                    try:
                        s_id = int(s_attr) if s_attr is not None else None
                    except ValueError:
                        s_id = None
                    if s_id is None:
                        continue
                    font = resolve_cell_font(s_id, fonts, cell_xfs)
                    if (
                        font.size_pt is None
                        or font.size_pt > _MICROSCOPIC_PT_THRESHOLD
                    ):
                        continue
                    text = _cell_text(cell)
                    if not text:
                        continue
                    cell_ref = cell.get("r") or "?"
                    preview = (
                        text if len(text) <= _PREVIEW_LIMIT
                        else text[:_PREVIEW_LIMIT] + "..."
                    )
                    findings.append(Finding(
                        mechanism="xlsx_microscopic_font",
                        tier=2,
                        confidence=1.0,
                        description=(
                            f"Cell {cell_ref} in {sheet_part} renders "
                            f"at {font.size_pt}pt, at or below the "
                            f"microscopic threshold of "
                            f"{_MICROSCOPIC_PT_THRESHOLD}pt. The text "
                            f"is unreadable in the rendered "
                            f"spreadsheet but is preserved in the "
                            f"cell's inline-string and read by every "
                            f"downstream extractor."
                        ),
                        location=f"{file_path}:{sheet_part}:{cell_ref}",
                        surface=f"cell {cell_ref} at {font.size_pt}pt",
                        concealed=(
                            f"sz={font.size_pt}pt; "
                            f"recovered text: {preview!r}"
                        ),
                        source_layer="zahir",
                    ))
    except (zipfile.BadZipFile, OSError):
        return findings
    return findings


__all__ = ["detect_xlsx_microscopic_font"]
