"""
csv_column_type_drift -- v1.1.2 F2 mechanism 1.

Al-Baqarah 2:42 applied to per-column type discipline. A spreadsheet
column's header is a contract: ``amount_usd`` declares the column
carries currency values, ``invoice_date`` declares ISO dates, ``sku``
declares short identifier tokens. The first few data rows establish
the de-facto type signature. A row that breaks the signature with a
multi-hundred-character free-text payload is the canonical
column-hijack shape: the header lies about what the column carries,
the surface still renders as a tabular grid, and the parser carries
the payload through unchanged.

Detector contract (per docs/adversarial/csv_json_gauntlet/REPORT.md):

  * Sample the first 5 data rows after the header.
  * Classify each cell into ``numeric`` / ``date`` / ``short_token`` /
    ``free_text``.
  * Majority-vote the column type from the sampled rows.
  * For each row beyond the sample, flag a cell whose column type is
    ``numeric`` or ``short_token`` and whose value is ``free_text``
    longer than 200 chars (severity 0.15) OR longer than 50 chars
    (severity 0.10 via severity_override). The 50-char band catches
    short-form column hijacks that the original 200-char threshold
    misses (e.g. fixture 01 carries a 60-char hijack).
  * Skip the flag if the column header contains ``note``, ``comment``,
    ``description``, or ``remarks`` (case-insensitive). Those headers
    are semantically free-text and would otherwise produce false
    positives on legitimate prose-bearing columns.
  * Run type analysis on min(header_count, row_count) columns even
    when the row's overall column count diverges from the header --
    the v1.1.7 short-circuit suppressed type-drift findings on rows
    that also tripped column-count anomalies (fixture 09).

Tier 2 batin (parser-visible structural divergence). The cell content
is plain text; it renders normally in a spreadsheet. The divergence
lives in the column-type contract the header established versus the
content the row delivers.

Severity 0.15 (default) or 0.10 (50-char band, via severity_override).
Same calibration family as csv_inconsistent_columns -- both are
structural-divergence shapes a human reader would catch on close
inspection but a downstream pipeline does not flag.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import TIER


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Number of data rows sampled (post-header) for column-type inference.
_SAMPLE_ROWS = 5

# Length threshold for a free_text cell to count as a payload-shaped
# divergence in a numeric / short_token column. 200 chars catches
# financial-column hijacks (typically 50-2000 chars of prose) without
# firing on legitimate short notes that may slip past the header
# allow-list below. v1.1.8 F2 calibration adds a second band at
# 50 chars (severity 0.10) for short-form hijacks.
_FREETEXT_DRIFT_THRESHOLD = 200
_FREETEXT_DRIFT_THRESHOLD_SHORT = 50
_FREETEXT_DRIFT_SEVERITY_SHORT = 0.10

# Maximum length of a free_text cell that still counts as short_token.
# Anything longer is free_text by length alone, even if it has no
# whitespace.
_SHORT_TOKEN_MAX_LEN = 30

# Headers (case-insensitive substring match) that are semantically
# free-text and must skip the drift flag. A column whose header
# contains any of these is allowed to carry long prose rows by design.
_FREETEXT_HEADER_TOKENS: frozenset[str] = frozenset({
    "note", "comment", "description", "remarks",
})

# ISO date and US slash date patterns. Conservative -- only these two
# shapes count as ``date`` in the inference. Anything else falls back
# to numeric / short_token / free_text.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_US_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{4}$")


# ---------------------------------------------------------------------------
# Type classification
# ---------------------------------------------------------------------------


def _classify_cell(value: str) -> str:
    """Classify a single cell value into one of four type buckets."""
    stripped = value.strip()
    if not stripped:
        # Empty cells are ignored in majority voting; report as
        # short_token so they do not drag the vote toward free_text.
        return "short_token"
    # Numeric: int, float, or signed/comma-separated numeric.
    # Strip a leading sign and one set of thousands-separating commas.
    candidate = stripped.lstrip("+-").replace(",", "")
    try:
        float(candidate)
        return "numeric"
    except ValueError:
        pass
    # Date.
    if _ISO_DATE_RE.match(stripped) or _US_DATE_RE.match(stripped):
        return "date"
    # Short token: no whitespace and length within bound.
    if " " not in stripped and len(stripped) <= _SHORT_TOKEN_MAX_LEN:
        return "short_token"
    return "free_text"


def _majority_type(samples: list[str]) -> str:
    """Return the majority-vote type for a column from sampled cells."""
    if not samples:
        return "free_text"
    counts: dict[str, int] = {}
    for cell in samples:
        kind = _classify_cell(cell)
        counts[kind] = counts.get(kind, 0) + 1
    # Tie-break by preferring stricter types (numeric > date >
    # short_token > free_text) -- a tied numeric/free_text column
    # should be treated as numeric so the drift flag can fire.
    rank = {"numeric": 0, "date": 1, "short_token": 2, "free_text": 3}
    best = max(counts.items(), key=lambda kv: (kv[1], -rank[kv[0]]))
    return best[0]


def _header_is_freetext(header: str) -> bool:
    """True if the header name signals a semantically free-text column."""
    lower = header.lower()
    return any(tok in lower for tok in _FREETEXT_HEADER_TOKENS)


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_column_type_drift(
    text: str,
    delimiter: str,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield csv_column_type_drift findings for the given CSV text.

    ``text`` is the already-decoded CSV body (NULs replaced, BOM
    stripped) -- the exact substrate ``CsvAnalyzer._walk_rows``
    consumes. ``delimiter`` is the inferred delimiter. ``file_path``
    is the source path used in finding ``location`` strings.
    """
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        # No data rows -- nothing to check.
        return
    header = rows[0]
    data_rows = rows[1:]
    if not data_rows:
        return

    # Inference window: first 5 data rows. Fewer is acceptable -- we
    # accept any majority on a smaller sample.
    sample_rows = data_rows[:_SAMPLE_ROWS]
    column_count = len(header)

    # Per-column samples. Cells past the header column count are
    # ignored here -- those are surplus-column territory, handled
    # separately by csv_surplus_column_payload.
    column_samples: list[list[str]] = [[] for _ in range(column_count)]
    for row in sample_rows:
        for col_index in range(min(len(row), column_count)):
            column_samples[col_index].append(row[col_index])

    column_types: list[str] = [
        _majority_type(samples) for samples in column_samples
    ]

    # Walk all data rows (including the sample) and emit a finding
    # for each free_text cell longer than the threshold in a
    # numeric- or short_token-typed column.
    for row_offset, row in enumerate(data_rows):
        # Row index reported to the user is 1-indexed on the data
        # rows (header is row 0 in spreadsheet terms; first data
        # row is row 1).
        row_index = row_offset + 1
        # v1.1.8 F2 item 8: walk min(header_count, row_count) cells
        # even when the row's column count diverges from the header.
        # The earlier short-circuit suppressed type-drift findings on
        # rows that also tripped column-count anomalies (fixture 09).
        scan_cols = min(len(row), column_count)
        for col_index in range(scan_cols):
            inferred = column_types[col_index]
            if inferred not in ("numeric", "short_token"):
                continue
            header_name = header[col_index] if col_index < len(header) else ""
            if _header_is_freetext(header_name):
                continue
            cell_value = row[col_index]
            cell_type = _classify_cell(cell_value)
            if cell_type != "free_text":
                continue
            cell_len = len(cell_value)
            if cell_len > _FREETEXT_DRIFT_THRESHOLD:
                severity_override = None
                band_label = "long"
            elif cell_len > _FREETEXT_DRIFT_THRESHOLD_SHORT:
                severity_override = _FREETEXT_DRIFT_SEVERITY_SHORT
                band_label = "short"
            else:
                continue
            yield Finding(
                mechanism="csv_column_type_drift",
                tier=TIER["csv_column_type_drift"],
                confidence=0.85,
                description=(
                    f"Column {header_name!r} (column {col_index}) was "
                    f"inferred as {inferred} from the first "
                    f"{len(column_samples[col_index])} data row(s); "
                    f"row {row_index} carries a free-text cell of "
                    f"{cell_len} characters in that column "
                    f"({band_label} band). The column header declares "
                    "a strict type signature; the row value violates "
                    "it by length and shape. A spreadsheet renderer "
                    "carries the value through unchanged, but "
                    "downstream type-aware consumers see a contract "
                    "violation."
                ),
                location=f"{file_path}:row={row_index},col={col_index}",
                surface=(
                    f"(column {header_name!r} typed as {inferred}; "
                    f"row {row_index} cell length {cell_len}, "
                    f"{band_label} band)"
                ),
                concealed=cell_value[:240],
                source_layer="batin",
                severity_override=severity_override,
            )
