"""
csv_payload_in_adjacent_cell -- v1.1.8 F2 calibration item 6.

Al-Baqarah 2:42 applied to multi-cell concealment shapes. A row
carrying a Tier 1 invisible-character finding (csv_bidi_payload or
csv_zero_width_payload) on one cell is already flagged at the cell
level. The adversarial extension is the adjacent-cell shape: the
flagged cell is a decoy, and the actual payload lives in another
cell of the same row. A reader who treats the flagged cell as the
hazard and scrubs it leaves the adjacent payload untouched.

Detector contract (per docs/adversarial/csv_json_gauntlet/REPORT.md
diagnosis of fixture 07):

  * Take as input the row indices of every Tier 1 csv_bidi_payload
    or csv_zero_width_payload finding emitted earlier in the scan.
  * For each such row, scan the OTHER cells in the same row.
  * Fire a Tier 2 batin finding when an adjacent cell in the same
    row carries free-text content longer than 100 characters.

Tier 2 batin (parser-visible co-occurrence pattern, depends on
prior findings). The cell content is plain text; both the flagged
cell and the adjacent cell render normally. The divergence lives
in the row-level intent: an invisible-character cell paired with a
long free-text cell in the same row is the canonical
flag-the-decoy-let-the-payload-through shape.

Severity 0.20. Same calibration as csv_zero_width_payload and
csv_bidi_payload -- the underlying invisible-character finding is
the precondition for this Tier 2 amplifier.

CostClass.C. Depends on prior findings (csv_bidi_payload and
csv_zero_width_payload must run first); cost is dominated by the
list-comprehension scan of rows already-walked by those detectors.

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

# Length threshold above which an adjacent cell counts as
# free-text-payload-shaped. 50 chars catches the canonical
# adversarial smuggled-payload shape (e.g. the 55-char
# HIDDEN_TEXT_PAYLOAD message used in gauntlet fixture 07) while
# excluding short labels, IDs, and formatted scalars (the
# legitimate shape, typically <=30 chars).
_ADJACENT_FREETEXT_THRESHOLD = 50

# Mechanisms whose findings act as preconditions for this detector.
# Both are Tier 1 zahir invisible-character detectors.
_PRECONDITION_MECHANISMS: frozenset[str] = frozenset({
    'csv_bidi_payload',
    'csv_zero_width_payload',
})

# Pattern matching the row index inside the location string
# emitted by the precondition mechanisms. Their location format is
# ``<path>:row=<int>,col=<int>``.
_ROW_RE = re.compile(r'row=(\d+)')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_indices_with_invisible_findings(
    prior_findings: list[Finding],
) -> dict[int, list[int]]:
    """Return ``{row_index: [flagged_col_indices]}`` for precondition findings.

    Pulls the row and column indices out of the precondition
    findings' ``location`` strings so this detector does not need
    to re-walk the cells those mechanisms already walked.
    """
    out: dict[int, list[int]] = {}
    col_re = re.compile(r'col=(\d+)')
    for finding in prior_findings:
        if finding.mechanism not in _PRECONDITION_MECHANISMS:
            continue
        row_match = _ROW_RE.search(finding.location)
        col_match = col_re.search(finding.location)
        if not row_match or not col_match:
            continue
        row_index = int(row_match.group(1))
        col_index = int(col_match.group(1))
        out.setdefault(row_index, []).append(col_index)
    return out


# ---------------------------------------------------------------------------
# Detector entry point
# ---------------------------------------------------------------------------


def detect_payload_in_adjacent_cell(
    text: str,
    delimiter: str,
    file_path: Path,
    prior_findings: list[Finding],
) -> Iterable[Finding]:
    """Yield csv_payload_in_adjacent_cell findings for the given CSV text.

    ``text`` is the already-decoded CSV body (NULs replaced, BOM
    stripped). ``delimiter`` is the inferred delimiter.
    ``prior_findings`` is the list of findings emitted by the
    csv_analyzer up to this point in the scan; this detector
    consumes the csv_bidi_payload and csv_zero_width_payload
    findings to determine which rows to scan for adjacent payloads.
    """
    flagged = _row_indices_with_invisible_findings(prior_findings)
    if not flagged:
        return
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = list(reader)
    if len(rows) < 2:
        return
    header = rows[0]
    data_rows = rows[1:]

    for flagged_row_index, flagged_cols in flagged.items():
        # The bidi / zwsp detectors emit row indices that mirror
        # csv.reader's 0-indexed position over rows (header is row
        # 0, first data row is row 1). The data_rows list is
        # 0-indexed at the first data row, so the data-rows index
        # is flagged_row_index - 1.
        data_index = flagged_row_index - 1
        if data_index < 0 or data_index >= len(data_rows):
            continue
        row = data_rows[data_index]
        flagged_cols_set = set(flagged_cols)
        for col_index, cell_value in enumerate(row):
            if col_index in flagged_cols_set:
                continue
            if len(cell_value) <= _ADJACENT_FREETEXT_THRESHOLD:
                continue
            header_name = (
                header[col_index] if col_index < len(header) else ''
            )
            flagged_header = ', '.join(
                repr(header[c] if c < len(header) else '')
                for c in sorted(flagged_cols)
            )
            yield Finding(
                mechanism='csv_payload_in_adjacent_cell',
                tier=TIER['csv_payload_in_adjacent_cell'],
                confidence=0.85,
                description=(
                    f'Row {flagged_row_index} carries a Tier 1 '
                    f'invisible-character finding on column(s) '
                    f'{sorted(flagged_cols)} (header(s) '
                    f'{flagged_header}); the same row carries a '
                    f'free-text cell of {len(cell_value)} characters '
                    f'in column {col_index} (header {header_name!r}). '
                    'The flagged invisible-character cell is the '
                    'visible alarm; the adjacent free-text cell is '
                    'where the payload typically lives. A reader '
                    'who scrubs the flagged cell leaves the adjacent '
                    'payload untouched.'
                ),
                location=(
                    f'{file_path}:row={flagged_row_index},'
                    f'col={col_index}'
                ),
                surface=(
                    f'(invisible-character row {flagged_row_index}; '
                    f'adjacent cell length {len(cell_value)} in '
                    f'column {header_name!r})'
                ),
                concealed=cell_value[:240],
                source_layer='batin',
            )


__all__ = ['detect_payload_in_adjacent_cell']
