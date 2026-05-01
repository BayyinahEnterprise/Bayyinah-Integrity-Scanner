"""
json_prototype_pollution_key -- v1.1.2 F2 mechanism 11.

A JSON object key matching ``__proto__``, ``constructor``, or
``prototype`` is the canonical prototype-pollution shape in any
JavaScript consumer that performs a recursive merge or
``Object.assign`` walk. The key is invisible to any post-parse Python
walk that treats the dict as opaque data, but a downstream JS
toolchain may treat it as a prototype-chain mutation primitive.

The concealment vector is the key itself: the byte stream and the
parsed object both carry it, but the human reader who treats JSON as
data (not as a JS prototype-mutation surface) does not see the
hazard. Canonical prototype-pollution CVEs across Lodash, jQuery,
minimist, and dozens of merge libraries exploit exactly this shape.

Detector contract (per bayyinah_v1_1_2_f2_plan_v2.md Section 3.10):

  * Walk the parsed tree's keys (recursively).
  * If a key matches one of ``__proto__``, ``constructor``, or
    ``prototype`` (case-sensitive), emit one finding per occurrence.
  * Evidence key carries the JSONPath-dotted path to the offending
    key so the reader can locate it without re-parsing.
  * Concealed field carries the polluting key's VALUE (recursively
    flattened, truncated to 500 chars) followed by the local
    object's other keys so the reader sees both the payload and the
    merge-target shape. v1.1.8 F2 calibration item 4: the value
    extraction surfaces nested HIDDEN_TEXT_PAYLOAD strings that
    fixture 05 buries under ``__proto__.polluted``.

Tier 1 batin (parser-invisible structural concealment, high weight).
The trigger is unambiguous (one of three canonical names) and the
JS consequence is severe (prototype-chain mutation). False-positive
surface is small: legitimate JSON rarely uses these as data keys
because mainstream JS environments forbid or coerce them.

Severity 0.20. Same calibration as csv_zero_width_payload and
csv_quoted_newline_payload: high-precision evidence of intent paired
with severe downstream consequence.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19700420.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# The three canonical prototype-pollution key names. Case-sensitive
# match because JS property lookup is case-sensitive and the
# vulnerable merge libraries match exactly these strings.
_POLLUTION_KEYS: frozenset[str] = frozenset({
    '__proto__',
    'constructor',
    'prototype',
})

# Concealed-field truncation ceiling. Mirrors the 240-char preview
# convention shared with json_duplicate_key_divergence and
# json_comment_anomaly.
_PREVIEW_LIMIT = 240


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------


def _walk_keys(
    tree: Any, path: str = '$',
) -> Iterable[tuple[str, str, list[str], Any]]:
    """Yield (json_path, key, sibling_keys, key_value) for every dict key found.

    ``json_path`` uses the same dotted notation as ``_walk_strings``
    in json_analyzer: ``$`` for root, ``.key`` for member access,
    ``[idx]`` for array index. ``sibling_keys`` is the full list of
    keys present in the same local object (including the matched
    key) so the concealed field can show the merge-target shape.
    ``key_value`` is the raw value the key maps to (any JSON type)
    so v1.1.8 F2 item 4 can extract the polluting payload.
    """
    if isinstance(tree, dict):
        sibling_keys = [str(k) for k in tree.keys()]
        for key, value in tree.items():
            key_str = str(key)
            subpath = f'{path}.{key_str}'
            yield (subpath, key_str, sibling_keys, value)
            yield from _walk_keys(value, subpath)
    elif isinstance(tree, list):
        for idx, value in enumerate(tree):
            subpath = f'{path}[{idx}]'
            yield from _walk_keys(value, subpath)


def _flatten_value(value: Any, limit: int = 500) -> str:
    """Render a JSON value to a compact string for concealed-field display.

    Recursively flattens objects/arrays via ``repr`` then truncates to
    ``limit`` characters. Strings render verbatim (quoted) so a
    HIDDEN_TEXT_PAYLOAD inside a nested string is recoverable. The
    truncation note is appended to the caller's wrapper, not here.
    """
    try:
        rendered = repr(value)
    except Exception:
        rendered = '<unrenderable>'
    if len(rendered) > limit:
        return rendered[:limit]
    return rendered


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_prototype_pollution_keys(
    tree: Any,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield json_prototype_pollution_key findings for the given tree.

    ``tree`` is the parsed JSON object from ``json.loads``.
    ``file_path`` is the source path used in finding ``location``
    strings. The function never raises.
    """
    for json_path, key, siblings, key_value in _walk_keys(tree):
        if key not in _POLLUTION_KEYS:
            continue
        # Show the local merge-target shape: the other keys present
        # in the same object alongside the polluting one.
        other_keys = [k for k in siblings if k != key]
        siblings_repr = repr(other_keys)[:_PREVIEW_LIMIT]
        truncation_note = (
            ' (truncated)'
            if len(repr(other_keys)) > _PREVIEW_LIMIT
            else ''
        )
        # v1.1.8 F2 item 4: include the polluting key's value so the
        # smuggled payload (e.g. fixture 05's nested HIDDEN_TEXT_PAYLOAD
        # under ``__proto__.polluted``) is recoverable directly from
        # this finding's concealed field.
        value_repr = _flatten_value(key_value, limit=500)
        value_truncation_note = (
            ' (truncated)'
            if len(repr(key_value)) > 500
            else ''
        )
        yield Finding(
            mechanism='json_prototype_pollution_key',
            tier=TIER['json_prototype_pollution_key'],
            confidence=0.95,
            description=(
                f'JSON object contains key {key!r} at {json_path}, '
                f'a canonical JavaScript prototype-pollution name. '
                f'Recursive-merge consumers (Lodash _.merge, jQuery '
                f'$.extend, minimist, dozens of others) treat such a '
                f'key as a prototype-chain mutation primitive rather '
                f'than data. The polluting value attached to this '
                f'key carries: {value_repr}{value_truncation_note}. '
                f'A human reader who sees this as JSON data does not '
                f'see the hazard.'
            ),
            location=f'{file_path}:{json_path}',
            surface=f'object key {key!r} (treated as data by the human reader)',
            concealed=(
                f'polluting value: {value_repr}{value_truncation_note}; '
                f'sibling keys in the same object: {siblings_repr}'
                f'{truncation_note}'
            ),
            source_layer='batin',
        )


__all__ = ['detect_prototype_pollution_keys']
