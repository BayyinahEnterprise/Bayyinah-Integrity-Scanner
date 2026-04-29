"""
Tier 2 / Tier 1 detector for PNG private ancillary chunks carrying
readable text payload (v1.1.2 image format gauntlet).

PNG chunk types follow a four-byte naming convention defined in RFC
2083:

  - First byte case: uppercase = critical, lowercase = ancillary.
  - Second byte case: uppercase = public, lowercase = private.
  - Third byte case: reserved (always uppercase).
  - Fourth byte case: uppercase = unsafe to copy, lowercase = safe.

A private ancillary chunk (lowercase first byte AND lowercase second
byte) is documented PNG infrastructure for vendor-specific metadata.
A photography application embedding lens-correction data, a print
driver embedding plate calibration, or an image editor embedding
non-standard layer state are all legitimate uses. The structural fact
"private chunk with readable text" therefore is notable but not
proof of concealment.

This mechanism emits two distinct signals:

  Tier 2 baseline: any private ancillary chunk whose data decodes to
    UTF-8 with at least 32 bytes of printable text at high density
    fires a Tier 2 finding. The Tier 2 baseline is the structural
    notability ("private chunk with payload-shaped readable text not
    matching a known vendor namespace").

  Tier 1 escalation: when the private chunk's text additionally
    exhibits any of three concealment triggers (parallel to
    pdf_metadata_analyzer's four-trigger pattern), a per-trigger
    Tier 1 finding is emitted alongside the Tier 2 baseline:

      - bidi: text contains a bidirectional override codepoint
        (U+202A through U+202E or U+2066 through U+2069).
      - zero_width: text contains a zero-width character (U+200B,
        U+200C, U+200D, or U+FEFF).
      - length: text exceeds the long-payload metadata threshold
        (1024 bytes).

    Each trigger emits its own Tier 1 finding so the report carries
    one finding per concealment shape per chunk.

Closes ``image_gauntlet`` fixture ``02_png_private_chunk.png``.

Distinct from ``suspicious_image_chunk`` (existing v1.1.1 finding
which fires on critical chunks only, missing private ancillary
chunks entirely) and from ``image_text_metadata`` (which scans the
public ancillary text chunks tEXt / iTXt / zTXt only).

Tier discipline: Tier 2 baseline + per-trigger Tier 1 escalation.
The Tier 2 finding is structural ("private chunk with readable
text"); the Tier 1 findings are byte-deterministic concealment
signals.
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_IMAGE_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 32
_PRINTABLE_DENSITY: float = 0.7
_LONG_PAYLOAD_THRESHOLD: int = 1024

_PNG_SIGNATURE: bytes = b"\x89PNG\r\n\x1a\n"

# Bidirectional override and isolate codepoints.
_BIDI_CODEPOINTS: frozenset[str] = frozenset(
    chr(cp) for cp in (
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
        0x2066, 0x2067, 0x2068, 0x2069,
    )
)

# Zero-width characters used for concealment.
_ZERO_WIDTH_CHARS: frozenset[str] = frozenset(
    chr(cp) for cp in (0x200B, 0x200C, 0x200D, 0xFEFF)
)


def _iter_png_chunks(
    data: bytes,
) -> Iterable[tuple[bytes, bytes, int]]:
    """Yield ``(chunk_type, chunk_data, offset)`` for each PNG chunk.

    Walks the PNG chunk stream after the 8-byte signature. Each
    chunk has a 4-byte big-endian length, 4-byte type, length bytes
    of data, and a 4-byte CRC. The walker stops on IEND or on a
    malformed chunk header.
    """
    if not data.startswith(_PNG_SIGNATURE):
        return

    end = len(data)
    i = 8  # past signature
    while i + 8 <= end:
        chunk_len = struct.unpack(">I", data[i:i + 4])[0]
        chunk_type = data[i + 4:i + 8]
        data_start = i + 8
        data_end = data_start + chunk_len
        if data_end + 4 > end:
            return
        yield chunk_type, data[data_start:data_end], i
        if chunk_type == b"IEND":
            return
        i = data_end + 4  # past CRC


def _is_private_ancillary(chunk_type: bytes) -> bool:
    """Return True for chunk types that are ancillary (lowercase
    first byte) AND private (lowercase second byte) per RFC 2083.
    """
    if len(chunk_type) != 4:
        return False
    first, second = chunk_type[0], chunk_type[1]
    # ASCII lowercase letters: 0x61-0x7A.
    return 0x61 <= first <= 0x7A and 0x61 <= second <= 0x7A


def _printable_density(text: str) -> float:
    """Return the fraction of characters that are printable ASCII or
    common UTF-8 letters.
    """
    if not text:
        return 0.0
    printable = 0
    for ch in text:
        cp = ord(ch)
        if 0x20 <= cp <= 0x7E:
            printable += 1
        elif cp >= 0x80 and ch.isprintable():
            printable += 1
    return printable / len(text)


def _has_bidi(text: str) -> bool:
    return any(ch in _BIDI_CODEPOINTS for ch in text)


def _has_zero_width(text: str) -> bool:
    return any(ch in _ZERO_WIDTH_CHARS for ch in text)


def detect_image_png_private_chunk(file_path: Path) -> Iterable[Finding]:
    """Surface PNG private ancillary chunks carrying readable text
    payload, with per-trigger Tier 1 escalation on concealment
    signals.
    """
    try:
        raw = file_path.read_bytes()
    except OSError:
        return

    if len(raw) > _MAX_IMAGE_BYTES:
        raw = raw[:_MAX_IMAGE_BYTES]

    if not raw.startswith(_PNG_SIGNATURE):
        return

    for chunk_type, chunk_data, offset in _iter_png_chunks(raw):
        if not _is_private_ancillary(chunk_type):
            continue

        try:
            text = chunk_data.decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - defensive
            continue

        text_clean = text.replace("\x00", "").strip()
        if len(text_clean) < _LENGTH_THRESHOLD:
            continue

        density = _printable_density(text_clean)
        if density < _PRINTABLE_DENSITY:
            continue

        chunk_type_str = chunk_type.decode("ascii", errors="replace")
        preview = text_clean[:_PREVIEW_LIMIT]

        # Tier 2 baseline finding.
        yield Finding(
            mechanism="image_png_private_chunk",
            tier=2,
            confidence=0.75,
            description=(
                f"PNG private ancillary chunk {chunk_type_str!r} at "
                f"offset {offset} carries {len(text_clean)} characters "
                f"of readable UTF-8 text at {density:.0%} printable "
                f"density. Private ancillary chunks are documented PNG "
                f"infrastructure for vendor-specific metadata, but "
                f"their use to carry natural-language text outside a "
                f"known vendor namespace is structurally notable. "
                f"Recovered text: {preview!r}."
            ),
            location=f"{file_path}@chunk:{offset}",
            surface=f"(PNG private chunk {chunk_type_str} not rendered)",
            concealed=preview,
            source_layer="batin",
        )

        # Tier 1 escalation: per-trigger findings.
        triggers: list[str] = []
        if _has_bidi(text_clean):
            triggers.append("bidi")
        if _has_zero_width(text_clean):
            triggers.append("zero_width")
        if len(text_clean) > _LONG_PAYLOAD_THRESHOLD:
            triggers.append("length")

        for trigger in triggers:
            yield Finding(
                mechanism="image_png_private_chunk",
                tier=1,
                confidence=0.9,
                description=(
                    f"PNG private ancillary chunk {chunk_type_str!r} "
                    f"at offset {offset} exhibits the {trigger!r} "
                    f"concealment trigger in addition to the Tier 2 "
                    f"baseline structural signal. Concealment "
                    f"triggers in private chunks elevate the finding "
                    f"to Tier 1: the structural anomaly now carries "
                    f"a byte-deterministic concealment shape. "
                    f"Recovered text: {preview!r}."
                ),
                location=f"{file_path}@chunk:{offset}",
                surface=f"(PNG private chunk {chunk_type_str} not rendered)",
                concealed=preview,
                source_layer="batin",
            )


__all__ = ["detect_image_png_private_chunk"]
