"""
Tier 1 detector for PNG public text chunks (tEXt, iTXt, zTXt) carrying
concealment-shaped payload (v1.1.2 image format gauntlet).

PNG defines three public ancillary chunk types for text metadata:

  - ``tEXt``: latin-1 keyword + NUL + latin-1 value
  - ``zTXt``: latin-1 keyword + NUL + compression byte + zlib-deflated value
  - ``iTXt``: UTF-8 keyword + NUL + compression flag + compression method
             + language tag + NUL + translated keyword + NUL + UTF-8 value

These chunks are documented PNG infrastructure; legitimate uses include
photographer credits, capture-time stamps, and software identifiers.
The structural fact "PNG carries text metadata" is therefore not by
itself evidence of concealment.

This mechanism mirrors ``pdf_metadata_analyzer``'s four-trigger model.
For each tEXt/iTXt/zTXt value field, four byte-deterministic triggers
are evaluated:

  1. length: UTF-8 byte length of the value exceeds 1024 bytes.
  2. bidi: value contains a bidirectional override codepoint
     (U+202A through U+202E or U+2066 through U+2069).
  3. zero_width: value contains a zero-width character (U+200B,
     U+200C, U+200D, or U+FEFF).
  4. divergence: value contains a known concealment marker
     (HIDDEN_, BATIN_, ZAHIR_, PAYLOAD) at any position, indicating
     explicit divergence between the visible image surface and the
     metadata layer.

Each trigger that fires emits its own Tier 1 finding so the report
carries one finding per concealment shape per chunk. This is the same
shape ``pdf_metadata_analyzer`` uses for PDF metadata fields: tier 1,
byte-deterministic, multiple findings per source.

Closes ``image_gauntlet`` fixture ``02_5_png_text_chunk_payload.png``.

Distinct from ``image_text_metadata`` (existing v1.1.1 detector that
surfaces the bare presence of any text chunk as a structural Tier 3
notice without evaluating concealment shape) and from
``image_png_private_chunk`` (which targets the private ancillary chunk
namespace, lowercase second byte, not the public text chunks).

Tier discipline: Tier 1 only. Each trigger is byte-deterministic;
unlike ``image_png_private_chunk`` there is no Tier 2 baseline because
the bare presence of a tEXt/iTXt/zTXt chunk is documented PNG
infrastructure and not structurally notable on its own.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Iterable

from domain.finding import Finding


_MAX_IMAGE_BYTES: int = 16 * 1024 * 1024
_PREVIEW_LIMIT: int = 240
_LENGTH_THRESHOLD: int = 1024

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

# Known concealment markers. These are conservative: each marker is a
# string adversaries have used in red-team payloads to delimit a hidden
# region from a visible region. A false positive on a marker substring
# is acceptable at Tier 1 because the marker itself is not natural
# language metadata; finding HIDDEN_ inside a Title field is itself
# structurally anomalous regardless of intent.
_DIVERGENCE_MARKERS: tuple[str, ...] = (
    "HIDDEN_",
    "BATIN_",
    "ZAHIR_",
    "PAYLOAD",
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


def _parse_text_chunk(
    chunk_type: bytes, chunk_data: bytes,
) -> tuple[str, str] | None:
    """Return ``(keyword, value)`` for a tEXt / iTXt / zTXt chunk.

    Returns None for chunks that fail to parse. Permissive: any
    decoding error falls back to ``errors="replace"`` so adversarial
    or malformed payloads still surface as findings.
    """
    if chunk_type == b"tEXt":
        # latin-1 keyword \\0 latin-1 value per RFC 2083. Real-world
        # adversaries write UTF-8 bytes into tEXt values to hide bidi /
        # zero-width codepoints from latin-1-only readers; we try a
        # UTF-8 reinterpretation when the latin-1 decode includes
        # high-bit bytes that look like a UTF-8 multibyte sequence.
        nul = chunk_data.find(b"\x00")
        if nul < 0:
            return None
        keyword = chunk_data[:nul].decode("latin-1", errors="replace")
        raw_value = chunk_data[nul + 1:]
        try:
            value = raw_value.decode("utf-8")
        except UnicodeDecodeError:
            value = raw_value.decode("latin-1", errors="replace")
        return keyword, value

    if chunk_type == b"zTXt":
        # latin-1 keyword \\0 compression-method byte zlib-deflate text
        nul = chunk_data.find(b"\x00")
        if nul < 0 or nul + 1 >= len(chunk_data):
            return None
        keyword = chunk_data[:nul].decode("latin-1", errors="replace")
        # Skip the compression-method byte at chunk_data[nul + 1].
        compressed = chunk_data[nul + 2:]
        try:
            decompressed = zlib.decompress(compressed)
        except zlib.error:
            return None
        value = decompressed.decode("latin-1", errors="replace")
        return keyword, value

    if chunk_type == b"iTXt":
        # UTF-8 keyword \\0 compression-flag compression-method
        # language-tag \\0 translated-keyword \\0 UTF-8 value
        parts = chunk_data.split(b"\x00", 1)
        if len(parts) != 2:
            return None
        keyword = parts[0].decode("utf-8", errors="replace")
        rest = parts[1]
        if len(rest) < 2:
            return None
        compression_flag = rest[0]
        # Skip compression-method byte at rest[1].
        after_flags = rest[2:]
        # language tag \\0 translated-keyword \\0 value
        lang_split = after_flags.split(b"\x00", 1)
        if len(lang_split) != 2:
            return None
        after_lang = lang_split[1]
        kw_split = after_lang.split(b"\x00", 1)
        if len(kw_split) != 2:
            return None
        raw_value = kw_split[1]
        if compression_flag == 1:
            try:
                raw_value = zlib.decompress(raw_value)
            except zlib.error:
                return None
        value = raw_value.decode("utf-8", errors="replace")
        return keyword, value

    return None


def _has_bidi(text: str) -> bool:
    return any(ch in _BIDI_CODEPOINTS for ch in text)


def _has_zero_width(text: str) -> bool:
    return any(ch in _ZERO_WIDTH_CHARS for ch in text)


def _bidi_codepoints(text: str) -> list[str]:
    found = sorted({c for c in text if c in _BIDI_CODEPOINTS})
    return [f"U+{ord(c):04X}" for c in found]


def _zero_width_codepoints(text: str) -> list[str]:
    found = sorted({c for c in text if c in _ZERO_WIDTH_CHARS})
    return [f"U+{ord(c):04X}" for c in found]


def _divergence_markers(text: str) -> list[str]:
    return [m for m in _DIVERGENCE_MARKERS if m in text]


def detect_image_png_text_chunk_payload(
    file_path: Path,
) -> Iterable[Finding]:
    """Surface PNG public text chunk values exhibiting concealment-
    shaped triggers, one finding per trigger per chunk.
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
        if chunk_type not in (b"tEXt", b"iTXt", b"zTXt"):
            continue

        parsed = _parse_text_chunk(chunk_type, chunk_data)
        if parsed is None:
            continue
        keyword, value = parsed
        if not value:
            continue

        chunk_type_str = chunk_type.decode("ascii", errors="replace")
        encoded_len = len(value.encode("utf-8", errors="replace"))
        preview = (
            value if len(value) <= _PREVIEW_LIMIT
            else value[:_PREVIEW_LIMIT] + "..."
        )

        # (a) length
        if encoded_len > _LENGTH_THRESHOLD:
            yield Finding(
                mechanism="image_png_text_chunk_payload",
                tier=1,
                confidence=0.9,
                description=(
                    f"PNG {chunk_type_str} chunk at offset {offset} "
                    f"with keyword {keyword!r} carries {encoded_len} "
                    f"UTF-8 bytes, exceeding the {_LENGTH_THRESHOLD}-"
                    f"byte length threshold. Long text in image "
                    f"metadata is structurally anomalous regardless "
                    f"of content. Recovered text: {preview!r}."
                ),
                location=f"{file_path}@chunk:{offset}",
                surface=(
                    f"(PNG {chunk_type_str} chunk keyword "
                    f"{keyword!r} not rendered)"
                ),
                concealed=preview,
                source_layer="batin",
            )

        # (b) bidi
        bidi_found = _bidi_codepoints(value)
        if bidi_found:
            yield Finding(
                mechanism="image_png_text_chunk_payload",
                tier=1,
                confidence=0.95,
                description=(
                    f"PNG {chunk_type_str} chunk at offset {offset} "
                    f"with keyword {keyword!r} contains "
                    f"bidirectional-override codepoints "
                    f"({', '.join(bidi_found)}) that reorder "
                    f"rendered glyphs vs. the underlying byte order. "
                    f"Recovered text: {preview!r}."
                ),
                location=f"{file_path}@chunk:{offset}",
                surface=(
                    f"(PNG {chunk_type_str} chunk keyword "
                    f"{keyword!r} not rendered)"
                ),
                concealed=preview,
                source_layer="batin",
            )

        # (c) zero-width
        zw_found = _zero_width_codepoints(value)
        if zw_found:
            yield Finding(
                mechanism="image_png_text_chunk_payload",
                tier=1,
                confidence=0.95,
                description=(
                    f"PNG {chunk_type_str} chunk at offset {offset} "
                    f"with keyword {keyword!r} contains zero-width "
                    f"codepoints ({', '.join(zw_found)}) that are "
                    f"invisible in any renderer but present in the "
                    f"bytes. Recovered text: {preview!r}."
                ),
                location=f"{file_path}@chunk:{offset}",
                surface=(
                    f"(PNG {chunk_type_str} chunk keyword "
                    f"{keyword!r} not rendered)"
                ),
                concealed=preview,
                source_layer="batin",
            )

        # (d) divergence
        markers = _divergence_markers(value)
        if markers:
            yield Finding(
                mechanism="image_png_text_chunk_payload",
                tier=1,
                confidence=0.9,
                description=(
                    f"PNG {chunk_type_str} chunk at offset {offset} "
                    f"with keyword {keyword!r} contains explicit "
                    f"concealment markers ({', '.join(markers)}). "
                    f"Markers of this shape are not natural-language "
                    f"metadata and indicate a hidden region delimited "
                    f"in the chunk value. Recovered text: {preview!r}."
                ),
                location=f"{file_path}@chunk:{offset}",
                surface=(
                    f"(PNG {chunk_type_str} chunk keyword "
                    f"{keyword!r} not rendered)"
                ),
                concealed=preview,
                source_layer="batin",
            )


__all__ = ["detect_image_png_text_chunk_payload"]
