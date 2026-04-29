"""
Tier 1 detector for hidden-text payloads in XLSX metadata parts (v1.1.2).

OOXML stores three metadata parts under ``docProps/`` for spreadsheets:

  * ``docProps/core.xml`` - Dublin-core fields (creator, title, subject,
    description, keywords, etc.).
  * ``docProps/app.xml`` - Application-level metadata (Application,
    AppVersion, Company, Manager, sheet counts, etc.).
  * ``docProps/custom.xml`` - Author-defined custom properties.
    Optional but a well-known location for arbitrary key/value content.

All three are read by Excel, indexers (Spotlight, Windows Search,
SharePoint), and any LLM ingestion path that walks the OOXML package
tree. None of them appear in cell text by default.

A run-of-the-mill spreadsheet carries short metadata strings (a title,
an author, a sheet name list). Adversarial use places long text payloads
or directive content in these fields, knowing that the rendered grid
shows nothing while every metadata-aware extractor reads the payload.

Mirrors ``docx_metadata_payload`` and ``pdf_metadata_analyzer`` with the
same triggers:

  (a) length: any field text exceeding 512 UTF-8 bytes is structurally
      anomalous;
  (b) divergence: a content-summary field (description, custom property
      values) that does not appear anywhere in rendered cell text and
      is at least 16 chars is anomalous.

Title / creator / subject (core) and Application / Company (app) and
sheet/row counts are intentionally exempted from the divergence trigger
because legitimate values frequently do not appear verbatim in cell
text.

Closes xlsx_gauntlet fixture 05_custom_xml_properties.xlsx.

Tier discipline: Tier 1 because every trigger is verifiable from the
file's bytes alone with no semantic claim.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from domain.finding import Finding


_FIELD_LENGTH_LIMIT = 512
_MIN_DIVERGENCE_LENGTH = 16
_PREVIEW_LIMIT = 240

_META_PARTS = (
    "docProps/core.xml",
    "docProps/app.xml",
    "docProps/custom.xml",
)

# Local-names exempt from the divergence trigger: legitimate values
# are unlikely to appear verbatim in cell text. Mirrors the DOCX
# exempt list with XLSX-specific additions for sheet/row counts.
_DIVERGENCE_EXEMPT_LOCALNAMES = frozenset({
    # core.xml - Dublin-core / dcterms fields.
    "title",
    "creator",
    "subject",
    "description",
    "lastModifiedBy",
    "lastPrinted",
    "revision",
    "created",
    "modified",
    "category",
    "contentStatus",
    "language",
    "identifier",
    "version",
    # app.xml - application-level metadata: short fixed strings, build
    # versions, company name, sheet/row/page counts.
    "Application",
    "AppVersion",
    "Company",
    "Manager",
    "DocSecurity",
    "TotalTime",
    "ScaleCrop",
    "LinksUpToDate",
    "SharedDoc",
    "HyperlinksChanged",
    "Template",
    # XLSX-specific app.xml fields:
    "TitlesOfParts",
    "HeadingPairs",
    "vector",
    "lpstr",
    "i4",
    "variant",
    # Counts (DOCX-style fields that may also appear):
    "Pages",
    "Words",
    "Characters",
    "Lines",
    "Paragraphs",
    "CharactersWithSpaces",
})

_NS_TAG = re.compile(r"^\{[^}]*\}")


def _local_name(tag: str) -> str:
    return _NS_TAG.sub("", tag)


def _extract_rendered_text(zf: zipfile.ZipFile) -> str:
    """Concatenate every visible cell text contributor: shared
    strings plus inline-string ``<is><t>`` runs in any worksheet.
    Used as the haystack for the divergence comparator.
    """
    chunks: list[str] = []
    names = zf.namelist()
    # Shared strings table
    if "xl/sharedStrings.xml" in names:
        try:
            xml_bytes = zf.read("xl/sharedStrings.xml")
            root = ET.fromstring(xml_bytes)
            for el in root.iter():
                if _local_name(el.tag) == "t" and el.text:
                    chunks.append(el.text)
        except (KeyError, ET.ParseError):
            pass
    # Inline strings in worksheets and any other <t> nodes
    for name in names:
        if name.startswith("xl/worksheets/") and name.endswith(".xml"):
            try:
                xml_bytes = zf.read(name)
                root = ET.fromstring(xml_bytes)
                for el in root.iter():
                    if _local_name(el.tag) == "t" and el.text:
                        chunks.append(el.text)
            except (KeyError, ET.ParseError):
                continue
    return "\n".join(chunks)


def _walk_metadata_fields(
    xml_bytes: bytes, part_name: str,
) -> Iterable[tuple[str, str, str]]:
    """Yield (field_label, divergence_lookup_key, text_value) triples
    for every leaf element with non-empty text in a metadata part.

    Custom-property parts use ``<property name="X"><vt:lpwstr>...
    </vt:lpwstr></property>``; the typed leaf carries the value while
    the parent's ``name`` attribute carries the field's identity.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return
    parent_map: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in parent:
            parent_map[child] = parent
    for el in root.iter():
        text = (el.text or "").strip()
        if not text:
            continue
        has_text_child = any((c.text or "").strip() for c in el)
        if has_text_child:
            continue
        local = _local_name(el.tag)
        parent = parent_map.get(el)
        parent_name = parent.get("name") if parent is not None else None
        if parent_name:
            label = f"{part_name}:{parent_name}"
            divergence_key = parent_name
        else:
            label = f"{part_name}:{local}"
            divergence_key = local
        yield label, divergence_key, text


def _check_field(
    field_label: str,
    value: str,
    rendered: str,
    divergence_eligible: bool,
) -> Iterable[Finding]:
    out: list[Finding] = []
    encoded_len = len(value.encode("utf-8", errors="replace"))
    # (a) length
    if encoded_len > _FIELD_LENGTH_LIMIT:
        preview = (
            value if len(value) <= _PREVIEW_LIMIT
            else value[:_PREVIEW_LIMIT] + "..."
        )
        out.append(Finding(
            mechanism="xlsx_metadata_payload",
            tier=1,
            confidence=1.0,
            description=(
                f"Metadata field {field_label} carries {encoded_len} "
                f"UTF-8 bytes, exceeding the {_FIELD_LENGTH_LIMIT}-"
                f"byte per-field limit. Long metadata is structurally "
                f"anomalous regardless of content."
            ),
            location=field_label,
            surface=f"metadata field {field_label}",
            concealed=f"length {encoded_len} bytes; text: {preview!r}",
            source_layer="batin",
        ))
    # (b) divergence
    if divergence_eligible:
        stripped = value.strip()
        if (
            len(stripped) >= _MIN_DIVERGENCE_LENGTH
            and stripped not in rendered
        ):
            preview = (
                stripped if len(stripped) <= _PREVIEW_LIMIT
                else stripped[:_PREVIEW_LIMIT] + "..."
            )
            out.append(Finding(
                mechanism="xlsx_metadata_payload",
                tier=1,
                confidence=1.0,
                description=(
                    f"Metadata field {field_label} carries text "
                    f"({len(stripped)} chars) that does not appear "
                    f"in any rendered cell. Content-summary fields "
                    f"whose text diverges from the visible grid are "
                    f"structurally anomalous: a downstream extractor "
                    f"reading the metadata sees content the human "
                    f"reader does not."
                ),
                location=field_label,
                surface=f"metadata field {field_label}",
                concealed=(
                    f"text not present in any rendered cell; "
                    f"recovered text: {preview!r}"
                ),
                source_layer="batin",
            ))
    return out


def detect_xlsx_metadata_payload(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for hidden-text payloads in
    ``docProps/*`` metadata parts of an XLSX package.
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            rendered = _extract_rendered_text(zf)
            names = zf.namelist()
            for part in _META_PARTS:
                if part not in names:
                    continue
                try:
                    xml_bytes = zf.read(part)
                except KeyError:
                    continue
                for label, divergence_key, value in (
                    _walk_metadata_fields(xml_bytes, part)
                ):
                    divergence_eligible = (
                        divergence_key
                        not in _DIVERGENCE_EXEMPT_LOCALNAMES
                    )
                    findings.extend(_check_field(
                        label, value, rendered,
                        divergence_eligible=divergence_eligible,
                    ))
    except (zipfile.BadZipFile, OSError):
        return findings
    return findings


__all__ = ["detect_xlsx_metadata_payload"]
