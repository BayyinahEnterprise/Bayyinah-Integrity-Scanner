"""
Tier 1 detector for orphan-footnote payloads in DOCX (v1.1.2).

OOXML stores footnote bodies in ``word/footnotes.xml``; each
``<w:footnote w:id="N">`` element holds the footnote text. The
visible-document part ``word/document.xml`` references a footnote via
``<w:footnoteReference w:id="N"/>`` markers placed inline in a run.
Word renders a footnote only where a reference marker exists; absent
the marker the footnote body is loaded by the package but never
appears in the rendered document, the footnote pane, or print output.

Adversarial use stores a payload as a footnote whose ``w:id`` is not
referenced from document.xml. The footnote part is registered in
``[Content_Types].xml`` and connected via the document's relationship
file, so every package walker, indexer, and LLM extractor that visits
the footnotes part reads the payload bytes verbatim, while the human
reader sees nothing in the rendered document and no marker in the
footnote pane.

Mirrors the PDF analyzer's ``pdf_hidden_text_annotation`` mechanism
in spirit (a content channel registered in the package but
unreferenced from the visible-content part) and the parallel DOCX
detector ``docx_comment_payload``. Closes docx_gauntlet fixture
06_footnote_payload.docx.

Tier discipline: Tier 1 because the trigger is byte-deterministic.
A footnote with content and no inline reference marker in
document.xml is a structural fact observable from a single walk of
the two parts. There is no heuristic threshold and no semantic
interpretation; either the marker exists or it does not. Source
layer is batin because the trigger lives outside the rendered text
surface and is only visible to a process that reads the footnotes
part directly.

Special-footnote filter: w:type="separator" and
w:type="continuationSeparator" footnotes are part of the OOXML
footnote infrastructure (they hold the horizontal-rule separator
between body text and footnotes). Word generates them automatically;
they have no content payload and no reference markers. The detector
skips any footnote with a ``w:type`` attribute set to one of the
infrastructure types.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.finding import Finding


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_FOOTNOTE = f"{{{_W_NS}}}footnote"
_W_FOOTNOTE_REFERENCE = f"{{{_W_NS}}}footnoteReference"
_W_T = f"{{{_W_NS}}}t"
_W_ID = f"{{{_W_NS}}}id"
_W_TYPE = f"{{{_W_NS}}}type"

# Infrastructure footnote types Word generates automatically. These
# carry no user content and no reference markers; the detector stays
# silent against them so a clean document does not false-positive.
_INFRASTRUCTURE_TYPES: frozenset[str] = frozenset(
    {"separator", "continuationSeparator"}
)

_PREVIEW_LIMIT = 240
_NS_TAG = re.compile(r"^\{[^}]*\}")


def _local_name(tag: str) -> str:
    return _NS_TAG.sub("", tag)


def _referenced_footnote_ids(zf: zipfile.ZipFile) -> set[str]:
    """Return the set of footnote w:ids referenced from document.xml.

    A footnote whose id is not in this set, and whose w:type is not
    an infrastructure type, is structurally orphaned.
    """
    if "word/document.xml" not in zf.namelist():
        return set()
    try:
        xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (KeyError, ET.ParseError):
        return set()
    ids: set[str] = set()
    for el in root.iter(_W_FOOTNOTE_REFERENCE):
        wid = el.get(_W_ID)
        if wid is not None:
            ids.add(wid)
    return ids


def _footnote_text(footnote_el: ET.Element) -> str:
    """Concatenate every <w:t> text node inside a footnote element."""
    chunks: list[str] = []
    for el in footnote_el.iter(_W_T):
        if el.text:
            chunks.append(el.text)
    return "".join(chunks).strip()


def detect_docx_orphan_footnote(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for footnotes whose w:id is not
    referenced from document.xml and whose w:type is not an
    infrastructure type.
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            names = zf.namelist()
            if "word/footnotes.xml" not in names:
                return findings
            try:
                xml_bytes = zf.read("word/footnotes.xml")
            except KeyError:
                return findings
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError:
                return findings

            referenced_ids = _referenced_footnote_ids(zf)

            for footnote in root.iter(_W_FOOTNOTE):
                wid = footnote.get(_W_ID, "?")
                ftype = footnote.get(_W_TYPE) or ""
                if ftype in _INFRASTRUCTURE_TYPES:
                    continue

                text = _footnote_text(footnote)
                if not text:
                    continue
                if wid in referenced_ids:
                    continue

                preview = (
                    text if len(text) <= _PREVIEW_LIMIT
                    else text[:_PREVIEW_LIMIT] + "..."
                )

                findings.append(Finding(
                    mechanism="docx_orphan_footnote",
                    tier=1,
                    confidence=1.0,
                    description=(
                        f"Footnote w:id={wid} carries text "
                        f"({len(text)} chars) but is not referenced "
                        f"from document.xml. The footnotes part is "
                        f"loaded by Word and by package walkers, but "
                        f"the rendered document and footnote pane "
                        f"show no indicator because document.xml has "
                        f"no <w:footnoteReference> pointing at this "
                        f"id. Likely adversarial concealment of "
                        f"payload in the footnotes channel."
                    ),
                    location=f"word/footnotes.xml#{wid}",
                    surface=f"footnote id={wid} (orphaned)",
                    concealed=(
                        f"orphan footnote ({len(text)} chars); "
                        f"recovered text: {preview!r}"
                    ),
                    source_layer="batin",
                ))
    except (zipfile.BadZipFile, OSError):
        return findings
    return findings


__all__ = ["detect_docx_orphan_footnote"]
