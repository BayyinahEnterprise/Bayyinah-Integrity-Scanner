"""
csv_bidi_payload -- v1.1.2 F2 mechanism 4 (zahir).

Al-Baqarah 2:42 applied to bidi-override codepoint smuggling. Unicode
defines a small set of bidirectional control codepoints:

  * U+202A through U+202E -- LRE / RLE / PDF / LRO / RLO. Embedding
    and override marks. RLO ("right-to-left override") forces the
    visual rendering of the following text to be reversed; LRO does
    the same in the other direction.
  * U+2066 through U+2069 -- LRI / RLI / FSI / PDI. Isolate marks
    introduced in Unicode 6.3 with stricter scoping.

In a CSV cell these codepoints are byte-deterministic anomalies. A
spreadsheet renderer (Excel, LibreOffice Calc, Google Sheets) honours
the bidi algorithm: a cell whose bytes read "=Total: 1000" with an
RLO injected can render on screen as "0001 :latoT=" while the parser,
the diff tool, and the forensics reader all see the original bytes.
The surface (visible glyph order) and the bytes (parser input)
diverge in the most literal way.

Detector contract (per docs/adversarial/csv_json_gauntlet/REPORT.md
section 3.4):

  * For each cell, scan for any codepoint in U+202A..U+202E or
    U+2066..U+2069.
  * Emit one finding per cell that carries one or more bidi
    codepoints.

Tier 1 zahir (the spreadsheet-rendered surface diverges from the
byte stream). Severity 0.25.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import BIDI_CONTROL_CHARS, TIER


def _bidi_codepoints_in(value: str) -> list[str]:
    """Return ordered list of bidi codepoints (as 'U+XXXX' strings)."""
    return [
        f"U+{ord(ch):04X}"
        for ch in value
        if ch in BIDI_CONTROL_CHARS
    ]


def detect_bidi_payload(
    text: str,
    delimiter: str,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield csv_bidi_payload findings.

    ``text`` is the already-decoded CSV body. ``delimiter`` is the
    inferred delimiter from the base analyzer.
    """
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return
    header = rows[0]
    for row_offset, row in enumerate(rows):
        for col_index, cell in enumerate(row):
            codepoints = _bidi_codepoints_in(cell)
            if not codepoints:
                continue
            header_name = (
                header[col_index] if col_index < len(header) else ""
            )
            yield Finding(
                mechanism="csv_bidi_payload",
                tier=TIER["csv_bidi_payload"],
                confidence=0.95,
                description=(
                    f"Cell at row {row_offset}, column {col_index} "
                    f"({header_name!r}) carries "
                    f"{len(codepoints)} Unicode bidi control "
                    f"codepoint(s): {codepoints}. The bidi "
                    "algorithm reorders the visual rendering of the "
                    "surrounding text in spreadsheet renderers "
                    "(Excel, LibreOffice Calc, Google Sheets); the "
                    "on-screen glyph order can differ from the byte "
                    "order. There is no legitimate use of bidi "
                    "override codepoints inside a CSV data cell."
                ),
                location=f"{file_path}:row={row_offset},col={col_index}",
                surface=(
                    f"(cell carries bidi codepoints: "
                    f"{codepoints})"
                ),
                concealed=cell[:240],
                source_layer="zahir",
            )
