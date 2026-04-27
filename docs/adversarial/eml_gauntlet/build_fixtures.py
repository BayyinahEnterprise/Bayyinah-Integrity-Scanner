"""
EML adversarial gauntlet — fixture builder.

Six concealment / spoofing techniques that v1.1.1 ``EmlAnalyzer`` does
*not* yet detect. We avoid the well-armored vectors: display-name
spoof on From/Sender/Reply-To, encoded-subject anomalies, smuggled
duplicate single-instance headers, multipart/alternative divergence,
hidden HTML content, executable / macro attachments, nested rfc822,
external references, and MIME boundary anomalies.

Surface (visible body) text mentions $1,000. Hidden payload mentions
$10,000. Same canonical contract-fraud setup.

Fixtures
--------

01 — From / Reply-To real-domain mismatch (no display-name spoof)
02 — Return-Path inconsistent with From
03 — Received chain with the last-hop domain disjoint from From's
04 — Base64-encoded text/plain body containing the payload
05 — Header-continuation smuggling (folded header carrying payload)
06 — Long X-* custom header carrying the payload as plaintext
"""

from __future__ import annotations

import base64
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

SURFACE_TEXT = (
    "Q3 financial summary - revenue grew 8% YoY to $1,000 thousand. "
    "Margins held steady. Cash position remains strong."
)
HIDDEN_PAYLOAD = (
    "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex"
)


def _write(path: Path, headers: list[tuple[str, str]], body: str) -> None:
    parts = []
    for k, v in headers:
        parts.append(f"{k}: {v}")
    parts.append("")  # blank line ends headers
    parts.append(body)
    path.write_text("\r\n".join(parts) + "\r\n", "utf-8")


def fixture_01_from_replyto_mismatch() -> tuple[Path, str]:
    """From and Reply-To are different real domains, no display-name spoof.

    EmlAnalyzer's display_name_spoof check fires only when the display
    name (the human-readable part) implies a domain different from the
    actual address. Here, no display-name games — just two different
    real domains in From and Reply-To. A reply goes to attacker-domain
    while the sender appears to be vendor-domain.
    """
    path = OUT / "01_from_replyto_mismatch.eml"
    headers = [
        ("From", "billing@trusted-vendor.example"),
        ("Reply-To", "wire-transfer@attacker-controlled.example"),
        ("To", "ap@victim-corp.example"),
        ("Subject", "Q3 invoice"),
        ("Date", "Mon, 26 Apr 2026 09:00:00 +0000"),
        ("Content-Type", "text/plain; charset=utf-8"),
    ]
    _write(path, headers, SURFACE_TEXT)
    return path, "From and Reply-To live in different real domains"


def fixture_02_returnpath_mismatch() -> tuple[Path, str]:
    """Return-Path disagrees with From.

    Return-Path is set by the receiving MTA from the SMTP MAIL FROM
    envelope. A divergence between Return-Path and From is the canonical
    sign of forged sender. EmlAnalyzer's header inspection does not
    cross-reference Return-Path against From.
    """
    path = OUT / "02_returnpath_mismatch.eml"
    headers = [
        ("Return-Path", "<bounces@attacker-bulk.example>"),
        ("From", "ceo@victim-corp.example"),
        ("To", "cfo@victim-corp.example"),
        ("Subject", "Wire authorisation - urgent"),
        ("Date", "Mon, 26 Apr 2026 09:00:00 +0000"),
        ("Content-Type", "text/plain; charset=utf-8"),
    ]
    _write(path, headers, SURFACE_TEXT)
    return path, "Return-Path domain disjoint from From domain"


def fixture_03_received_chain_anomaly() -> tuple[Path, str]:
    """Received chain whose last hop is disjoint from From domain.

    A genuine email from `vendor.example` typically shows a Received
    chain that includes the vendor's outbound MTA. Here the last hop
    is `relay.attacker.example` while From is `vendor.example`. No
    EmlAnalyzer mechanism walks the Received chain.
    """
    path = OUT / "03_received_chain_anomaly.eml"
    headers = [
        (
            "Received",
            "from relay.attacker.example "
            "(unknown [203.0.113.42]) by mx.victim-corp.example "
            "with ESMTPS id ABC123 for <ap@victim-corp.example>; "
            "Mon, 26 Apr 2026 09:00:01 +0000",
        ),
        (
            "Received",
            "from internal.attacker.example "
            "([10.0.0.5]) by relay.attacker.example "
            "with ESMTPSA id XYZ987; "
            "Mon, 26 Apr 2026 09:00:00 +0000",
        ),
        ("From", "billing@trusted-vendor.example"),
        ("To", "ap@victim-corp.example"),
        ("Subject", "Q3 invoice"),
        ("Date", "Mon, 26 Apr 2026 09:00:00 +0000"),
        ("Content-Type", "text/plain; charset=utf-8"),
    ]
    _write(path, headers, SURFACE_TEXT)
    return (
        path,
        "Last Received hop is attacker-domain; From claims vendor-domain",
    )


def fixture_04_base64_body_payload() -> tuple[Path, str]:
    """text/plain body with Content-Transfer-Encoding: base64.

    The body decodes to the surface text concatenated with the hidden
    payload. EmlAnalyzer reads the decoded body for HTML hidden-text
    checks but does not run a corpus-divergence / payload check on the
    decoded plaintext body, so an attacker who hides a long payload
    inside a base64 plaintext block escapes detection.
    """
    path = OUT / "04_base64_body_payload.eml"
    raw_body = (
        f"{SURFACE_TEXT}\r\n\r\n"
        f"{HIDDEN_PAYLOAD}\r\n"
    )
    encoded = base64.b64encode(raw_body.encode("utf-8")).decode("ascii")
    # break into 76-char lines per RFC 2045
    encoded_lines = "\r\n".join(
        encoded[i:i + 76] for i in range(0, len(encoded), 76)
    )
    headers = [
        ("From", "billing@vendor.example"),
        ("To", "ap@victim-corp.example"),
        ("Subject", "Q3 invoice"),
        ("Date", "Mon, 26 Apr 2026 09:00:00 +0000"),
        ("Content-Type", "text/plain; charset=utf-8"),
        ("Content-Transfer-Encoding", "base64"),
    ]
    _write(path, headers, encoded_lines)
    return path, "Base64-encoded plaintext body containing the payload"


def fixture_05_header_continuation_smuggle() -> tuple[Path, str]:
    """Long X-* header folded across many lines containing the payload.

    RFC 5322 allows header values to be folded with CRLF + whitespace
    continuation. A header field whose value spans many continuation
    lines and contains a long natural-language payload is invisible to
    most mail UIs (they show the first line only) and uninspected by
    EmlAnalyzer.
    """
    path = OUT / "05_header_continuation_smuggle.eml"
    payload_repeat = (HIDDEN_PAYLOAD + " ") * 4
    # Fold across multiple continuation lines (CRLF then SPACE)
    folded = payload_repeat.replace(" ", "\r\n ")
    headers = [
        ("From", "ops@vendor.example"),
        ("To", "ap@victim-corp.example"),
        ("Subject", "Q3 invoice"),
        ("Date", "Mon, 26 Apr 2026 09:00:00 +0000"),
        ("X-Custom-Note", folded),
        ("Content-Type", "text/plain; charset=utf-8"),
    ]
    _write(path, headers, SURFACE_TEXT)
    return path, "Folded X-Custom-Note header smuggling the payload"


def fixture_06_long_xheader_payload() -> tuple[Path, str]:
    """Plain (unfolded) X-Originating-Note containing the payload.

    Variants of the above without folding — a single-line X-* header
    field whose value is a multi-hundred-character payload. Common
    real-world abuse shape (X-Spam-Status, X-Originating-IP have been
    historical exfil channels). EmlAnalyzer iterates a fixed allowlist
    of headers and ignores the rest.
    """
    path = OUT / "06_long_xheader_payload.eml"
    payload = HIDDEN_PAYLOAD * 3  # ~120 chars
    headers = [
        ("From", "ops@vendor.example"),
        ("To", "ap@victim-corp.example"),
        ("Subject", "Q3 invoice"),
        ("Date", "Mon, 26 Apr 2026 09:00:00 +0000"),
        ("X-Originating-Note", payload),
        ("Content-Type", "text/plain; charset=utf-8"),
    ]
    _write(path, headers, SURFACE_TEXT)
    return path, "Long X-Originating-Note header with payload as plaintext"


BUILDERS = [
    fixture_01_from_replyto_mismatch,
    fixture_02_returnpath_mismatch,
    fixture_03_received_chain_anomaly,
    fixture_04_base64_body_payload,
    fixture_05_header_continuation_smuggle,
    fixture_06_long_xheader_payload,
]


if __name__ == "__main__":
    for builder in BUILDERS:
        path, desc = builder()
        size = path.stat().st_size
        print(f"{path.name:<42} {size:>7} bytes  - {desc}")
