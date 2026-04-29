"""
Tier 2 detector for sender-identity mismatch between the ``From`` and
``Reply-To`` headers (v1.1.2 EML format gauntlet).

The reader of an email perceives a single "sender" - whatever the mail
client renders prominently next to the message in the inbox. RFC 5322
permits a separate ``Reply-To`` header that silently redirects every
reply to a different mailbox. When the two domains diverge, the message
performs trust toward one party (``From: billing@trusted-vendor.example``)
while the recipient's reply lands somewhere else
(``Reply-To: wire-transfer@attacker-controlled.example``). The reader
sees one routing story; their replies follow another.

This is the exact 2:14 shape at the envelope surface: one surface to
the believer, another to the chiefs of disbelief. Sender identity is
the rendered surface readers act on, so the mechanism sits in the
zahir layer.

Trigger: ``From`` and ``Reply-To`` are both present, both parse to a
syntactically valid address, and the registered domain (the e-mail
domain past the ``@``, lower-cased) of ``Reply-To`` differs from the
registered domain of ``From``. Pure-prefix differences inside the same
domain (``billing@vendor.example`` vs ``replies@vendor.example``) do
not fire.

Closes ``eml_gauntlet`` fixture ``01_from_replyto_mismatch.eml``.

Tier discipline: Tier 2 structural. The trigger is a deterministic
domain-comparison; the *interpretation* (this is phishing) is not made
by this detector - it surfaces the structural divergence and lets the
report assemble the picture.
"""
from __future__ import annotations

import email
import email.policy
import email.utils
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_EML_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240


def _domain_of(address: str) -> str:
    """Lower-cased registered domain (everything after the last ``@``)."""
    if "@" not in address:
        return ""
    return address.rsplit("@", 1)[1].strip().lower().rstrip(">")


def detect_eml_from_replyto_mismatch(file_path: Path) -> Iterable[Finding]:
    """Surface ``From`` / ``Reply-To`` domain divergence."""
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

    from_value = msg.get("From")
    replyto_value = msg.get("Reply-To")
    if not from_value or not replyto_value:
        return

    try:
        _, from_addr = email.utils.parseaddr(str(from_value))
    except Exception:  # noqa: BLE001 - defensive on malformed values
        return
    try:
        _, replyto_addr = email.utils.parseaddr(str(replyto_value))
    except Exception:  # noqa: BLE001 - defensive on malformed values
        return

    if not from_addr or not replyto_addr:
        return

    from_domain = _domain_of(from_addr)
    replyto_domain = _domain_of(replyto_addr)
    if not from_domain or not replyto_domain:
        return

    if from_domain == replyto_domain:
        return

    surface_preview = str(from_value)[:_PREVIEW_LIMIT]
    concealed_preview = str(replyto_value)[:_PREVIEW_LIMIT]

    yield Finding(
        mechanism="eml_from_replyto_mismatch",
        tier=2,
        confidence=0.9,
        description=(
            f"Reply-To domain {replyto_domain!r} differs from From "
            f"domain {from_domain!r}. The reader's mail client renders "
            f"{from_addr!r} as the sender; replies are silently routed "
            f"to {replyto_addr!r}. Performed-alignment shape at the "
            f"envelope surface - one routing story for the reader, "
            f"another for their replies."
        ),
        location=f"{file_path}:header:reply-to",
        surface=f"From: {surface_preview}",
        concealed=f"Reply-To: {concealed_preview}",
        source_layer="zahir",
    )


__all__ = ["detect_eml_from_replyto_mismatch"]
