"""
Tier 1 detector for hidden-text payloads in DOCX metadata parts (v1.1.2).

OOXML stores three metadata parts under ``docProps/``:

  * ``docProps/core.xml`` - Dublin-core fields (creator, title, subject,
    description, keywords, etc.). Always present in a Word-saved file.
  * ``docProps/app.xml`` - Application-level metadata (Application,
    AppVersion, Company, Manager, etc.). Always present in a
    Word-saved file.
  * ``docProps/custom.xml`` - Author-defined custom properties. Optional
    but a well-known location for arbitrary key/value content.

All three are read by Word, indexers (Spotlight, Windows Search,
SharePoint), and any LLM ingestion path that walks the OOXML package
tree. None of them appear in ``word/document.xml`` rendered text by
default (titles abbreviate, descriptions summarize, custom values are
free-form key/value text).

A run-of-the-mill Word document carries short metadata strings (a
title, an author name, a keyword list with a handful of comma-
separated items). Adversarial use places long text payloads or
directive content in these fields, knowing that the rendered page
shows nothing while every metadata-aware extractor reads the payload.

Mirrors the PDF analyzer's ``pdf_metadata_analyzer`` mechanism with
the same triggers:

  (a) length: any field text exceeding 512 UTF-8 bytes is structurally
      anomalous;
  (b) divergence: a content-summary field (description, custom
      property values) that does not appear in document.xml's
      rendered text and is at least 16 chars is anomalous.

Title / creator / subject (core) and Application / Company (app) are
intentionally exempted from the divergence trigger because legitimate
values frequently do not appear verbatim in the body.

Closes docx_gauntlet fixture 03_custom_xml_properties.docx.

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


# Field length ceiling in UTF-8 bytes; matches ``pdf_metadata_analyzer``
# for cross-format consistency.
_FIELD_LENGTH_LIMIT = 512

# Floor on metadata text considered for the divergence trigger.
_MIN_DIVERGENCE_LENGTH = 16

# Preview ceiling for inversion_recovery.concealed bytes.
_PREVIEW_LIMIT = 240

# Metadata parts to inspect.
_META_PARTS = (
    "docProps/core.xml",
    "docProps/app.xml",
    "docProps/custom.xml",
)

# Tag local-names whose divergence with rendered text is *not*
# structurally suspicious because legitimate values commonly do not
# appear verbatim in the document body. Matches the exclusion list
# documented in pdf_metadata_analyzer.
_DIVERGENCE_EXEMPT_LOCALNAMES = frozenset({
    # core.xml — all canonical Dublin-core / dcterms fields:
    # legitimate values frequently do not appear verbatim in the body
    # (titles abbreviate, creator names are credited differently,
    # subjects summarize, descriptions auto-populate from generator
    # software like python-docx). Date stamps obviously never appear
    # as visible body text. The /Keywords analogue equivalent in
    # core.xml is ``keywords`` which IS divergence-eligible (parallel
    # to PDF /Info /Keywords) - kept off this exempt list.
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
    # app.xml - application-level metadata; legitimate values are
    # short fixed strings ("Microsoft Office Word", a build version,
    # a company name, page/word counts) - all unlikely to appear
    # verbatim in body text yet legitimately divergent.
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
    "Pages",
    "Words",
    "Characters",
    "Lines",
    "Paragraphs",
    "CharactersWithSpaces",
    "PresentationFormat",
    "Slides",
    "Notes",
    "HiddenSlides",
    "MMClips",
})

# Regex for stripping namespace from a tag.
_NS_TAG = re.compile(r"^\{[^}]*\}")


def _local_name(tag: str) -> str:
    return _NS_TAG.sub("", tag)


def _extract_rendered_text(zf: zipfile.ZipFile) -> str:
    """Best-effort: concatenate every ``<w:t>`` text node in
    ``word/document.xml``. Used only as the haystack for the
    divergence comparator; missing some legitimate text causes false
    positives only if the divergent metadata happens to mirror that
    gap, which is bounded by ``_MIN_DIVERGENCE_LENGTH``.
    """
    if "word/document.xml" not in zf.namelist():
        return ""
    try:
        xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (KeyError, ET.ParseError):
        return ""
    chunks: list[str] = []
    for el in root.iter():
        if _local_name(el.tag) == "t" and el.text:
            chunks.append(el.text)
    return "\n".join(chunks)


def _walk_metadata_fields(
    xml_bytes: bytes, part_name: str,
) -> Iterable[tuple[str, str, str]]:
    """Yield (field_label, local_name_for_exempt_lookup, text_value)
    triples for every leaf element with non-empty text content in a
    metadata part. Custom-property parts use a different layout (each
    ``<property>`` element wraps the value in a typed child like
    ``<vt:lpwstr>``); the parent's ``name`` attribute is the field's
    semantic identity, while the typed leaf is where the text lives.
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return
    # Build a parent map so we can recover a typed leaf's parent
    # ``<property>`` element when iterating custom.xml.
    parent_map: dict[ET.Element, ET.Element] = {}
    for parent in root.iter():
        for child in parent:
            parent_map[child] = parent
    # core.xml / app.xml: leaf elements like <dc:title>, <dc:keywords>.
    # custom.xml: <property name="..."><vt:lpwstr>...</vt:lpwstr></property>.
    # Both reduce to "leaf with non-empty text" iteration; for the
    # custom-property case we promote the parent's ``name`` attribute
    # to the divergence-lookup local-name so legitimate well-known
    # property names can be exempted explicitly if ever needed.
    for el in root.iter():
        text = (el.text or "").strip()
        if not text:
            continue
        # Leaves only; if any child has text, prefer the child as the
        # leaf (custom.xml's <vt:lpwstr> is the leaf, not <property>).
        has_text_child = any((c.text or "").strip() for c in el)
        if has_text_child:
            continue
        local = _local_name(el.tag)
        parent = parent_map.get(el)
        parent_name = parent.get("name") if parent is not None else None
        if parent_name:
            # Custom property: "docProps/custom.xml:ActualRevenue".
            # divergence-lookup uses parent_name, so unique custom
            # property names CAN be exempted in the future without
            # affecting other custom properties.
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
            mechanism="docx_metadata_payload",
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
                mechanism="docx_metadata_payload",
                tier=1,
                confidence=1.0,
                description=(
                    f"Metadata field {field_label} carries text "
                    f"({len(stripped)} chars) that does not appear "
                    f"in word/document.xml. Content-summary fields "
                    f"whose text diverges from the visible surface "
                    f"are structurally anomalous: a downstream "
                    f"extractor reading the metadata sees content "
                    f"the human reader does not."
                ),
                location=field_label,
                surface=f"metadata field {field_label}",
                concealed=(
                    f"text not present in any rendered run; "
                    f"recovered text: {preview!r}"
                ),
                source_layer="batin",
            ))
    return out


def detect_docx_metadata_payload(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for hidden-text payloads in
    ``docProps/*`` metadata parts.
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


__all__ = ["detect_docx_metadata_payload"]
