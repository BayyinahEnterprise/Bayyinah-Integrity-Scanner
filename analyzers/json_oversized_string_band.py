"""
json_oversized_string_band -- v1.1.8 F2 calibration item 5.

Al-Baqarah 2:42 applied to per-string-value length discipline. A
JSON document's string values are typically short identifiers,
human-readable labels, or formatted scalars. Multi-paragraph payloads
embedded in a single string value are the canonical "long-string
hijack" shape: the document still parses cleanly, the JSON tree
still renders as structured data, but one leaf string carries content
that dwarfs every other string in the document.

Detector contract:

  * Walk the parsed tree's string values (recursively).
  * Compute the median string length over all string leaves.
  * Fire a Tier 2 zahir finding when a string is BOTH longer than
    1000 characters AND longer than 5x the document's median string
    length.

Tier 2 zahir (single deterministic walk over the parsed tree's
string values): the string length is observable from any single
parse of the file. The divergence is structural in shape (document
carries short labels; this string carries a paragraph), not
encoding.

Severity 0.15. Same calibration family as csv_oversized_freetext_cell
and csv_column_type_drift -- structural-divergence shapes a human
reader catches on close inspection but a downstream consumer that
treats JSON as opaque data does not flag.

False-positive guard: the 5x median requirement excludes documents
where every string is long (legitimate text-corpus exports). The
1000-char absolute threshold excludes short-string documents where
the median is small but no value is actually a payload.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

from pathlib import Path
from statistics import median
from typing import Any, Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Absolute floor: a string shorter than this never triggers,
# regardless of how much shorter the document median is.
_ABSOLUTE_LENGTH_THRESHOLD = 1000

# Multiplier over the document median that the string must exceed.
_MEDIAN_RATIO_THRESHOLD = 5.0

# Minimum number of string leaves required for the median comparison
# to be meaningful. With fewer than 3 strings, the median is
# dominated by the long string itself.
_MIN_STRINGS_FOR_MEDIAN = 3


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------


def _walk_strings(
    tree: Any, path: str = '$',
) -> Iterable[tuple[str, str]]:
    """Yield (json_path, string_value) for every string leaf in the tree.

    Mirrors analyzers/json_analyzer._walk_strings -- duplicated here
    rather than imported to keep the v1.1.8 mechanism self-contained
    (the json_analyzer's walker has the same shape but is not part
    of the analyzer's public interface).
    """
    if isinstance(tree, str):
        yield path, tree
    elif isinstance(tree, dict):
        for key, value in tree.items():
            subpath = f'{path}.{key}'
            yield from _walk_strings(value, subpath)
    elif isinstance(tree, list):
        for idx, value in enumerate(tree):
            subpath = f'{path}[{idx}]'
            yield from _walk_strings(value, subpath)


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_oversized_string_band(
    tree: Any,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield json_oversized_string_band findings for the given tree.

    ``tree`` is the parsed JSON object from ``json.loads``.
    ``file_path`` is the source path used in finding ``location``
    strings.
    """
    string_leaves = list(_walk_strings(tree))
    if len(string_leaves) < _MIN_STRINGS_FOR_MEDIAN:
        return
    lengths = [len(value) for _, value in string_leaves]
    doc_median = median(lengths)
    # Guard against zero / very small medians where the ratio test
    # would always pass.
    if doc_median < 1.0:
        doc_median = 1.0

    for json_path, value in string_leaves:
        value_len = len(value)
        if value_len <= _ABSOLUTE_LENGTH_THRESHOLD:
            continue
        if value_len < (doc_median * _MEDIAN_RATIO_THRESHOLD):
            continue
        yield Finding(
            mechanism='json_oversized_string_band',
            tier=TIER['json_oversized_string_band'],
            confidence=0.85,
            description=(
                f'JSON string at {json_path} carries {value_len} '
                f'characters; the document median string length is '
                f'{doc_median:.0f} characters across '
                f'{len(string_leaves)} string leaves '
                f'({value_len / doc_median:.1f}x the median). A '
                f'JSON document carries short labels and formatted '
                f'scalars by convention. A string longer than '
                f'{_ABSOLUTE_LENGTH_THRESHOLD} characters AND more '
                f'than {_MEDIAN_RATIO_THRESHOLD:.0f}x the document '
                'median is a multi-paragraph payload smuggled into '
                'a single leaf value.'
            ),
            location=f'{file_path}:{json_path}',
            surface=(
                f'(document median string length {doc_median:.0f}; '
                f'this string {value_len} characters)'
            ),
            concealed=value[:240],
            source_layer='zahir',
        )


__all__ = ['detect_oversized_string_band']
