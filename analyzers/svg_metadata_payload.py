"""
Tier 1 batin detector for payload-shaped SVG <metadata> content
(v1.1.2 image format gauntlet).

The SVG ``<metadata>`` element carries machine-readable annotations
(typically RDF/XML, Dublin Core, Creative Commons license blocks).
Crawlers, indexers, and LLMs that ingest SVG read this surface; it
is not rendered as glyph content. Legitimate metadata blocks are
typically short (CC license URI, single dc:title, dc:creator), but
some formats (e.g. Inkscape exports with author/notes) can include
modest descriptive text.

Threshold rationale: 128 bytes is calibrated between ``<title>``
(64 bytes, terse tooltip) and ``<desc>`` (256 bytes, multi-sentence
accessibility narrative). Empirically, well-formed metadata blocks
holding only a license URI and creator name fall well below 128
bytes; payload-bearing metadata blocks (multi-sentence
``dc:description`` content, narrative ``dc:abstract`` blocks) cross
the threshold.

Closes ``image_gauntlet`` fixture ``05_svg_metadata_payload.svg``.

Distinct from ``svg_title_payload`` (64-byte threshold on
``<title>``) and ``svg_desc_payload`` (256-byte threshold on
``<desc>``).

Tier discipline: Tier 1. The threshold is a fixed structural
signal: aggregate text content within ``<metadata>`` exceeding 128
bytes is empirically rare in clean SVG corpora and the recovery
field carries the literal text for human verification. The fact
claim is "metadata text content is N bytes", verifiable by
re-reading the file; no interpretive inference required.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from domain.finding import Finding


_MAX_IMAGE_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 128

_SVG_METADATA: str = "metadata"


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _gather_text(elem: ET.Element) -> str:
    """Concatenate all descendant text content of an element.

    Mirrors the recovery convention used by ``svg_title_payload`` and
    ``svg_desc_payload``. ``<metadata>`` typically wraps an
    ``<rdf:RDF>`` block with nested ``<rdf:Description>`` /
    ``<dc:title>`` / ``<dc:description>`` / ``<dc:creator>``
    elements; we capture every text node so the recovered preview
    matches what a metadata-aware indexer or LLM would read.
    """
    parts: list[str] = []
    if elem.text:
        parts.append(elem.text)
    for child in elem.iter():
        if child is elem:
            continue
        if child.text:
            parts.append(child.text)
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def detect_svg_metadata_payload(file_path: Path) -> Iterable[Finding]:
    """Surface SVG ``<metadata>`` elements whose aggregate text
    content exceeds the 128-byte legitimate-metadata threshold.
    """
    try:
        raw = file_path.read_bytes()
    except OSError:
        return

    if len(raw) > _MAX_IMAGE_BYTES:
        raw = raw[:_MAX_IMAGE_BYTES]

    text = raw.decode("utf-8", errors="replace")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return

    if _strip_ns(root.tag) != "svg":
        return

    for elem in root.iter():
        if _strip_ns(elem.tag) != _SVG_METADATA:
            continue

        content = _gather_text(elem).strip()
        if not content:
            continue

        encoded_len = len(content.encode("utf-8", errors="replace"))
        if encoded_len <= _LENGTH_THRESHOLD:
            continue

        preview = (
            content if len(content) <= _PREVIEW_LIMIT
            else content[:_PREVIEW_LIMIT] + "..."
        )

        yield Finding(
            mechanism="svg_metadata_payload",
            tier=1,
            confidence=0.85,
            description=(
                f"SVG <metadata> block carries {encoded_len} UTF-8 "
                f"bytes of aggregate text content, exceeding the "
                f"{_LENGTH_THRESHOLD}-byte threshold for legitimate "
                f"RDF/Dublin Core metadata. Long metadata text is "
                f"structurally anomalous: <metadata> is the SVG "
                f"machine-readable annotation surface (license, "
                f"creator, title), scanned by indexers and LLMs "
                f"but not rendered as glyph content. Recovered "
                f"text: {preview!r}."
            ),
            location=f"{file_path}@svg:metadata",
            surface="(SVG <metadata> not rendered as glyph content)",
            concealed=preview,
            source_layer="batin",
        )


__all__ = ["detect_svg_metadata_payload"]
