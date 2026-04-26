"""
Tests for analyzers.html_analyzer.HtmlAnalyzer.

Phase 16 guardrails. HtmlAnalyzer is a dual-witness — zahir
(render-suppressed elements, plus the shared zero-width / TAG / bidi /
homoglyph detectors applied to every *visible* text run) and batin
(inline scripts, event-handler attributes, long data-* payloads,
external resource references). Each detector has a targeted unit test
that writes a minimal HTML document to ``tmp_path`` and scans it.

Calling ``HtmlAnalyzer().scan(path)`` directly (not via ``ScanService``)
isolates HtmlAnalyzer from TextFileAnalyzer and the correlator. The
fixture-level walker in ``tests/test_html_fixtures.py`` exercises the
full pipeline; these unit tests exercise the analyzer alone.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzers import HtmlAnalyzer
from analyzers.base import BaseAnalyzer
from domain import IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(HtmlAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert HtmlAnalyzer.name == "html"
    assert HtmlAnalyzer.error_prefix == "HTML scan error"
    # Class-level source_layer is batin for scan_error attribution.
    # Per-finding source_layer is set explicitly when emitted.
    assert HtmlAnalyzer.source_layer == "batin"


def test_supported_kinds_is_html_only() -> None:
    assert HtmlAnalyzer.supported_kinds == frozenset({FileKind.HTML})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_html(tmp_path: Path, content: str, name: str = "doc.html") -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _scan(path: Path) -> IntegrityReport:
    return HtmlAnalyzer().scan(path)


def _mechanisms(report: IntegrityReport) -> list[str]:
    return [f.mechanism for f in report.findings]


# ---------------------------------------------------------------------------
# Clean HTML
# ---------------------------------------------------------------------------


def test_clean_html_produces_no_findings(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        "<!doctype html>\n"
        "<html><head><title>Clean</title></head>\n"
        "<body><h1>Hello</h1><p>World.</p></body></html>\n"
    ))
    report = _scan(path)
    assert report.findings == []
    assert report.integrity_score == 1.0
    assert not report.scan_incomplete


# ---------------------------------------------------------------------------
# html_hidden_text — CSS and attribute variants
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("style", [
    "display:none",
    "display: none",
    "DISPLAY:NONE",
    "visibility:hidden",
    "visibility: collapse",
    "opacity:0",
    "opacity: 0.0",
    "font-size:0",
    "font-size: 0px",
    "position:absolute; left:-9999px",
    "position:absolute; top:-1000px",
])
def test_hidden_style_variants_fire(tmp_path: Path, style: str) -> None:
    path = _write_html(tmp_path, (
        f'<html><body><p style="{style}">payload</p></body></html>'
    ))
    report = _scan(path)
    assert "html_hidden_text" in _mechanisms(report), (
        f"style={style!r} did not fire html_hidden_text; "
        f"findings={_mechanisms(report)}"
    )


def test_hidden_attribute_fires(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        '<html><body><p hidden>payload</p></body></html>'
    ))
    assert "html_hidden_text" in _mechanisms(_scan(path))


def test_aria_hidden_true_fires(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        '<html><body><p aria-hidden="true">payload</p></body></html>'
    ))
    assert "html_hidden_text" in _mechanisms(_scan(path))


def test_aria_hidden_false_does_not_fire(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        '<html><body><p aria-hidden="false">payload</p></body></html>'
    ))
    assert "html_hidden_text" not in _mechanisms(_scan(path))


def test_normal_visible_text_does_not_fire_hidden(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        "<html><body><p>ordinary visible paragraph</p></body></html>"
    ))
    assert _scan(path).findings == []


def test_hidden_text_inherits_from_ancestor(tmp_path: Path) -> None:
    """Text inside a nested child of a hidden element is still hidden."""
    path = _write_html(tmp_path, (
        '<html><body><div style="display:none">'
        '<p><span>nested hidden payload</span></p>'
        '</div></body></html>'
    ))
    mechs = _mechanisms(_scan(path))
    assert "html_hidden_text" in mechs


# ---------------------------------------------------------------------------
# html_inline_script — <script> bodies and event handlers
# ---------------------------------------------------------------------------


def test_inline_script_body_fires(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        "<html><body><script>alert(1);</script></body></html>"
    ))
    assert "html_inline_script" in _mechanisms(_scan(path))


def test_empty_script_does_not_fire_inline(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        "<html><body><script></script></body></html>"
    ))
    # Empty body has no inline-script content to emit.
    assert "html_inline_script" not in _mechanisms(_scan(path))


def test_script_with_src_only_does_not_fire_inline(tmp_path: Path) -> None:
    """A <script src=...> with no body should only emit external_reference."""
    path = _write_html(tmp_path, (
        '<html><body><script src="https://cdn.example.com/x.js"></script></body></html>'
    ))
    mechs = _mechanisms(_scan(path))
    assert "html_inline_script" not in mechs
    assert "html_external_reference" in mechs


@pytest.mark.parametrize("handler,value", [
    ("onclick", "alert(1)"),
    ("onmouseover", "fetch('/x')"),
    ("onload", "doit()"),
    ("onerror", "console.log('e')"),
    ("onsubmit", "return false"),
])
def test_event_handler_attributes_fire(
    tmp_path: Path, handler: str, value: str,
) -> None:
    path = _write_html(tmp_path, (
        f'<html><body><button {handler}="{value}">Go</button></body></html>'
    ))
    assert "html_inline_script" in _mechanisms(_scan(path))


def test_non_on_attribute_does_not_fire_inline(tmp_path: Path) -> None:
    """An attribute with 'on' elsewhere (but not at the start) is not a handler."""
    path = _write_html(tmp_path, (
        '<html><body><div data-cordon="x">content</div></body></html>'
    ))
    assert "html_inline_script" not in _mechanisms(_scan(path))


# ---------------------------------------------------------------------------
# html_external_reference
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tag,attr,value", [
    ("script", "src",    "https://evil.example.com/x.js"),
    ("link",   "href",   "http://cdn.example.com/a.css"),
    ("img",    "src",    "https://img.example.com/pixel.png"),
    ("iframe", "src",    "//other.example.com/embed"),
    ("object", "data",   "https://example.com/flash.swf"),
    ("embed",  "src",    "https://example.com/thing"),
    ("form",   "action", "https://attacker.example.com/submit"),
    ("video",  "poster", "https://cdn.example.com/thumb.jpg"),
])
def test_external_reference_attributes_fire(
    tmp_path: Path, tag: str, attr: str, value: str,
) -> None:
    path = _write_html(tmp_path, (
        f'<html><body><{tag} {attr}="{value}"></{tag}></body></html>'
    ))
    assert "html_external_reference" in _mechanisms(_scan(path))


@pytest.mark.parametrize("url", [
    "relative.js",
    "./scripts/a.js",
    "../assets/b.css",
    "/absolute-path-same-origin.js",
    "#anchor",
    "mailto:a@b.test",
])
def test_relative_urls_do_not_fire_external(tmp_path: Path, url: str) -> None:
    path = _write_html(tmp_path, (
        f'<html><body><script src="{url}"></script></body></html>'
    ))
    assert "html_external_reference" not in _mechanisms(_scan(path))


def test_a_href_does_not_fire_external(tmp_path: Path) -> None:
    """<a href> is plain navigation, not a resource-load event."""
    path = _write_html(tmp_path, (
        '<html><body><a href="https://example.com/">link</a></body></html>'
    ))
    assert "html_external_reference" not in _mechanisms(_scan(path))


# ---------------------------------------------------------------------------
# html_data_attribute
# ---------------------------------------------------------------------------


def test_long_data_attribute_fires(tmp_path: Path) -> None:
    payload = "A" * 96  # above 64-char threshold
    path = _write_html(tmp_path, (
        f'<html><body><div data-smuggled="{payload}">x</div></body></html>'
    ))
    assert "html_data_attribute" in _mechanisms(_scan(path))


def test_short_data_attribute_does_not_fire(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        '<html><body><div data-role="button" data-id="42">x</div></body></html>'
    ))
    assert "html_data_attribute" not in _mechanisms(_scan(path))


def test_non_data_long_attribute_does_not_fire(tmp_path: Path) -> None:
    """A 96-char value on a non-``data-`` attribute is not flagged."""
    path = _write_html(tmp_path, (
        f'<html><body><div title="{"A" * 96}">x</div></body></html>'
    ))
    assert "html_data_attribute" not in _mechanisms(_scan(path))


# ---------------------------------------------------------------------------
# Zahir per-run detectors on visible text
# ---------------------------------------------------------------------------


def test_zero_width_in_visible_fires(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        "<html><body><p>hi\u200bworld</p></body></html>"
    ))
    assert "zero_width_chars" in _mechanisms(_scan(path))


def test_tag_chars_in_visible_fires(tmp_path: Path) -> None:
    payload = "".join(chr(0xE0000 + ord(c)) for c in "SECRET")
    path = _write_html(tmp_path, (
        f"<html><body><p>visible text{payload}</p></body></html>"
    ))
    assert "tag_chars" in _mechanisms(_scan(path))


def test_bidi_control_in_visible_fires(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        "<html><body><p>logic\u202Ereverse</p></body></html>"
    ))
    assert "bidi_control" in _mechanisms(_scan(path))


def test_homoglyph_in_visible_fires(tmp_path: Path) -> None:
    # Cyrillic 'а' (U+0430) inside Latin 'admin'.
    path = _write_html(tmp_path, (
        "<html><body><p>Welcome, \u0430dmin</p></body></html>"
    ))
    assert "homoglyph" in _mechanisms(_scan(path))


# ---------------------------------------------------------------------------
# Zahir detectors are NOT applied to script / style bodies
# ---------------------------------------------------------------------------


def test_zero_width_in_script_body_does_not_fire_zahir(tmp_path: Path) -> None:
    """Script bodies are batin source, not zahir text — skip the zahir
    codepoint scanners."""
    path = _write_html(tmp_path, (
        "<html><body><script>var x = 'a\u200bb';</script></body></html>"
    ))
    mechs = _mechanisms(_scan(path))
    # Inline-script fires (there is a non-empty script body); but
    # zero_width_chars should NOT fire — the scanner only walks visible
    # text.
    assert "html_inline_script" in mechs
    assert "zero_width_chars" not in mechs


def test_tag_chars_in_style_body_does_not_fire(tmp_path: Path) -> None:
    payload = "".join(chr(0xE0000 + ord(c)) for c in "HIDDEN")
    path = _write_html(tmp_path, (
        f"<html><body><style>body::after {{ content: '{payload}'; }}</style>"
        f"<p>visible</p></body></html>"
    ))
    # Style bodies are not visible text; TAG chars parked inside them
    # are not the zahir signal we're looking for. (They are still
    # present in the file and would be caught by a TextFileAnalyzer run,
    # but that is a separate witness.)
    assert "tag_chars" not in _mechanisms(_scan(path))


# ---------------------------------------------------------------------------
# Hidden text scanning still applies the zahir per-run detectors
# ---------------------------------------------------------------------------


def test_hidden_text_with_tag_payload_fires_both(tmp_path: Path) -> None:
    """Hidden text is doubly concealed: render-suppressed AND
    carrying a TAG payload. Both detectors must fire."""
    payload = "".join(chr(0xE0000 + ord(c)) for c in "PRIVATE")
    path = _write_html(tmp_path, (
        f'<html><body><p style="display:none">cover{payload}</p></body></html>'
    ))
    mechs = set(_mechanisms(_scan(path)))
    assert {"html_hidden_text", "tag_chars"}.issubset(mechs)


# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


def test_tag_payload_in_comment_fires_tag_chars(tmp_path: Path) -> None:
    payload = "".join(chr(0xE0000 + ord(c)) for c in "INJECT")
    path = _write_html(tmp_path, (
        f"<html><body><!-- cover{payload} --><p>visible</p></body></html>"
    ))
    report = _scan(path)
    assert "tag_chars" in _mechanisms(report)
    # Comment-sourced findings should carry a :comment suffix in their
    # location so a reader can tell it apart from an element-text
    # finding at a glance.
    tag_finding = next(
        f for f in report.findings if f.mechanism == "tag_chars"
    )
    assert tag_finding.location.endswith(":comment")


def test_clean_comment_does_not_fire(tmp_path: Path) -> None:
    path = _write_html(tmp_path, (
        "<html><body><!-- ordinary comment --><p>hello</p></body></html>"
    ))
    assert _scan(path).findings == []


# ---------------------------------------------------------------------------
# Malformed / robust input
# ---------------------------------------------------------------------------


def test_unclosed_tags_do_not_crash(tmp_path: Path) -> None:
    """HTMLParser is lenient; the analyzer must be too.

    The outer tags (``<html>``, ``<body>``, ``<p>``, ``<div>``) are
    never closed; the analyzer must complete the walk and still surface
    the inline-script finding from the well-formed ``<script>`` element
    nested inside the mess.
    """
    path = _write_html(tmp_path, (
        "<html><body><p>unclosed<div>mixed"
        "<script>alert(1);</script>"
    ))
    report = _scan(path)
    # Inline script still fires even though the surrounding tags are
    # never closed.
    assert "html_inline_script" in _mechanisms(report)
    assert not report.scan_incomplete


def test_non_existent_file_surfaces_scan_error(tmp_path: Path) -> None:
    path = tmp_path / "nonexistent.html"
    report = _scan(path)
    assert any(f.mechanism == "scan_error" for f in report.findings)
    assert report.scan_incomplete


def test_bytes_above_cap_are_truncated(tmp_path: Path, monkeypatch) -> None:
    """A file above _MAX_HTML_BYTES is read to the cap and still scans."""
    import analyzers.html_analyzer as ha
    # Set a small cap so the test runs quickly.
    monkeypatch.setattr(ha, "_MAX_HTML_BYTES", 256)
    # Body is 300 bytes of clean text; the trailing adversarial span
    # lives past the cap and must not be picked up.
    clean_head = (
        "<html><body><p>" + "A" * 270 + "</p>"
    )
    adversarial_tail = (
        '<p style="display:none">payload</p></body></html>'
    )
    path = _write_html(tmp_path, clean_head + adversarial_tail)
    report = _scan(path)
    # The hidden paragraph was truncated away; no finding from it.
    assert "html_hidden_text" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Muwazana score clamps correctly on combined adversarial inputs
# ---------------------------------------------------------------------------


def test_combined_adversarial_drives_score_down(tmp_path: Path) -> None:
    """An HTML document firing multiple mechanisms must score strictly
    below 1.0. This is the equal-witnesses composition test — each
    detector's severity contributes additively, no mechanism is
    privileged or silenced."""
    payload = "X" * 96
    path = _write_html(tmp_path, (
        f'<html><head>'
        f'<script src="https://evil.example.com/x.js"></script>'
        f'</head><body>'
        f'<script>alert(1);</script>'
        f'<p style="display:none">hidden</p>'
        f'<div data-smuggled="{payload}">d</div>'
        f'<button onclick="doit()">Go</button>'
        f'</body></html>'
    ))
    report = _scan(path)
    # Every intended detector fires.
    firing = set(_mechanisms(report))
    assert {
        "html_inline_script",
        "html_external_reference",
        "html_hidden_text",
        "html_data_attribute",
    }.issubset(firing)
    assert report.integrity_score < 1.0
    assert not report.scan_incomplete
