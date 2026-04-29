"""
Tier 1 detector for hidden-text payloads in the ``<title>`` element
that diverge from the rendered body (v1.1.2 HTML format gauntlet).

The ``<title>`` element is the document's titled identifier - it
appears in the browser tab, in the bookmarks list, in search-engine
results, in social-media unfurlers, and in every metadata-aware
extractor. It does NOT appear in the rendered body of the page.

That asymmetric placement is the smuggling shape this detector targets:
a title that diverges substantially from the body - in particular, a
title whose contents do not appear anywhere in the body text and whose
length exceeds a routine title length - is a high-signal payload-
carrying surface.

Triggers (any one is sufficient):

  (a) length: a ``<title>`` value exceeding ``_LENGTH_THRESHOLD``
      characters;
  (b) divergence: a ``<title>`` value of at least
      ``_DIVERGENCE_MIN_LENGTH`` chars whose text does not appear
      anywhere in the rendered body. The floor is set at 40 chars so
      routine page-name titles ("About Us", "Q3 Summary") are exempt
      and only payload-shaped titles trigger.

Closes html_gauntlet fixture 06_title_payload.html.

Tier discipline: Tier 1. Triggers are byte-deterministic - a length
threshold and a substring comparison between two windows of the same
file. No semantic claim about user intent.

Why ``zahir`` and not ``batin``: a title is rendered text - it appears
in the browser chrome and is the public-facing identifier of the
document. The divergence between a rendered surface (the title) and
another rendered surface (the body) is a zahir-on-zahir mismatch,
parallel to the ``surface_text_divergence`` family.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_HTML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 80
# Routine titles are typically short identifiers (page name, brand,
# section). The divergence trigger needs a length floor that excludes
# those: 40 chars is well above standard SEO title length advice and
# catches the payload-shaped "smuggled directive" case while leaving
# normal page titles alone.
_DIVERGENCE_MIN_LENGTH: int = 40

# Match <title>...</title>. Non-greedy body capture; case-insensitive.
_TITLE_PATTERN: re.Pattern[str] = re.compile(
    r"<title\b[^>]*>(.*?)</title\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Patterns we strip before computing the rendered-body text used for
# divergence comparison.
_NON_RENDER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<head\b[^>]*>.*?</head\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<script\b[^>]*>.*?</script\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<style\b[^>]*>.*?</style\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<noscript\b[^>]*>.*?</noscript\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<template\b[^>]*>.*?</template\s*>", re.IGNORECASE | re.DOTALL),
    re.compile(r"<!--.*?-->", re.DOTALL),
)
_TAG_STRIP_PATTERN: re.Pattern[str] = re.compile(r"<[^>]+>")


def _rendered_body_text(text: str) -> str:
    stripped = text
    for pattern in _NON_RENDER_PATTERNS:
        stripped = pattern.sub(" ", stripped)
    stripped = _TAG_STRIP_PATTERN.sub(" ", stripped)
    return stripped


def detect_html_title_text_divergence(file_path: Path) -> Iterable[Finding]:
    """Surface ``<title>`` values that diverge from the rendered body."""
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

    title_match = _TITLE_PATTERN.search(text)
    if not title_match:
        return

    title = title_match.group(1).strip()
    if not title:
        return

    line_no = text[: title_match.start()].count("\n") + 1
    preview = title[:_PREVIEW_LIMIT]
    body_text = _rendered_body_text(text)

    length_hit = len(title) > _LENGTH_THRESHOLD
    divergence_hit = (
        len(title) >= _DIVERGENCE_MIN_LENGTH
        and title not in body_text
    )

    if not (length_hit or divergence_hit):
        return

    if length_hit and divergence_hit:
        reason = (
            f"is {len(title)} characters AND does not appear "
            f"anywhere in the rendered body"
        )
    elif length_hit:
        reason = (
            f"is {len(title)} characters - well above the routine "
            f"title length of 60-70"
        )
    else:
        reason = (
            f"is {len(title)} characters and does not appear "
            f"anywhere in the rendered body of the document"
        )

    yield Finding(
        mechanism="html_title_text_divergence",
        tier=1,
        confidence=1.0,
        description=(
            f"<title> {reason}. Browser tab, bookmarks, search results, "
            f"and social-media unfurlers display this string while the "
            f"rendered body shows different content. Recovered text: "
            f"{preview!r}."
        ),
        location=f"{file_path}:line{line_no}:title",
        surface=f"browser tab title: {preview!r}",
        concealed=f"title diverges from rendered body: {preview!r}",
        source_layer="zahir",
    )


__all__ = ["detect_html_title_text_divergence"]
