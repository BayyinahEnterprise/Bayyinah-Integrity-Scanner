"""
Tier 1 batin detector for payload-shaped SVG <desc> content
(v1.1.2 image format gauntlet).

The SVG ``<desc>`` element is the long-form accessibility
description: screen readers announce it on demand, and indexers /
LLMs reading SVG ingest it. ``<desc>`` is structurally analogous to
``<title>`` but has a different legitimate-use distribution:

  - ``<title>`` is the always-short tooltip (median under 30 chars,
    95th percentile under 50). Threshold: 64 bytes.
  - ``<desc>`` is the long-form description (multi-sentence chart
    legends, scientific diagram captions, accessibility narratives
    for complex visualizations). Threshold: 256 bytes.

A single combined threshold across both elements would either false-
positive on legitimate ``<desc>`` (which can run several sentences)
or false-negative on adversarial ``<title>`` (which only needs to
hide a one-paragraph payload). The split preserves one-detector-per-
mechanism discipline and keeps the threshold rationale traceable for
each element's clean-corpus distribution.

Closes ``image_gauntlet`` fixture ``04_5_svg_desc_payload.svg``.

Distinct from ``svg_title_payload`` (64-byte threshold on ``<title>``)
and from ``svg_metadata_payload`` (which targets ``<metadata>``
containing RDF/XML or Dublin Core blocks, threshold 128 bytes).

Tier discipline: Tier 1. The threshold is a fixed structural
signal: a ``<desc>`` longer than 256 bytes is empirically rare in
clean SVG corpora and the recovery field carries the literal text
for human verification. The fact-claim is "desc is N bytes",
verifiable by re-reading the file; no interpretive inference
required.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from domain.finding import Finding


_MAX_IMAGE_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 256

_SVG_DESC: str = "desc"


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _gather_text(elem: ET.Element) -> str:
    """Concatenate all descendant text content of an element.

    Mirrors the recovery convention used by ``svg_title_payload``: a
    single ``<desc>`` may contain nested elements (rich-text accessibility
    markup) with text and tail content; we capture every visible
    character so the recovered preview matches what an indexer or
    LLM would read.
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


def detect_svg_desc_payload(file_path: Path) -> Iterable[Finding]:
    """Surface SVG ``<desc>`` elements whose text content exceeds the
    256-byte legitimate-description threshold.
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
        if _strip_ns(elem.tag) != _SVG_DESC:
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
            mechanism="svg_desc_payload",
            tier=1,
            confidence=0.85,
            description=(
                f"SVG <desc> element carries {encoded_len} UTF-8 "
                f"bytes of text content, exceeding the "
                f"{_LENGTH_THRESHOLD}-byte threshold for legitimate "
                f"accessibility descriptions. Long descriptions are "
                f"structurally anomalous: <desc> is the SVG long-form "
                f"accessibility surface, scanned by indexers and LLMs "
                f"but not rendered as glyph content. Recovered text: "
                f"{preview!r}."
            ),
            location=f"{file_path}@svg:desc",
            surface="(SVG <desc> not rendered as glyph content)",
            concealed=preview,
            source_layer="batin",
        )


__all__ = ["detect_svg_desc_payload"]
