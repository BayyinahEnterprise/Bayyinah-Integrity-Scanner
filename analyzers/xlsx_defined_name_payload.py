"""
Tier 2 detector for defined-name string payloads in XLSX (v1.1.2).

OOXML workbooks declare named ranges and named formulas in
``xl/workbook.xml`` under ``<definedNames>``. The body of a
``<definedName>`` is normally a range reference like
``Sheet1!$A$1:$B$10`` or a formula like ``=SUM(A:A)``. The spec
permits string-literal values (a ``<definedName>`` whose body is a
quoted string), and Excel honours them in formulas. Adversarial use
stores a payload as a defined-name string literal: it is registered
in the workbook part, accessible from every formula evaluator, and
carried by every package walker, but it is not rendered anywhere in
the visible spreadsheet UI unless the user opens the Name Manager.

Mirrors the DOCX analyzer's ``docx_metadata_payload`` and the PDF
``pdf_metadata_analyzer`` in spirit: a content channel registered in
the package but invisible from the rendered surface. Closes
xlsx_gauntlet fixture 03_defined_name_payload.xlsx.

Tier discipline: Tier 2 because legitimate uses of string-literal
defined names exist (configuration constants, documentation
strings, version markers). The trigger is byte-deterministic (the
body parses as a quoted string rather than a range reference), but
the interpretation of "long string-literal name" as adversarial
versus legitimate is structural rather than semantic. Tier 2 is
the right home for that ambiguity.

The detector treats two body shapes as concealment-eligible:
  1. The body matches the quoted-string form ``"..."`` (with
     optional surrounding whitespace).
  2. The body is at least ``_MIN_PAYLOAD_LEN`` characters and does
     not begin with a known formula or range opening token (``=``,
     ``$``, ``SUMPRODUCT(``, etc.). This catches unquoted long
     strings that some tools emit.

Source layer is batin because the defined-names list is not part
of the rendered text surface and is only visible to a process that
reads the workbook part directly.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.finding import Finding


_S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_S_DEFINED_NAMES = f"{{{_S_NS}}}definedNames"
_S_DEFINED_NAME = f"{{{_S_NS}}}definedName"

_PREVIEW_LIMIT = 240
_MIN_PAYLOAD_LEN = 16

# Opening tokens that mark the body as a legitimate range or formula.
# A body starting with any of these is treated as not-a-string-payload.
_FORMULA_OPENERS: tuple[str, ...] = (
    "=", "+", "-", "@", "$", "#",
)


def _looks_like_quoted_string(body: str) -> bool:
    """Return True when the body parses as a quoted string literal.

    Matches ``"..."`` with optional surrounding whitespace. Empty
    quoted strings (``""``) are not flagged because they are a
    common Excel idiom for "no value".
    """
    s = body.strip()
    if len(s) < 3:
        return False
    if s[0] != '"' or s[-1] != '"':
        return False
    return len(s) > 2  # exclude empty ""


def _looks_like_long_unquoted_payload(body: str) -> bool:
    """Return True when the body is a long string that does not look
    like a formula or range reference.
    """
    s = body.strip()
    if len(s) < _MIN_PAYLOAD_LEN:
        return False
    if any(s.startswith(op) for op in _FORMULA_OPENERS):
        return False
    # Range references contain ``!`` and ``$`` but no leading sigil;
    # bodies without ``!`` and without ``$`` are unlikely to be a
    # range reference.
    if "!" in s or "$" in s:
        return False
    return True


def detect_xlsx_defined_name_payload(file_path: Path) -> list[Finding]:
    """Return Tier 2 findings for defined-name elements whose body
    is a string literal payload rather than a range or formula.
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            if "xl/workbook.xml" not in zf.namelist():
                return findings
            try:
                xml_bytes = zf.read("xl/workbook.xml")
            except KeyError:
                return findings
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError:
                return findings
            defined_names_el = root.find(_S_DEFINED_NAMES)
            if defined_names_el is None:
                return findings
            for dn in defined_names_el.findall(_S_DEFINED_NAME):
                name = dn.get("name") or "?"
                body = (dn.text or "").strip()
                if not body:
                    continue
                quoted = _looks_like_quoted_string(body)
                long_unquoted = _looks_like_long_unquoted_payload(body)
                if not (quoted or long_unquoted):
                    continue
                # Strip surrounding quotes for the recovered preview
                # so reviewers see the readable payload.
                inner = body
                if quoted:
                    inner = body.strip()[1:-1]
                preview = (
                    inner if len(inner) <= _PREVIEW_LIMIT
                    else inner[:_PREVIEW_LIMIT] + "..."
                )
                trigger = (
                    "quoted_string" if quoted else "long_unquoted"
                )
                findings.append(Finding(
                    mechanism="xlsx_defined_name_payload",
                    tier=2,
                    confidence=1.0,
                    description=(
                        f"Defined name {name!r} in xl/workbook.xml "
                        f"carries a string-literal body "
                        f"({len(inner)} chars, trigger={trigger}) "
                        f"rather than a range reference or formula. "
                        f"The string is not rendered anywhere in the "
                        f"visible spreadsheet UI but is registered in "
                        f"the workbook and accessible to every "
                        f"formula evaluator and package walker."
                    ),
                    location=(
                        f"{file_path}:xl/workbook.xml:"
                        f"definedName[name={name!r}]"
                    ),
                    surface=f"definedName {name!r} (string-literal body)",
                    concealed=(
                        f"name={name!r}; trigger={trigger}; "
                        f"recovered text: {preview!r}"
                    ),
                    source_layer="batin",
                ))
    except (zipfile.BadZipFile, OSError):
        return findings
    return findings


__all__ = ["detect_xlsx_defined_name_payload"]
