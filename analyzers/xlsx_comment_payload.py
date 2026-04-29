"""
Tier 2 detector for cell-comment payloads in XLSX (v1.1.2).

OOXML workbooks store cell comments in ``xl/comments/comment*.xml``
and threaded comments in ``xl/threadedComments/*.xml``. The comment
text is rendered only when the user hovers a comment indicator on a
cell, and many automated readers (CSV exporters, headless table
extractors, LLM ingestion tools) skip the comment parts entirely.
Adversarial use stores a payload in a ``<comment>/<text>/<t>`` body:
the byte sits in the workbook package, but the rendered surface
never carries it.

Mirrors ``docx_comment_payload`` in spirit. Closes xlsx_gauntlet
fixture 04_cell_comment.xlsx.

Tier discipline: Tier 2 because cell comments have legitimate uses
(reviewer notes, audit trails, formula explanations). The trigger
is byte-deterministic (a comment whose text body length meets the
threshold) but the interpretation of "long comment" as adversarial
versus legitimate is structural rather than semantic.

Source layer is batin because comment text lives in a separate
package part and is not part of the rendered cell text surface.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.finding import Finding


_S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_S_T = f"{{{_S_NS}}}t"
_S_TEXT = f"{{{_S_NS}}}text"
_S_COMMENT = f"{{{_S_NS}}}comment"
_S_COMMENT_LIST = f"{{{_S_NS}}}commentList"

# Threaded comments use a different namespace.
_TC_NS = (
    "http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments"
)
_TC_THREADED_COMMENT = f"{{{_TC_NS}}}threadedComment"
_TC_TEXT = f"{{{_TC_NS}}}text"

_PREVIEW_LIMIT = 240
_MIN_PAYLOAD_LEN = 16


_COMMENT_PART_RE = re.compile(r"^xl/comments/comment[^/]*\.xml$")
_THREADED_COMMENT_PART_RE = re.compile(
    r"^xl/threadedComments/[^/]+\.xml$"
)


def _extract_text_concat(elem: ET.Element) -> str:
    """Concatenate all text content under ``elem`` in document order."""
    parts: list[str] = []
    for descendant in elem.iter():
        if descendant.text:
            parts.append(descendant.text)
    return "".join(parts).strip()


def _scan_classic_comments(
    xml_bytes: bytes,
    part_name: str,
    file_path: Path,
) -> list[Finding]:
    """Scan a classic ``xl/comments/comment*.xml`` part."""
    findings: list[Finding] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return findings
    comment_list = root.find(_S_COMMENT_LIST)
    if comment_list is None:
        return findings
    for idx, comment in enumerate(comment_list.findall(_S_COMMENT)):
        ref = comment.get("ref") or "?"
        text_el = comment.find(_S_TEXT)
        body = ""
        if text_el is not None:
            body = _extract_text_concat(text_el)
        if len(body) < _MIN_PAYLOAD_LEN:
            continue
        preview = (
            body if len(body) <= _PREVIEW_LIMIT
            else body[:_PREVIEW_LIMIT] + "..."
        )
        findings.append(Finding(
            mechanism="xlsx_comment_payload",
            tier=2,
            confidence=1.0,
            description=(
                f"Cell comment at {ref} in {part_name} carries a "
                f"text body of {len(body)} characters. The text is "
                f"rendered only on hover and is skipped by most "
                f"automated table readers, but it lives in the "
                f"workbook package and is recoverable from the "
                f"part bytes."
            ),
            location=(
                f"{file_path}:{part_name}:comment[{idx}](ref={ref})"
            ),
            surface=f"comment at cell {ref}",
            concealed=(
                f"part={part_name}; ref={ref}; "
                f"recovered text: {preview!r}"
            ),
            source_layer="batin",
        ))
    return findings


def _scan_threaded_comments(
    xml_bytes: bytes,
    part_name: str,
    file_path: Path,
) -> list[Finding]:
    """Scan a threaded ``xl/threadedComments/*.xml`` part."""
    findings: list[Finding] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return findings
    # Threaded comments may have the namespaced root element either
    # at root or as direct children. Iterate either way.
    threaded = list(root.iter(_TC_THREADED_COMMENT))
    for idx, tc in enumerate(threaded):
        ref = tc.get("ref") or "?"
        text_el = tc.find(_TC_TEXT)
        body = ""
        if text_el is not None and text_el.text:
            body = text_el.text.strip()
        else:
            body = _extract_text_concat(tc)
        if len(body) < _MIN_PAYLOAD_LEN:
            continue
        preview = (
            body if len(body) <= _PREVIEW_LIMIT
            else body[:_PREVIEW_LIMIT] + "..."
        )
        findings.append(Finding(
            mechanism="xlsx_comment_payload",
            tier=2,
            confidence=1.0,
            description=(
                f"Threaded comment at {ref} in {part_name} carries "
                f"a text body of {len(body)} characters. Threaded "
                f"comments live in a separate package part and are "
                f"not exported by most automated table readers."
            ),
            location=(
                f"{file_path}:{part_name}:"
                f"threadedComment[{idx}](ref={ref})"
            ),
            surface=f"threaded comment at cell {ref}",
            concealed=(
                f"part={part_name}; ref={ref}; "
                f"recovered text: {preview!r}"
            ),
            source_layer="batin",
        ))
    return findings


def detect_xlsx_comment_payload(file_path: Path) -> list[Finding]:
    """Return Tier 2 findings for comment parts whose text bodies
    meet the payload-length threshold.
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            for name in zf.namelist():
                if _COMMENT_PART_RE.match(name):
                    try:
                        xml_bytes = zf.read(name)
                    except KeyError:
                        continue
                    findings.extend(
                        _scan_classic_comments(
                            xml_bytes, name, file_path
                        )
                    )
                elif _THREADED_COMMENT_PART_RE.match(name):
                    try:
                        xml_bytes = zf.read(name)
                    except KeyError:
                        continue
                    findings.extend(
                        _scan_threaded_comments(
                            xml_bytes, name, file_path
                        )
                    )
    except (zipfile.BadZipFile, OSError):
        return findings
    return findings


__all__ = ["detect_xlsx_comment_payload"]
