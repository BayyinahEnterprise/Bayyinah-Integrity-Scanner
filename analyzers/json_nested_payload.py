"""
json_nested_payload -- v1.1.2 F2 mechanism 12.

A JSON tree whose nesting depth crosses the parser-exhaustion
threshold AND which carries a long string leaf is the canonical
shape of a deep-nesting payload smuggle: the deep nesting evades
naive shallow walkers (recursive merge tools, sanitizers, schema
validators that stop at depth N), while the leaf string carries the
payload that the deeply-buried locus conceals.

The existing v1.1 ``excessive_nesting`` mechanism fires on any tree
beyond depth 32. That alone is structurally honest but generates
false positives on deeply nested but data-shaped configs (Kubernetes
manifests, deeply nested AST dumps). The combined shape -- deep AND
payload-bearing -- is a higher-precision concealment signal.

Detector contract (per bayyinah_v1_1_2_f2_plan_v2.md Section 3.11):

  * Walk the parsed tree, tracking the current path and depth.
  * If a string leaf at depth >= 32 has length > 256 chars, emit a
    finding. Both thresholds must hold for the same leaf (the
    concealment signal is the conjunction, not either alone).
  * Evidence key carries the JSONPath to the offending leaf so the
    reader can locate it without re-parsing.
  * Concealed field carries a 240-char preview of the payload.

Tier 2 batin (parser-invisible structural concealment, mid weight).
The trigger is a conjunction (depth AND length) which is rare in
legitimate data; the false-positive surface is small but non-zero
(a deeply nested log structure with a long error message could land
here legitimately). Tier 2 reflects that residual ambiguity.

Severity 0.15. Same calibration as csv_column_type_drift and the
mid-weight batin family.

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

# Depth threshold. Matches the existing v1.1 _EXCESSIVE_NESTING
# threshold so the conjunction fires on exactly the same depth band
# the structural detector flags.
_DEPTH_THRESHOLD = 32

# Leaf-string length threshold. 256 chars is a common payload-floor
# in adversarial JSON corpora and matches the boundary used by other
# v1.1.2 length-based detectors.
_LENGTH_THRESHOLD = 256

# Concealed-field truncation ceiling.
_PREVIEW_LIMIT = 240


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------


def _walk_with_depth(
    tree: Any, path: str = '$', depth: int = 0,
) -> Iterable[tuple[str, int, str]]:
    """Yield (json_path, depth, string_value) for every string leaf.

    ``depth`` is the count of container levels above the leaf. The
    root primitive is depth 0; a string inside ``{"a": "x"}`` is at
    depth 1; a string inside ``{"a": {"b": "x"}}`` is at depth 2.
    """
    if isinstance(tree, str):
        yield path, depth, tree
    elif isinstance(tree, dict):
        for key, value in tree.items():
            subpath = f'{path}.{key}'
            yield from _walk_with_depth(value, subpath, depth + 1)
    elif isinstance(tree, list):
        for idx, value in enumerate(tree):
            subpath = f'{path}[{idx}]'
            yield from _walk_with_depth(value, subpath, depth + 1)


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_nested_payload(
    tree: Any,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield json_nested_payload findings for the given parsed tree.

    Fires once per leaf string that satisfies BOTH the depth
    threshold AND the length threshold. The conjunction is the
    signal; either alone is structural noise.
    """
    for json_path, depth, value in _walk_with_depth(tree):
        if depth < _DEPTH_THRESHOLD:
            continue
        if len(value) <= _LENGTH_THRESHOLD:
            continue
        preview = value[:_PREVIEW_LIMIT]
        truncation_note = (
            ' (truncated)' if len(value) > _PREVIEW_LIMIT else ''
        )
        yield Finding(
            mechanism='json_nested_payload',
            tier=TIER['json_nested_payload'],
            confidence=0.90,
            description=(
                f'JSON tree carries a long string leaf '
                f'({len(value)} chars) at nesting depth {depth} '
                f'(threshold {_DEPTH_THRESHOLD}). The conjunction '
                f'of deep nesting and a payload-bearing leaf is the '
                f'canonical deep-nesting smuggle shape: shallow '
                f'walkers (recursive merge, sanitizers, schema '
                f'validators that bail at depth N) skip over the '
                f'payload entirely.'
            ),
            location=f'{file_path}:{json_path}',
            surface=(
                f'string leaf at depth {depth} '
                f'(length {len(value)} chars)'
            ),
            concealed=(
                f'leaf-string preview: {preview!r}'
                f'{truncation_note}'
            ),
            source_layer='batin',
        )


__all__ = ['detect_nested_payload']
