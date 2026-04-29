"""
Tier 1 detector for ``X-*`` headers carrying anomalously long values
(v1.1.2 EML format gauntlet).

RFC 6648 deprecated the ``X-`` prefix as the marker for experimental
or local-use headers, but in practice mail systems still use it for
infrastructure annotations: ``X-Mailer``, ``X-Originating-IP``,
``X-Spam-Status``, ``X-Priority``. These values are short - a mailer
name, an IP address, a numeric flag - because the header was never
intended as a long-form payload carrier. Mail clients hide the
extended header panel by default; the reader does not see X-* values.

A non-standard ``X-*`` header whose value crosses the long-header
length threshold is structurally anomalous: there is no legitimate
reason for a custom annotation to carry hundreds of characters of
text, and the surface is ideal for payload smuggling - every parser
preserves the value, no client renders it, no byte-level scanner
checks the length of values in headers it does not recognise.

Trigger: any header whose name begins with ``X-`` (case-insensitive),
is not in the legitimate-large set (vendor signatures and bulk-
infrastructure headers), whose unfolded value length is at or above
the length threshold (default 128 chars).

Closes ``eml_gauntlet`` fixture ``06_long_xheader_payload.eml``.

Distinct from ``eml_header_continuation_payload`` (which fires on
heavy fold-line counts regardless of total length) and from
``eml_smuggled_header`` (which fires on duplicate single-instance
headers and on CRLF injection).

Tier discipline: Tier 1. Trigger is a deterministic length check on
unfolded UTF-8 text; no semantic claims.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_EML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 128

# X-* header names where long values are routine and legitimate.
# These are vendor signatures, bulk-infrastructure annotations, or
# ARC/DKIM ports that legitimately carry hundreds of bytes.
_LEGITIMATE_LARGE_X_HEADERS: frozenset[str] = frozenset({
    "x-google-dkim-signature",
    "x-gm-message-state",
    "x-received",
    "x-google-smtp-source",
    "x-ms-exchange-organization-authas",
    "x-ms-exchange-crosstenant-id",
    "x-ms-exchange-transport-crosstenantheadersstamped",
    "x-ms-exchange-antispam-messagedata",
    "x-microsoft-antispam-prvs",
    "x-microsoft-antispam",
    "x-mimecast-spam-signature",
    "x-mimecast-bulk-signature",
    "x-spam-checker-version",
    "x-spam-status",
    "x-spam-report",
    "x-virus-scanned",
    "x-amazonses-outgoing",
    "x-ses-receipt",
    "x-mailgun-sending-ip",
    "x-sendgrid-eid",
    "x-mc-user",
    "x-feedback-id",
    "list-unsubscribe",
})

_HEADER_START: re.Pattern[bytes] = re.compile(
    rb"^(?P<name>[A-Za-z][A-Za-z0-9\-_]*):[ \t]?",
    re.MULTILINE,
)


def _split_headers_and_body(raw: bytes) -> bytes:
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = raw.find(sep)
        if idx >= 0:
            return raw[:idx]
    return raw


def _split_individual_headers(header_block: bytes) -> list[tuple[bytes, bytes]]:
    out: list[tuple[bytes, bytes]] = []
    matches = list(_HEADER_START.finditer(header_block))
    for idx, match in enumerate(matches):
        name = match.group("name")
        value_start = match.end()
        if idx + 1 < len(matches):
            value_end = matches[idx + 1].start()
        else:
            value_end = len(header_block)
        out.append((name, header_block[value_start:value_end]))
    return out


def detect_eml_xheader_payload(file_path: Path) -> Iterable[Finding]:
    """Surface ``X-*`` headers whose unfolded value exceeds the length
    threshold."""
    try:
        raw = file_path.read_bytes()
    except OSError:
        return

    if len(raw) > _MAX_EML_BYTES:
        raw = raw[:_MAX_EML_BYTES]

    header_block = _split_headers_and_body(raw)
    if not header_block:
        return

    pairs = _split_individual_headers(header_block)

    for name_bytes, value_bytes in pairs:
        try:
            name = name_bytes.decode("ascii", errors="replace").lower()
        except Exception:  # noqa: BLE001 - defensive
            continue

        if not name.startswith("x-"):
            continue
        if name in _LEGITIMATE_LARGE_X_HEADERS:
            continue

        try:
            value_text = value_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - defensive
            continue

        unfolded = re.sub(r"\r?\n[ \t]+", " ", value_text).strip()
        if len(unfolded) < _LENGTH_THRESHOLD:
            continue

        unfolded_preview = unfolded[:_PREVIEW_LIMIT]

        yield Finding(
            mechanism="eml_xheader_payload",
            tier=1,
            confidence=0.9,
            description=(
                f"Header {name!r} carries {len(unfolded)} characters "
                f"of unfolded value - well above the routine length "
                f"for custom X-* annotations. Mail clients hide the "
                f"extended header panel by default; X-* values do not "
                f"reach the reader. Recovered value: "
                f"{unfolded_preview!r}."
            ),
            location=f"{file_path}:header:{name}",
            surface="(X-* header not rendered to reader)",
            concealed=f"{name}: {unfolded_preview}",
            source_layer="batin",
        )


__all__ = ["detect_eml_xheader_payload"]
