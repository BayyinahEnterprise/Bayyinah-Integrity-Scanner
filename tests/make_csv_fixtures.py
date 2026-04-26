"""
Phase 20 fixture generator — clean + adversarial CSV / TSV / PSV corpus.

    وَلَا تَلْبِسُوا الْحَقَّ بِالْبَاطِلِ وَتَكْتُمُوا الْحَقَّ وَأَنتُمْ تَعْلَمُونَ
    "Do not mix truth with falsehood, nor conceal the truth while you
    know it." — Al-Baqarah 2:42

Delimited-data files are the surface where the human reader and the
automated parser most literally disagree. The human opens the file in
a spreadsheet and sees rendered cells — where ``=HYPERLINK(...)``
displays as a clickable link that exfiltrates on click. The text-
editor reader sees the raw formula source. The downstream data
pipeline silently skips comment rows, pads ragged columns, truncates
at null bytes, and preserves leading BOMs in header names. Six
documented divergence shapes; this corpus makes each of them visible.

Each fixture is a minimal, hand-crafted byte string that fires EXACTLY
its intended mechanism(s) through the full ``application.ScanService``
pipeline. Extras are false positives, missing firings are false
negatives. The expectation table below pins the contract.

Determinism: every fixture is built from explicit bytes with fixed
row terminators (``\\r\\n``, per RFC 4180), fixed column counts, and
no wall-clock or random content. Running this module twice produces
byte-identical output.

Output layout (relative to ``tests/fixtures/``):

    csv/clean/plain_comma.csv
    csv/clean/plain_tab.tsv
    csv/clean/plain_pipe.psv
    csv/adversarial/formula_injection_equals.csv
    csv/adversarial/formula_injection_plus.csv
    csv/adversarial/formula_injection_minus.csv
    csv/adversarial/formula_injection_at.csv
    csv/adversarial/formula_injection_tab.csv
    csv/adversarial/null_byte.csv
    csv/adversarial/comment_row.csv
    csv/adversarial/inconsistent_columns.csv
    csv/adversarial/bom_leading.csv
    csv/adversarial/bom_embedded.csv
    csv/adversarial/mixed_encoding.csv
    csv/adversarial/mixed_delimiter.csv
    csv/adversarial/quoting_anomaly.csv
    csv/adversarial/zero_width_in_cell.csv
    csv/adversarial/tag_chars_in_cell.csv
    csv/adversarial/bidi_in_cell.csv
    csv/adversarial/homoglyph_in_cell.csv

``csv_oversized_field`` is deliberately not represented here — a 1 MiB
fixture committed to the repo is heavier than the signal it carries.
It is covered by an in-memory unit test in
``tests/analyzers/test_csv_analyzer.py``.

Each fixture pairs with an expectation row in
``CSV_FIXTURE_EXPECTATIONS``. ``tests/test_csv_fixtures.py`` walks
that table and asserts per-fixture expectations.
"""

from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "csv"
CLEAN_DIR = FIXTURES_DIR / "clean"
ADV_DIR = FIXTURES_DIR / "adversarial"


# ---------------------------------------------------------------------------
# Expectation table
# ---------------------------------------------------------------------------

# Maps each fixture's path (relative to ``tests/fixtures/csv/``) to the
# mechanisms it SHOULD fire. An empty list means "clean — no analyzer
# should fire". ``tests/test_csv_fixtures.py`` walks this table and
# asserts per-fixture expectations via set equality on the mechanism
# names (i.e. the fixture fires exactly this set, no more, no less).
#
# A fixture that carries TWO mechanism names lists both because the
# analyzer's faithful reading of the bytes naturally surfaces both —
# e.g. ``bom_embedded.csv`` trips both ``csv_bom_anomaly`` (at the
# byte-offset level) AND ``zero_width_chars`` (because the mid-stream
# BOM survives into a csv-reader cell as U+FEFF, which is in the
# shared zero-width set). The co-firing is a correctness signal, not
# a false positive.
CSV_FIXTURE_EXPECTATIONS: dict[str, list[str]] = {
    # Clean — any firing is a false positive.
    "clean/plain_comma.csv": [],
    "clean/plain_tab.tsv": [],
    "clean/plain_pipe.psv": [],

    # Zahir — formula injection, one fixture per OWASP prefix char.
    "adversarial/formula_injection_equals.csv":
        ["csv_formula_injection"],
    "adversarial/formula_injection_plus.csv":
        ["csv_formula_injection"],
    "adversarial/formula_injection_minus.csv":
        ["csv_formula_injection"],
    "adversarial/formula_injection_at.csv":
        ["csv_formula_injection"],
    "adversarial/formula_injection_tab.csv":
        ["csv_formula_injection"],

    # Batin — structural concealment.
    "adversarial/null_byte.csv": ["csv_null_byte"],
    "adversarial/comment_row.csv": ["csv_comment_row"],
    "adversarial/inconsistent_columns.csv": ["csv_inconsistent_columns"],
    "adversarial/bom_leading.csv": ["csv_bom_anomaly"],
    "adversarial/bom_embedded.csv":
        ["csv_bom_anomaly", "zero_width_chars"],
    "adversarial/mixed_encoding.csv": ["csv_mixed_encoding"],
    "adversarial/mixed_delimiter.csv": ["csv_mixed_delimiter"],
    "adversarial/quoting_anomaly.csv": ["csv_quoting_anomaly"],

    # Zahir — per-cell Unicode concealment (shared mechanism names).
    "adversarial/zero_width_in_cell.csv": ["zero_width_chars"],
    "adversarial/tag_chars_in_cell.csv": ["tag_chars"],
    "adversarial/bidi_in_cell.csv": ["bidi_control"],
    "adversarial/homoglyph_in_cell.csv": ["homoglyph"],
}


# ---------------------------------------------------------------------------
# Byte-construction helpers
# ---------------------------------------------------------------------------

# Canonical RFC 4180 row terminator. CSV fixtures use CRLF uniformly so
# the bytes are stable across platforms — LF-only terminators would
# differ on Windows checkouts when git normalises line endings.
CRLF = b"\r\n"


def _crlf_join(*lines: str | bytes) -> bytes:
    """Join CSV rows with CRLF terminators, accepting str or bytes.

    A trailing CRLF is appended so the fixture's final row ends in a
    canonical terminator. Individual builders that want to omit the
    trailing terminator (e.g. the quoting-anomaly fixture, where the
    final bad quote must sit at EOF rather than carry into another
    row) bypass this helper and emit bytes directly.
    """
    out: list[bytes] = []
    for line in lines:
        if isinstance(line, str):
            out.append(line.encode("utf-8"))
        else:
            out.append(line)
    return CRLF.join(out) + CRLF


def _write(rel: str, content: bytes) -> None:
    """Write a fixture, creating parent directories as needed."""
    path = FIXTURES_DIR / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ---------------------------------------------------------------------------
# Clean fixtures
# ---------------------------------------------------------------------------

def build_plain_comma_clean() -> bytes:
    """A minimal, fully ordinary comma-delimited CSV.

    Three columns, three data rows, ASCII-only, no quoting, consistent
    comma delimiter, UTF-8 encodable without BOM, no leading formula
    characters, no comments, no null bytes. Every detector must stay
    silent.
    """
    return _crlf_join(
        "name,age,city",
        "Alice,30,Seattle",
        "Bob,25,Boston",
        "Carol,42,Denver",
    )


def build_plain_tab_clean() -> bytes:
    """A minimal, fully ordinary tab-delimited TSV.

    Same shape as the comma fixture but tab-delimited with a ``.tsv``
    extension. The file router classifies by extension + content
    sniff; the analyzer re-infers the delimiter from the bytes, so
    the same detector pipeline runs uniformly across delimiters.
    """
    return _crlf_join(
        "name\tage\tcity",
        "Alice\t30\tSeattle",
        "Bob\t25\tBoston",
        "Carol\t42\tDenver",
    )


def build_plain_pipe_clean() -> bytes:
    """A minimal, fully ordinary pipe-delimited PSV.

    Pipe separators are common in European / Unix data pipelines —
    log exports, awk-friendly tabular dumps. The ``.psv`` extension
    is routed as CSV-family; the analyzer's delimiter inference
    picks ``|`` as the winner.
    """
    return _crlf_join(
        "name|age|city",
        "Alice|30|Seattle",
        "Bob|25|Boston",
        "Carol|42|Denver",
    )


# ---------------------------------------------------------------------------
# Adversarial — formula injection (zahir, one fixture per prefix char)
# ---------------------------------------------------------------------------

def build_formula_injection_equals() -> bytes:
    """Cell C2 begins with ``=`` — evaluates as a formula on open.

    The cell's literal text is ``=1+1+cmd|'/c calc'!A1``; a
    spreadsheet app opens the file and shows the formula's result,
    not its source. OWASP calls this CSV Injection. The other cells
    are plain ASCII — only ``csv_formula_injection`` fires.
    """
    return _crlf_join(
        "header1,header2,header3",
        "safe,normal,=1+1",
        "after,clean,here",
    )


def build_formula_injection_plus() -> bytes:
    """Cell C2 begins with ``+`` — same pattern as the equals fixture."""
    return _crlf_join(
        "header1,header2,header3",
        "safe,normal,+1+1",
        "after,clean,here",
    )


def build_formula_injection_minus() -> bytes:
    """Cell C2 begins with ``-`` — OWASP-documented prefix."""
    return _crlf_join(
        "header1,header2,header3",
        "safe,normal,-2+3",
        "after,clean,here",
    )


def build_formula_injection_at() -> bytes:
    """Cell C2 begins with ``@`` — Excel's deprecated formula prefix.

    Modern Excel still honours ``@`` as a formula lead in some locales
    and pre-2016 Excel unconditionally evaluates it. LibreOffice Calc
    and Google Sheets disagree on the details but all three render
    the result, not the source.
    """
    return _crlf_join(
        "header1,header2,header3",
        "safe,normal,@SUM(1+1)",
        "after,clean,here",
    )


def build_formula_injection_tab() -> bytes:
    """Cell B2 contains a quoted value whose first codepoint is TAB.

    A leading TAB inside a quoted cell is a clipboard-paste attack
    vector — some spreadsheet apps strip the quotes and inherit the
    TAB as a formula prefix. The cell must be double-quoted so
    csv.reader parses it as a single field whose value begins with
    ``\\t``; the raw-line quote count is even (the two enclosing
    quotes) so no quoting anomaly fires.

    The embedded TAB itself is not consequential for delimiter
    inference — the TAB sits inside a CSV cell (not at a row level),
    so the inferrer's line-count heuristic scores comma only.
    """
    return _crlf_join(
        "h1,h2,h3",
        "plain,\"\tformula_body\",trailing",
        "clean,row,data",
    )


# ---------------------------------------------------------------------------
# Adversarial — batin (structural concealment)
# ---------------------------------------------------------------------------

def build_null_byte() -> bytes:
    """A NUL byte in a data cell — parser-asymmetry at the byte level.

    Python's csv module silently truncates at NUL; Excel treats NUL
    as end-of-field; pandas refuses to parse; awk disagrees with all
    three. The analyzer records the NUL offset, then sanitises the
    byte to U+FFFD (REPLACEMENT CHARACTER) so the rest of the scan
    can continue. U+FFFD is deliberately outside every concealment
    set, so no follow-on mechanism fires.
    """
    # Hand-assemble bytes so the NUL is literal and offset-stable.
    return (
        b"h1,h2,h3\r\n"
        b"alpha,null\x00byte,gamma\r\n"
        b"clean,row,data\r\n"
    )


def build_comment_row() -> bytes:
    """A ``#``-prefix row silently skipped by some parsers.

    R's ``read.csv``, pandas' ``read_csv(comment='#')``, and awk's
    default behaviour skip such rows; Python's csv module and Excel
    carry them through as literal single-cell content. The analyzer
    fires ``csv_comment_row`` and simultaneously excludes the
    comment row from column-count accounting (the skip in
    ``_walk_rows`` sees a single-cell ``#``-prefix row and continues
    without setting ``expected_columns``). The subsequent data rows
    are consistent, so nothing else fires.
    """
    return _crlf_join(
        "# generated 2026-04-22 by export_pipeline v3.2",
        "name,age,city",
        "Alice,30,Seattle",
        "Bob,25,Boston",
    )


def build_inconsistent_columns() -> bytes:
    """Row 3 has one more cell than the header claims.

    pandas pads with NaN; awk truncates; Excel carries the mismatch
    as a ragged row; Python's csv module returns the row verbatim.
    Different parsers see different cells. The fixture stays
    minimal — a single mismatched row — so only
    ``csv_inconsistent_columns`` fires, once.
    """
    return _crlf_join(
        "h1,h2,h3",
        "alpha,beta,gamma",
        "extra,cells,here,oops",
    )


def build_bom_leading() -> bytes:
    """UTF-8 BOM at file offset 0.

    Most modern readers strip the BOM; naive parsers (awk, Python's
    ``open(..., newline='')`` without explicit ``utf-8-sig``) carry
    it into the first header cell — the cell reads as ``\\ufeffname``
    instead of ``name``. The analyzer records the anomaly, strips
    the BOM before the row walk, and surfaces no downstream
    zero-width finding because the BOM is stripped cleanly.
    """
    bom = b"\xef\xbb\xbf"
    body = _crlf_join(
        "name,age,city",
        "Alice,30,Seattle",
        "Bob,25,Boston",
    )
    return bom + body


def build_bom_embedded() -> bytes:
    """UTF-8 BOM embedded mid-stream — never legitimate.

    The BOM sits between the header row and row 2, so the decoded
    text carries a U+FEFF that lands at the head of cell A2. The
    analyzer fires ``csv_bom_anomaly`` from the byte-level scan and
    ``zero_width_chars`` from the per-cell string scan (U+FEFF is
    in the shared zero-width set). Both firings are correct reads
    of the same concealment — the fixture expectation lists both.
    """
    bom = b"\xef\xbb\xbf"
    return (
        b"h1,h2,h3\r\n"
        + bom + b"alpha,beta,gamma\r\n"
        + b"clean,row,data\r\n"
    )


def build_mixed_encoding() -> bytes:
    """Bytes are not valid UTF-8 but are valid Latin-1.

    A lone ``\\xff`` byte in a cell: a UTF-8-aware reader (pandas'
    default, Python 3 ``open``) raises UnicodeDecodeError at that
    offset; a Latin-1-aware reader (Excel's Windows default, legacy
    shell tools) renders it as ``ÿ`` (U+00FF) and carries on. The
    analyzer falls back to Latin-1 and records ``csv_mixed_encoding``.
    U+00FF is intentionally outside every concealment set, so no
    downstream Unicode mechanism fires.
    """
    return (
        b"h1,h2,h3\r\n"
        b"alpha,test\xffdata,gamma\r\n"
        b"clean,row,data\r\n"
    )


def build_mixed_delimiter() -> bytes:
    """Two delimiters (tab and comma) both parse the file consistently.

    Each row contains three tabs AND three commas. The inferrer
    scores both with the same agreement count; tabs win on the
    candidate-order tiebreak (tab precedes comma in
    ``_CANDIDATE_DELIMITERS``). The comma meets the secondary
    threshold (first-row count ≥ 2, agreeing-rows ≥ half the
    sample), so the analyzer fires ``csv_mixed_delimiter``.

    A tab-delimited reading splits each row into four cells:
    ``['A,B', 'C,D', 'E,F', 'G']``. Column count is consistent
    across rows, no cell begins with a formula prefix, no quoting,
    no Unicode concealment — only the mixed-delimiter mechanism
    fires.
    """
    # Each row: commas=3, tabs=3. Tab wins primary; comma is
    # secondary that also passes the mixed-delimiter threshold.
    return _crlf_join(
        "A,B\tC,D\tE,F\tG",
        "1,2\t3,4\t5,6\t7",
        "a,b\tc,d\te,f\tg",
        "x,y\tz,w\tu,v\tq",
    )


def build_quoting_anomaly() -> bytes:
    """An odd unescaped-quote count on the last raw line.

    The last line ``d,e,"unclosed`` has exactly one ``"`` character
    (odd after ``""`` pairs are stripped). Different parsers resolve
    the unbalanced quote differently — some consume the rest of the
    file as continuation of the quoted field, some raise, some
    truncate at the quote.

    The fixture ends with no trailing CRLF after ``unclosed`` so
    csv.reader sees EOF inside the quoted field and yields a
    three-cell row. Row 1 and row 2 are clean three-cell rows;
    column count is consistent; no other mechanism fires.
    """
    # Hand-built to omit the trailing CRLF after the bad line.
    return (
        b"h1,h2,h3\r\n"
        b"alpha,beta,gamma\r\n"
        b"d,e,\"unclosed"
    )


# ---------------------------------------------------------------------------
# Adversarial — zahir per-cell Unicode concealment (shared mechanisms)
# ---------------------------------------------------------------------------

def build_zero_width_in_cell() -> bytes:
    """Cell B2 contains a zero-width space (U+200B).

    The cell reads as ``bad<ZWSP>value`` to the parser; a human
    reader in a spreadsheet app sees ``badvalue`` with no visual
    indication of the inner codepoint. Fires ``zero_width_chars``
    on the per-cell string scan. No other mechanism matches this
    byte pattern.
    """
    cell = "bad\u200Bvalue"
    return _crlf_join(
        "label,note",
        f"entry,{cell}",
    )


def build_tag_chars_in_cell() -> bytes:
    """Cell B2 contains Unicode TAG characters (E0020..E007F).

    TAG codepoints are invisible to every renderer but decodable by
    LLMs — a documented prompt-injection smuggling vector. The cell
    here embeds two TAG codepoints (``E0049`` and ``E004F``,
    shadow-decoding to ``I`` and ``O``) inside otherwise plain
    ASCII content. Fires ``tag_chars``.
    """
    # U+E0049 and U+E004F — TAG LATIN CAPITAL I and O.
    cell = "plain\U000E0049\U000E004Fsuffix"
    return _crlf_join(
        "label,note",
        f"entry,{cell}",
    )


def build_bidi_in_cell() -> bytes:
    """Cell B2 contains a RIGHT-TO-LEFT OVERRIDE (U+202E).

    The classic display-reversal shape applied to a CSV cell —
    spreadsheet renderers that honour BIDI will reverse the glyph
    order at the RLO boundary while the codepoint stream is
    unchanged. Fires ``bidi_control``.
    """
    cell = "invoice\u202Efdp.doc"
    return _crlf_join(
        "label,note",
        f"entry,{cell}",
    )


def build_homoglyph_in_cell() -> bytes:
    """Cell B2 contains a word mixing Latin and a Cyrillic confusable.

    The word ``аpple`` starts with U+0430 (Cyrillic small ``a``)
    followed by Latin ``pple`` — visually indistinguishable from
    the ASCII word ``apple``. The analyzer's word-level check
    requires a Latin letter to co-occur with at least one
    confusable, which this pattern satisfies. Fires ``homoglyph``.
    """
    # U+0430 (Cyrillic) + "pple" (Latin).
    cell = "\u0430pple"
    return _crlf_join(
        "label,note",
        f"entry,{cell}",
    )


# ---------------------------------------------------------------------------
# Builder dispatch
# ---------------------------------------------------------------------------

_BUILDERS: dict[str, callable] = {
    # Clean
    "clean/plain_comma.csv": build_plain_comma_clean,
    "clean/plain_tab.tsv": build_plain_tab_clean,
    "clean/plain_pipe.psv": build_plain_pipe_clean,
    # Formula injection
    "adversarial/formula_injection_equals.csv":
        build_formula_injection_equals,
    "adversarial/formula_injection_plus.csv":
        build_formula_injection_plus,
    "adversarial/formula_injection_minus.csv":
        build_formula_injection_minus,
    "adversarial/formula_injection_at.csv":
        build_formula_injection_at,
    "adversarial/formula_injection_tab.csv":
        build_formula_injection_tab,
    # Structural concealment
    "adversarial/null_byte.csv": build_null_byte,
    "adversarial/comment_row.csv": build_comment_row,
    "adversarial/inconsistent_columns.csv": build_inconsistent_columns,
    "adversarial/bom_leading.csv": build_bom_leading,
    "adversarial/bom_embedded.csv": build_bom_embedded,
    "adversarial/mixed_encoding.csv": build_mixed_encoding,
    "adversarial/mixed_delimiter.csv": build_mixed_delimiter,
    "adversarial/quoting_anomaly.csv": build_quoting_anomaly,
    # Per-cell Unicode concealment
    "adversarial/zero_width_in_cell.csv": build_zero_width_in_cell,
    "adversarial/tag_chars_in_cell.csv": build_tag_chars_in_cell,
    "adversarial/bidi_in_cell.csv": build_bidi_in_cell,
    "adversarial/homoglyph_in_cell.csv": build_homoglyph_in_cell,
}


def build_all() -> None:
    """Regenerate every fixture in the corpus."""
    for rel, builder in _BUILDERS.items():
        _write(rel, builder())


__all__ = [
    "FIXTURES_DIR",
    "CSV_FIXTURE_EXPECTATIONS",
    "build_all",
]


if __name__ == "__main__":
    build_all()
    print(f"Wrote {len(_BUILDERS)} CSV fixtures to {FIXTURES_DIR}")
