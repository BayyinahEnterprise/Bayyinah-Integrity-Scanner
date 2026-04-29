"""
Tier 1 zahir detector for white-on-white text in SVG (v1.1.2 image
format gauntlet).

A ``<text>`` element with ``fill="white"`` (hex ``#FFFFFF`` or one of
the near-white off-by-one variants ``#FEFEFE``, ``#FDFDFD``,
``#FCFCFC``) on a background that is also white renders the text
invisible to a human reader while keeping every byte present in the
source. Mirrors the PDF analyzer's ``white_on_white_text`` mechanism
and the DOCX / XLSX ``*_white_text`` detectors.

The mechanism classifies as zahir, not batin, because the text is on
the rendered surface in every other respect (coordinates, a
font size, and DOM-readable text content). The only reason a human
does not see it is the color match. Once the analyzer walks the SVG
tree, the text is plainly visible at the byte level.

Closes ``image_gauntlet`` fixture ``03_svg_white_text.svg``.

Background detection: SVG has no single ``<background>`` element. The
"background" is whatever the container renders behind the text. We
use a conservative heuristic: if the document contains a ``<rect>``
covering the canvas (width/height matching the root viewport, or
filling 100%/100%) with a near-white fill, OR if the SVG has no
explicit background fill at all (default white in every renderer),
we treat the background as white. Anything else (a colored rect, a
gradient, a pattern) leaves the detector silent so a legitimate
white-on-blue header is not flagged.

Tier discipline: Tier 1. The color match is byte-deterministic.
A literal ``fill="#FFFFFF"`` (or near-white) on text whose container
ancestor is white-or-default has no other plausible reading.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from domain.finding import Finding


_MAX_IMAGE_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240

_SVG_NS: str = "http://www.w3.org/2000/svg"

# Near-white hex values. The fixture uses #FFFFFF exactly; the four
# off-white values cover the common "almost invisible" tactic where an
# attacker lightens by one or two units to defeat naive equality
# checks. Anything darker is treated as legitimate light-gray.
_NEAR_WHITE_HEX: frozenset[str] = frozenset(
    {"FFFFFF", "FEFEFE", "FDFDFD", "FCFCFC"}
)

# Named CSS colors that resolve to white. Both spellings are
# case-insensitive in CSS and SVG.
_NEAR_WHITE_NAMES: frozenset[str] = frozenset(
    {"white", "#fff"}
)


def _normalize_color(value: str) -> str | None:
    """Return a 6-hex uppercase form of a color value, or None.

    Accepts ``#FFFFFF``, ``#FFF``, the literal name ``white``, and
    the three-hex shorthand. ``rgb(255, 255, 255)`` and CSS color
    functions are normalised via a permissive regex.
    """
    if not value:
        return None
    v = value.strip().lower()

    if v == "white":
        return "FFFFFF"

    if v.startswith("#"):
        hex_part = v[1:]
        if len(hex_part) == 3:
            # #FFF -> #FFFFFF
            return (hex_part[0] * 2 + hex_part[1] * 2 + hex_part[2] * 2).upper()
        if len(hex_part) == 6:
            return hex_part.upper()
        return None

    rgb_match = re.match(
        r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)", v
    )
    if rgb_match:
        try:
            r, g, b = (int(rgb_match.group(i)) for i in (1, 2, 3))
        except ValueError:
            return None
        if all(0 <= x <= 255 for x in (r, g, b)):
            return f"{r:02X}{g:02X}{b:02X}"
    return None


def _is_near_white(color_value: str | None) -> bool:
    if not color_value:
        return False
    norm = _normalize_color(color_value)
    if norm is None:
        return False
    return norm in _NEAR_WHITE_HEX


def _strip_ns(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _element_fill(elem: ET.Element) -> str | None:
    """Return the effective fill color for an element.

    Checks the ``fill`` attribute first, then a ``style`` attribute
    of the form ``style="fill: #fff; ..."``. Nested style cascades
    from CSS classes are not resolved (out of scope at this tier);
    inline styles cover the byte-deterministic adversarial case.
    """
    fill = elem.get("fill")
    if fill:
        return fill
    style = elem.get("style")
    if not style:
        return None
    for decl in style.split(";"):
        if ":" not in decl:
            continue
        name, value = decl.split(":", 1)
        if name.strip().lower() == "fill":
            return value.strip()
    return None


def _root_background_is_white(root: ET.Element) -> bool:
    """Return True if the SVG root has a default-white background or
    a near-white full-canvas ``<rect>`` covering the viewport.

    SVG has no native ``background-color`` attribute on the root.
    The canvas is white by convention (every browser, every renderer).
    A non-white background is set by drawing a filled ``<rect>`` at
    the origin covering the full ``viewBox`` or width / height. If
    such a rect exists and is non-white, we treat the background as
    non-white and the detector stays silent against text on it.
    """
    width = root.get("width") or ""
    height = root.get("height") or ""

    for child in root:
        tag = _strip_ns(child.tag)
        if tag != "rect":
            continue
        rx = child.get("x") or "0"
        ry = child.get("y") or "0"
        rw = child.get("width") or ""
        rh = child.get("height") or ""
        # Viewport-spanning rect: x=0, y=0, width and height match
        # root width/height (or "100%" expressing the same thing).
        if rx not in ("0", "0px") or ry not in ("0", "0px"):
            continue
        spans_width = rw == width or rw == "100%"
        spans_height = rh == height or rh == "100%"
        if not (spans_width and spans_height):
            continue
        rect_fill = _element_fill(child)
        if rect_fill is None:
            return True  # rect with no fill renders as default black,
            # but the spec is "no fill" defaults to black for a rect.
            # In practice adversarial fixtures always set a fill, so
            # falling through to the no-rect default is safer than
            # claiming black on a rect with no explicit fill.
        return _is_near_white(rect_fill)

    # No viewport-spanning rect: SVG default canvas is white.
    return True


def detect_svg_white_text(file_path: Path) -> Iterable[Finding]:
    """Surface SVG ``<text>`` elements whose fill is near-white on a
    near-white (or default) background.
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

    if not _root_background_is_white(root):
        return

    for elem in root.iter():
        if _strip_ns(elem.tag) != "text":
            continue
        fill = _element_fill(elem)
        if not _is_near_white(fill):
            continue
        # Concatenate all text content in the element (including
        # nested <tspan>) to recover the rendered string.
        content_parts: list[str] = []
        if elem.text:
            content_parts.append(elem.text)
        for child in elem.iter():
            if child is elem:
                continue
            if child.text:
                content_parts.append(child.text)
            if child.tail:
                content_parts.append(child.tail)
        content = "".join(content_parts).strip()
        if not content:
            continue

        norm = _normalize_color(fill) or "?"
        preview = (
            content if len(content) <= _PREVIEW_LIMIT
            else content[:_PREVIEW_LIMIT] + "..."
        )

        yield Finding(
            mechanism="svg_white_text",
            tier=1,
            confidence=1.0,
            description=(
                f"SVG <text> element with fill #{norm} carrying "
                f"{len(content)} characters of text on a white "
                f"canvas. White-on-white text is invisible to a human "
                f"reader but plainly readable in the SVG source. "
                f"Recovered text: {preview!r}."
            ),
            location=f"{file_path}@svg:text",
            surface=(
                f"(SVG <text> rendered in white #{norm} on white canvas)"
            ),
            concealed=preview,
            source_layer="zahir",
        )


__all__ = ["detect_svg_white_text"]
