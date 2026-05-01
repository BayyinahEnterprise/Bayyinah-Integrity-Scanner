"""
json_key_invisible_chars -- v1.1.8 F2 calibration item 3.

Al-Baqarah 2:42 applied to JSON object keys. The key is the contract:
``{"amount_usd": 1000}`` declares the value-of-record under the
identifier ``amount_usd``. A key carrying zero-width or
bidi-override codepoints renders identically (or near-identically)
to a clean key in any pretty-printer or text editor while the byte
stream carries a different identifier. A downstream consumer keying
on ``amount_usd`` reads the clean key; a different consumer keying
on the bytes-exact form reads the polluted variant.

The hazard surfaces in any cross-system handoff: a configuration
file shared between a UI (which renders the key) and a backend
(which keys on bytes) sees two different documents.

Detector contract:

  * Walk the parsed tree's keys (recursively).
  * If a key contains any of:
      * U+200B / U+200C / U+200D (zero-width space / non-joiner /
        joiner)
      * U+FEFF (zero-width no-break space, BOM)
      * U+2060 (word joiner)
      * U+202A..U+202E (bidi embedding / override)
      * U+2066..U+2069 (bidi isolate)
    emit one finding per occurrence.
  * The codepoint set mirrors v1.1.2 csv_zero_width_payload and
    csv_bidi_payload but applied to JSON keys (which are not in
    scope for those detectors -- the F2 string-walker walks values
    only).

Tier 1 batin (parser-invisible structural concealment, high weight).
The trigger is unambiguous and the consequence is severe: the key
the human reader sees is not the key the parser stored.

Severity 0.25. Same calibration as csv_bidi_payload (also Tier 1
zahir-shaped invisible-codepoint detector). Severity is one notch
above csv_zero_width_payload because the key-position concealment
is harder to spot than a value-position one (most JSON viewers
highlight values but not keys).

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Codepoints that render zero-width or rearrange surrounding text in
# any JSON pretty-printer / text editor. Matches the v1.1.2 zahir
# csv_bidi_payload + csv_zero_width_payload sets, applied here to
# JSON keys (which the F2 string-walker does not visit).
_ZERO_WIDTH_CODEPOINTS: frozenset[str] = frozenset({
    '\u200b',  # zero-width space
    '\u200c',  # zero-width non-joiner
    '\u200d',  # zero-width joiner
    '\ufeff',  # zero-width no-break space (BOM)
    '\u2060',  # word joiner
})

_BIDI_CODEPOINTS: frozenset[str] = frozenset({
    '\u202a',  # left-to-right embedding
    '\u202b',  # right-to-left embedding
    '\u202c',  # pop directional formatting
    '\u202d',  # left-to-right override
    '\u202e',  # right-to-left override
    '\u2066',  # left-to-right isolate
    '\u2067',  # right-to-left isolate
    '\u2068',  # first-strong isolate
    '\u2069',  # pop directional isolate
})

_INVISIBLE_CODEPOINTS: frozenset[str] = (
    _ZERO_WIDTH_CODEPOINTS | _BIDI_CODEPOINTS
)


# ---------------------------------------------------------------------------
# Tree walker
# ---------------------------------------------------------------------------


def _walk_keys(
    tree: Any, path: str = '$',
) -> Iterable[tuple[str, str]]:
    """Yield (json_path, key) for every dict key in the tree.

    Mirrors json_prototype_pollution_key._walk_keys minus the sibling
    and value bookkeeping (this detector only needs the key string).
    """
    if isinstance(tree, dict):
        for key, value in tree.items():
            key_str = str(key)
            subpath = f'{path}.{key_str}'
            yield (subpath, key_str)
            yield from _walk_keys(value, subpath)
    elif isinstance(tree, list):
        for idx, value in enumerate(tree):
            subpath = f'{path}[{idx}]'
            yield from _walk_keys(value, subpath)


def _classify_offending_codepoints(key: str) -> dict[str, list[str]]:
    """Return a mapping of category -> list of offending codepoint hex strings.

    The split between zero-width and bidi categories is reported in
    the finding description so the reader can act on the specific
    concealment vector without re-decoding the key.
    """
    found: dict[str, list[str]] = {'zero_width': [], 'bidi': []}
    for ch in key:
        if ch in _ZERO_WIDTH_CODEPOINTS:
            found['zero_width'].append(f'U+{ord(ch):04X}')
        elif ch in _BIDI_CODEPOINTS:
            found['bidi'].append(f'U+{ord(ch):04X}')
    return found


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_key_invisible_chars(
    tree: Any,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield json_key_invisible_chars findings for the given tree.

    ``tree`` is the parsed JSON object from ``json.loads``.
    ``file_path`` is the source path used in finding ``location``
    strings. The function never raises.
    """
    for json_path, key in _walk_keys(tree):
        offending = _classify_offending_codepoints(key)
        zw = offending['zero_width']
        bidi = offending['bidi']
        if not (zw or bidi):
            continue
        # Render a sanitised key for the surface field: replace
        # invisible codepoints with their hex notation so the reader
        # sees what bytes are actually present.
        sanitised = ''.join(
            f'<{f"U+{ord(ch):04X}"}>' if ch in _INVISIBLE_CODEPOINTS else ch
            for ch in key
        )
        categories = []
        if zw:
            categories.append(f'{len(zw)} zero-width ({", ".join(zw)})')
        if bidi:
            categories.append(f'{len(bidi)} bidi ({", ".join(bidi)})')
        category_text = '; '.join(categories)
        yield Finding(
            mechanism='json_key_invisible_chars',
            tier=TIER['json_key_invisible_chars'],
            confidence=0.95,
            description=(
                f'JSON object key at {json_path} contains '
                f'{category_text}. A pretty-printer or text editor '
                f'renders the key indistinguishably (zero-width) or '
                f'with reordered glyphs (bidi) from a clean variant; '
                f'the byte stream carries the polluted form. A '
                f'consumer keying on the rendered name and a '
                f'consumer keying on the byte-exact name see two '
                f'different documents.'
            ),
            location=f'{file_path}:{json_path}',
            surface=(
                f'rendered key {sanitised!r} '
                f'(invisible codepoints made visible)'
            ),
            concealed=(
                f'key bytes (verbatim, length {len(key)}): {key!r}'
            ),
            source_layer='batin',
        )


__all__ = ['detect_key_invisible_chars']
