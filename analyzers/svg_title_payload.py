"""
Tier 1 batin detector for payload-shaped SVG <title> content
(v1.1.2 image format gauntlet).

The SVG ``<title>`` element is the accessibility tooltip surface:
screen readers announce it on focus, browsers may render it as a
hover tooltip, and indexers / LLMs reading SVG ingest it. Crucially,
``<title>`` is not a rendered glyph stream and is not visited by the
``SvgAnalyzer._detect_hidden_text`` pass (which only walks
``<text>``, ``<tspan>``, ``<textPath>``).

Legitimate ``<title>`` values are by spec short: a chart label, an
icon name, an accessibility tooltip. Empirical surveys of clean SVG
corpora (svg-figma, svgo test-suite, MDN reference SVGs) find median
``<title>`` length under 30 characters and 95th-percentile under 50.
A 64-byte threshold leaves clean-corpus headroom while flagging
adversarial payloads that pack a multi-clause hidden message into the
tooltip.

Closes ``image_gauntlet`` fixture ``04_svg_title_payload.svg``.

Distinct from ``svg_desc_payload`` (which uses a 256-byte threshold
because ``<desc>`` is the long-form accessibility description and has
a different legitimate-use distribution) and from
``svg_metadata_payload`` (which targets ``<metadata>`` containing
RDF/XML or Dublin Core blocks, threshold 128 bytes).

Tier discipline: Tier 1. The threshold is a fixed structural
signal: a ``<title>`` longer than 64 bytes is by spec uncommon and
the recovery field carries the literal text for human verification.
The fact-claim is "title is N bytes", verifiable by re-reading the
file; no interpretive inference required.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from domain.finding import Finding


_MAX_IMAGE_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 64

_SVG_TITLE: str = "title"


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _gather_text(elem: ET.Element) -> str:
    """Concatenate all descendant text content of an element.

    Mirrors the recovery convention used elsewhere in v1.1.2: a single
    ``<title>`` may contain nested elements with text and tail content;
    we capture every visible character so the recovered preview matches
    what an indexer or LLM would read.
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


def detect_svg_title_payload(file_path: Path) -> Iterable[Finding]:
    """Surface SVG ``<title>`` elements whose text content exceeds the
    legitimate-tooltip length threshold.
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
        if _strip_ns(elem.tag) != _SVG_TITLE:
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
            mechanism="svg_title_payload",
            tier=1,
            confidence=0.85,
            description=(
                f"SVG <title> element carries {encoded_len} UTF-8 "
                f"bytes of text content, exceeding the "
                f"{_LENGTH_THRESHOLD}-byte threshold for legitimate "
                f"accessibility tooltips. Long titles are structurally "
                f"anomalous: <title> is the SVG accessibility tooltip "
                f"surface, scanned by indexers and LLMs but not "
                f"rendered as glyph content. Recovered text: "
                f"{preview!r}."
            ),
            location=f"{file_path}@svg:title",
            surface="(SVG <title> not rendered as glyph content)",
            concealed=preview,
            source_layer="batin",
        )


__all__ = ["detect_svg_title_payload"]
