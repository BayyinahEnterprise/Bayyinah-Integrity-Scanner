"""
Tier 1 detector for hidden-text payloads injected via CSS ``content:``
property strings (v1.1.2 HTML format gauntlet).

CSS pseudo-elements (``::before``, ``::after``) accept a ``content``
property whose string value is rendered as generated content adjacent
to the matched element. Two adversarial uses combine on this surface:

  (a) The ``content`` string text lives inside a ``<style>`` block
      (a non-visible container the existing HtmlAnalyzer skips for
      zahir detection) - never seen by a casual reader of the source.
  (b) A neighbouring ``color: white`` (or ``color: #fff`` /
      ``color: transparent`` / ``opacity: 0``) declaration suppresses
      the rendered glyphs from view; the text exists in the DOM
      (accessible via ``getComputedStyle().content``), reaches every
      LLM that flattens HTML to text, and ships through copy-paste
      pipelines that ignore CSS.

The rendered grid shows nothing. The DOM carries the payload.

Triggers (any one is sufficient):

  (a) length: any ``content: "..."`` string exceeding
      ``_LENGTH_THRESHOLD`` chars;
  (b) suppressing-style: any ``content`` string of at least
      ``_MIN_PAYLOAD_LENGTH`` chars whose enclosing rule also carries
      a render-suppressing color / opacity declaration.

Closes html_gauntlet fixture 05_css_content.html.

Tier discipline: Tier 1. Triggers are byte-deterministic regex matches
on the ``<style>`` body; no semantic claim about user intent.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_HTML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 64
_MIN_PAYLOAD_LENGTH: int = 16

# Match every <style>...</style> block body.
_STYLE_BLOCK_PATTERN: re.Pattern[str] = re.compile(
    r"<style\b[^>]*>(.*?)</style\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Match every CSS rule {selector + body}. We only care about the body
# string between the curly braces. Non-greedy on the body so nested
# constructs (we don't care about them; CSS rules don't legally nest
# at this level outside of @-rules) end at the first '}'.
_RULE_PATTERN: re.Pattern[str] = re.compile(
    r"([^{}]+)\{([^{}]*)\}",
    re.DOTALL,
)

# Match a content: declaration with a single- or double-quoted string.
_CONTENT_DECL_PATTERN: re.Pattern[str] = re.compile(
    r"content\s*:\s*(?: \"([^\"]*)\" | '([^']*)' )",
    re.IGNORECASE | re.VERBOSE,
)

# Render-suppressing companions inside the same rule body. Any one of
# these alongside a content: string is the "doubly hidden" shape.
_SUPPRESS_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"color\s*:\s*white\b", re.IGNORECASE),
    re.compile(r"color\s*:\s*#fff(?:fff)?\b", re.IGNORECASE),
    re.compile(
        r"color\s*:\s*rgb\s*\(\s*255\s*,\s*255\s*,\s*255\s*\)",
        re.IGNORECASE,
    ),
    re.compile(r"color\s*:\s*transparent\b", re.IGNORECASE),
    re.compile(r"opacity\s*:\s*0(?:\.0+)?\b", re.IGNORECASE),
    re.compile(r"visibility\s*:\s*hidden\b", re.IGNORECASE),
    re.compile(r"display\s*:\s*none\b", re.IGNORECASE),
    re.compile(r"font-size\s*:\s*0(?:px|pt|em)?\b", re.IGNORECASE),
)


def _has_suppressing_style(rule_body: str) -> bool:
    for pattern in _SUPPRESS_PATTERNS:
        if pattern.search(rule_body):
            return True
    return False


def detect_html_style_content_payload(file_path: Path) -> Iterable[Finding]:
    """Surface CSS ``content:`` strings that smuggle text payloads."""
    try:
        raw = file_path.read_bytes()
    except OSError:
        return

    if len(raw) > _MAX_HTML_BYTES:
        raw = raw[:_MAX_HTML_BYTES]

    try:
        text = raw.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 - defensive
        return

    for style_match in _STYLE_BLOCK_PATTERN.finditer(text):
        style_body = style_match.group(1)
        style_offset = style_match.start(1)

        for rule_match in _RULE_PATTERN.finditer(style_body):
            selector = rule_match.group(1).strip()
            rule_body = rule_match.group(2)

            for content_match in _CONTENT_DECL_PATTERN.finditer(rule_body):
                content = (
                    content_match.group(1)
                    if content_match.group(1) is not None
                    else (content_match.group(2) or "")
                )
                if len(content) < _MIN_PAYLOAD_LENGTH:
                    continue

                # Compute line number of the content: declaration.
                abs_offset = (
                    style_offset
                    + rule_match.start(2)
                    + content_match.start()
                )
                line_no = text[:abs_offset].count("\n") + 1
                preview = content[:_PREVIEW_LIMIT]

                length_hit = len(content) > _LENGTH_THRESHOLD
                suppress_hit = _has_suppressing_style(rule_body)

                if not (length_hit or suppress_hit):
                    continue

                if length_hit and suppress_hit:
                    reason = (
                        f"is {len(content)} characters AND lives in a "
                        f"rule body that also carries a render-"
                        f"suppressing declaration"
                    )
                elif length_hit:
                    reason = (
                        f"is {len(content)} characters - well above "
                        f"routine pseudo-element content length"
                    )
                else:
                    reason = (
                        f"lives in a rule body that also carries a "
                        f"render-suppressing declaration "
                        f"(white / transparent / opacity:0 / "
                        f"display:none / visibility:hidden)"
                    )

                yield Finding(
                    mechanism="html_style_content_payload",
                    tier=1,
                    confidence=1.0,
                    description=(
                        f"<style> block contains a CSS content: "
                        f"declaration on {selector!r} that {reason}. "
                        f"Pseudo-element content reaches the DOM via "
                        f"getComputedStyle and is read by indexers and "
                        f"LLM ingestion paths regardless of color or "
                        f"visibility. Recovered text: {preview!r}."
                    ),
                    location=(
                        f"{file_path}:line{line_no}:style:"
                        f"{selector[:40]}"
                    ),
                    surface="(rendered view suppresses or omits this text)",
                    concealed=(
                        f"CSS content payload on {selector!r}: {preview!r}"
                    ),
                    source_layer="batin",
                )


__all__ = ["detect_html_style_content_payload"]
