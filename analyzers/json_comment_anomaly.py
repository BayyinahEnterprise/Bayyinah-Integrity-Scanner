"""
json_comment_anomaly -- v1.1.2 F2 mechanism 10.

RFC 8259 (strict JSON) does not permit comments. JSON5, jsonc, and
many lenient parsers (VS Code's settings parser, json5, hjson) accept
``//`` line comments and ``/* ... */`` block comments silently. A
document presented to a strict-JSON consumer parses cleanly because
the strict parser fails closed, but the comment text is invisible to
any toolchain that walks the parsed tree. A document presented to a
lenient consumer simply ignores the comment, and the comment text is
again invisible to the parsed-tree walk.

The concealment surface is the comment payload itself: the byte
stream carries human-readable text (instructions, payload-bearing
tokens, second-channel content) that no post-parse walk surfaces.

Detector contract (per bayyinah_v1_1_2_f2_plan_v2.md Section 3.9):

  * Decode the file bytes as UTF-8 with errors='replace'.
  * Walk a single-pass state machine: outside-string, inside-string.
    A ``"`` toggles inside-string only when the preceding backslash
    count is even (an escaped quote inside a string does not close
    the string).
  * Outside any string, look for ``//`` (line comment, runs to end
    of line) and ``/* ... */`` (block comment, runs to closing
    ``*/``). Each match yields one finding.
  * Concealed field carries the comment text truncated to 240 chars.

Tier 2 batin (parser-invisible structural concealment, mid weight).
The trigger is unambiguous (strict-JSON disallows comments outright),
but the false-positive surface is real: tooling-emitted ``.jsonc``
files, .vscode/settings.json, package.json with editor metadata.
Tier 2 calibration mirrors csv_comment_row: structurally clear, but
contextually legitimate in some legitimate-toolchain workflows.

Severity 0.15. Same calibration as csv_comment_row and the structural
batin family for that tier.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19700420.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum length of comment text recovered into the concealed field.
# Mirrors json_duplicate_key_divergence's 240-char preview ceiling.
_PREVIEW_LIMIT = 240


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


def _scan_comments(text: str) -> Iterable[tuple[int, str, str]]:
    """Walk ``text`` once, yielding (start_index, kind, comment_text)
    for every comment found outside string literals.

    ``kind`` is ``'line'`` for ``//`` comments (text is the comment
    body up to but not including the terminating newline) or
    ``'block'`` for ``/* ... */`` comments (text is the comment body
    between the opening ``/*`` and the closing ``*/``).

    The state machine has two states: inside-string and outside.
    A ``"`` toggles state only when the immediately preceding
    consecutive-backslash run is even. An unterminated block comment
    runs to end of file (we still yield it; the truncation is a
    signal in itself).
    """
    n = len(text)
    i = 0
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            if ch == '\\':
                # Skip the next character; an escaped quote does not
                # close the string. Bounds-safe: i+2 may exceed n
                # which simply ends the loop.
                i += 2
                continue
            if ch == '"':
                in_string = False
                i += 1
                continue
            i += 1
            continue
        # Outside any string.
        if ch == '"':
            in_string = True
            i += 1
            continue
        if ch == '/' and i + 1 < n:
            nxt = text[i + 1]
            if nxt == '/':
                # Line comment: scan to next \n or end of text.
                start = i
                end = text.find('\n', i + 2)
                if end == -1:
                    end = n
                body = text[i + 2:end]
                yield (start, 'line', body)
                i = end
                continue
            if nxt == '*':
                # Block comment: scan to next */ or end of text.
                start = i
                close = text.find('*/', i + 2)
                if close == -1:
                    body = text[i + 2:]
                    yield (start, 'block', body)
                    i = n
                    continue
                body = text[i + 2:close]
                yield (start, 'block', body)
                i = close + 2
                continue
        i += 1


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_comment_anomaly(
    text: str,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield json_comment_anomaly findings for the given JSON text.

    ``text`` is the file bytes already decoded as UTF-8 with
    ``errors='replace'``. ``file_path`` is the source path used in
    finding ``location`` strings. The function never raises.
    """
    for start, kind, body in _scan_comments(text):
        # Approximate line / column for the reader.
        prefix = text[:start]
        line = prefix.count('\n') + 1
        last_nl = prefix.rfind('\n')
        col = start - (last_nl if last_nl != -1 else -1)
        preview = body[:_PREVIEW_LIMIT]
        kind_label = 'line' if kind == 'line' else 'block'
        truncation_note = (
            ' (truncated)' if len(body) > _PREVIEW_LIMIT else ''
        )
        yield Finding(
            mechanism='json_comment_anomaly',
            tier=TIER['json_comment_anomaly'],
            confidence=1.0,
            description=(
                f'JSON {kind_label} comment found at line {line} '
                f'column {col}. RFC 8259 (strict JSON) does not '
                f'permit comments; lenient parsers (JSON5, jsonc) '
                f'silently ignore them. The comment text is '
                f'invisible to any post-parse tree walk: the byte '
                f'stream carries the payload, the parsed object '
                f'never sees it.'
            ),
            location=f'{file_path}:line={line},column={col}',
            surface=f'{kind_label} comment (invisible to JSON tree walk)',
            concealed=(
                f'{kind_label} comment text: {preview!r}'
                f'{truncation_note}'
            ),
            source_layer='batin',
        )


__all__ = ['detect_comment_anomaly']
