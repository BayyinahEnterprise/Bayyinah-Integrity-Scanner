"""
CsvAnalyzer — Al-Baqarah 2:42 applied to the delimited-data surface.

    وَلَا تَلْبِسُوا الْحَقَّ بِالْبَاطِلِ وَتَكْتُمُوا الْحَقَّ وَأَنتُمْ تَعْلَمُونَ
    (Al-Baqarah 2:42)

    "And do not mix the truth with falsehood, nor conceal the truth
    while you know it."

Architectural reading. A delimited-data file (CSV / TSV / PSV) is the
format where the human reader and the automated parser most literally
disagree. The reader sees a rendered grid — in Excel, in a spreadsheet
preview, in a pandas DataFrame display. The parser sees bytes governed
by quoting and delimiter rules nobody inspects. The two views can
diverge in six documented ways:

  * **Zahir (spreadsheet-rendered)** — the cells a human sees when the
    file is opened in Excel, LibreOffice Calc, or Google Sheets. A
    cell that begins with ``=``, ``+``, ``-``, ``@``, TAB, or CR is
    interpreted as a formula by all three applications; the cell's
    on-screen display is the formula's result, not its source — the
    literal ``=HYPERLINK("http://evil/", "click me")`` renders as
    "click me" and exfiltrates on click. OWASP calls this CSV Injection;
    every CSV-as-input ingestion pipeline has this surface.

  * **Batin (parser-visible)** — content that text-editor readers see
    but spreadsheet-app readers filter away: comment rows (``#`` prefix,
    silently consumed by R's ``read.csv``, pandas' ``comment='#'``, awk),
    rows with inconsistent column counts (some parsers pad, others
    truncate, others error), null bytes (Python's ``csv`` module
    truncates silently, Excel treats as end-of-field), BOM in the first
    cell (some parsers strip, others preserve, leaving a header cell
    named ``"\ufeffDate"``), and oversized fields (DoS-shaped exports).

  * **Structural ambiguity** — the same byte sequence can carry
    different delimiters on different rows (row 1 comma-delimited,
    row 2 tab-delimited), the file's declared encoding can be invalid
    UTF-8 that decodes differently as Latin-1 (mojibake carrying
    different glyphs to UTF-8-aware vs. Latin-1-aware readers), and
    quoting can be unbalanced or inconsistently applied across rows.

``CsvAnalyzer`` is therefore both a **zahir witness** (the spreadsheet
app's rendered view — formula injection, per-cell Unicode concealment)
and a **batin witness** (the parser's substrate — null bytes, comment
rows, ragged columns, BOM anomalies, encoding ambiguity, delimiter
mixing, quoting anomalies, oversized DoS fields). ``source_layer`` is
set per-finding; the class default (``batin``) applies to ``scan_error``
findings emitted by the base helper.

Supported FileKinds: ``{FileKind.CSV}``. The router classifies .csv,
.tsv, and .psv by extension and by content-sniff (consistent-delimiter
heuristic at the head of the file); the CsvAnalyzer re-infers the
delimiter from the bytes it reads, independent of the router's sniff,
so the same analyzer handles comma, tab, and pipe separators
transparently.

Priority order (from the user's Phase 20 brief): formula injection is
the most dangerous (Tier 1 verified, 0.30 severity); null bytes are the
same tier (Tier 1 verified, 0.30 — pure parser-truncation vector);
comment rows and inconsistent columns are the most common
(Tier 2 structural); BOM / mixed encoding / mixed delimiter are the
most subtle (Tier 2 structural); quoting anomalies and oversized fields
are tier 3 interpretive. Build and test in that order.

Additive-only. Nothing in this module is imported by ``bayyinah_v0.py``
or ``bayyinah_v0_1.py``; the PDF pipeline is untouched. The new
mechanisms are registered in ``domain/config.py`` alongside the
existing mechanism catalog — old mechanism names, severities, and
tiers are unchanged.

Reference: Munafiq Protocol §9. DOI: 10.5281/zenodo.19677111.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import ClassVar, Iterable

from analyzers.base import BaseAnalyzer
from analyzers.csv_column_type_drift import detect_column_type_drift
from analyzers.csv_bidi_payload import detect_bidi_payload
from analyzers.csv_zero_width_payload import detect_zero_width_payload
from analyzers.csv_quoted_newline_payload import (
    detect_quoted_newline_payload,
)
from analyzers.csv_encoding_divergence import detect_encoding_divergence
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
    get_current_limits,
)
from domain.config import (
    BIDI_CONTROL_CHARS,
    CONFUSABLE_TO_LATIN,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Read limit — 32 MB bounds the footprint of a single CSV scan. Legitimate
# tabular exports rarely exceed this; adversarial DoS-sized files are
# truncated rather than loaded whole. Matches the XlsxAnalyzer / DocxAnalyzer
# bound so the memory envelope is uniform across format analyzers.
_MAX_READ_BYTES = 32 * 1024 * 1024

# Row limit — bound the number of rows we walk. Legitimate tabular
# exports with more than this row count still get their headers and
# first ~200k rows scanned; the tail is covered by the DoS-detection
# finding (``csv_oversized_field`` or an equivalent row-count signal).
#
# Phase 21 — the hard-coded ceiling is retained as the module-level
# *fallback* used when ``get_current_limits()`` cannot be consulted
# (it never fails in practice — the thread-local always returns
# ``DEFAULT_LIMITS`` — but keeping the constant keeps older tests that
# import it by name working). ``_walk_rows`` now reads
# ``get_current_limits().max_csv_rows`` on each call, with a value of
# ``0`` interpreted as "no row limit" (Al-Baqarah 2:286: never burden
# the scanner beyond capacity, but allow the caller to declare their
# capacity explicitly).
_MAX_ROWS = 200_000

# Per-field byte threshold at which ``csv_oversized_field`` fires. A
# legitimate cell value is almost never larger than this; a megabyte-
# scale cell in a tabular export is a DoS / parser-exhaustion shape.
_OVERSIZED_FIELD_THRESHOLD = 1024 * 1024  # 1 MB

# First-byte characters that make a cell a formula when opened in Excel,
# LibreOffice Calc, or Google Sheets. The set is the OWASP-documented
# CSV-injection prefix set: ``=``, ``+``, ``-``, ``@``, plus ``TAB``
# (U+0009) and ``CR`` (U+000D) which some clipboard paths also honour
# as formula triggers. All six are first-byte triggers — the check is
# strictly positional.
_FORMULA_PREFIX_CHARS: frozenset[str] = frozenset({
    "=", "+", "-", "@", "\t", "\r",
})

# Candidate delimiters considered during delimiter inference. Order is
# intentional: tab is the least likely false positive inside prose,
# pipe next, comma last (commas do appear in prose). The first delimiter
# that "wins" (≥2 occurrences on the first row and a majority of the
# sampled rows agree within ±1 count) is used as the file's inferred
# delimiter. Semicolon is included because European locales (Excel's
# German / French default export) use ``;`` as the list separator.
_CANDIDATE_DELIMITERS: tuple[str, ...] = ("\t", "|", ",", ";")

# Number of rows sampled for delimiter inference.
_DELIM_INFERENCE_SAMPLE = 8

# UTF-8 BOM, used for BOM-anomaly detection.
_BOM = "\ufeff"

# Raise Python's csv.field_size_limit so a legitimately large cell
# doesn't raise ``_csv.Error: field larger than field limit (131072)``
# before the ``csv_oversized_field`` detector can examine it. Python's
# default limit is 128 KiB — well below our 1 MiB oversized-field
# threshold, which means a megabyte-scale cell would otherwise surface
# as a ``scan_error`` and clamp the scan. We bound the new limit to the
# file-read ceiling so the csv module cannot buffer more than the scan
# has already read. This is a module-load-time side effect (the setting
# is global to the csv module), matching the discipline of other
# analyzers that tune parser knobs once at import.
csv.field_size_limit(_MAX_READ_BYTES)

# Word-level homoglyph detection shares the same Latin-letter range as
# every other analyzer — kept local rather than factored out to preserve
# module independence.
_LATIN_RANGES = (
    range(0x0041, 0x005B),  # A-Z
    range(0x0061, 0x007B),  # a-z
)


def _is_latin_letter(ch: str) -> bool:
    cp = ord(ch)
    return any(cp in r for r in _LATIN_RANGES)


def _column_ref(col_index: int) -> str:
    """Return a 1-based Excel-style column reference (A, B, …, AA)."""
    if col_index < 0:
        return "?"
    n = col_index + 1
    out = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


# ---------------------------------------------------------------------------
# CsvAnalyzer
# ---------------------------------------------------------------------------


class CsvAnalyzer(BaseAnalyzer):
    """Detects zahir and batin concealment in delimited-data files.

    The analyzer reads the file bytes (bounded by ``_MAX_READ_BYTES``),
    detects BOM / encoding / null-byte anomalies at the byte level,
    decodes to text, infers the delimiter from the first several rows,
    walks every row with ``csv.reader`` (the stdlib parser, which
    tolerates quoting / escaping the way every Python data-ingestion
    pipeline does), and runs per-cell detectors: formula-injection
    prefix, per-cell Unicode concealment (zero-width / TAG / bidi /
    homoglyph), and per-cell size checking for DoS-shaped fields.

    Findings fired once per file:
      * ``csv_null_byte`` — batin, 0.30 severity, tier 1 verified
      * ``csv_bom_anomaly`` — batin, 0.10, tier 2 structural
      * ``csv_mixed_encoding`` — batin, 0.15, tier 2 structural
      * ``csv_mixed_delimiter`` — batin, 0.15, tier 2 structural

    Findings fired once per occurrence:
      * ``csv_formula_injection`` — zahir, 0.30, tier 1 verified
        (one finding per offending cell)
      * ``csv_comment_row`` — batin, 0.15, tier 2 structural
        (one finding per comment row)
      * ``csv_inconsistent_columns`` — batin, 0.15, tier 2 structural
        (one finding per row with mismatched column count)
      * ``csv_quoting_anomaly`` — batin, 0.10, tier 3 interpretive
        (one finding per row with unbalanced quoting)
      * ``csv_oversized_field`` — batin, 0.10, tier 3 interpretive
        (one finding per oversized cell)
      * Per-cell zahir concealment: ``zero_width_chars``, ``tag_chars``,
        ``bidi_control``, ``homoglyph`` — shared generic mechanisms,
        same shape XlsxAnalyzer / DocxAnalyzer / HtmlAnalyzer emit for
        per-string Unicode scans.

    Corrupt / unreadable / wholly-undecodable inputs are converted to a
    single ``scan_error`` finding via ``_scan_error_report`` — consistent
    with the middle-community contract (Al-Baqarah 2:143): one witness
    failing does not silence the others, and the failure itself is a
    signal.
    """

    name: ClassVar[str] = "csv"
    error_prefix: ClassVar[str] = "CSV scan error"
    # Class default — batin. ``scan_error`` findings emitted by the
    # base-class helper are structural (the tabular substrate was not
    # inspected). Per-finding source_layer is set individually for
    # every zahir detector below.
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({FileKind.CSV})

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the delimited-data file at ``file_path``."""
        try:
            raw = self._read_bounded(file_path)
        except OSError as exc:
            return self._scan_error_report(file_path, str(exc))
        if raw is None:
            return self._scan_error_report(
                file_path, "could not read file bytes",
            )

        findings: list[Finding] = []

        # ---- Byte-level detectors ----
        # These fire before decode because decoding can silently hide
        # the signal: a Python ``str.decode`` with ``errors='replace'``
        # would mask a null byte as U+FFFD, and a permissive Latin-1
        # decode would paper over an invalid-UTF-8 mojibake shape.
        findings.extend(self._detect_null_byte(raw, file_path))
        findings.extend(self._detect_bom_anomaly(raw, file_path))

        # Decode with mixed-encoding awareness.
        text, mixed_encoding_finding = self._decode_mixed(raw, file_path)
        if mixed_encoding_finding is not None:
            findings.append(mixed_encoding_finding)
        if text is None:
            # Completely undecodable — surface as scan_error and return
            # the partial report. The middle-community contract requires
            # that earlier successful byte-level detectors stay on the
            # record even if the rest of the scan aborts.
            error_rep = self._scan_error_report(
                file_path,
                "bytes could not be decoded as UTF-8 or Latin-1",
            )
            error_rep.findings[0:0] = findings
            # Recompute the score with the partial findings preserved.
            error_rep.integrity_score = compute_muwazana_score(
                error_rep.findings,
            )
            return error_rep

        # Strip a single leading BOM from the decoded text before the
        # per-row walk. The ``csv_bom_anomaly`` finding (if one was
        # emitted above) has already recorded its presence; carrying it
        # into the first cell would produce a misleading ``"\ufeffDate"``
        # header name in every downstream finding's location field.
        if text.startswith(_BOM):
            text = text[len(_BOM):]

        # Sanitise NULs before the row walk. Python's ``csv.reader``
        # raises ``_csv.Error: line contains NUL`` the moment it meets a
        # ``\x00``, aborting the whole walk. We've already recorded the
        # null-byte finding at the byte level; replacing NULs with the
        # Unicode replacement character U+FFFD lets the walker continue
        # and surface every other finding in the file. The reader-
        # asymmetry the null byte represents is captured by the
        # ``csv_null_byte`` mechanism already on the record; sanitising
        # here is purely to keep the rest of the scan running.
        if "\x00" in text:
            text = text.replace("\x00", "\ufffd")

        # ---- Delimiter inference + per-row walk ----
        delimiter, mixed_delim_finding = self._infer_delimiter(text, file_path)
        if mixed_delim_finding is not None:
            findings.append(mixed_delim_finding)

        try:
            findings.extend(
                self._walk_rows(text, delimiter, file_path),
            )
            # F2 mechanism 1: per-column type-drift detector. Runs
            # after the row walk so it sees the same delimiter the
            # base walker used.
            findings.extend(
                detect_column_type_drift(text, delimiter, file_path),
            )
            # F2 mechanism 3: RFC 4180 quoted multi-line payload
            # detector. Pairs an embedded-newline count with an
            # unquoted-cell length threshold; both must trip.
            findings.extend(
                detect_quoted_newline_payload(
                    text, delimiter, file_path,
                ),
            )
            # F2 mechanism 4: bidi-override codepoint detector
            # (zahir). Any cell carrying U+202A..U+202E or
            # U+2066..U+2069 fires; spreadsheet renderers reorder
            # the visible glyphs while the bytes carry the original.
            findings.extend(
                detect_bidi_payload(text, delimiter, file_path),
            )
            # F2 mechanism 5: zero-width codepoint detector (zahir).
            # Any cell carrying U+200B / U+200C / U+200D, or
            # U+FEFF mid-stream (file-start BOM is stripped before
            # this point) fires. The codepoint IS in the cell-text
            # stream, the spreadsheet renderer simply renders zero
            # pixels for it - same surface-readable shape as v1.1.1
            # zero_width_chars (also zahir).
            findings.extend(
                detect_zero_width_payload(text, delimiter, file_path),
            )
            # F2 mechanism 6: encoding-divergence detector (batin).
            # Re-reads the file bytes and decodes them twice (UTF-8
            # and latin-1); per-cell value divergence between the
            # two decoded surfaces is surfaced as one finding per
            # divergent cell. Capped at 16 MB; above that the
            # detector yields nothing (the orchestrator's existing
            # scan_limited path already records the truncation).
            findings.extend(
                detect_encoding_divergence(delimiter, file_path),
            )
        except Exception as exc:  # noqa: BLE001 -- deliberately broad
            # An unexpected parser failure becomes a scan_error that
            # composes with the findings already accumulated.
            partial = self._scan_error_report(
                file_path,
                f"unexpected failure during CSV row walk: {exc}",
            )
            partial.findings[0:0] = findings
            partial.integrity_score = compute_muwazana_score(partial.findings)
            return partial

        # Phase 21 — if any ceiling tripped inside ``_walk_rows`` it
        # emitted a ``scan_limited`` finding. We promote that signal to
        # the report's ``scan_incomplete=True`` flag so the 0.5 clamp
        # applies — "absence of findings past the ceiling is not
        # evidence of cleanness."
        scan_incomplete = any(f.mechanism == "scan_limited" for f in findings)
        score = compute_muwazana_score(findings)
        score = apply_scan_incomplete_clamp(
            score, scan_incomplete=scan_incomplete,
        )
        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=score,
            findings=findings,
            scan_incomplete=scan_incomplete,
        )

    # ------------------------------------------------------------------
    # Byte-level detectors (fire before decode)
    # ------------------------------------------------------------------

    def _detect_null_byte(
        self, raw: bytes, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire once if a NUL byte appears anywhere in the file.

        A null byte inside a CSV field has no legitimate reading in any
        real-world CSV dialect: Python's ``csv`` module silently
        truncates at the NUL; Excel treats it as end-of-field; pandas
        refuses to parse; awk disagrees with both. The asymmetry is the
        concealment shape — different readers see different cells. Tier
        1 verified; severity 0.30.
        """
        idx = raw.find(b"\x00")
        if idx < 0:
            return
        # Report the offset of the first null byte. If the file carries
        # more than one, the single finding is sufficient — the tier-1
        # mechanism itself is binary.
        total = raw.count(b"\x00")
        yield Finding(
            mechanism="csv_null_byte",
            tier=TIER["csv_null_byte"],
            confidence=1.0,
            description=(
                f"CSV bytes contain {total} NUL byte(s); the first "
                f"appears at offset {idx}. A NUL inside a CSV field has "
                "no legitimate reading: Python's csv module truncates "
                "silently, Excel treats it as end-of-field, pandas "
                "refuses to parse, and awk disagrees with all three. "
                "The asymmetry is the concealment shape — different "
                "readers see different cells."
            ),
            location=f"{file_path}:byte={idx}",
            surface="(cell appears truncated or absent in some readers)",
            concealed=f"{total} NUL byte(s) in field data",
            source_layer="batin",
        )

    def _detect_bom_anomaly(
        self, raw: bytes, file_path: Path,
    ) -> Iterable[Finding]:
        """Fire on BOM at file start that could misread the first header cell,
        or on a BOM embedded mid-stream (never legitimate).

        UTF-8 BOM at offset 0 is tolerated by most readers (json.loads,
        pandas, csv.reader all strip it) but NOT by all — the first
        header cell in naive readers becomes ``\\ufeffDate`` instead of
        ``Date``. The mechanism fires to surface the asymmetry; downstream
        decode handles the BOM explicitly so the per-row walk is clean.

        A BOM at any offset > 0 is never legitimate — it always
        indicates a concatenation anomaly or an adversarial payload
        designed to split readers. Fires with higher confidence.
        """
        bom_bytes = b"\xef\xbb\xbf"
        idx = raw.find(bom_bytes)
        if idx < 0:
            return
        if idx == 0:
            # Leading BOM — subtle but real.
            yield Finding(
                mechanism="csv_bom_anomaly",
                tier=TIER["csv_bom_anomaly"],
                confidence=0.7,
                description=(
                    "CSV file begins with a UTF-8 BOM (EF BB BF). Most "
                    "modern readers strip it, but naive parsers (awk, "
                    "Python's ``open(..., newline='')`` without explicit "
                    "``utf-8-sig`` encoding, some shell tools) carry it "
                    "into the first header cell — the cell named ``Date`` "
                    "in a human view reads as ``\\ufeffDate`` to a "
                    "downstream filter. The asymmetry is the concealment "
                    "shape."
                ),
                location=f"{file_path}:byte=0",
                surface="(header row appears normal in BOM-aware readers)",
                concealed="leading BOM may be preserved by naive readers",
                source_layer="batin",
            )
            # Check for a SECOND BOM further on — that's the higher-
            # confidence case and deserves its own finding.
            second = raw.find(bom_bytes, 3)
            if second > 0:
                yield Finding(
                    mechanism="csv_bom_anomaly",
                    tier=TIER["csv_bom_anomaly"],
                    confidence=1.0,
                    description=(
                        f"CSV file contains a second UTF-8 BOM at offset "
                        f"{second} (beyond the leading BOM at offset 0). "
                        "A mid-stream BOM is never legitimate in a "
                        "single-file export; it indicates concatenation "
                        "of two files or an adversarial payload designed "
                        "to split readers on a row boundary."
                    ),
                    location=f"{file_path}:byte={second}",
                    surface="(no visible indicator)",
                    concealed=f"embedded BOM at byte {second}",
                    source_layer="batin",
                )
        else:
            # BOM at offset > 0 — always a concealment signal.
            yield Finding(
                mechanism="csv_bom_anomaly",
                tier=TIER["csv_bom_anomaly"],
                confidence=1.0,
                description=(
                    f"CSV file contains a UTF-8 BOM (EF BB BF) embedded "
                    f"at offset {idx} rather than at the file start. "
                    "A mid-stream BOM is never legitimate in a single-"
                    "file export; it indicates concatenation of two "
                    "files or an adversarial payload designed to split "
                    "readers on a row boundary."
                ),
                location=f"{file_path}:byte={idx}",
                surface="(no visible indicator)",
                concealed=f"embedded BOM at byte {idx}",
                source_layer="batin",
            )

    # ------------------------------------------------------------------
    # Decode (UTF-8 strict → Latin-1 fallback with mixed-encoding finding)
    # ------------------------------------------------------------------

    def _decode_mixed(
        self, raw: bytes, file_path: Path,
    ) -> tuple[str | None, Finding | None]:
        """Try strict UTF-8; on failure, fall back to Latin-1 and emit a
        ``csv_mixed_encoding`` finding.

        Returns ``(text, finding_or_None)``. If Latin-1 also fails (which
        is vanishingly rare — Latin-1 maps every byte), returns
        ``(None, None)`` and the caller produces a ``scan_error``.
        """
        try:
            return raw.decode("utf-8", errors="strict"), None
        except UnicodeDecodeError as exc:
            # Bytes are valid Latin-1 (every byte is) but the attempted
            # UTF-8 decode failed at a specific offset. Surface the
            # offset and byte; a mixed-encoding export (legitimate legacy
            # data) lands here, but so does an adversarial payload that
            # decodes to different glyphs for UTF-8-aware vs Latin-1-aware
            # readers.
            try:
                text = raw.decode("latin-1", errors="strict")
            except UnicodeDecodeError:
                return None, None
            finding = Finding(
                mechanism="csv_mixed_encoding",
                tier=TIER["csv_mixed_encoding"],
                confidence=0.8,
                description=(
                    f"CSV bytes are not valid UTF-8 — decode failed at "
                    f"offset {exc.start} (byte 0x{raw[exc.start]:02X}). "
                    "Bytes are valid Latin-1, so a UTF-8-aware reader "
                    "(pandas default, Python 3 ``open``) will see a "
                    "UnicodeDecodeError while a Latin-1-aware reader "
                    "(Excel's default on Windows, legacy shell tools) "
                    "sees renderable but different glyphs. The asymmetry "
                    "is the concealment shape."
                ),
                location=f"{file_path}:byte={exc.start}",
                surface="(renders as Latin-1 glyphs in some readers)",
                concealed=(
                    "bytes decode to different glyphs under "
                    "UTF-8 vs. Latin-1"
                ),
                source_layer="batin",
            )
            return text, finding

    # ------------------------------------------------------------------
    # Delimiter inference
    # ------------------------------------------------------------------

    def _infer_delimiter(
        self, text: str, file_path: Path,
    ) -> tuple[str, Finding | None]:
        """Infer the file's delimiter and, if inconsistent, emit a
        ``csv_mixed_delimiter`` finding.

        Returns ``(delimiter, finding_or_None)``. If the file genuinely
        cannot be classified (zero delimiter candidates win), defaults
        to ``","`` — the most common separator. The per-row walk will
        then often fire ``csv_inconsistent_columns`` for every row.
        """
        # Take the first N non-empty non-comment lines.
        content_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            content_lines.append(line)
            if len(content_lines) >= _DELIM_INFERENCE_SAMPLE:
                break

        if not content_lines:
            return ",", None

        # For each candidate delimiter, score how consistently it
        # appears across the sampled rows. A delimiter that appears ≥2x
        # on the first row AND with the same count (±1) on most other
        # rows is the winner.
        first = content_lines[0]
        scores: list[tuple[str, int, int]] = []  # (delim, first_count, agreeing_rows)
        for delim in _CANDIDATE_DELIMITERS:
            first_count = first.count(delim)
            if first_count < 1:
                continue
            agreeing = 0
            for line in content_lines[1:]:
                cnt = line.count(delim)
                if abs(cnt - first_count) <= 1:
                    agreeing += 1
            scores.append((delim, first_count, agreeing))

        if not scores:
            return ",", None

        # Pick the highest-scoring delimiter: most agreeing rows, then
        # highest first-row count.
        scores.sort(key=lambda s: (-s[2], -s[1], _CANDIDATE_DELIMITERS.index(s[0])))
        winner = scores[0][0]

        # Mixed-delimiter detection: if a SECOND delimiter also scores
        # highly (agreeing >= half the sample, first_count >= 2), flag
        # the file.
        mixed = None
        for delim, fcount, agreeing in scores[1:]:
            # Ignore delimiters that happen to appear equally in prose
            # (agreeing by accident). Require a clear "there are two
            # honestly-present delimiters" signal.
            if fcount >= 2 and agreeing >= max(2, (len(content_lines) - 1) // 2):
                # The winning delimiter is winner, the secondary is delim.
                delim_display = "\\t" if delim == "\t" else delim
                winner_display = "\\t" if winner == "\t" else winner
                mixed = Finding(
                    mechanism="csv_mixed_delimiter",
                    tier=TIER["csv_mixed_delimiter"],
                    confidence=0.75,
                    description=(
                        f"CSV file carries two candidate delimiters that "
                        f"both parse: primary {winner_display!r} "
                        f"(first-row count {scores[0][1]}, {scores[0][2]} "
                        f"agreeing rows) and secondary {delim_display!r} "
                        f"(first-row count {fcount}, {agreeing} agreeing "
                        "rows). A reader that picks the secondary splits "
                        "every row into different cells than a reader "
                        "that picks the primary — classic cross-audience "
                        "divergence at the delimited-data surface."
                    ),
                    location=f"{file_path}:line=1",
                    surface=f"(parses with delimiter {winner_display!r})",
                    concealed=(
                        f"also parses with delimiter {delim_display!r} — "
                        "different reader sees different cells"
                    ),
                    source_layer="batin",
                )
                break
        return winner, mixed

    # ------------------------------------------------------------------
    # Per-row walk
    # ------------------------------------------------------------------

    def _walk_rows(
        self, text: str, delimiter: str, file_path: Path,
    ) -> Iterable[Finding]:
        """Walk every row with ``csv.reader`` and emit per-row / per-cell
        findings.

        The walk operates on the decoded text rather than the raw bytes
        so the delimiter and quoting rules apply against codepoints —
        the same way pandas / Python csv / Excel see the file.
        """
        # First pass: enumerate comment rows and inconsistent-column
        # rows by walking the raw lines, because ``csv.reader`` silently
        # consumes nothing but newlines — a ``#``-prefix row would come
        # through as a single-cell "cell" indistinguishable from an
        # ordinary single-cell row otherwise.
        raw_lines = text.splitlines()

        # Detect comment rows (``#``-prefix on a non-empty row). These
        # are silently consumed by R's ``read.csv``, pandas'
        # ``read_csv(comment='#')``, and awk's default behaviour — but
        # csv.reader and Excel carry them through verbatim as the first
        # cell of a single-cell row.
        for line_index, line in enumerate(raw_lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                preview = stripped[:120]
                yield Finding(
                    mechanism="csv_comment_row",
                    tier=TIER["csv_comment_row"],
                    confidence=0.85,
                    description=(
                        f"Row {line_index + 1} begins with '#' and is a "
                        "comment-prefixed row. R's ``read.csv``, pandas' "
                        "``read_csv(comment='#')``, and awk's default "
                        "behaviour silently skip such rows; Python's "
                        "``csv`` module and Excel carry them through as "
                        f"literal single-cell content. Preview: {preview!r}."
                    ),
                    location=f"{file_path}:line={line_index + 1}",
                    surface=(
                        "(some readers skip, others carry through "
                        "as single-cell row)"
                    ),
                    concealed=(
                        f"comment-prefixed row: {preview!r}"
                    ),
                    source_layer="batin",
                )

        # Second pass: parse with csv.reader for per-row / per-cell
        # findings. We pass strict=False so the parser tolerates
        # quoting errors rather than raising; we detect quoting anomalies
        # ourselves via a parallel check on the raw line.
        reader = csv.reader(
            io.StringIO(text),
            delimiter=delimiter,
            quotechar='"',
            skipinitialspace=False,
        )
        # Phase 21 — read the per-scan ceilings once. ``0`` on either
        # ceiling means "no limit" (explicit opt-out for trusted
        # corpora); a positive integer is the hard ceiling after which
        # the walker emits a ``scan_limited`` finding and stops.
        limits = get_current_limits()
        max_rows = limits.max_csv_rows
        max_field_bytes = limits.max_field_length
        expected_columns: int | None = None
        row_index = 0
        for row in reader:
            row_index += 1
            if max_rows and row_index > max_rows:
                yield Finding(
                    mechanism="scan_limited",
                    tier=3,
                    confidence=1.0,
                    description=(
                        f"CSV row walk stopped at row {max_rows} — configured "
                        f"max_csv_rows={max_rows} reached. Remaining rows "
                        "were not inspected; their findings (if any) are "
                        "absent from this report."
                    ),
                    location=f"{file_path}:row={max_rows}",
                    surface=f"(first {max_rows} rows scanned)",
                    concealed=(
                        "remaining rows past max_csv_rows were not "
                        "examined; scan is incomplete"
                    ),
                    source_layer="batin",
                )
                break
            # Skip genuinely empty rows (reader yields [] for blank lines).
            if not row:
                continue
            # Skip rows whose single cell is a comment-row payload —
            # those are counted above and must not double-fire
            # csv_inconsistent_columns if they parse as one cell.
            if len(row) == 1 and row[0].strip().startswith("#"):
                continue

            # Column-count consistency.
            if expected_columns is None:
                expected_columns = len(row)
            elif len(row) != expected_columns:
                # Surplus-cell payload extraction (F2 extension).
                # When the row has MORE cells than the header, the
                # extra cells are content the header schema did not
                # name. Some parsers drop them silently, others carry
                # them through unnamed. Either way, the bytes are in
                # the row; the concealed surface should expose them.
                surplus_text = ""
                surplus_count = 0
                if len(row) > expected_columns:
                    surplus_cells = row[expected_columns:]
                    surplus_count = len(surplus_cells)
                    surplus_text = " | ".join(surplus_cells)[:500]
                if surplus_count:
                    concealed_text = (
                        f"expected {expected_columns}, got {len(row)}: "
                        f"parser disagreement. Surplus cell content "
                        f"({surplus_count} extra cell(s)): {surplus_text!r}"
                    )
                else:
                    concealed_text = (
                        f"expected {expected_columns}, got {len(row)}: "
                        "parser disagreement"
                    )
                yield Finding(
                    mechanism="csv_inconsistent_columns",
                    tier=TIER["csv_inconsistent_columns"],
                    confidence=0.9,
                    description=(
                        f"Row {row_index} has {len(row)} column(s); the "
                        f"header row and earlier data rows have "
                        f"{expected_columns}. Different parsers resolve "
                        "the mismatch differently: pandas pads with NaN, "
                        "awk truncates, Excel carries the mismatch "
                        "through as a ragged row, and Python's csv "
                        "module returns the row verbatim. The divergence "
                        "is the concealment surface."
                    ),
                    location=f"{file_path}:row={row_index}",
                    surface=f"(row has {len(row)} cell(s) visibly)",
                    concealed=concealed_text,
                    source_layer="batin",
                )

            # Per-cell detectors.
            for col_index, cell in enumerate(row):
                col_ref = _column_ref(col_index)
                cell_loc = f"{file_path}:{col_ref}{row_index}"

                # Formula injection (zahir — renders in spreadsheet app).
                if cell and cell[0] in _FORMULA_PREFIX_CHARS:
                    lead = cell[0]
                    lead_display = (
                        "\\t" if lead == "\t"
                        else "\\r" if lead == "\r"
                        else lead
                    )
                    preview = cell[:200]
                    yield Finding(
                        mechanism="csv_formula_injection",
                        tier=TIER["csv_formula_injection"],
                        confidence=0.95 if lead in ("=", "+", "-", "@")
                        else 0.8,  # TAB / CR slightly lower
                        description=(
                            f"Cell {col_ref}{row_index} begins with "
                            f"{lead_display!r} and is interpreted as a "
                            "formula by Excel, LibreOffice Calc, and "
                            "Google Sheets when the file is opened. The "
                            "rendered cell shows the formula's result, "
                            "not its source — the literal text of the "
                            "cell (which a text-editor reader sees) "
                            "diverges from what a spreadsheet-app reader "
                            f"sees. OWASP calls this CSV Injection. "
                            f"Preview: {preview!r}."
                        ),
                        location=cell_loc,
                        surface="(spreadsheet apps render formula result)",
                        concealed=(
                            f"cell source begins with {lead_display!r} — "
                            "formula evaluates on open"
                        ),
                        source_layer="zahir",
                    )

                # Oversized-field DoS detection.
                cell_size_bytes = len(cell.encode("utf-8", errors="replace"))
                if cell_size_bytes >= _OVERSIZED_FIELD_THRESHOLD:
                    size_bytes = cell_size_bytes
                    yield Finding(
                        mechanism="csv_oversized_field",
                        tier=TIER["csv_oversized_field"],
                        confidence=0.8,
                        description=(
                            f"Cell {col_ref}{row_index} is "
                            f"{size_bytes:,} bytes — above the "
                            f"{_OVERSIZED_FIELD_THRESHOLD:,}-byte threshold. "
                            "Megabyte-scale cells in tabular exports are "
                            "a DoS / parser-exhaustion shape; some "
                            "parsers buffer unbounded, others truncate, "
                            "others reject. Legitimate log-message "
                            "exports can reach this size, so the signal "
                            "is tier-3 interpretive."
                        ),
                        location=cell_loc,
                        surface="(cell present but very large)",
                        concealed=(
                            f"{size_bytes:,} bytes — potential DoS"
                        ),
                        source_layer="batin",
                    )

                # Phase 21 — max_field_length ceiling. This is the
                # scanner-capacity cut-off: the oversized-field finding
                # above flags the adversarial shape; max_field_length
                # refuses to spend the cycles doing per-codepoint
                # Unicode concealment analysis on a multi-megabyte cell.
                # When the ceiling is hit we emit ``scan_limited`` and
                # skip the per-cell Unicode scan for THIS cell only; the
                # row walk continues for every remaining cell and row.
                # ``max_field_bytes == 0`` disables the ceiling (opt-out
                # for trusted, known-large corpora).
                if max_field_bytes and cell_size_bytes > max_field_bytes:
                    yield Finding(
                        mechanism="scan_limited",
                        tier=3,
                        confidence=1.0,
                        description=(
                            f"Cell {col_ref}{row_index} is {cell_size_bytes:,} "
                            f"bytes — above the configured "
                            f"max_field_length={max_field_bytes:,}. Per-cell "
                            "Unicode concealment analysis was skipped for "
                            "this cell to bound scanner memory/CPU; other "
                            "findings for this cell (formula injection, "
                            "oversized-field) were emitted above."
                        ),
                        location=cell_loc,
                        surface=f"(cell is {cell_size_bytes:,} bytes)",
                        concealed=(
                            f"exceeds max_field_length={max_field_bytes:,}; "
                            "zahir Unicode scan not run on this cell"
                        ),
                        source_layer="batin",
                    )
                    continue

                # Per-cell Unicode concealment (shared zahir mechanisms).
                yield from self._scan_cell_string(cell, cell_loc)

        # Third pass: quoting anomalies. An unbalanced quote in a raw
        # line is often papered over by csv.reader's error-tolerant
        # mode (we passed strict=False above), so we detect it
        # independently at the line level.
        for line_index, line in enumerate(raw_lines):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                continue
            # Count unescaped double-quote characters. An odd count on a
            # non-empty row indicates unbalanced quoting that different
            # parsers resolve differently.
            #
            # csv.reader tolerates ``""`` as an escaped quote inside a
            # quoted field, so we pre-strip ``""`` pairs before counting.
            probe = line.replace('""', "")
            quote_count = probe.count('"')
            if quote_count % 2 == 1:
                yield Finding(
                    mechanism="csv_quoting_anomaly",
                    tier=TIER["csv_quoting_anomaly"],
                    confidence=0.6,
                    description=(
                        f"Row {line_index + 1} has an odd number of "
                        f"unescaped double-quote characters ({quote_count} "
                        "after ``\"\"`` pairs removed). Different parsers "
                        "resolve the unbalanced quote differently — some "
                        "consume the next row as continuation of the "
                        "quoted field, some raise, some truncate at the "
                        "quote. The divergence is a classic tier-3 "
                        "concealment shape."
                    ),
                    location=f"{file_path}:line={line_index + 1}",
                    surface="(row displays with visible quotes)",
                    concealed=(
                        "odd quote count — parser disagreement on "
                        "field boundaries"
                    ),
                    source_layer="batin",
                )

    # ------------------------------------------------------------------
    # Shared zahir-layer per-cell string check
    # ------------------------------------------------------------------

    def _scan_cell_string(
        self, value: str, location: str,
    ) -> Iterable[Finding]:
        """Zahir-layer Unicode concealment checks for a single cell value.

        Emits the shared generic mechanisms (``zero_width_chars``,
        ``tag_chars``, ``bidi_control``, ``homoglyph``) — the same
        per-string scan XlsxAnalyzer / DocxAnalyzer / HtmlAnalyzer run.
        The cell's column/row coordinate in ``location`` pins the reader
        to the exact cell; each mechanism surfaces at most once per call.
        """
        if not value:
            return

        # Zero-width.
        zw = [c for c in value if c in ZERO_WIDTH_CHARS]
        if zw:
            codepoints = ", ".join(sorted({f"U+{ord(c):04X}" for c in zw}))
            yield Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.9,
                description=(
                    f"{len(zw)} zero-width character(s) in this cell "
                    f"value ({codepoints}) — invisible to a human "
                    "reader, preserved by parsers and tokenizers."
                ),
                location=location,
                surface="(no visible indication)",
                concealed=f"{len(zw)} zero-width codepoint(s)",
                source_layer="zahir",
            )

        # TAG block — prompt-injection vector.
        tags = [c for c in value if ord(c) in TAG_CHAR_RANGE]
        if tags:
            shadow = "".join(
                chr(ord(c) - 0xE0000) if 0x20 <= ord(c) - 0xE0000 <= 0x7E
                else "?"
                for c in tags
            )
            yield Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=1.0,
                description=(
                    f"{len(tags)} Unicode TAG character(s) in this cell "
                    "value. TAG codepoints are invisible to human "
                    "readers and decodable by LLMs — a documented "
                    "prompt-injection smuggling vector. Decoded shadow: "
                    f"{shadow!r}."
                ),
                location=location,
                surface="(no visible indication)",
                concealed=f"TAG payload ({len(tags)} codepoints)",
                source_layer="zahir",
            )

        # Bidi-control.
        bidi = [c for c in value if c in BIDI_CONTROL_CHARS]
        if bidi:
            codepoints = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in bidi})
            )
            yield Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(bidi)} bidi-control character(s) in this "
                    f"cell value ({codepoints}) — reorders display "
                    "without changing the codepoint stream."
                ),
                location=location,
                surface="(reordered display)",
                concealed=f"{len(bidi)} bidi-override codepoint(s)",
                source_layer="zahir",
            )

        # Homoglyph — word-level mix of Latin + confusable.
        for word in value.split():
            if len(word) < 2:
                continue
            confusables = [c for c in word if c in CONFUSABLE_TO_LATIN]
            latin_letters = [c for c in word if _is_latin_letter(c)]
            if not confusables:
                continue
            if not (latin_letters or len(confusables) >= 2):
                continue
            recovered = "".join(
                CONFUSABLE_TO_LATIN.get(c, c) for c in word
            )
            cp_info = ", ".join(
                sorted({f"U+{ord(c):04X}" for c in confusables})
            )
            yield Finding(
                mechanism="homoglyph",
                tier=TIER["homoglyph"],
                confidence=0.85,
                description=(
                    f"Word mixes Latin letters with {len(confusables)} "
                    f"confusable codepoint(s) ({cp_info}) — visually "
                    f"impersonates {recovered!r}."
                ),
                location=location,
                surface=word,
                concealed=f"appears identical to {recovered!r}",
                source_layer="zahir",
            )

    # ------------------------------------------------------------------
    # Bounded file read
    # ------------------------------------------------------------------

    def _read_bounded(self, file_path: Path) -> bytes | None:
        """Read at most ``_MAX_READ_BYTES`` from ``file_path``.

        Returns the bytes, or ``None`` if the file could not be opened.
        Memory envelope is uniform with DocxAnalyzer / XlsxAnalyzer /
        PptxAnalyzer — 32 MB.
        """
        try:
            with file_path.open("rb") as fh:
                return fh.read(_MAX_READ_BYTES)
        except OSError:
            return None


__all__ = ["CsvAnalyzer"]
