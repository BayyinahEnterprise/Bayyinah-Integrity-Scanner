"""
Tier 1 detector for hidden-text payloads inside ``<noscript>`` elements
(v1.1.2 HTML format gauntlet).

The ``<noscript>`` element is rendered only when the user agent has
JavaScript disabled. In every modern browser session - and in every LLM
ingestion path that flattens HTML to text - the ``<noscript>`` body
either renders silently as text or is dropped entirely. Indexers,
crawlers, and copy-paste pipelines see the body verbatim regardless of
the JavaScript state.

The existing ``HtmlAnalyzer`` already classifies ``<noscript>`` as a
"non-visible container" and skips its body during the zahir walk. That
is correct for the unicode-concealment detectors (zero-width / TAG /
bidi / homoglyph) but leaves a payload-recovery gap: the body text
itself - the actual concealed message - is never witnessed.

This detector closes that gap. It surfaces every non-empty
``<noscript>`` body as a Tier 1 batin finding with the recovered text
embedded in ``concealed``.

Closes html_gauntlet fixture 01_noscript.html.

Tier discipline: Tier 1 because the trigger is purely structural -
"there is text inside a <noscript> tag" - and every trigger is
verifiable from the file bytes alone with no semantic claim about
intent.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


# Maximum HTML size we inspect in one pass. Mirrors HtmlAnalyzer's cap.
_MAX_HTML_BYTES: int = 16 * 1024 * 1024

# Preview length for the recovered payload inside ``concealed``.
_PREVIEW_LIMIT: int = 240

# Match <noscript>...</noscript>. The body is captured non-greedily so
# nested elements end at the first </noscript>. Case-insensitive and
# DOTALL so newlines inside the body are captured.
_NOSCRIPT_PATTERN: re.Pattern[str] = re.compile(
    r"<noscript\b[^>]*>(.*?)</noscript\s*>",
    re.IGNORECASE | re.DOTALL,
)

# Strip inline tags from the body before reporting - we want the human-
# readable text, not nested HTML markup.
_TAG_STRIP_PATTERN: re.Pattern[str] = re.compile(r"<[^>]+>")


def detect_html_noscript_payload(file_path: Path) -> Iterable[Finding]:
    """Surface every non-empty ``<noscript>`` body as a Tier 1 finding.

    Reads the file as bytes, decodes permissively (errors=replace),
    runs a single regex pass for ``<noscript>...</noscript>`` blocks,
    and emits one Finding per non-empty body.
    """
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

    for match in _NOSCRIPT_PATTERN.finditer(text):
        body = match.group(1)
        # Strip nested tags, then collapse whitespace.
        cleaned = _TAG_STRIP_PATTERN.sub(" ", body).strip()
        if not cleaned:
            continue

        # Find line number for location.
        line_no = text[: match.start()].count("\n") + 1
        preview = cleaned[:_PREVIEW_LIMIT]

        yield Finding(
            mechanism="html_noscript_payload",
            tier=1,
            confidence=1.0,
            description=(
                f"<noscript> element carries {len(cleaned)} characters "
                f"of body text. The browser renders this only when "
                f"JavaScript is disabled, but indexers, crawlers, and "
                f"LLM ingestion pipelines read the body verbatim "
                f"regardless of script state. Recovered text: "
                f"{preview!r}."
            ),
            location=f"{file_path}:line{line_no}:noscript",
            surface="(rendered view omits this text)",
            concealed=f"noscript body: {preview!r}",
            source_layer="batin",
        )


__all__ = ["detect_html_noscript_payload"]
