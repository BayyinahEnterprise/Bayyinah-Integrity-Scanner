"""The raw content-stream scan must not go quadratic on ordinary streams.

Two real two-page resumes took 130 s and 217 s in ``_scan_raw_unicode``:
lazy ``.*?`` patterns restarted a scan to the end of the stream from every
opening bracket that was not followed by the expected operator.
"""
from __future__ import annotations

import time

from analyzers import text_analyzer as ta


def test_string_patterns_keep_their_meaning() -> None:
    assert [m.group(1) for m in ta._TJ_LITERAL.finditer("(plain) Tj")] == ["plain"]
    assert [m.group(1) for m in ta._TJ_LITERAL.finditer("(a(b)c) Tj")] == ["a(b)c"]
    assert [m.group(1) for m in ta._TJ_LITERAL.finditer(r"(esc\) paren) Tj")] == [r"esc\) paren"]
    assert [m.group(1) for m in ta._TJ_LITERAL.finditer("(not shown) Td (x) Tj")] == ["x"]
    assert [m.group(1) for m in ta._TJ_ARRAY.finditer("[(ab) -20 (cd) <0041>] TJ")] == ["(ab) -20 (cd) <0041>"]
    assert [m.group(1) for m in ta._TJ_ARRAY.finditer("[1 0 0 1 0 0] cm [(x)] TJ")] == ["(x)"]
    assert [m.group(1) for m in ta._HEX_SHOW.finditer("<0041 0042> Tj <00> Td")] == ["0041 0042"]


def test_scan_time_grows_linearly_with_stream_size() -> None:
    # Strings shown with ' and arrays used for dashes: none is followed by
    # Tj or TJ, which is the case that sent the old patterns to the end of
    # the stream from every bracket.
    unit = "(a line of text) ' [3 2] 0 d 1 0 0 1 10 20 cm (another) ' <0041> Td\n"
    stream = unit * 20_000                      # about 1.3 MB
    start = time.perf_counter()
    for pat in (ta._TJ_LITERAL, ta._TJ_ARRAY, ta._HEX_SHOW):
        assert sum(1 for _ in pat.finditer(stream)) == 0
    assert time.perf_counter() - start < 5.0
