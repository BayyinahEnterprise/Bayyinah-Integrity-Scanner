"""
Tier 1 detector for RFC 5322 folded-continuation lines used to smuggle
payload text inside a header (v1.1.2 EML format gauntlet).

RFC 5322 §2.2.3 lets a header value continue across multiple lines by
ending each line with CRLF and starting the next with whitespace
(``CRLF SP`` or ``CRLF HT``). The folded form is collapsed by every
RFC-compliant parser when the value is read - the mail client never
shows folded continuations to the reader, the user-visible header
panel renders only first-line summaries, and most byte-level scanners
read the raw bytes line-by-line and never reassemble the unfolded
value. The result is a header surface where many lines of payload
text can hide behind a routine-looking first line.

Routine header folding produces 1-2 continuations on long structured
headers (DKIM-Signature, ARC-*, Received). A header carrying six or
more folded continuation lines, or whose joined post-fold value
exceeds the long-header length threshold, is structurally anomalous -
the shape exists to PERFORM brevity to the byte-level scanner while
the value the parser actually delivers carries a payload.

Trigger: any header (other than the legitimate-large set:
DKIM-Signature, ARC-Seal, ARC-Message-Signature,
ARC-Authentication-Results, Authentication-Results, Received,
Received-SPF) whose raw form contains six or more CRLF+WSP fold
sequences.

Closes ``eml_gauntlet`` fixture ``05_header_continuation_smuggle.eml``.

Distinct from ``eml_smuggled_header`` (which fires on duplicate
single-instance headers and on bare CRLF without WSP - i.e. CRLF
injection rather than legitimate folding).

Tier discipline: Tier 1. Trigger is a byte count of CRLF+WSP
sequences inside the raw header block; no semantic interpretation.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_EML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_FOLD_THRESHOLD: int = 6

# Headers where heavy folding is legitimate and routine.
_LEGITIMATE_LARGE_HEADERS: frozenset[str] = frozenset({
    "dkim-signature",
    "arc-seal",
    "arc-message-signature",
    "arc-authentication-results",
    "authentication-results",
    "received",
    "received-spf",
    "x-google-dkim-signature",
})

# A header line begins with ``Name: ...`` at column 0 of a line.
# Continuation lines start with whitespace.
_HEADER_START: re.Pattern[bytes] = re.compile(
    rb"^(?P<name>[A-Za-z][A-Za-z0-9\-_]*):[ \t]?",
    re.MULTILINE,
)


def _split_headers_and_body(raw: bytes) -> bytes:
    """Return the raw header block (everything before the first blank
    line). Handles both CRLF and LF line terminators."""
    # The header/body separator is a blank line (CRLF CRLF or LF LF).
    for sep in (b"\r\n\r\n", b"\n\n"):
        idx = raw.find(sep)
        if idx >= 0:
            return raw[:idx]
    return raw


def _split_individual_headers(header_block: bytes) -> list[tuple[bytes, bytes]]:
    """Split header block into ``(name, raw-value-with-folds)`` pairs.

    The raw-value preserves CRLF and WSP so we can count folds.
    """
    # Normalise to CRLF for consistent counting; track CRLF and LF.
    out: list[tuple[bytes, bytes]] = []
    matches = list(_HEADER_START.finditer(header_block))
    for idx, match in enumerate(matches):
        name = match.group("name")
        value_start = match.end()
        if idx + 1 < len(matches):
            value_end = matches[idx + 1].start()
        else:
            value_end = len(header_block)
        value = header_block[value_start:value_end]
        out.append((name, value))
    return out


def detect_eml_header_continuation_payload(file_path: Path) -> Iterable[Finding]:
    """Surface headers whose folded continuation depth exceeds the
    structural threshold."""
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

        if name in _LEGITIMATE_LARGE_HEADERS:
            continue

        # Count CRLF+WSP and LF+WSP fold sequences inside the value.
        crlf_folds = len(re.findall(rb"\r\n[ \t]", value_bytes))
        lf_folds = len(re.findall(rb"(?<!\r)\n[ \t]", value_bytes))
        fold_count = crlf_folds + lf_folds

        if fold_count < _FOLD_THRESHOLD:
            continue

        # Decode the value for preview / recovery.
        try:
            value_text = value_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - defensive
            value_text = ""
        # Unfolded form (what a parser delivers).
        unfolded = re.sub(r"\r?\n[ \t]+", " ", value_text).strip()
        unfolded_preview = unfolded[:_PREVIEW_LIMIT]
        first_line = value_text.splitlines()[0] if value_text else ""
        first_line_preview = first_line.strip()[:_PREVIEW_LIMIT]

        yield Finding(
            mechanism="eml_header_continuation_payload",
            tier=1,
            confidence=0.9,
            description=(
                f"Header {name!r} carries {fold_count} folded "
                f"continuation lines - well above the routine fold "
                f"depth for non-DKIM/ARC/Received headers. The mail "
                f"client renders only the first-line summary; most "
                f"byte-level scanners read raw lines and never "
                f"reassemble the unfolded value. Unfolded value: "
                f"{unfolded_preview!r}."
            ),
            location=f"{file_path}:header:{name}",
            surface=f"{name}: {first_line_preview}",
            concealed=(
                f"{fold_count} fold continuations; unfolded value: "
                f"{unfolded_preview}"
            ),
            source_layer="batin",
        )


__all__ = ["detect_eml_header_continuation_payload"]
