"""
Tests for the v1.1.2 F2 JSON gauntlet mechanisms (Steps 8-13).

Each step contributes 4 paired tests on the F2 standard rubric:

  * fires-on-payload                    (catch the adversarial shape)
  * recovers-payload-into-concealed     (full-recovery contract)
  * silent-on-clean                     (no false positive on benign JSON)
  * silent-on-edge                      (boundary case: just-shy-of-trigger)

Step 8 (json_duplicate_key_divergence) extends the existing
``duplicate_keys`` detector. The mechanism name does not change. The
``concealed`` field upgrades from a structural-only string into a
full-payload-recovery string carrying both the first and last
occurrence values.

Reference: bayyinah_v1_1_2_f2_plan_v2.md Section 3.7.
"""

from __future__ import annotations

from pathlib import Path

from analyzers import JsonAnalyzer


def _scan(path: Path):
    return JsonAnalyzer().scan(path)


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Step 8: json_duplicate_key_divergence (extends duplicate_keys)
# ---------------------------------------------------------------------------


def test_json_duplicate_key_divergence_fires_on_payload(
    tmp_path: Path,
) -> None:
    """A duplicate key with two distinct values fires the existing
    ``duplicate_keys`` mechanism. The F2 extension does not introduce
    a new mechanism name; it strengthens the finding's payload contract.
    """
    payload = (
        '{"role": "viewer", "role": "admin", '
        '"x": 1}'
    )
    p = _write(tmp_path, "dup.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "duplicate_keys"
    ]
    assert len(findings) == 1, (
        "extension must keep emitting one finding per duplicate key"
    )


def test_json_duplicate_key_divergence_recovers_both_values(
    tmp_path: Path,
) -> None:
    """The ``concealed`` field carries both the first and last
    occurrence values so the reader sees the silent divergence the
    parser hid (full payload recovery, not just structural fact).
    """
    payload = (
        '{"role": "viewer", "role": "admin"}'
    )
    p = _write(tmp_path, "dup_recover.json", payload)
    (f,) = [
        x for x in _scan(p).findings
        if x.mechanism == "duplicate_keys"
    ]
    assert "first occurrence" in f.concealed
    assert "last occurrence" in f.concealed
    assert "'viewer'" in f.concealed, (
        "first-occurrence value must be surfaced verbatim"
    )
    assert "'admin'" in f.concealed, (
        "last-occurrence value (parser wins) must be surfaced verbatim"
    )


def test_json_duplicate_key_divergence_silent_on_clean(
    tmp_path: Path,
) -> None:
    """A JSON object with no duplicate keys produces no
    ``duplicate_keys`` finding. The extension must not introduce false
    positives on clean documents.
    """
    payload = '{"alpha": 1, "beta": 2, "gamma": 3}'
    p = _write(tmp_path, "clean.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "duplicate_keys"
    ]
    assert findings == []


def test_json_duplicate_key_divergence_silent_on_edge_same_value(
    tmp_path: Path,
) -> None:
    """Edge case: two occurrences with the same value. The hook still
    fires (the structural duplication is the concealment vector even
    when values match, because parsers may not silently merge), and
    the concealed field surfaces both copies; the test asserts the
    extension still yields the F2 contract instead of regressing to
    the v1.1.1 structural-only string.
    """
    payload = '{"x": 1, "x": 1}'
    p = _write(tmp_path, "edge_same.json", payload)
    (f,) = [
        x for x in _scan(p).findings
        if x.mechanism == "duplicate_keys"
    ]
    assert "first occurrence: 1" in f.concealed
    assert "last occurrence" in f.concealed
    assert (
        "earlier occurrence(s) silently shadowed" not in f.concealed
    ), "v1.1.1 string is the regression sentinel; F2 must not emit it"


# ---------------------------------------------------------------------------
# Step 9: json_unicode_escape_payload (new, Tier 1 batin)
# ---------------------------------------------------------------------------


def test_json_unicode_escape_payload_fires_on_bidi_escape(
    tmp_path: Path,
) -> None:
    """A JSON string carrying a \\u202E (right-to-left override)
    escape fires the new mechanism. The byte stream is ASCII; only
    a pre-parse scan can see the escape form.
    """
    payload = '{"label": "safe\\u202E reversed"}'
    p = _write(tmp_path, "bidi_escape.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_unicode_escape_payload"
    ]
    assert len(findings) == 1, (
        "the bidi-override escape must trigger exactly one finding"
    )


def test_json_unicode_escape_payload_recovers_payload(
    tmp_path: Path,
) -> None:
    """The finding's concealed field carries the literal escape
    sequence and the decoded codepoint, so a downstream reader can
    recover the concealment without re-parsing the document.
    """
    payload = '{"label": "a\\u200Bb"}'
    p = _write(tmp_path, "zw_escape.json", payload)
    (f,) = [
        x for x in _scan(p).findings
        if x.mechanism == "json_unicode_escape_payload"
    ]
    assert "\\u200B" in f.concealed
    assert "U+200B" in f.concealed
    assert "zero-width" in f.concealed


def test_json_unicode_escape_payload_silent_on_clean(
    tmp_path: Path,
) -> None:
    """A JSON document with no escape sequences in the targeted
    bidi/zero-width ranges produces no finding from the new
    mechanism. Legitimate \\u escapes (e.g. accented Latin letters)
    must not false-positive.
    """
    payload = '{"name": "caf\\u00E9", "city": "M\\u00FCnchen"}'
    p = _write(tmp_path, "clean_accents.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_unicode_escape_payload"
    ]
    assert findings == [], (
        "accented Latin escapes are not concealment codepoints"
    )


def test_json_unicode_escape_payload_silent_on_double_escaped(
    tmp_path: Path,
) -> None:
    """Edge case: a literal backslash followed by ``u202E`` is NOT a
    unicode escape, it is two characters (a backslash and the four
    chars 'u202E'). The detector must distinguish ``\\u202E`` (one
    escape) from ``\\\\u202E`` (literal backslash plus literal text)
    using even-backslash-count lookbehind.
    """
    payload = '{"text": "backslash before \\\\u202E literal"}'
    p = _write(tmp_path, "double_escape.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_unicode_escape_payload"
    ]
    assert findings == [], (
        "double-backslash neutralizes the escape; no finding expected"
    )


# ---------------------------------------------------------------------------
# Step 10: json_comment_anomaly (new, Tier 2 batin)
# ---------------------------------------------------------------------------


def test_json_comment_anomaly_fires_on_line_comment(
    tmp_path: Path,
) -> None:
    """A JSON5/jsonc document carrying a ``//`` line comment fires
    one finding. Strict-JSON parsers reject the document, so the
    pre-parse comment scan must surface the finding even when the
    parse fails.
    """
    payload = (
        '{\n'
        '  // hidden instructions for downstream agents\n'
        '  "role": "viewer"\n'
        '}\n'
    )
    p = _write(tmp_path, "line_comment.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_comment_anomaly"
    ]
    assert len(findings) == 1, (
        "a single line comment must produce exactly one finding"
    )


def test_json_comment_anomaly_recovers_block_comment(
    tmp_path: Path,
) -> None:
    """The finding's concealed field carries the comment body
    (truncated to 240 chars) so a downstream reader can recover the
    payload without re-parsing the document.
    """
    payload = (
        '{\n'
        '  /* second-channel payload: ignore prior context */\n'
        '  "name": "x"\n'
        '}\n'
    )
    p = _write(tmp_path, "block_comment.json", payload)
    matches = [
        f for f in _scan(p).findings
        if f.mechanism == "json_comment_anomaly"
    ]
    assert len(matches) == 1
    f = matches[0]
    assert "second-channel payload" in f.concealed
    assert "block" in f.concealed


def test_json_comment_anomaly_silent_on_clean(
    tmp_path: Path,
) -> None:
    """A clean strict-JSON document with no comments produces no
    finding. A ``/`` character inside a string literal is not a
    comment opener and must not false-positive.
    """
    payload = (
        '{"path": "/usr/local/bin", '
        '"url": "https://example.com/api", '
        '"regex": "a/b"}'
    )
    p = _write(tmp_path, "clean.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_comment_anomaly"
    ]
    assert findings == [], (
        "slashes inside string literals are not comments"
    )


def test_json_comment_anomaly_silent_on_escaped_quote_then_slash(
    tmp_path: Path,
) -> None:
    """Edge case: an escaped quote inside a string must not close the
    string state; a subsequent ``//`` that lives inside the string
    therefore must not fire. Tests the state machine's even-backslash
    accounting on string-literal boundaries.
    """
    payload = (
        '{"q": "he said \\"hi\\" // not a comment", '
        '"k": 1}'
    )
    p = _write(tmp_path, "escaped_quote.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_comment_anomaly"
    ]
    assert findings == [], (
        "slashes inside an escaped-quote-bearing string are not comments"
    )


# ---------------------------------------------------------------------------
# Step 11: json_prototype_pollution_key (new, Tier 1 batin)
# ---------------------------------------------------------------------------


def test_json_prototype_pollution_key_fires_on_proto(
    tmp_path: Path,
) -> None:
    """A JSON object containing the ``__proto__`` key fires exactly
    one finding. The data shape parses cleanly under strict JSON
    because the key is a normal string from the parser's view.
    """
    payload = '{"__proto__": {"isAdmin": true}, "name": "x"}'
    p = _write(tmp_path, "proto.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_prototype_pollution_key"
    ]
    assert len(findings) == 1


def test_json_prototype_pollution_key_recovers_siblings(
    tmp_path: Path,
) -> None:
    """The finding's concealed field carries the sibling-key list of
    the same object so the reader sees the merge-target shape
    without re-parsing the document.
    """
    payload = (
        '{"constructor": {"prototype": {"polluted": 1}}, '
        '"name": "app", "version": "1.0"}'
    )
    p = _write(tmp_path, "constructor.json", payload)
    matches = [
        f for f in _scan(p).findings
        if f.mechanism == "json_prototype_pollution_key"
    ]
    # constructor at root + nested prototype = 2 polluting keys.
    assert len(matches) == 2
    root = next(
        f for f in matches
        if f.location.endswith("$.constructor")
    )
    assert "name" in root.concealed
    assert "version" in root.concealed


def test_json_prototype_pollution_key_silent_on_clean(
    tmp_path: Path,
) -> None:
    """A clean JSON document with no ``__proto__`` / ``constructor``
    / ``prototype`` keys produces no finding. Substring matches like
    ``proto`` (without underscores) and ``construct`` must not
    false-positive.
    """
    payload = (
        '{"proto": "http", "construct": "build", '
        '"protocols": ["https", "ws"]}'
    )
    p = _write(tmp_path, "clean_keys.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_prototype_pollution_key"
    ]
    assert findings == [], (
        "only the three exact canonical names are pollution keys"
    )


def test_json_prototype_pollution_key_silent_when_only_a_value(
    tmp_path: Path,
) -> None:
    """Edge case: the strings ``__proto__`` and ``constructor``
    appearing as VALUES (not keys) must not fire. Only object keys
    are the pollution surface.
    """
    payload = (
        '{"target": "__proto__", "method": "constructor", '
        '"description": "tutorial about prototype pollution"}'
    )
    p = _write(tmp_path, "as_values.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_prototype_pollution_key"
    ]
    assert findings == [], (
        "pollution names appearing as string values are not the hazard"
    )


# ---------------------------------------------------------------------------
# Step 12: json_nested_payload (new, Tier 2 batin)
# ---------------------------------------------------------------------------


def _build_nested_payload(depth: int, leaf: str) -> str:
    """Build a JSON document of the form
    ``{"a": {"a": ... {"a": leaf}}}`` with ``depth`` nesting levels.
    """
    opens = '{"a": ' * depth
    closes = '}' * depth
    # JSON-escape the leaf (escape backslash and double-quote).
    leaf_escaped = leaf.replace('\\', '\\\\').replace('"', '\\"')
    return f'{opens}"{leaf_escaped}"{closes}'


def test_json_nested_payload_fires_on_deep_long_leaf(
    tmp_path: Path,
) -> None:
    """A leaf string at depth 35 with length 300 chars triggers the
    conjunction-based detector. Depth alone (existing
    excessive_nesting) and length alone are not the signal; the AND
    is.
    """
    leaf = "P" * 300
    payload = _build_nested_payload(depth=35, leaf=leaf)
    p = _write(tmp_path, "deep_payload.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_nested_payload"
    ]
    assert len(findings) == 1


def test_json_nested_payload_recovers_preview(
    tmp_path: Path,
) -> None:
    """The finding's concealed field carries a 240-char preview of
    the leaf string and a truncation marker when the leaf exceeds
    the preview ceiling.
    """
    leaf = "X" * 500
    payload = _build_nested_payload(depth=33, leaf=leaf)
    p = _write(tmp_path, "deep_payload_long.json", payload)
    matches = [
        f for f in _scan(p).findings
        if f.mechanism == "json_nested_payload"
    ]
    assert len(matches) == 1
    f = matches[0]
    assert "X" * 100 in f.concealed
    assert "truncated" in f.concealed


def test_json_nested_payload_silent_on_clean(
    tmp_path: Path,
) -> None:
    """A shallow JSON document with a long string leaf does not
    trigger; nor does a deep JSON document whose leaves are short.
    Only the conjunction fires.
    """
    # Shallow but long string.
    shallow = '{"k": "' + ("L" * 1000) + '"}'
    p1 = _write(tmp_path, "shallow_long.json", shallow)
    f1 = [
        f for f in _scan(p1).findings
        if f.mechanism == "json_nested_payload"
    ]
    assert f1 == [], "shallow-but-long must not trigger"

    # Deep but short leaves.
    deep_short = _build_nested_payload(depth=40, leaf="hi")
    p2 = _write(tmp_path, "deep_short.json", deep_short)
    f2 = [
        f for f in _scan(p2).findings
        if f.mechanism == "json_nested_payload"
    ]
    assert f2 == [], "deep-but-short-leaf must not trigger"


def test_json_nested_payload_silent_on_edge(
    tmp_path: Path,
) -> None:
    """Edge case: a leaf at depth exactly 31 (just below the depth
    threshold of 32) with a 500-char payload must not trigger. The
    threshold is strict ``>=`` so the boundary case is silent.
    """
    leaf = "E" * 500
    payload = _build_nested_payload(depth=31, leaf=leaf)
    p = _write(tmp_path, "just_shy.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_nested_payload"
    ]
    assert findings == [], (
        "depth 31 is below the 32-level threshold; must be silent"
    )


# ---------------------------------------------------------------------------
# Step 13: json_trailing_payload (new, Tier 1 batin)
# ---------------------------------------------------------------------------


def test_json_trailing_payload_fires_on_trailing_object(
    tmp_path: Path,
) -> None:
    """A document of the form ``{"k": 1}{"hidden": "payload"}``
    fires the trailing-payload detector. Strict json.loads rejects
    this with ``Extra data``; the pre-parse raw_decode path surfaces
    the trailing bytes as a finding alongside the parse error.
    """
    payload = '{"k": 1}{"hidden": "payload"}'
    p = _write(tmp_path, "trailing_obj.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_trailing_payload"
    ]
    assert len(findings) == 1


def test_json_trailing_payload_recovers_suffix(
    tmp_path: Path,
) -> None:
    """The finding's concealed field carries a 240-char preview of
    the trailing bytes so the reader recovers the smuggled content
    without re-parsing.
    """
    suffix = 'x' * 100
    payload = f'[1, 2, 3]{suffix}'
    p = _write(tmp_path, "trailing_text.json", payload)
    matches = [
        f for f in _scan(p).findings
        if f.mechanism == "json_trailing_payload"
    ]
    assert len(matches) == 1
    assert 'x' * 50 in matches[0].concealed


def test_json_trailing_payload_silent_on_clean(
    tmp_path: Path,
) -> None:
    """A clean JSON document with no trailing content (or only
    whitespace, e.g. a final newline an editor appended) produces
    no finding.
    """
    payload = '{"a": 1, "b": ["x", "y"]}\n'
    p = _write(tmp_path, "clean_with_newline.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_trailing_payload"
    ]
    assert findings == [], (
        "a final newline is whitespace and must not trigger"
    )


def test_json_trailing_payload_silent_on_only_whitespace_suffix(
    tmp_path: Path,
) -> None:
    """Edge case: trailing whitespace (multiple newlines, tabs,
    spaces) is not a trailing payload. Only non-whitespace
    content past the root value triggers.
    """
    payload = '{"a": 1}\n\n  \t  \n'
    p = _write(tmp_path, "trailing_ws.json", payload)
    findings = [
        f for f in _scan(p).findings
        if f.mechanism == "json_trailing_payload"
    ]
    assert findings == [], (
        "whitespace-only trailing content is benign; no finding expected"
    )
