"""
Tier 1 detector for hidden-text payloads inside ``<template>`` elements
(v1.1.2 HTML format gauntlet).

The ``<template>`` element holds inert markup that the browser parses
but does not render until JavaScript instantiates it via
``document.importNode`` or shadow-DOM cloning. The body text lives in
the DOM tree (under ``HTMLTemplateElement.content``), is reachable from
every script context, is read by every HTML-flattener and indexer, and
yet never appears on the rendered page unless explicitly activated.

The existing ``HtmlAnalyzer`` classifies ``<template>`` as a
"non-visible container" and skips its body during the zahir walk -
correct for the unicode-concealment detectors but leaves the actual
body text un-witnessed. This detector surfaces it.

Closes html_gauntlet fixture 02_template.html.

Tier discipline: Tier 1. The trigger is purely structural ("there is
non-empty text inside a <template> tag") and verifiable from the file
bytes alone.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_HTML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240

# Match <template ...>...</template>. Non-greedy body capture, case-
# insensitive, DOTALL so newlines are captured.
_TEMPLATE_PATTERN: re.Pattern[str] = re.compile(
    r"<template\b[^>]*>(.*?)</template\s*>",
    re.IGNORECASE | re.DOTALL,
)

_TAG_STRIP_PATTERN: re.Pattern[str] = re.compile(r"<[^>]+>")


def detect_html_template_payload(file_path: Path) -> Iterable[Finding]:
    """Surface every non-empty ``<template>`` body as a Tier 1 finding."""
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

    for match in _TEMPLATE_PATTERN.finditer(text):
        body = match.group(1)
        cleaned = _TAG_STRIP_PATTERN.sub(" ", body).strip()
        if not cleaned:
            continue

        line_no = text[: match.start()].count("\n") + 1
        preview = cleaned[:_PREVIEW_LIMIT]

        yield Finding(
            mechanism="html_template_payload",
            tier=1,
            confidence=1.0,
            description=(
                f"<template> element carries {len(cleaned)} characters "
                f"of body text. The browser parses but does not render "
                f"<template> contents until JavaScript instantiates "
                f"them; indexers and LLM ingestion paths flatten the "
                f"body to text regardless. Recovered text: {preview!r}."
            ),
            location=f"{file_path}:line{line_no}:template",
            surface="(rendered view omits this text)",
            concealed=f"template body: {preview!r}",
            source_layer="batin",
        )


__all__ = ["detect_html_template_payload"]
