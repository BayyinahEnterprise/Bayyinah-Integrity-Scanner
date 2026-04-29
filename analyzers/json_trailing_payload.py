"""
json_trailing_payload -- v1.1.2 F2 mechanism 13.

A JSON document whose byte stream contains content after the root
value's closing token is the canonical trailing-payload concealment
shape. Strict-JSON parsers (RFC 8259, Python's ``json.loads``)
reject the input outright with an ``Extra data`` error. Lenient
wrappers (``json.JSONDecoder.raw_decode``, jq, Node's
``JSON.parse`` after a slice, the streaming-JSON family of parsers)
accept the prefix and silently discard the suffix. The suffix
carries the payload that any tool reading the parsed value alone
never sees.

The concealment is symmetric to json_comment_anomaly: the payload
lives outside the parsed-tree surface entirely. Comments inhabit
the source-text channel; trailing bytes inhabit the post-root-EOF
channel. Both are strictly forbidden by RFC 8259 yet routinely
accepted by lenient consumers.

Detector contract (per bayyinah_v1_1_2_f2_plan_v2.md Section 3.12):

  * Decode the file bytes as UTF-8 with errors='replace'.
  * Use ``json.JSONDecoder.raw_decode`` to parse the first JSON
    value in the stream. raw_decode returns (value, end_index).
  * If the file contains non-whitespace content after end_index,
    emit one finding. Whitespace-only trailing content (e.g. a
    final newline appended by an editor) is benign and silent.
  * Concealed field carries a 240-char preview of the trailing
    bytes so the reader recovers the smuggled content.

Tier 1 batin (parser-invisible structural concealment, high weight).
The trigger is unambiguous: any non-whitespace after the root close
brace/bracket is a strict-JSON violation that a lenient consumer
would silently discard. False-positive surface is essentially zero
on legitimate single-value JSON; the design space for trailing
content is JSONL/NDJSON streams, which travel under a different
file extension and a different consumer contract.

Severity 0.20. Same calibration as json_unicode_escape_payload and
the high-weight Tier 1 batin family.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19700420.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PREVIEW_LIMIT = 240


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_trailing_payload(
    text: str,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield json_trailing_payload findings for the given JSON text.

    ``text`` is the file bytes already decoded as UTF-8 with
    ``errors='replace'``. The detector parses the first JSON value
    via ``raw_decode`` and inspects the suffix. The function never
    raises; a stream that fails raw_decode (truly malformed JSON)
    yields nothing.
    """
    decoder = json.JSONDecoder()
    # Skip leading whitespace before raw_decode; raw_decode itself
    # does not skip leading whitespace.
    start = 0
    while start < len(text) and text[start].isspace():
        start += 1
    if start >= len(text):
        return
    try:
        _value, end = decoder.raw_decode(text, start)
    except json.JSONDecodeError:
        # Truly malformed JSON; the parse-error path in
        # json_analyzer.py already surfaces this as a scan_error.
        # The trailing-payload detector is silent on unparseable
        # input by design.
        return
    suffix = text[end:]
    if not suffix.strip():
        # Whitespace-only suffix (final newline, trailing CRLF) is
        # benign. The middle-community contract is satisfied: we
        # report only on non-whitespace structural irregularity.
        return
    # Locate the first non-whitespace byte of the suffix for the
    # finding's line/column.
    offset = 0
    while offset < len(suffix) and suffix[offset].isspace():
        offset += 1
    abs_pos = end + offset
    prefix = text[:abs_pos]
    line = prefix.count('\n') + 1
    last_nl = prefix.rfind('\n')
    col = abs_pos - (last_nl if last_nl != -1 else -1)
    preview = suffix.lstrip()[:_PREVIEW_LIMIT]
    truncation_note = (
        ' (truncated)'
        if len(suffix.lstrip()) > _PREVIEW_LIMIT
        else ''
    )
    yield Finding(
        mechanism='json_trailing_payload',
        tier=TIER['json_trailing_payload'],
        confidence=0.95,
        description=(
            f'JSON document carries non-whitespace content after '
            f'the root value, starting at line {line} column {col} '
            f'(byte offset {abs_pos}). Strict-JSON parsers reject '
            f'this outright; lenient consumers (raw_decode, jq, '
            f'streaming JSON, naive ``JSON.parse`` after a slice) '
            f'silently discard the suffix. The trailing bytes are '
            f'invisible to any tool that walks the parsed value '
            f'alone.'
        ),
        location=f'{file_path}:line={line},column={col}',
        surface='trailing content past root close (strict-JSON violation)',
        concealed=(
            f'trailing bytes preview: {preview!r}'
            f'{truncation_note}'
        ),
        source_layer='batin',
    )


__all__ = ['detect_trailing_payload']
