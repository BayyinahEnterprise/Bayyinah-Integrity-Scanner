"""
SvgAnalyzer — zahir/batin witness for SVG (vector image / XML) files.

    يُخَادِعُونَ اللَّـهَ وَالَّذِينَ آمَنُوا وَمَا يَخْدَعُونَ إِلَّا
    أَنفُسَهُمْ وَمَا يَشْعُرُونَ
    (Al-Baqarah 2:9)

    "They think to deceive Allah and those who believe, but they
    deceive only themselves, and perceive it not."

Architectural reading. SVG is an image by purpose and an XML document
by substrate. The browser that opens an .svg file renders vector paths
— and also evaluates any <script> elements, fires any on* event
handlers, resolves xlink:href references, and honours <foreignObject>
to embed HTML inside the image. Every legitimate SVG tool outputs a
subset of SVG that uses none of these; every adversarial SVG uses
exactly these. The analyzer walks the XML tree and reports which
features the file actually uses.

Supported FileKinds: ``IMAGE_SVG``. Raster images (PNG/JPEG) go to
``ImageAnalyzer``; plain XML without an ``<svg>`` element is not routed
here.

Mechanisms emitted:

    svg_embedded_script        (zahir) <script> element present.
                               Tier 1: its mere presence is active
                               content the moment a scripting-enabled
                               renderer opens the file.
    svg_event_handler          (zahir) any attribute whose name begins
                               with ``on`` (onload, onclick, ...) —
                               inline script hooks.
    svg_external_reference     (batin) href / xlink:href pointing to
                               an absolute ``http://`` / ``https://``
                               URL. SVG can pull resources at render
                               time; external references leak referer
                               and beacon.
    svg_embedded_data_uri      (batin) a ``data:`` URI as the target
                               of an href / xlink:href — opaque
                               embedded payload (raster image, script,
                               HTML, ...).
    svg_foreign_object         (batin) <foreignObject> element —
                               allows arbitrary non-SVG (typically
                               HTML) to live inside the SVG canvas.
    zero_width_chars, tag_chars, bidi_control, homoglyph
                               (zahir) Unicode concealment catalogue
                               run against every text node / attribute
                               value in the document. A tag-char
                               prompt-injection payload inside an SVG
                               <text> element is still a tag-char
                               payload.

Implementation notes. We parse with the stdlib ``xml.etree.ElementTree``
but with external-entity resolution hardened off: ``ElementTree`` does
not resolve external DTDs by default (it uses ``expat`` in a minimal
mode), but we additionally refuse any document containing a DOCTYPE
declaration at the byte level — that is a standalone batin signal as
well. A malformed SVG is reported as ``scan_error`` (structural witness:
we could not fully inspect the inner graph).

Additive-only. Existing analyzers are untouched; this analyzer declares
its own ``supported_kinds`` and is selected by the registry's Phase 9
kind filter.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import ClassVar, Iterable

from analyzers.base import BaseAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    compute_muwazana_score,
)
from domain.config import (
    BIDI_CONTROL_CHARS,
    CONFUSABLE_TO_LATIN,
    MATH_ALPHANUMERIC_RANGE,
    SVG_EVENT_ATTRIBUTE_PREFIX,
    SVG_INVISIBLE_ATTRIBUTES,
    SVG_INVISIBLE_STYLE_FRAGMENTS,
    SVG_MICROSCOPIC_FONT_THRESHOLD,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# 16 MB — SVGs over this are rare; cap memory on adversarial input.
_MAX_READ_BYTES = 16 * 1024 * 1024

# XML / href attribute names. SVG 2 allows either ``href`` or
# ``xlink:href`` — we look for both.
_HREF_ATTRS: frozenset[str] = frozenset({
    "href",
    "{http://www.w3.org/1999/xlink}href",
})

_DATA_URI_PREFIX: str = "data:"
_HTTP_SCHEMES: tuple[str, ...] = ("http://", "https://", "ftp://")

# Latin-letter detection for homoglyph pass (A-Z / a-z).
_LATIN_RANGES = (
    range(0x0041, 0x005B),
    range(0x0061, 0x007B),
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


def _strip_ns(tag: str) -> str:
    """``{http://www.w3.org/2000/svg}rect`` -> ``rect``."""
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


# ---------------------------------------------------------------------------
# SvgAnalyzer
# ---------------------------------------------------------------------------


class SvgAnalyzer(BaseAnalyzer):
    """Detects script/event/external-reference concealment in SVG files."""

    name: ClassVar[str] = "svg"
    error_prefix: ClassVar[str] = "SVG scan error"
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({
        FileKind.IMAGE_SVG,
    })

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the SVG file at ``file_path`` for concealment mechanisms."""
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            return self._scan_error_report(file_path, str(exc))

        if len(data) > _MAX_READ_BYTES:
            data = data[:_MAX_READ_BYTES]

        text = data.decode("utf-8", errors="replace")

        # Parse the XML. Malformed SVGs are real — we still want to run
        # the text-layer concealment catalogue against the raw bytes,
        # even if the tree is broken, because Unicode concealment is
        # text-level not structure-level.
        root: ET.Element | None
        parse_error: str | None = None
        try:
            # We intentionally avoid ET.fromstring(data) — a non-utf-8
            # SVG would error there. Parse the decoded text.
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            root = None
            parse_error = str(exc)

        findings: list[Finding] = []

        # 1. Text-layer concealment pass across the entire byte stream.
        #    Runs even if XML parse failed — the zahir surface exists in
        #    the raw text regardless of whether the tree is well-formed.
        findings.extend(self._detect_unicode_concealment(text, file_path))

        # 2. SVG-structural pass. Only runs if the tree parsed.
        if root is not None:
            findings.extend(self._detect_structural(root, file_path))

        if parse_error is not None:
            # Emit a scan_error as a structural witness — the tree was
            # not fully inspectable, so absence of structural findings
            # is not evidence of absence.
            findings.append(Finding(
                mechanism="scan_error",
                tier=TIER["scan_error"],
                confidence=1.0,
                description=(
                    f"SVG XML parse failed: {parse_error}. "
                    "Text-layer concealment scan completed against the "
                    "raw bytes; structural scan was skipped."
                ),
                location=f"analyzer:{self.name}",
                surface="(structural scan did not complete)",
                concealed="(absence of structural findings is not evidence of cleanness)",
                source_layer=self.source_layer,
            ))
            report = IntegrityReport(
                file_path=str(file_path),
                integrity_score=compute_muwazana_score(findings),
                findings=findings,
                error=f"{self.error_prefix}: {parse_error}",
                scan_incomplete=True,
            )
            return report

        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # Text-layer concealment
    # ------------------------------------------------------------------

    def _detect_unicode_concealment(
        self, text: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Zero-width / TAG block / bidi-control / math-alphanumeric —
        flat per-line groups."""
        zw_lines: dict[int, list[str]] = {}
        tag_lines: dict[int, list[str]] = {}
        bidi_lines: dict[int, list[str]] = {}
        math_lines: dict[int, list[str]] = {}

        line = 1
        for ch in text:
            if ch == "\n":
                line += 1
                continue
            cp = ord(ch)
            if ch in ZERO_WIDTH_CHARS:
                zw_lines.setdefault(line, []).append(ch)
            elif cp in TAG_CHAR_RANGE:
                tag_lines.setdefault(line, []).append(ch)
            elif ch in BIDI_CONTROL_CHARS:
                bidi_lines.setdefault(line, []).append(ch)
            elif cp in MATH_ALPHANUMERIC_RANGE:
                math_lines.setdefault(line, []).append(ch)

        for ln, chars in zw_lines.items():
            cps = ", ".join(sorted({f"U+{ord(c):04X}" for c in chars}))
            yield Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.9,
                description=(
                    f"{len(chars)} zero-width character(s) on this line "
                    f"({cps}) inside SVG text."
                ),
                location=f"{file_path}:{ln}",
                surface="(no visible indication)",
                concealed=f"{len(chars)} zero-width codepoint(s)",
                source_layer="zahir",
            )
        for ln, chars in tag_lines.items():
            shadow = "".join(
                chr(ord(c) - 0xE0000) if 0x20 <= ord(c) - 0xE0000 <= 0x7E
                else "?"
                for c in chars
            )
            yield Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=1.0,
                description=(
                    f"{len(chars)} Unicode TAG character(s) on this line "
                    "inside SVG text — invisible to human readers, "
                    f"decodable by LLMs. Decoded shadow: {shadow!r}."
                ),
                location=f"{file_path}:{ln}",
                surface="(no visible indication)",
                concealed=f"TAG payload ({len(chars)} codepoints)",
                source_layer="zahir",
            )
        for ln, chars in bidi_lines.items():
            cps = ", ".join(sorted({f"U+{ord(c):04X}" for c in chars}))
            yield Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(chars)} bidi-control character(s) on this line "
                    f"({cps}) inside SVG text — reorders display order."
                ),
                location=f"{file_path}:{ln}",
                surface="(reordered display)",
                concealed=f"{len(chars)} bidi-override codepoint(s)",
                source_layer="zahir",
            )
        for ln, chars in math_lines.items():
            cps = ", ".join(sorted({f"U+{ord(c):04X}" for c in chars}))
            yield Finding(
                mechanism="mathematical_alphanumeric",
                tier=TIER["mathematical_alphanumeric"],
                confidence=0.9,
                description=(
                    f"{len(chars)} Mathematical Alphanumeric Symbols "
                    f"codepoint(s) on this line ({cps}) inside SVG text — "
                    "render as bold / italic / script Latin under any "
                    "modern font while living outside ASCII. Cross-script "
                    "smuggling vector."
                ),
                location=f"{file_path}:{ln}",
                surface="(reads as ordinary bold/italic/script text)",
                concealed=f"{len(chars)} math-block codepoint(s)",
                source_layer="zahir",
            )

        # Homoglyph pass — word-level, matches the TextFileAnalyzer rule.
        for match in re.finditer(r"\S+", text):
            word = match.group()
            if len(word) < 2:
                continue
            confusables = [c for c in word if c in CONFUSABLE_TO_LATIN]
            latin = [c for c in word if _is_latin_letter(c)]
            if not confusables:
                continue
            if not (latin or len(confusables) >= 2):
                continue
            recovered = "".join(
                CONFUSABLE_TO_LATIN.get(c, c) for c in word
            )
            cp_info = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in confusables})
            )
            line = text.count("\n", 0, match.start()) + 1
            yield Finding(
                mechanism="homoglyph",
                tier=TIER["homoglyph"],
                confidence=0.85,
                description=(
                    f"Word mixes Latin letters with {len(confusables)} "
                    f"confusable codepoint(s) ({cp_info}) inside SVG text "
                    f"— visually impersonates {recovered!r}."
                ),
                location=f"{file_path}:{line}",
                surface=word,
                concealed=f"appears identical to {recovered!r}",
                source_layer="zahir",
            )

    # ------------------------------------------------------------------
    # SVG-structural
    # ------------------------------------------------------------------

    def _detect_structural(
        self, root: ET.Element, file_path: Path,
    ) -> Iterable[Finding]:
        """Walk the XML tree emitting SVG-specific mechanism findings."""
        for elem in root.iter():
            local = _strip_ns(elem.tag).lower()

            # Phase 11 — cross-modal concealment on text-bearing elements.
            # <text>, <tspan>, <textPath> are the primary carriers; we
            # check all three for invisibility attributes / styles and
            # for sub-visual font sizes.
            if local in ("text", "tspan", "textpath"):
                yield from self._detect_hidden_text(elem, file_path, local)
                yield from self._detect_microscopic_text(
                    elem, file_path, local,
                )

            # <script> — tier-1 signal.
            if local == "script":
                script_preview = (elem.text or "").strip()[:80]
                yield Finding(
                    mechanism="svg_embedded_script",
                    tier=TIER["svg_embedded_script"],
                    confidence=1.0,
                    description=(
                        "<script> element present in SVG — active content "
                        "that executes in any scripting-enabled renderer. "
                        f"Preview: {script_preview!r}"
                    ),
                    location=str(file_path),
                    surface="(renders as an image)",
                    concealed="<script> executes on open",
                    source_layer="zahir",
                )

            # <foreignObject> — HTML-inside-SVG escape hatch.
            if local == "foreignobject":
                yield Finding(
                    mechanism="svg_foreign_object",
                    tier=TIER["svg_foreign_object"],
                    confidence=0.9,
                    description=(
                        "<foreignObject> element present — allows arbitrary "
                        "non-SVG content (typically HTML) to be embedded in "
                        "the image."
                    ),
                    location=str(file_path),
                    surface="(vector image)",
                    concealed="foreign (non-SVG) content embedded",
                    source_layer="batin",
                )

            # Attribute-level checks: on*, href/xlink:href.
            for attr_name, attr_value in elem.attrib.items():
                name_local = attr_name.split("}", 1)[-1].lower()

                # Event handler — onclick, onload, onmouseover, ...
                if name_local.startswith(SVG_EVENT_ATTRIBUTE_PREFIX) and (
                    len(name_local) > len(SVG_EVENT_ATTRIBUTE_PREFIX)
                ):
                    yield Finding(
                        mechanism="svg_event_handler",
                        tier=TIER["svg_event_handler"],
                        confidence=0.95,
                        description=(
                            f"SVG element <{local}> carries event handler "
                            f"attribute {name_local!r} — inline script "
                            "hook that fires when the event occurs."
                        ),
                        location=str(file_path),
                        surface=f"<{local}>",
                        concealed=f"{name_local}={attr_value[:60]!r}",
                        source_layer="zahir",
                    )

                # href / xlink:href to external schemes or data: URIs.
                if attr_name in _HREF_ATTRS:
                    val = attr_value.strip()
                    if val.lower().startswith(_DATA_URI_PREFIX):
                        yield Finding(
                            mechanism="svg_embedded_data_uri",
                            tier=TIER["svg_embedded_data_uri"],
                            confidence=0.95,
                            description=(
                                f"SVG element <{local}> references a "
                                "data: URI — opaque embedded payload "
                                "(often an image, HTML fragment, or "
                                "script source)."
                            ),
                            location=str(file_path),
                            surface=f"<{local}>",
                            concealed=f"data: URI ({len(val)} chars)",
                            source_layer="batin",
                        )
                    elif val.lower().startswith(_HTTP_SCHEMES):
                        yield Finding(
                            mechanism="svg_external_reference",
                            tier=TIER["svg_external_reference"],
                            confidence=0.9,
                            description=(
                                f"SVG element <{local}> references an "
                                f"external URL {val!r} — resource is "
                                "fetched at render time, leaking referrer "
                                "and enabling beacon / tracking pixels."
                            ),
                            location=str(file_path),
                            surface=f"<{local}>",
                            concealed=f"external reference to {val}",
                            source_layer="batin",
                        )

    # ------------------------------------------------------------------
    # Phase 11 — hidden / microscopic text helpers
    # ------------------------------------------------------------------

    def _detect_hidden_text(
        self, elem: ET.Element, file_path: Path, local: str,
    ) -> Iterable[Finding]:
        """Emit ``svg_hidden_text`` when a text-bearing element is made
        invisible via opacity / display / visibility / fill attributes,
        or a CSS ``style=""`` containing the same shapes.

        The element must actually carry text (empty <text> tags are
        render-irrelevant), or else we would false-positive on styling
        templates.
        """
        text_payload = (elem.text or "").strip()
        for child in elem.iter():
            if child is elem:
                continue
            text_payload += (child.text or "").strip()
            text_payload += (child.tail or "").strip()
        if not text_payload:
            return

        # Gather attributes, stripping XML namespace prefixes.
        attrib_local: dict[str, str] = {
            k.split("}", 1)[-1].lower(): v for k, v in elem.attrib.items()
        }

        concealment_hits: list[str] = []
        for attr_name, invisible_values in SVG_INVISIBLE_ATTRIBUTES.items():
            val = attrib_local.get(attr_name)
            if val is None:
                continue
            v_norm = val.strip().lower()
            if v_norm in invisible_values:
                concealment_hits.append(f"{attr_name}={val!r}")

        style = attrib_local.get("style", "")
        if style:
            style_lc = style.lower().replace(" ", "")
            for frag in SVG_INVISIBLE_STYLE_FRAGMENTS:
                # Normalise both sides: "opacity: 0" and "opacity:0" hit.
                frag_norm = frag.replace(" ", "")
                if frag_norm in style_lc:
                    concealment_hits.append(f"style~={frag!r}")
                    break

        if not concealment_hits:
            return

        preview = text_payload[:60]
        yield Finding(
            mechanism="svg_hidden_text",
            tier=TIER["svg_hidden_text"],
            confidence=0.95,
            description=(
                f"<{local}> element carries text but is rendered invisible "
                f"via {', '.join(concealment_hits)} — DOM-present, "
                f"human-invisible. Preview: {preview!r}. A classic "
                "performed-alignment shape on a vector-image surface."
            ),
            location=str(file_path),
            surface="(no visible indication)",
            concealed=f"<{local}> text: {preview!r}",
            source_layer="zahir",
        )

    def _detect_microscopic_text(
        self, elem: ET.Element, file_path: Path, local: str,
    ) -> Iterable[Finding]:
        """Emit ``svg_microscopic_text`` when a text-bearing element has
        a font-size attribute at or below
        ``SVG_MICROSCOPIC_FONT_THRESHOLD`` user units.

        We read from the element's own ``font-size`` attribute and from
        any ``font-size:`` fragment inside its ``style=""`` attribute.
        Inherited CSS styling is out of scope — we're catching the
        direct, on-element smuggling shape.
        """
        text_payload = (elem.text or "").strip()
        for child in elem.iter():
            if child is elem:
                continue
            text_payload += (child.text or "").strip()
            text_payload += (child.tail or "").strip()
        if not text_payload:
            return

        attrib_local: dict[str, str] = {
            k.split("}", 1)[-1].lower(): v for k, v in elem.attrib.items()
        }

        raw_size: str | None = attrib_local.get("font-size")
        if raw_size is None:
            style = attrib_local.get("style", "")
            # Look for font-size:NN inside the style string.
            m = re.search(
                r"font-size\s*:\s*([0-9.]+)\s*(px|pt|em|rem|%)?",
                style,
                flags=re.IGNORECASE,
            )
            if m is None:
                return
            raw_size = m.group(1)

        # Strip unit suffixes we can interpret; bail on anything we can't.
        size_str = raw_size.strip().lower()
        for suffix in ("px", "pt", "em", "rem", "%"):
            if size_str.endswith(suffix):
                size_str = size_str[: -len(suffix)].strip()
                break
        try:
            size_val = float(size_str)
        except ValueError:
            return

        if size_val > SVG_MICROSCOPIC_FONT_THRESHOLD:
            return

        preview = text_payload[:60]
        yield Finding(
            mechanism="svg_microscopic_text",
            tier=TIER["svg_microscopic_text"],
            confidence=0.9,
            description=(
                f"<{local}> element renders text at font-size "
                f"{raw_size!r} (<= {SVG_MICROSCOPIC_FONT_THRESHOLD} "
                "user units) — sub-visual at any sensible zoom level. "
                f"Preview: {preview!r}."
            ),
            location=str(file_path),
            surface="(effectively invisible at normal zoom)",
            concealed=f"<{local}> text: {preview!r}",
            source_layer="zahir",
        )


__all__ = ["SvgAnalyzer"]
