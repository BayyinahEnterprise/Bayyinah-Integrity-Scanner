"""
csv_quoted_newline_payload -- v1.1.2 F2 mechanism 3.

Al-Baqarah 2:42 applied to RFC 4180 quoted multi-line cells. A quoted
CSV field is allowed to carry embedded newlines: the spec permits a
single quoted address or memo cell to span multiple physical lines so
long as the field is enclosed in double quotes. Legitimate uses exist
(postal addresses, street-level descriptions, brief notes). The
adversarial shape is the same byte feature, scaled: a quoted cell
that carries multiple paragraphs of payload text inside what the
header schema declares as a single tabular value. The grid still
renders as one row; the cell's content carries the entire payload.

Detector contract (per docs/adversarial/csv_json_gauntlet/REPORT.md
section 3.3):

  * For each cell, count the number of newline characters that appear
    inside the cell's quoted region (before CSV unquoting).
  * Compute the unquoted cell value length.
  * Standard band: embedded_newline_count >= 2 AND cell_length > 128
    fires (severity 0.20).
  * v1.1.8 F2 calibration item 7 second band: embedded_newline_count
    >= 3 AND cell_length > 256 fires regardless of column count
    (severity 0.20). The second band is logically OR-combined with
    the first; cells matching both bands report against the standard
    band only.

Both conditions together guard against false positives on multi-line
address or notes fields, which typically carry one or two newlines
and remain under the 128-char budget.

Tier 1 batin (parser-visible, byte-deterministic). The cell content
is plain text; it renders normally in a spreadsheet. The divergence
lives in the cell-as-grid-value contract a tabular file establishes
versus the multi-paragraph payload the cell delivers.

Severity 0.20.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum embedded newline count inside a quoted region for the cell
# to count as a multi-line payload candidate.
_MIN_EMBEDDED_NEWLINES = 2

# Length threshold above which a multi-line cell counts as
# payload-shaped. 128 chars accommodates legitimate two-line postal
# addresses (which typically run 60-100 chars) without firing.
_CELL_LENGTH_THRESHOLD = 128

# v1.1.8 F2 calibration item 7 second band: a cell with 3+ embedded
# newlines and length > 256 fires regardless of column-count
# divergence. Multi-paragraph payload smuggled with a clear paragraph
# count would not survive a legitimate notes-field rationale.
_BAND2_MIN_EMBEDDED_NEWLINES = 3
_BAND2_CELL_LENGTH_THRESHOLD = 256


# ---------------------------------------------------------------------------
# Tokenizer: tracks quoted-region newlines per cell
# ---------------------------------------------------------------------------


def _tokenize_with_newline_counts(
    text: str,
    delimiter: str,
) -> list[list[tuple[str, int]]]:
    """Walk the raw CSV text and yield (unquoted_value, embedded_nl) per cell.

    Returns a list of rows; each row is a list of (value, count) pairs.
    The newline count is the number of literal newlines that appear
    INSIDE the cell's quoted region (the bytes between the opening
    and closing quote). Non-quoted cells are reported with count 0.

    This function implements a small RFC-4180-aware state machine
    rather than wrapping ``csv.reader``: csv.reader unquotes cells
    and discards the information about whether a newline came from
    inside a quoted region (the adversarial signal) or from the row
    terminator (legitimate). The state machine preserves both.
    """
    rows: list[list[tuple[str, int]]] = []
    cells: list[tuple[str, int]] = []
    buf: list[str] = []
    nl_count = 0
    in_quotes = False
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_quotes:
            if ch == '"':
                # Lookahead for escaped quote.
                if i + 1 < n and text[i + 1] == '"':
                    buf.append('"')
                    i += 2
                    continue
                # Closing quote.
                in_quotes = False
                i += 1
                continue
            if ch == "\n":
                nl_count += 1
                buf.append(ch)
                i += 1
                continue
            buf.append(ch)
            i += 1
            continue
        # Outside quoted region.
        if ch == '"' and not buf:
            # Opening quote at start of cell.
            in_quotes = True
            i += 1
            continue
        if ch == delimiter:
            cells.append(("".join(buf), nl_count))
            buf = []
            nl_count = 0
            i += 1
            continue
        if ch == "\n":
            cells.append(("".join(buf), nl_count))
            rows.append(cells)
            cells = []
            buf = []
            nl_count = 0
            i += 1
            continue
        if ch == "\r":
            # Treat CR as part of CRLF: skip; next iteration handles LF.
            i += 1
            continue
        buf.append(ch)
        i += 1
    # Flush trailing cell / row.
    if buf or cells:
        cells.append(("".join(buf), nl_count))
        rows.append(cells)
    return rows


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_quoted_newline_payload(
    text: str,
    delimiter: str,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield csv_quoted_newline_payload findings.

    ``text`` is the already-decoded CSV body (NULs replaced, BOM
    stripped). ``delimiter`` is the inferred delimiter from the
    base analyzer.
    """
    rows = _tokenize_with_newline_counts(text, delimiter)
    if not rows:
        return
    header = rows[0] if rows else []
    for row_offset, row in enumerate(rows):
        # Row 0 is the header; row index reported is 1-indexed
        # against data rows for consistency with other CSV
        # detectors. The header itself can also carry the shape;
        # we report it as row 0 in that case.
        row_index = row_offset
        for col_index, (value, nl_count) in enumerate(row):
            cell_len = len(value)
            band1 = (
                nl_count >= _MIN_EMBEDDED_NEWLINES
                and cell_len > _CELL_LENGTH_THRESHOLD
            )
            band2 = (
                nl_count >= _BAND2_MIN_EMBEDDED_NEWLINES
                and cell_len > _BAND2_CELL_LENGTH_THRESHOLD
            )
            if not (band1 or band2):
                continue
            band_label = "standard" if band1 else "high-density"
            header_name = (
                header[col_index][0] if col_index < len(header) else ""
            )
            yield Finding(
                mechanism="csv_quoted_newline_payload",
                tier=TIER["csv_quoted_newline_payload"],
                confidence=0.85,
                description=(
                    f"Cell at row {row_index}, column {col_index} "
                    f"({header_name!r}) is an RFC 4180 quoted field "
                    f"carrying {nl_count} embedded newline(s) and "
                    f"{cell_len} characters of content ({band_label} "
                    f"band). RFC 4180 permits embedded newlines inside "
                    "quoted fields, and legitimate multi-line address "
                    "or notes cells typically carry one newline. Two "
                    "or more embedded newlines paired with a cell "
                    "length above 128 characters (standard band), or "
                    "three or more newlines paired with a length above "
                    "256 characters (high-density band), indicates "
                    "multi-paragraph payload smuggled into a single "
                    "tabular cell."
                ),
                location=f"{file_path}:row={row_index},col={col_index}",
                surface=(
                    f"(quoted cell with {nl_count} embedded newlines, "
                    f"length {cell_len}, {band_label} band)"
                ),
                concealed=value[:240],
                source_layer="batin",
            )
