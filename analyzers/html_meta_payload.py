"""
Tier 1 detector for hidden-text payloads in ``<meta>`` content
attributes (v1.1.2 HTML format gauntlet).

``<meta>`` elements expose document metadata to crawlers, search
engines, social-media unfurlers (Open Graph, Twitter Card), feed
readers, and LLM ingestion pipelines that walk the head of the page.
Routine ``<meta>`` content is short: a description sentence, a comma-
separated keyword list, a charset declaration. Long content values
are structurally anomalous and a documented payload-smuggling carrier
- the page renders nothing while every metadata-aware extractor reads
the field.

Triggers (any one is sufficient):

  (a) length: a ``<meta name=... content=...>`` value exceeding
      ``_LENGTH_THRESHOLD`` UTF-8 chars;
  (b) divergence: a ``description`` or ``keywords`` content value of
      at least ``_MIN_DIVERGENCE_LENGTH`` chars whose text does not
      appear anywhere in the rendered body of the document.

charset / viewport / http-equiv / og:image-style URL fields are
exempted - they are routinely short and tightly constrained.

Closes html_gauntlet fixture 04_meta_content.html.

Tier discipline: Tier 1. Triggers are byte-deterministic; the
divergence trigger compares two byte-windows of the same file and
makes no semantic claim.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_HTML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 256
_MIN_DIVERGENCE_LENGTH: int = 16

# Meta name values whose content is a content-summary surface (subject
# to the divergence trigger). Other names (charset, viewport, robots,
# refresh, og:image, og:url, twitter:card, ...) are exempt.
_DIVERGENCE_NAMES: frozenset[str] = frozenset({
    "description",
    "keywords",
    "abstract",
    "subject",
    "summary",
    "og:description",
    "twitter:description",
})

# Match every <meta ...> tag. The attribute order is not fixed in
# HTML, so we capture the whole tag and parse attributes separately.
_META_TAG_PATTERN: re.Pattern[str] = re.compile(
    r"<meta\b([^>]*)>",
    re.IGNORECASE,
)

# Attribute matcher: name="value" or name='value' or name=value (no
# quotes). Permissive on whitespace.
_ATTR_PATTERN: re.Pattern[str] = re.compile(
    r"""([a-zA-Z][a-zA-Z0-9:_\-]*)\s*=\s*
        (?: "([^"]*)" | '([^']*)' | ([^\s>]+) )""",
    re.VERBOSE,
)

# Strip <script>, <style>, <noscript>, <template>, comments before we
# build the rendered-body text used for divergence comparison. We do
# NOT want a payload that lives inside <noscript> to mask a meta
# divergence on the same string.
_NON_RENDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<template\b[^>]*>.*?</template\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"<head\b[^>]*>.*?</head\s*>", re.IGNORECASE | re.DOTALL),
)
_TAG_STRIP_PATTERN: re.Pattern[str] = re.compile(r"<[^>]+>")


def _parse_attrs(attr_blob: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in _ATTR_PATTERN.finditer(attr_blob):
        key = match.group(1).lower()
        # The value lives in whichever capture group matched.
        value = match.group(2) or match.group(3) or match.group(4) or ""
        out[key] = value
    return out


def _rendered_body_text(text: str) -> str:
    """Approximate the rendered body text for divergence comparison."""
    stripped = text
    for pattern in _NON_RENDER_PATTERNS:
        stripped = pattern.sub(" ", stripped)
    stripped = _TAG_STRIP_PATTERN.sub(" ", stripped)
    return stripped


def detect_html_meta_payload(file_path: Path) -> Iterable[Finding]:
    """Surface ``<meta>`` content fields whose value is anomalously long
    or absent from the rendered body."""
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

    body_text = _rendered_body_text(text)

    for match in _META_TAG_PATTERN.finditer(text):
        attrs = _parse_attrs(match.group(1))
        # We care about (name, content) pairs. ``http-equiv`` values
        # are out of scope (charset, refresh, content-security-policy
        # all fit under specific RFC shapes; payload smuggling there
        # would be a different mechanism).
        name = attrs.get("name", "").strip().lower()
        prop = attrs.get("property", "").strip().lower()  # OG / Twitter
        content = attrs.get("content", "")
        if not content:
            continue

        # Pick the meaningful identifier - ``name`` for HTML5 meta,
        # ``property`` for Open Graph / Twitter.
        identifier = name or prop
        if not identifier:
            continue

        line_no = text[: match.start()].count("\n") + 1
        preview = content[:_PREVIEW_LIMIT]

        # Length trigger - applies to any meta name/property.
        if len(content) > _LENGTH_THRESHOLD:
            yield Finding(
                mechanism="html_meta_payload",
                tier=1,
                confidence=1.0,
                description=(
                    f"<meta {('name' if name else 'property')}="
                    f"{identifier!r} content=...> carries "
                    f"{len(content)} characters - well above the "
                    f"routine meta length. Meta content reaches "
                    f"every crawler, social unfurler, and LLM "
                    f"ingestion path while staying off the rendered "
                    f"page. Recovered text: {preview!r}."
                ),
                location=f"{file_path}:line{line_no}:meta:{identifier}",
                surface="(rendered view omits this text)",
                concealed=f"meta {identifier} content: {preview!r}",
                source_layer="batin",
            )
            continue

        # Divergence trigger - only for content-summary surfaces.
        if (
            identifier in _DIVERGENCE_NAMES
            and len(content) >= _MIN_DIVERGENCE_LENGTH
            and content not in body_text
        ):
            yield Finding(
                mechanism="html_meta_payload",
                tier=1,
                confidence=1.0,
                description=(
                    f"<meta {('name' if name else 'property')}="
                    f"{identifier!r} content=...> carries "
                    f"{len(content)} characters that do not appear "
                    f"anywhere in the rendered body of the document. "
                    f"Indexers and unfurlers read this verbatim; the "
                    f"rendered page does not. Recovered text: "
                    f"{preview!r}."
                ),
                location=f"{file_path}:line{line_no}:meta:{identifier}",
                surface="(rendered view omits this text)",
                concealed=f"meta {identifier} content: {preview!r}",
                source_layer="batin",
            )


__all__ = ["detect_html_meta_payload"]
