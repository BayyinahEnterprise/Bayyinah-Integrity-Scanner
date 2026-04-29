"""
Tier 1 detector for ``base64`` transfer-encoding applied to a plain-text
part (v1.1.2 EML format gauntlet).

RFC 2045 §6 distinguishes ``Content-Transfer-Encoding`` mechanisms by
their intended purpose: ``7bit`` and ``8bit`` for already-safe text,
``quoted-printable`` for mostly-ASCII text with occasional 8-bit
characters, ``base64`` for binary data that would otherwise be
mangled by mail relays. Plain text bodies overwhelmingly travel as
``7bit`` or ``quoted-printable``; the rare exceptions are non-Latin
scripts where every byte is non-ASCII.

Wrapping a routine ``text/plain`` body in ``base64`` is a documented
content-scanner evasion: byte-level keyword filters that look for
``HIDDEN_TEXT_PAYLOAD``, ``actual revenue``, wire-instructions, or any
other red-flag string read the encoded base64 alphabet and miss the
payload entirely. The reader's mail client decodes the base64 and
renders the full body to them - the human surface is intact, the
filter's surface is a wall of opaque base64.

This is the exact 2:42 shape at the body-encoding layer: do not mix
truth with falsehood, nor conceal the truth while you know it. The
surface a scanner reads is base64; the surface a human reads is the
decoded text.

Trigger: the message has at least one ``text/*`` MIME part whose
``Content-Transfer-Encoding`` is ``base64``. Surface: the raw base64
bytes (what byte-level scanners read). Concealed: the decoded text
(preview-truncated). Recovered text intentionally includes any
payload markers in the decoded body so the report's correlation
engine can link this to other format-gauntlet findings.

Closes ``eml_gauntlet`` fixture ``04_base64_body_payload.eml``.

Tier discipline: Tier 1. Trigger is a deterministic header check;
recovery is a deterministic base64 decode. No semantic claims.
"""
from __future__ import annotations

import email
import email.policy
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_EML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240


def _walk_text_parts(msg):
    """Iterate over every ``text/*`` MIME part in the message tree."""
    if msg.is_multipart():
        for part in msg.walk():
            if part is msg:
                continue
            ctype = part.get_content_type() or ""
            if ctype.startswith("text/") and not part.is_multipart():
                yield part
    else:
        ctype = msg.get_content_type() or ""
        if ctype.startswith("text/"):
            yield msg


def detect_eml_base64_text_part(file_path: Path) -> Iterable[Finding]:
    """Surface ``text/*`` parts encoded as ``base64``."""
    try:
        raw = file_path.read_bytes()
    except OSError:
        return

    if len(raw) > _MAX_EML_BYTES:
        raw = raw[:_MAX_EML_BYTES]

    try:
        msg = email.message_from_bytes(raw, policy=email.policy.default)
    except Exception:  # noqa: BLE001 - defensive
        return

    for part in _walk_text_parts(msg):
        cte = (part.get("Content-Transfer-Encoding") or "").strip().lower()
        if cte != "base64":
            continue

        ctype = part.get_content_type() or "text/plain"

        # Decode the body. ``get_payload(decode=True)`` returns bytes if
        # the encoding is recognised; permissive decode to UTF-8 text.
        try:
            decoded_bytes = part.get_payload(decode=True) or b""
        except Exception:  # noqa: BLE001 - defensive
            decoded_bytes = b""
        try:
            decoded_text = decoded_bytes.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - defensive
            decoded_text = ""

        # Raw base64 surface (what a byte-level scanner would read).
        try:
            raw_payload = part.get_payload(decode=False) or ""
        except Exception:  # noqa: BLE001 - defensive
            raw_payload = ""
        if isinstance(raw_payload, list):
            raw_payload = ""

        surface_preview = str(raw_payload)[:_PREVIEW_LIMIT]
        decoded_preview = decoded_text[:_PREVIEW_LIMIT]

        yield Finding(
            mechanism="eml_base64_text_part",
            tier=1,
            confidence=0.95,
            description=(
                f"Part {ctype!r} carries Content-Transfer-Encoding: "
                f"base64. Plain-text bodies routinely travel as 7bit or "
                f"quoted-printable; base64 wrapping on a text part is a "
                f"documented content-scanner evasion - byte-level "
                f"keyword filters read the encoded alphabet and miss "
                f"the payload, while the reader's mail client decodes "
                f"and renders the full body. Recovered text: "
                f"{decoded_preview!r}."
            ),
            location=f"{file_path}:part:{ctype}",
            surface=f"base64 body: {surface_preview}",
            concealed=f"decoded body: {decoded_preview}",
            source_layer="zahir",
        )


__all__ = ["detect_eml_base64_text_part"]
