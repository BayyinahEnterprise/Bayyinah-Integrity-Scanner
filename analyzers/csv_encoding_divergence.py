"""
csv_encoding_divergence -- v1.1.2 F2 mechanism 6 (batin).

Al-Baqarah 2:42 applied to encoding-fork smuggling. A CSV file's
bytes carry a single payload, but the rendered surface depends on
which codec the consumer uses. UTF-8 and latin-1 are the two
universal CSV codecs; latin-1 always succeeds (every byte 0x00..
0xFF has a latin-1 mapping) and UTF-8 is the modern default.

When the same byte stream decodes to a different cell value under
the two codecs, the file carries an encoding-fork payload: one
consumer (UTF-8 spreadsheet) sees one cell text, another consumer
(latin-1 legacy parser, byte-oriented exporter, downstream
indexer) sees different cell text. The bytes hide the divergence
behind the codec choice.

This is batin by definition. The divergence is not visible from
any single deterministic walk of any single decoded surface; it
is only visible by walking the same bytes through two codecs and
diff-ing the field stream. The scanner's job is to surface the
fork.

Detector contract (per docs/adversarial/csv_json_gauntlet/REPORT.md
section 3.6):

  * Read the file bytes (capped at 16 MB; beyond that, the
    orchestrator's existing scan_limited / read-cap machinery
    already fires; this detector simply yields nothing on
    truncation rather than introducing a second cap path).
  * Decode twice: UTF-8 with errors='replace', and latin-1
    (always succeeds).
  * Parse each decoded string with Python's csv module using the
    same delimiter the orchestrator inferred.
  * Walk the parsed rows in lockstep and compare field-by-field.
  * For each (row, column) where the two decoded values differ,
    emit one finding.

Tier 1 batin. Severity 0.20.

Reference: Munafiq Protocol Sec. 9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Iterable

from domain import Finding
from domain.config import TIER

# Read cap. Above this, the detector yields nothing rather than
# loading a second copy of the bytes; the orchestrator's scan_limited
# pathway already records the truncation at the file-load layer.
_DETECTOR_READ_CAP_BYTES = 16 * 1024 * 1024


def _safe_read_bytes(file_path: Path) -> bytes | None:
    """Return the file bytes, or None if over the detector cap."""
    try:
        size = file_path.stat().st_size
    except OSError:
        return None
    if size > _DETECTOR_READ_CAP_BYTES:
        return None
    try:
        return file_path.read_bytes()
    except OSError:
        return None


def _strip_leading_bom(data: bytes) -> bytes:
    """Strip a single leading UTF-8 BOM if present.

    The base CSV decoder does the same on the UTF-8 side; matching
    here keeps the field-by-field walk aligned with what the rest
    of the analyzer sees.
    """
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:]
    return data


def _parse_rows(decoded: str, delimiter: str) -> list[list[str]]:
    """Parse a decoded string into rows; defensive against malformed CSV."""
    try:
        return list(csv.reader(io.StringIO(decoded), delimiter=delimiter))
    except csv.Error:
        return []


def detect_encoding_divergence(
    delimiter: str,
    file_path: Path,
) -> Iterable[Finding]:
    """Yield csv_encoding_divergence findings.

    Unlike the other CSV F2 detectors, this one re-reads the file
    bytes itself rather than receiving the decoded ``text``. The
    point of the mechanism is to expose the fact that two valid
    decodes produce different surfaces; receiving a single decoded
    string would defeat the test.
    """
    raw = _safe_read_bytes(file_path)
    if raw is None:
        return
    bom_stripped = _strip_leading_bom(raw)

    # Two independent decodes. UTF-8 with errors='replace' so a
    # malformed UTF-8 byte sequence still produces a comparable
    # string (the U+FFFD replacement character will itself differ
    # from whatever latin-1 produces, which is the divergence).
    try:
        utf8_text = bom_stripped.decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001 -- defensive
        return
    try:
        latin1_text = bom_stripped.decode("latin-1")
    except Exception:  # noqa: BLE001 -- defensive
        return

    # If the two decodes produced byte-identical strings, no
    # divergence is possible at the cell level. Short-circuit.
    if utf8_text == latin1_text:
        return

    utf8_rows = _parse_rows(utf8_text, delimiter)
    latin1_rows = _parse_rows(latin1_text, delimiter)

    # Walk in lockstep up to the shorter row count. A row-count
    # mismatch is itself a divergence shape, but it is already
    # surfaced by the inconsistent_columns / row-count machinery;
    # this detector stays focused on per-cell value divergence.
    row_count = min(len(utf8_rows), len(latin1_rows))
    for row_offset in range(row_count):
        utf8_row = utf8_rows[row_offset]
        latin1_row = latin1_rows[row_offset]
        col_count = min(len(utf8_row), len(latin1_row))
        for col_index in range(col_count):
            utf8_cell = utf8_row[col_index]
            latin1_cell = latin1_row[col_index]
            if utf8_cell == latin1_cell:
                continue
            yield Finding(
                mechanism="csv_encoding_divergence",
                tier=TIER["csv_encoding_divergence"],
                confidence=0.9,
                description=(
                    f"Cell at row {row_offset}, column {col_index} "
                    f"decodes to different strings under UTF-8 and "
                    f"latin-1. The byte stream carries an encoding-"
                    f"fork payload: a UTF-8 reader and a latin-1 "
                    f"reader will see different cell text from the "
                    f"same bytes. UTF-8 decode: {utf8_cell[:120]!r}; "
                    f"latin-1 decode: {latin1_cell[:120]!r}."
                ),
                location=f"{file_path}:row={row_offset},col={col_index}",
                surface=(
                    f"(UTF-8 decode: {utf8_cell[:80]!r}; "
                    f"latin-1 decode: {latin1_cell[:80]!r})"
                ),
                concealed=(
                    f"UTF-8: {utf8_cell[:120]!r}; "
                    f"latin-1: {latin1_cell[:120]!r}"
                )[:240],
                source_layer="batin",
            )
