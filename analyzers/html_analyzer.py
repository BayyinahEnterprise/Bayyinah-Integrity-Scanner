"""
HtmlAnalyzer — full zahir/batin witness for HTML documents.

    وَلَا تَلْبِسُوا الْحَقَّ بِالْبَاطِلِ وَتَكْتُمُوا الْحَقَّ وَأَنتُمْ تَعْلَمُونَ
    (Al-Baqarah 2:42)

    "Do not mix truth with falsehood, nor conceal the truth while you
    know it."

Architectural reading. HTML is the purest mixing-of-truth-and-falsehood
surface Bayyinah reads: every document is a tree whose rendered
projection — what the human opens in a browser — is only a *subset* of
what the file contains. Style, scripts, data-attributes, comments,
external references, and HTML5 ``hidden`` attributes all live in the
file but may or may not survive to the reader's eye. The scanner's job
is to surface that gap.

Zahir (rendered text vs. file stream)
  * ``html_hidden_text``  — an element whose style or attributes
    suppress it from rendering (``display:none``,
    ``visibility:hidden``, ``opacity:0``, ``font-size:0``, offscreen
    positioning, the HTML5 ``hidden`` attribute,
    ``aria-hidden="true"``) — yet the text lives in the DOM and
    reaches every indexer, copy-paste pipeline, and LLM ingesting the
    page.
  * Per-run ``zero_width_chars`` / ``tag_chars`` / ``bidi_control`` /
    ``homoglyph`` — applied only to *visible* text, never to script
    or style bodies, so the detector scopes to the zahir surface.

Batin (object graph / what the file carries)
  * ``html_inline_script`` — ``<script>`` with inline content or any
    element carrying an ``on*=`` event handler. Executable code the
    moment a scripting-capable renderer opens the page; most
    dangerous HTML concealment vector.
  * ``html_data_attribute`` — a ``data-*`` attribute whose value is
    long enough (>= ``_DATA_ATTR_MIN_LENGTH``) to plausibly carry a
    payload rather than a short id / flag. Most subtle vector: custom
    data- attrs are routine, so a reader does not instinctively
    inspect them.
  * ``html_external_reference`` — a resource-loading attribute
    pointing at an absolute remote URL. The renderer reaches outside
    the document when the page opens; tracking beacon / remote-load
    shape.

Parsing strategy: stdlib ``html.parser.HTMLParser``. No external
dependency. The parser is tolerant of malformed input (it will not
raise on missing close tags or bad nesting) — appropriate for
adversarial HTML, where strict parsing would refuse a payload the
browser would still render.

Supported FileKinds: ``{FileKind.HTML}``. The router already classifies
HTML files via magic-byte sniff (``<!doctype html``, ``<html``,
``<body``, ``<head``) plus extension fallback (``.html``, ``.htm``);
this analyzer is the zahir/batin specialist the router's HTML dispatch
was waiting for. ``TextFileAnalyzer`` also declares ``FileKind.HTML``
support and keeps firing on HTML files as a flat-text witness; both
witnesses compose without privilege per 2:143.

Additive-only. Nothing here is imported by ``bayyinah_v0.py`` or
``bayyinah_v0_1.py``; the PDF pipeline is untouched. The new
mechanisms are registered in ``domain/config.py`` alongside the
existing mechanism catalog — old mechanism names, severities, and
tiers are unchanged.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
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
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind

# v1.1.2 HTML format-gauntlet detectors. Each is a standalone byte-
# deterministic Tier 1 detector that opens the file and yields
# Findings. They run alongside the HTMLParser walk above and surface
# payload loci the walker intentionally skips (non-visible containers,
# meta content, comments, CSS pseudo-element content, title/body
# divergence).
from analyzers.html_noscript_payload import detect_html_noscript_payload
from analyzers.html_template_payload import detect_html_template_payload
from analyzers.html_comment_payload import detect_html_comment_payload
from analyzers.html_meta_payload import detect_html_meta_payload
from analyzers.html_style_content_payload import (
    detect_html_style_content_payload,
)
from analyzers.html_title_text_divergence import (
    detect_html_title_text_divergence,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum HTML size we inspect in one pass. Standard HTML documents
# rarely exceed a few MB; very large pages are either adversarial bulk
# or machine-generated logs. Either shape, a 16 MB cap is ample.
_MAX_HTML_BYTES: int = 16 * 1024 * 1024

# Minimum length of a ``data-*`` attribute value before it is flagged.
# Short data- attrs (``data-id="42"``, ``data-role="button"``) are
# routine; long values are the attr-encoding payload shape we want to
# surface. 64 chars catches base64 paragraphs and JWT-sized blobs while
# ignoring the common short-identifier pattern.
_DATA_ATTR_MIN_LENGTH: int = 64

# Tag names whose content we treat as *not* visible text. Anything
# inside these elements is script source or stylesheet source; it lives
# in the batin layer, not the rendered surface.
_NON_VISIBLE_CONTAINERS: frozenset[str] = frozenset({
    "script", "style", "template", "noscript",
})

# Attributes that load an external resource at render time, per element.
# Only these attribute positions are inspected for external-URL patterns
# — a ``<a href="https://...">`` is plain navigation and is not
# a resource-load event, so ``<a>`` is deliberately excluded.
_EXTERNAL_REF_ATTRS: dict[str, frozenset[str]] = {
    "script":    frozenset({"src"}),
    "link":      frozenset({"href"}),
    "img":       frozenset({"src", "srcset"}),
    "iframe":    frozenset({"src"}),
    "video":     frozenset({"src", "poster"}),
    "audio":     frozenset({"src"}),
    "source":    frozenset({"src", "srcset"}),
    "object":    frozenset({"data"}),
    "embed":     frozenset({"src"}),
    "form":      frozenset({"action"}),
    "track":     frozenset({"src"}),
    "input":     frozenset({"formaction"}),
    "button":    frozenset({"formaction"}),
}

# URL prefixes we treat as "absolute / external". Protocol-relative
# ``//host/path`` is treated as external too — browsers resolve it to
# the current scheme and the fetch still leaves the document's origin.
_EXTERNAL_URL_PREFIXES: tuple[str, ...] = (
    "http://",
    "https://",
    "//",
    "ftp://",
)

# CSS patterns that suppress rendering. The matchers are case-insensitive
# and tolerant of whitespace around the colon. Each pattern is
# intentionally conservative: we match the idioms used in practice
# rather than trying to cover every equivalent CSS expression.
_HIDDEN_STYLE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"display\s*:\s*none\b",           re.IGNORECASE),
    re.compile(r"visibility\s*:\s*hidden\b",      re.IGNORECASE),
    re.compile(r"visibility\s*:\s*collapse\b",    re.IGNORECASE),
    re.compile(r"opacity\s*:\s*0(?:\.0+)?\b",     re.IGNORECASE),
    re.compile(r"font-size\s*:\s*0(?:px|pt|em)?\b", re.IGNORECASE),
)

# Offscreen positioning idiom: absolute positioning with a large negative
# offset. The ``-9999px`` convention is the conventional signature; we
# accept any 3+ digit negative offset on ``left`` or ``top``.
_OFFSCREEN_PATTERN: re.Pattern[str] = re.compile(
    r"position\s*:\s*absolute[^;]*;?\s*(?:left|top)\s*:\s*-\d{3,}",
    re.IGNORECASE,
)

# HTML5 standalone ``hidden`` attribute names we recognise. ``hidden``
# on its own (no value, or ``hidden=""``) is the canonical HTML5 form;
# ``aria-hidden="true"`` is the ARIA form.
_HIDDEN_ATTR_EQUIVALENTS: frozenset[str] = frozenset({"hidden"})

# Latin letter codepoint ranges — used by the homoglyph detector to
# decide whether a word mixes Latin with confusable glyphs.
_LATIN_RANGES = (
    range(0x0041, 0x005B),  # A-Z
    range(0x0061, 0x007B),  # a-z
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


def _has_hidden_style(style_value: str) -> bool:
    """True when ``style_value`` contains any render-suppressing pattern.

    The detector scans for the recognised patterns in the value string
    verbatim; it does not parse CSS properly. That is sufficient for a
    diagnostic — a browser looking at the same string will have made
    the same decision the pattern matcher is trying to echo.
    """
    if not style_value:
        return False
    for pattern in _HIDDEN_STYLE_PATTERNS:
        if pattern.search(style_value):
            return True
    if _OFFSCREEN_PATTERN.search(style_value):
        return True
    return False


def _is_external_url(url: str) -> bool:
    """True when ``url`` is absolute-remote or protocol-relative."""
    if not url:
        return False
    stripped = url.strip().lower()
    return stripped.startswith(_EXTERNAL_URL_PREFIXES)


# ---------------------------------------------------------------------------
# Internal parser — gathers findings as the walk progresses
# ---------------------------------------------------------------------------


class _HtmlWalker(HTMLParser):
    """Stream HTML through stdlib ``HTMLParser`` and collect findings.

    The walker maintains a stack of (tag, is_hidden_ancestor) pairs so
    that text inside an element whose ancestry carries a hidden-style /
    hidden-attribute flag is attributed to ``html_hidden_text``. Script
    and style bodies are tracked separately — text inside them is batin
    (source code), not zahir (rendered content), so the zahir detectors
    do not apply.

    The walker does not raise on malformed input; ``HTMLParser`` is
    lenient by design. Parse errors surface as swallowed exceptions via
    the parent ``scan`` method, which converts them to a single
    ``scan_error`` finding.

    Attributes
    ----------
    findings
        List of ``Finding`` emitted during the walk. The analyzer
        consumes this list and recomputes the integrity score.
    file_path
        Path used in finding ``location`` strings. Lines are appended
        where possible via ``self.getpos()`` — HTMLParser tracks the
        current line internally.
    """

    def __init__(self, file_path: Path) -> None:
        # ``convert_charrefs=True`` (the default since 3.5) causes the
        # parser to decode ``&amp;`` etc. into real characters before
        # calling ``handle_data`` — we rely on this so that HTML-escaped
        # codepoints are inspected as codepoints, not as entity names.
        super().__init__(convert_charrefs=True)
        self.findings: list[Finding] = []
        self.file_path: Path = file_path
        # Stack of (tag_name, is_hidden_here). ``is_hidden_here`` is
        # True when the element itself sets a hidden style/attribute;
        # effective hidden-ness at any point is the OR of the stack.
        self._stack: list[tuple[str, bool]] = []
        # Parallel flag — True when we are inside a <script>, <style>,
        # <template>, or <noscript> (anywhere in the stack).
        self._non_visible_depth: int = 0

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_hidden(self) -> bool:
        return any(is_hidden for _tag, is_hidden in self._stack)

    def _loc(self, suffix: str = "") -> str:
        """Build a finding location string with the current parser line.

        HTMLParser exposes ``self.getpos()`` returning ``(line, col)``
        of the current token. We include the line so a reader can
        jump to the relevant span. The suffix lets a specific detector
        append a sub-coordinate (tag name, attribute name, …).
        """
        line, _col = self.getpos()
        tail = f":{suffix}" if suffix else ""
        return f"{self.file_path}:line{line}{tail}"

    # ------------------------------------------------------------------
    # Tag handling
    # ------------------------------------------------------------------

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> None:
        self._inspect_attributes(tag, attrs)
        is_hidden_here = self._tag_is_hidden(tag, attrs)
        self._stack.append((tag, is_hidden_here))
        if tag in _NON_VISIBLE_CONTAINERS:
            self._non_visible_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> None:
        """Void / self-closing tag (``<br/>``, ``<img ... />``).

        We still inspect the attributes for external refs, event
        handlers, data-attrs, and hidden styling — these mechanisms
        live in the tag's attribute set, independent of whether the
        element carries children.
        """
        self._inspect_attributes(tag, attrs)
        # No stack push — the element is immediately closed. A void
        # element cannot contain hidden text, so the hidden-ness of the
        # tag itself has no downstream effect.

    def handle_endtag(self, tag: str) -> None:
        # Robust to malformed HTML: search the stack from the top for
        # a matching tag and pop up to (and including) it. If no match,
        # silently ignore — the browser would.
        for i in range(len(self._stack) - 1, -1, -1):
            stacked_tag, _ = self._stack[i]
            if stacked_tag == tag:
                # Count how many non-visible containers we are popping.
                for popped_tag, _ in self._stack[i:]:
                    if popped_tag in _NON_VISIBLE_CONTAINERS:
                        self._non_visible_depth -= 1
                self._stack = self._stack[:i]
                return
        # No match — ignore, consistent with browser leniency.

    # ------------------------------------------------------------------
    # Attribute-level detectors (called for every start tag)
    # ------------------------------------------------------------------

    def _inspect_attributes(
        self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered_tag = tag.lower()
        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            value = raw_value or ""

            # ---- html_inline_script via on* handler ----
            if name.startswith("on") and value.strip():
                self.findings.append(Finding(
                    mechanism="html_inline_script",
                    tier=TIER["html_inline_script"],
                    confidence=1.0,
                    description=(
                        f"<{lowered_tag}> carries an inline event "
                        f"handler {name!r}. Event-handler attributes "
                        "execute JavaScript in the renderer's context "
                        "the moment the event fires — unlike an "
                        "external ``<script src>``, there is no URL "
                        "the reader can inspect in isolation."
                    ),
                    location=self._loc(f"{lowered_tag}:{name}"),
                    surface=f"<{lowered_tag}> (no visible script indicator)",
                    concealed=f"{name}={value[:80]!r}",
                    source_layer="batin",
                ))

            # ---- html_external_reference ----
            if (
                lowered_tag in _EXTERNAL_REF_ATTRS
                and name in _EXTERNAL_REF_ATTRS[lowered_tag]
                and _is_external_url(value)
            ):
                self.findings.append(Finding(
                    mechanism="html_external_reference",
                    tier=TIER["html_external_reference"],
                    confidence=0.9,
                    description=(
                        f"<{lowered_tag} {name}=…> points at an "
                        f"absolute remote URL {value[:120]!r}. The "
                        "renderer reaches outside the document when "
                        "the page opens; common vectors include "
                        "remote scripts, tracking pixels, and "
                        "embedded iframes."
                    ),
                    location=self._loc(f"{lowered_tag}:{name}"),
                    surface=f"<{lowered_tag}> (no inline indicator)",
                    concealed=f"external target {value[:120]!r}",
                    source_layer="batin",
                ))

            # ---- html_data_attribute ----
            if name.startswith("data-") and len(value) >= _DATA_ATTR_MIN_LENGTH:
                self.findings.append(Finding(
                    mechanism="html_data_attribute",
                    tier=TIER["html_data_attribute"],
                    confidence=0.8,
                    description=(
                        f"<{lowered_tag} {name}=…> carries a "
                        f"{len(value)}-character payload in a "
                        "data-* attribute — well above the routine "
                        "length for id / flag values. data-* attrs "
                        "are invisible to a casual DOM read and are a "
                        "documented payload-smuggling carrier."
                    ),
                    location=self._loc(f"{lowered_tag}:{name}"),
                    surface=f"<{lowered_tag}> (no rendered indicator)",
                    concealed=f"data payload {value[:80]!r}…",
                    source_layer="batin",
                ))

    # ------------------------------------------------------------------
    # Hidden-ness detection
    # ------------------------------------------------------------------

    def _tag_is_hidden(
        self, tag: str, attrs: list[tuple[str, str | None]],
    ) -> bool:
        """True when *this element* (not its ancestors) is render-suppressed.

        Ancestor hidden-ness is handled at the ``handle_data`` site via
        ``_current_hidden``. Separating the two layers means a nested
        tree of hidden elements is only attributed once, at the
        innermost text content.
        """
        for raw_name, raw_value in attrs:
            name = (raw_name or "").lower()
            value = raw_value or ""
            if name == "style" and _has_hidden_style(value):
                return True
            if name in _HIDDEN_ATTR_EQUIVALENTS:
                # HTML5 ``hidden`` is a boolean attribute — presence is
                # enough, independent of value.
                return True
            if name == "aria-hidden" and value.strip().lower() == "true":
                return True
        return False

    # ------------------------------------------------------------------
    # Text / data handling
    # ------------------------------------------------------------------

    def handle_data(self, data: str) -> None:
        # Text inside <script>, <style>, <template>, <noscript> is not
        # rendered text — skip the zahir detectors entirely. The
        # inline-script check has already fired at the <script>
        # start-tag if a src= was present; we don't need to re-witness
        # the script body here. (An empty <script></script> with no
        # src= is not executable and not worth flagging.)
        if self._non_visible_depth > 0:
            # However: a <script> element with inline body content IS
            # executable code, and that's the most dangerous mechanism
            # the analyzer targets. Flag it here, once per script body.
            if (
                self._stack
                and self._stack[-1][0] == "script"
                and data.strip()
            ):
                self._emit_inline_script_body(data)
            return

        if not data:
            return

        # Attribute the data to the current effective hidden state.
        hidden = self._current_hidden()
        if hidden and data.strip():
            self._emit_hidden_text(data)
            # Hidden text is still the visible text stream from a
            # machine-reader's standpoint (indexers, LLMs ingest it).
            # Scan it for the shared unicode concealment mechanisms too
            # — a hidden run carrying a TAG-block payload is doubly
            # concealed.
            self._scan_visible(data)
            return

        # Normal visible text — run the shared zahir detectors.
        self._scan_visible(data)

    def handle_comment(self, data: str) -> None:
        """Comments are not visible to the reader, but they are present
        in the document stream. We do not emit a dedicated mechanism
        (comments are overwhelmingly routine), but we do check the
        comment text for concealment codepoints — a zero-width or TAG
        payload parked in a comment is adversarial regardless of its
        rendering context.
        """
        if not data:
            return
        # Reuse the same per-run scanners that visible text runs go
        # through. Findings will carry a :comment suffix so the reader
        # can distinguish a comment-sourced finding from a data-sourced
        # one at a glance.
        self._scan_visible(data, location_suffix="comment")

    # ------------------------------------------------------------------
    # Emission helpers
    # ------------------------------------------------------------------

    def _emit_hidden_text(self, data: str) -> None:
        stripped = data.strip()
        preview = stripped[:120]
        self.findings.append(Finding(
            mechanism="html_hidden_text",
            tier=TIER["html_hidden_text"],
            confidence=1.0,
            description=(
                f"Text content within a render-suppressed element "
                f"(display:none / visibility:hidden / opacity:0 / "
                f"offscreen / hidden attribute / aria-hidden). "
                "The text is in the DOM and readable by indexers, "
                "copy-paste pipelines, and LLMs, but the page does "
                f"not render it. Preview: {preview!r}."
            ),
            location=self._loc(),
            surface="(rendered view omits this text)",
            concealed=f"hidden text {preview!r}",
            source_layer="zahir",
        ))

    def _emit_inline_script_body(self, data: str) -> None:
        """Fire ``html_inline_script`` once for a non-empty <script> body."""
        preview = data.strip()[:80]
        self.findings.append(Finding(
            mechanism="html_inline_script",
            tier=TIER["html_inline_script"],
            confidence=1.0,
            description=(
                f"<script> element carries inline JavaScript body "
                f"({len(data)} chars). Inline script executes in the "
                "renderer's context the moment the parser closes the "
                "element — unlike a ``<script src=…>``, the payload "
                "has no URL the reader can inspect in isolation."
            ),
            location=self._loc("script"),
            surface="<script> (no external URL to inspect)",
            concealed=f"inline JS body {preview!r}…",
            source_layer="batin",
        ))

    # ------------------------------------------------------------------
    # Per-run zahir detectors — shared with Zahir/Docx/Json analyzers
    # ------------------------------------------------------------------

    def _scan_visible(
        self, value: str, *, location_suffix: str = "",
    ) -> None:
        """Zero-width / TAG / bidi / homoglyph on a visible text run.

        Structured in parallel with ``DocxAnalyzer._scan_string`` and
        ``JsonAnalyzer._scan_string_value`` — same mechanism set, same
        per-run granularity, same emission shape.
        """
        loc = self._loc(location_suffix) if location_suffix else self._loc()

        # Zero-width.
        zw = [c for c in value if c in ZERO_WIDTH_CHARS]
        if zw:
            codepoints = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in zw})
            )
            self.findings.append(Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.9,
                description=(
                    f"{len(zw)} zero-width character(s) in this "
                    f"text run ({codepoints}) — invisible to a human "
                    "reader, preserved by parsers and tokenizers."
                ),
                location=loc,
                surface="(no visible indication)",
                concealed=f"{len(zw)} zero-width codepoint(s)",
                source_layer="zahir",
            ))

        # TAG block.
        tags = [c for c in value if ord(c) in TAG_CHAR_RANGE]
        if tags:
            shadow = "".join(
                chr(ord(c) - 0xE0000) if 0x20 <= ord(c) - 0xE0000 <= 0x7E
                else "?"
                for c in tags
            )
            self.findings.append(Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=1.0,
                description=(
                    f"{len(tags)} Unicode TAG character(s) in this "
                    "text run. TAG codepoints are invisible to human "
                    "readers and decodable by LLMs — a documented "
                    "prompt-injection smuggling vector. Decoded "
                    f"shadow: {shadow!r}."
                ),
                location=loc,
                surface="(no visible indication)",
                concealed=f"TAG payload ({len(tags)} codepoints)",
                source_layer="zahir",
            ))

        # Bidi control.
        bidi = [c for c in value if c in BIDI_CONTROL_CHARS]
        if bidi:
            codepoints = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in bidi})
            )
            self.findings.append(Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(bidi)} bidi-control character(s) in this "
                    f"text run ({codepoints}) — reorders display "
                    "without changing the codepoint stream."
                ),
                location=loc,
                surface="(reordered display)",
                concealed=f"{len(bidi)} bidi-override codepoint(s)",
                source_layer="zahir",
            ))

        # Homoglyph.
        for word in value.split():
            if len(word) < 2:
                continue
            confusables = [c for c in word if c in CONFUSABLE_TO_LATIN]
            latin_letters = [c for c in word if _is_latin_letter(c)]
            if not confusables:
                continue
            if not (latin_letters or len(confusables) >= 2):
                continue
            recovered = "".join(
                CONFUSABLE_TO_LATIN.get(c, c) for c in word
            )
            cp_info = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in confusables})
            )
            self.findings.append(Finding(
                mechanism="homoglyph",
                tier=TIER["homoglyph"],
                confidence=0.85,
                description=(
                    f"Word mixes Latin letters with {len(confusables)} "
                    f"confusable codepoint(s) ({cp_info}) — visually "
                    f"impersonates {recovered!r}."
                ),
                location=loc,
                surface=word,
                concealed=f"appears identical to {recovered!r}",
                source_layer="zahir",
            ))


# ---------------------------------------------------------------------------
# HtmlAnalyzer
# ---------------------------------------------------------------------------


class HtmlAnalyzer(BaseAnalyzer):
    """Dual-witness analyzer for HTML documents.

    Opens the file, enforces ``_MAX_HTML_BYTES``, hands the bytes to
    ``_HtmlWalker`` (a stdlib ``HTMLParser`` subclass), and collects
    the walker's findings into one ``IntegrityReport``.

    On unreadable / undecodable input, emits a single ``scan_error``
    finding via the base helper and marks the scan incomplete. This is
    consistent with the middle-community contract (2:143): a single
    witness' failure does not silence the others, and the failure
    itself is a signal.
    """

    name: ClassVar[str] = "html"
    error_prefix: ClassVar[str] = "HTML scan error"
    # Class default — ``scan_error`` findings are structural in nature
    # (the inner state was not inspected). Per-finding source_layer is
    # set individually for every zahir / batin detector above.
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.HTML})

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the HTML file at ``file_path``."""
        try:
            raw = file_path.read_bytes()
        except OSError as exc:
            return self._scan_error_report(
                file_path, f"could not read file: {exc}",
            )

        if len(raw) > _MAX_HTML_BYTES:
            raw = raw[:_MAX_HTML_BYTES]

        # Decode permissively — adversarial HTML may contain stray
        # byte sequences that are not valid UTF-8. ``errors="replace"``
        # keeps the walk going; the replacement character does not
        # match any of the zahir mechanisms, so it cannot cause a
        # false positive.
        try:
            text = raw.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001 — defensive
            return self._scan_error_report(
                file_path, f"could not decode as text: {exc}",
            )

        walker = _HtmlWalker(file_path)
        try:
            walker.feed(text)
            walker.close()
        except Exception as exc:  # noqa: BLE001 — HTMLParser is lenient
            # HTMLParser deliberately does not raise on malformed HTML,
            # but a pathological input could still surface an
            # exception (e.g. UnicodeDecodeError on a replacement-char
            # interaction). Fold any such failure into a scan_error.
            partial = self._partial_report(file_path, walker.findings)
            partial.findings.append(Finding(
                mechanism="scan_error",
                tier=TIER["scan_error"],
                confidence=1.0,
                description=(
                    f"HTML parser failed partway through: {exc}"
                ),
                location=str(file_path),
                surface="(walk aborted)",
                concealed=(
                    "absence of later findings cannot be taken as cleanness"
                ),
                source_layer="batin",
            ))
            partial.integrity_score = compute_muwazana_score(partial.findings)
            partial.scan_incomplete = True
            return partial

        # v1.1.2 - run the format-gauntlet detectors after the walker.
        # Each detector reads its own bytes from the same path; this
        # mirrors the DOCX / XLSX wiring pattern. Detector failures are
        # absorbed silently here (the surface they target is the same
        # bytes the walker just successfully decoded, so a failure is
        # extremely unlikely; if one occurs, the walker's findings
        # remain authoritative).
        v112_findings: list[Finding] = []
        for detector in (
            detect_html_noscript_payload,
            detect_html_template_payload,
            detect_html_comment_payload,
            detect_html_meta_payload,
            detect_html_style_content_payload,
            detect_html_title_text_divergence,
        ):
            try:
                v112_findings.extend(detector(file_path))
            except Exception:  # noqa: BLE001 - defensive, keep walker's findings
                continue

        all_findings = walker.findings + v112_findings
        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(all_findings),
            findings=all_findings,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _partial_report(
        self, file_path: Path, findings: Iterable[Finding],
    ) -> IntegrityReport:
        fs = list(findings)
        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(fs),
            findings=fs,
        )


__all__ = ["HtmlAnalyzer"]
