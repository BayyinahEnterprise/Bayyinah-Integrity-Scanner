"""
Tests for analyzers.eml_analyzer.EmlAnalyzer.

Phase 19 guardrails. EmlAnalyzer is a dual witness — batin (duplicate /
CRLF-injected headers, executable / macro attachments, nested
message/rfc822 attachments, MIME boundary anomalies, external remote
references) and zahir (multipart/alternative plain-vs-html divergence,
hidden HTML body content, display-name spoofing, RFC 2047
encoded-subject concealment). Each detector has a targeted unit test
that builds minimal .eml bytes in ``tmp_path`` and scans it.

The builders here are intentionally separate from
``tests/make_eml_fixtures.py``. That module produces the committed
fixture corpus; these tests build one-off bytes per test so each
detector can be exercised in isolation with clean pass/fail semantics.

Mirrors the structure of ``tests/analyzers/test_pptx_analyzer.py``
and ``tests/analyzers/test_xlsx_analyzer.py``.

Al-Baqarah 2:42: "Do not mix truth with falsehood, nor conceal the
truth while you know it." Each per-detector test is a single
pretend-truth / real-truth pair — the analyzer's job is to surface
the second when the first is performed.
"""

from __future__ import annotations

import base64
from pathlib import Path

from analyzers import EmlAnalyzer
from analyzers.base import BaseAnalyzer
from domain import IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(EmlAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert EmlAnalyzer.name == "eml"
    assert EmlAnalyzer.error_prefix == "EML scan error"
    # Class-level source_layer is batin for scan_error attribution.
    # Per-finding source_layer is set explicitly on each detector.
    assert EmlAnalyzer.source_layer == "batin"


def test_supported_kinds_is_eml_only() -> None:
    assert EmlAnalyzer.supported_kinds == frozenset({FileKind.EML})


# ---------------------------------------------------------------------------
# Byte-construction helpers
# ---------------------------------------------------------------------------

CRLF = b"\r\n"


def _eml(*lines: str | bytes) -> bytes:
    out: list[bytes] = []
    for line in lines:
        if isinstance(line, str):
            out.append(line.encode("utf-8"))
        else:
            out.append(line)
    return CRLF.join(out)


def _write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def _mechanisms(report: IntegrityReport) -> set[str]:
    return {f.mechanism for f in report.findings}


# ---------------------------------------------------------------------------
# Clean — nothing fires
# ---------------------------------------------------------------------------


def test_clean_plain_text_scores_1(tmp_path: Path) -> None:
    data = _eml(
        "From: alice@example.com",
        "To: bob@example.com",
        "Subject: plain",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Nothing unusual here at all.",
        "",
    )
    path = _write(tmp_path, "clean.eml", data)
    report = EmlAnalyzer().scan(path)
    assert report.findings == []
    assert report.integrity_score == 1.0
    assert not report.scan_incomplete


# ---------------------------------------------------------------------------
# Zahir — multipart/alternative divergence
# ---------------------------------------------------------------------------


def test_multipart_alternative_divergence_fires(tmp_path: Path) -> None:
    boundary = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: alt",
        "MIME-Version: 1.0",
        f"Content-Type: multipart/alternative; boundary={boundary}",
        "",
        f"--{boundary}",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Routine quarterly summary normal reporting nothing unusual today.",
        "",
        f"--{boundary}",
        "Content-Type: text/html; charset=utf-8",
        "",
        (
            "<html><body>URGENT your account compromised suspended blocked "
            "verify credentials password banking details confirm "
            "immediately before cancellation.</body></html>"
        ),
        "",
        f"--{boundary}--",
        "",
    )
    path = _write(tmp_path, "alt.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_multipart_alternative_divergence" in _mechanisms(report)


def test_multipart_alternative_equivalent_silent(tmp_path: Path) -> None:
    boundary = "BBBBBBBBBBBBBBBBBBBBBBBBBBBBBB"
    shared = (
        "The project is on track for the April milestone the testing "
        "phase completed and the team is reviewing results this week."
    )
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: alt clean",
        "MIME-Version: 1.0",
        f"Content-Type: multipart/alternative; boundary={boundary}",
        "",
        f"--{boundary}",
        "Content-Type: text/plain; charset=utf-8",
        "",
        shared,
        "",
        f"--{boundary}",
        "Content-Type: text/html; charset=utf-8",
        "",
        f"<html><body><p>{shared}</p></body></html>",
        "",
        f"--{boundary}--",
        "",
    )
    path = _write(tmp_path, "alt_clean.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_multipart_alternative_divergence" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Zahir — hidden HTML content
# ---------------------------------------------------------------------------


def test_hidden_html_display_none_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: newsletter",
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        (
            "<html><body>"
            "<p>Visible header.</p>"
            "<span style=\"display:none\">hidden prompt override.</span>"
            "<p>Visible footer.</p>"
            "</body></html>"
        ),
        "",
    )
    path = _write(tmp_path, "hidden.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_hidden_html_content" in _mechanisms(report)


def test_hidden_html_attribute_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: newsletter",
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        (
            "<html><body>"
            "<p>Visible header.</p>"
            "<div hidden>hidden prompt override.</div>"
            "<p>Visible footer.</p>"
            "</body></html>"
        ),
        "",
    )
    path = _write(tmp_path, "hidden2.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_hidden_html_content" in _mechanisms(report)


def test_clean_html_body_no_hidden(tmp_path: Path) -> None:
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: newsletter",
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        "<html><body><p>Visible only.</p></body></html>",
        "",
    )
    path = _write(tmp_path, "clean_html.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_hidden_html_content" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Zahir — display-name spoofing
# ---------------------------------------------------------------------------


def test_display_name_spoof_brand_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: \"Bank Support\" <attacker@evil.example>",
        "To: b@c.com",
        "Subject: verify",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Please verify your account.",
        "",
    )
    path = _write(tmp_path, "spoof_brand.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_display_name_spoof" in _mechanisms(report)


def test_display_name_spoof_embedded_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: \"support@trusted.example\" <attacker@evil.example>",
        "To: b@c.com",
        "Subject: follow-up",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "We received your inquiry.",
        "",
    )
    path = _write(tmp_path, "spoof_embed.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_display_name_spoof" in _mechanisms(report)


def test_display_name_matching_domain_no_spoof(tmp_path: Path) -> None:
    """Display name contains a brand keyword but the actual domain IS
    derived from that brand — no spoof."""
    data = _eml(
        "From: \"Google Security\" <noreply@google.com>",
        "To: b@c.com",
        "Subject: ordinary",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "This is an ordinary message from the real domain.",
        "",
    )
    path = _write(tmp_path, "legit.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_display_name_spoof" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Zahir — RFC 2047 encoded-subject anomalies
# ---------------------------------------------------------------------------


def _encoded_word_subject(text: str) -> str:
    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    return f"=?UTF-8?B?{encoded}?="


def test_encoded_subject_zero_width_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        f"Subject: {_encoded_word_subject('Hello' + chr(0x200B) + 'world')}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "body.",
        "",
    )
    path = _write(tmp_path, "enc_zw.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_encoded_subject_anomaly" in _mechanisms(report)


def test_encoded_subject_bidi_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        f"Subject: {_encoded_word_subject('invoice' + chr(0x202E) + 'fdp.doc')}",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "body.",
        "",
    )
    path = _write(tmp_path, "enc_bidi.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_encoded_subject_anomaly" in _mechanisms(report)


def test_plain_ascii_subject_no_encoded_anomaly(tmp_path: Path) -> None:
    """An unencoded subject — even if it contained unusual codepoints —
    does NOT fire this detector. The mechanism is specifically about
    the encoded-word carrier shape, not general subject concealment."""
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: Ordinary ASCII subject line",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "body.",
        "",
    )
    path = _write(tmp_path, "plain_subject.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_encoded_subject_anomaly" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — executable / macro attachments
# ---------------------------------------------------------------------------


def _build_attachment_eml(filename: str, mime: str) -> bytes:
    boundary = "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCC"
    payload = b"PLACEHOLDER_ATTACHMENT_" * 4
    b64 = base64.b64encode(payload).decode("ascii")
    b64_lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    return _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: attachments",
        "MIME-Version: 1.0",
        f"Content-Type: multipart/mixed; boundary={boundary}",
        "",
        f"--{boundary}",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "See attached.",
        "",
        f"--{boundary}",
        f"Content-Type: {mime}; name=\"{filename}\"",
        "Content-Transfer-Encoding: base64",
        f"Content-Disposition: attachment; filename=\"{filename}\"",
        "",
        *b64_lines,
        "",
        f"--{boundary}--",
        "",
    )


def test_executable_attachment_fires(tmp_path: Path) -> None:
    data = _build_attachment_eml("malicious.exe", "application/octet-stream")
    path = _write(tmp_path, "exe.eml", data)
    report = EmlAnalyzer().scan(path)
    mechs = _mechanisms(report)
    assert "eml_executable_attachment" in mechs
    assert "eml_attachment_present" in mechs


def test_macro_attachment_fires(tmp_path: Path) -> None:
    data = _build_attachment_eml(
        "report.docm",
        "application/vnd.ms-word.document.macroEnabled.12",
    )
    path = _write(tmp_path, "macro.eml", data)
    report = EmlAnalyzer().scan(path)
    mechs = _mechanisms(report)
    assert "eml_macro_attachment" in mechs
    assert "eml_attachment_present" in mechs


def test_benign_attachment_only_fires_attachment_present(tmp_path: Path) -> None:
    """A .txt attachment is routine — only the interpretive
    ``eml_attachment_present`` should surface, not the executable /
    macro classes."""
    data = _build_attachment_eml("notes.txt", "text/plain")
    path = _write(tmp_path, "txt.eml", data)
    report = EmlAnalyzer().scan(path)
    mechs = _mechanisms(report)
    assert "eml_attachment_present" in mechs
    assert "eml_executable_attachment" not in mechs
    assert "eml_macro_attachment" not in mechs


# ---------------------------------------------------------------------------
# Batin — external reference
# ---------------------------------------------------------------------------


def test_external_reference_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: tracker",
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        (
            "<html><body>"
            "<p>Hello.</p>"
            "<img src=\"http://evil.example/pixel.gif\" width=\"1\">"
            "</body></html>"
        ),
        "",
    )
    path = _write(tmp_path, "ext.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_external_reference" in _mechanisms(report)


def test_local_ref_no_external_fire(tmp_path: Path) -> None:
    """A relative / cid: reference is intra-message; no external fire."""
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: cid",
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        (
            "<html><body>"
            "<img src=\"cid:embedded-logo@example.com\" width=\"1\">"
            "</body></html>"
        ),
        "",
    )
    path = _write(tmp_path, "cid.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_external_reference" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — smuggled / duplicate headers
# ---------------------------------------------------------------------------


def test_duplicate_from_header_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: alice@trusted.example",
        "From: mallory@evil.example",
        "To: c@d.com",
        "Subject: dup",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "body.",
        "",
    )
    path = _write(tmp_path, "dup.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_smuggled_header" in _mechanisms(report)


def test_received_header_not_single_instance(tmp_path: Path) -> None:
    """Received: IS legitimately multi-occurrence — must not fire."""
    data = _eml(
        "Received: from m1 by m2 id 1",
        "Received: from m2 by m3 id 2",
        "Received: from m3 by m4 id 3",
        "From: alice@example.com",
        "To: c@d.com",
        "Subject: routing",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "body.",
        "",
    )
    path = _write(tmp_path, "received.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_smuggled_header" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Batin — nested message/rfc822
# ---------------------------------------------------------------------------


def test_nested_eml_attachment_fires(tmp_path: Path) -> None:
    inner = _eml(
        "From: x@y.com",
        "To: z@w.com",
        "Subject: inner",
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "inner body.",
        "",
    )
    boundary = "DDDDDDDDDDDDDDDDDDDDDDDDDDDDDD"
    outer = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: fwd",
        "MIME-Version: 1.0",
        f"Content-Type: multipart/mixed; boundary={boundary}",
        "",
        f"--{boundary}",
        "Content-Type: text/plain; charset=utf-8",
        "",
        "Forwarded.",
        "",
        f"--{boundary}",
        "Content-Type: message/rfc822",
        "Content-Disposition: attachment; filename=\"inner.eml\"",
        "",
        "",
    ) + inner + _eml(
        "",
        f"--{boundary}--",
        "",
    )
    path = _write(tmp_path, "nested.eml", outer)
    report = EmlAnalyzer().scan(path)
    mechs = _mechanisms(report)
    assert "eml_nested_eml" in mechs
    assert "eml_attachment_present" in mechs


# ---------------------------------------------------------------------------
# Batin — MIME boundary anomalies
# ---------------------------------------------------------------------------


def test_short_boundary_fires(tmp_path: Path) -> None:
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: short",
        "MIME-Version: 1.0",
        "Content-Type: multipart/mixed; boundary=XY",
        "",
        "--XY",
        "Content-Type: text/plain",
        "",
        "first.",
        "",
        "--XY",
        "Content-Type: text/plain",
        "",
        "second.",
        "",
        "--XY--",
        "",
    )
    path = _write(tmp_path, "short.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_mime_boundary_anomaly" in _mechanisms(report)


def test_legitimate_boundary_no_anomaly(tmp_path: Path) -> None:
    boundary = "LEGITIMATE_RANDOM_BOUNDARY_THIRTY_CHARS"
    data = _eml(
        "From: a@b.com",
        "To: c@d.com",
        "Subject: normal",
        "MIME-Version: 1.0",
        f"Content-Type: multipart/mixed; boundary={boundary}",
        "",
        f"--{boundary}",
        "Content-Type: text/plain",
        "",
        "first.",
        "",
        f"--{boundary}--",
        "",
    )
    path = _write(tmp_path, "normal.eml", data)
    report = EmlAnalyzer().scan(path)
    assert "eml_mime_boundary_anomaly" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_file_returns_scan_error(tmp_path: Path) -> None:
    report = EmlAnalyzer().scan(tmp_path / "does_not_exist.eml")
    assert report.scan_incomplete
    assert any(f.mechanism == "scan_error" for f in report.findings)


def test_empty_file_is_not_crash(tmp_path: Path) -> None:
    path = _write(tmp_path, "empty.eml", b"")
    report = EmlAnalyzer().scan(path)
    # Either a scan_error or simply zero findings — the contract is
    # "don't crash and don't silently mark a file clean when it's
    # actually unparseable". An empty string is technically a valid
    # (trivial) RFC 5322 message per python's email lib, so zero
    # findings is acceptable; the key is no exception.
    assert isinstance(report, IntegrityReport)
