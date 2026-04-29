"""
Tier 2 detector for routing-envelope mismatch between the ``Return-Path``
and ``From`` headers (v1.1.2 EML format gauntlet).

``Return-Path`` is set by the receiving mail server from the SMTP
``MAIL FROM`` command - it captures the bounce-handling address the
sending machine asserted at the envelope layer. ``From`` is what the
mail client renders to the reader. When the two domains diverge, the
SMTP envelope was authored by one infrastructure
(``Return-Path: <bounces@attacker-bulk.example>``) while the visible
sender claims a different one (``From: ceo@victim-corp.example``).

The reader never sees ``Return-Path``. Mail servers and reputation
systems do. This is structural concealment of prior-state routing -
the sending machine PERFORMS one identity to other machines and a
different one to the human reader. Batin layer: the surface is hidden
from the reader by default.

Trigger: ``Return-Path`` is present, ``From`` is present, both parse
to syntactically valid addresses, and the lower-cased domain past the
final ``@`` differs.

Closes ``eml_gauntlet`` fixture ``02_returnpath_mismatch.eml``.

Tier discipline: Tier 2 structural. Domain comparison is byte-
deterministic; the interpretation (CEO-fraud / spoofed-envelope /
bulk-mailer impersonation) is not made by this detector.
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


def detect_eml_returnpath_from_mismatch(file_path: Path) -> Iterable[Finding]:
    """Surface ``Return-Path`` / ``From`` domain divergence."""
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

    return_path_value = msg.get("Return-Path")
    from_value = msg.get("From")
    if not return_path_value or not from_value:
        return

    # Return-Path is wrapped in <...> per RFC 5321; parseaddr handles it.
    try:
        _, return_path_addr = email.utils.parseaddr(str(return_path_value))
    except Exception:  # noqa: BLE001 - defensive
        return
    try:
        _, from_addr = email.utils.parseaddr(str(from_value))
    except Exception:  # noqa: BLE001 - defensive
        return

    if not return_path_addr or not from_addr:
        return

    return_domain = _domain_of(return_path_addr)
    from_domain = _domain_of(from_addr)
    if not return_domain or not from_domain:
        return

    if return_domain == from_domain:
        return

    surface_preview = str(from_value)[:_PREVIEW_LIMIT]
    concealed_preview = str(return_path_value)[:_PREVIEW_LIMIT]

    yield Finding(
        mechanism="eml_returnpath_from_mismatch",
        tier=2,
        confidence=0.9,
        description=(
            f"Return-Path domain {return_domain!r} differs from From "
            f"domain {from_domain!r}. The mail client renders "
            f"{from_addr!r} to the reader; the SMTP envelope and bounce "
            f"handling route through {return_path_addr!r}. Mail servers "
            f"and reputation systems see one identity, the human reader "
            f"sees another - structural concealment of prior-state "
            f"routing at the envelope layer."
        ),
        location=f"{file_path}:header:return-path",
        surface=f"From: {surface_preview}",
        concealed=f"Return-Path: {concealed_preview}",
        source_layer="batin",
    )


__all__ = ["detect_eml_returnpath_from_mismatch"]
