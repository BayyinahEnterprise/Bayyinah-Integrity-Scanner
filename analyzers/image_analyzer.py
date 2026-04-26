"""
ImageAnalyzer — zahir/batin witness for raster image files (PNG, JPEG).

    أَفَلَا يَتَدَبَّرُونَ الْقُرْآنَ ۚ وَلَوْ كَانَ مِنْ عِندِ غَيْرِ
    اللَّـهِ لَوَجَدُوا فِيهِ اخْتِلَافًا كَثِيرًا
    (An-Nisa 4:82)

    "Then do they not reflect upon the Qur'an? If it had been from
    [any] other than Allah, they would have found within it much
    contradiction."

Architectural reading. The image format makes one clean claim — "these
are the pixels." An image reader renders those pixels and nothing more.
But a PNG or JPEG file is a sequence of self-describing chunks, and the
chunk sequence carries more than the pixels: text metadata, colour
profiles, private payloads, bytes appended after the declared end
marker. When what the renderer draws does not match what the file
contains, the reader who opened only the image has seen one witness;
the file carries another. The analyzer reads both and reports the gap.

Supported FileKinds: ``IMAGE_PNG``, ``IMAGE_JPEG`` (the binary-raster
family). SVG — which is XML text — has its own analyzer and is not
dispatched here. Extension mismatches are signalled at the router level.

Mechanisms emitted:

    trailing_data              (batin) bytes appended after the declared
                               IEND (PNG) or EOI (JPEG) marker. A
                               renderer stops at the marker; the rest of
                               the file sits on disk waiting for a
                               different reader.
    suspicious_image_chunk     (batin) a PNG chunk type not in the
                               standard set, or a JPEG segment marker
                               outside the standard set. Tier-3 signal —
                               private/experimental chunks are a known
                               steganography vector but can also be
                               legitimate tooling output.
    oversized_metadata         (batin) a single metadata chunk or
                               segment exceeds the configured size limit
                               (64 KB by default). Legitimate EXIF / ICC
                               / XMP fits comfortably; oversized blobs
                               are typically carrying something else.
    image_text_metadata        (zahir) PNG tEXt/iTXt/zTXt or JPEG COM /
                               EXIF UserComment containing human-
                               readable text. Surface-readable to any
                               parser that opens the file, absent from
                               the rendered image — the classic
                               performed-alignment shape.
    zero_width_chars / tag_chars / bidi_control
                               (zahir) Unicode concealment mechanisms
                               applied to any extracted metadata text.
                               Re-uses the domain's shared concealment
                               catalog — a tag-char prompt-injection
                               payload inside a PNG tEXt chunk is no
                               less a tag-char payload for being inside
                               an image.

Additive-only. Existing analyzers (``ZahirTextAnalyzer``,
``BatinObjectAnalyzer``, ``TextFileAnalyzer``, ``JsonAnalyzer``) are
untouched; this analyzer declares its own ``supported_kinds`` and is
selected by the registry's Phase 9 kind filter.
"""

from __future__ import annotations

import math
import re
import struct
import zlib
from pathlib import Path
from typing import ClassVar, Iterable, Iterator

from analyzers.base import BaseAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    compute_muwazana_score,
)
from domain.config import (
    BIDI_CONTROL_CHARS,
    GENERATIVE_CIPHER_B64_PATTERN,
    GENERATIVE_CIPHER_HEX_PATTERN,
    GENERATIVE_CIPHER_MIN_BYTES,
    HIGH_ENTROPY_MIN_BYTES,
    HIGH_ENTROPY_THRESHOLD,
    IMAGE_METADATA_SIZE_LIMIT,
    IMAGE_TRAILING_DATA_THRESHOLD,
    JPEG_STANDARD_MARKERS,
    LSB_MIN_SAMPLES,
    LSB_UNIFORMITY_TOLERANCE,
    MATH_ALPHANUMERIC_RANGE,
    PNG_STANDARD_CHUNKS,
    PNG_TEXT_CHUNKS,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind

# Phase 12 — pre-compiled cipher-shape regexes.
_B64_RE = re.compile(GENERATIVE_CIPHER_B64_PATTERN)
_HEX_RE = re.compile(GENERATIVE_CIPHER_HEX_PATTERN)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Upper bound on bytes we will read for one image scan. A 32 MB cap is
# generous for every realistic photograph and image and bounds memory
# pressure from adversarially large inputs.
_MAX_READ_BYTES = 32 * 1024 * 1024

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOI = b"\xff\xd8"
_JPEG_EOI = b"\xff\xd9"

# Tolerance: tiny amounts of trailing data (e.g. a single trailing
# newline on a file that was touched by a text editor) don't fire.
# The threshold lives in config so the contract is explicit.
_TRAILING_DATA_TOLERANCE = IMAGE_TRAILING_DATA_THRESHOLD


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode_latin1_or_utf8(b: bytes) -> str:
    """PNG tEXt is latin-1, PNG iTXt is UTF-8; EXIF UserComment is often
    UTF-8 but can be ASCII with an 8-byte character-code prefix.

    We try UTF-8 first (it is a strict superset of ASCII); on failure we
    fall back to latin-1, which never fails and preserves byte values.
    Errors are replaced rather than strict because malformed bytes in
    metadata are themselves a signal — we keep the scan going.
    """
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin-1", errors="replace")


def _has_unicode_concealment(text: str) -> dict[str, list[str]]:
    """Return a dict of mechanism -> [codepoint hex strings] present.

    Covers ``zero_width_chars``, ``tag_chars``, ``bidi_control``, and —
    as of Phase 11 — ``mathematical_alphanumeric`` (Unicode U+1D400 ..
    U+1D7FF). Used to re-run the zahir-layer concealment catalog against
    extracted metadata text, so a TAG-block prompt-injection payload
    hidden in a PNG tEXt chunk is surfaced with the same mechanism name
    as the same payload hidden in a plain Markdown file.
    """
    found: dict[str, list[str]] = {}
    for ch in text:
        cp = ord(ch)
        if ch in ZERO_WIDTH_CHARS:
            found.setdefault("zero_width_chars", []).append(f"U+{cp:04X}")
        elif cp in TAG_CHAR_RANGE:
            found.setdefault("tag_chars", []).append(f"U+{cp:04X}")
        elif ch in BIDI_CONTROL_CHARS:
            found.setdefault("bidi_control", []).append(f"U+{cp:04X}")
        elif cp in MATH_ALPHANUMERIC_RANGE:
            found.setdefault(
                "mathematical_alphanumeric", [],
            ).append(f"U+{cp:04X}")
    return found


# ---------------------------------------------------------------------------
# Phase 11 — statistical helpers
# ---------------------------------------------------------------------------


def _shannon_entropy(data: bytes) -> float:
    """Shannon entropy of a byte string, in bits per byte.

    Returns 0.0 for empty input. A uniformly-random byte sequence maxes
    at exactly 8.0; base64 / most ciphertext sits around 7.5-7.9; English
    prose is roughly 4.0; repetitive markup is lower still. We use this
    only as a sniff for ``high_entropy_metadata`` — we do not claim it
    proves encryption, only that the payload is statistically dense.
    """
    if not data:
        return 0.0
    counts = [0] * 256
    for b in data:
        counts[b] += 1
    n = len(data)
    entropy = 0.0
    for c in counts:
        if c == 0:
            continue
        p = c / n
        entropy -= p * math.log2(p)
    return entropy


def _detect_lsb_uniformity(sample: bytes) -> tuple[int, float] | None:
    """Look for a suspiciously uniform distribution of least-significant
    bits in a byte sequence.

    Returns ``(n_bytes, proportion)`` if the sample is large enough AND
    the LSB-1 proportion sits within ``LSB_UNIFORMITY_TOLERANCE`` of 0.5
    — the signature of a payload embedded bit-by-bit into the LSB plane
    of pixel bytes. Returns ``None`` otherwise.

    The test is a weak signal on purpose. A natural photograph can
    occasionally hit near-50/50 balance on a cropped region; requiring
    ``LSB_MIN_SAMPLES`` bytes gives the distribution room to express a
    natural skew. The detector is tier-3 (interpretive) precisely
    because of this — it marks the *signature*, not a verdict.
    """
    n = len(sample)
    if n < LSB_MIN_SAMPLES:
        return None
    ones = 0
    for b in sample:
        ones += b & 1
    prop = ones / n
    if abs(prop - 0.5) <= LSB_UNIFORMITY_TOLERANCE:
        return (n, prop)
    return None


# ---------------------------------------------------------------------------
# PNG parsing
# ---------------------------------------------------------------------------


def _iter_png_chunks(data: bytes) -> Iterator[tuple[bytes, bytes, int, int]]:
    """Yield ``(chunk_type, chunk_data, length, declared_crc)`` for each
    chunk in a PNG byte stream. Does not validate CRCs — a CRC failure
    is itself a batin signal but out of scope for v0.

    The PNG chunk layout, repeated until IEND:

        4 bytes   length (big-endian uint32) of the data field
        4 bytes   chunk type (ASCII, e.g. b"IHDR")
        N bytes   chunk data
        4 bytes   CRC-32 of (type + data)

    Stops yielding at IEND or end-of-buffer. Silently truncates on a
    malformed length field rather than raising — the caller is
    responsible for reporting the structural gap.
    """
    if not data.startswith(_PNG_SIGNATURE):
        return
    i = len(_PNG_SIGNATURE)
    while i + 8 <= len(data):
        length = struct.unpack(">I", data[i : i + 4])[0]
        chunk_type = data[i + 4 : i + 8]
        data_end = i + 8 + length
        crc_end = data_end + 4
        if crc_end > len(data):
            # Truncated chunk — stop and let the caller decide what to do.
            return
        chunk_data = data[i + 8 : data_end]
        crc = struct.unpack(">I", data[data_end : data_end + 4])[0]
        yield chunk_type, chunk_data, length, crc
        i = crc_end
        if chunk_type == b"IEND":
            return


def _parse_png_text(chunk_type: bytes, chunk_data: bytes) -> tuple[str, str]:
    """Extract (keyword, value) from a PNG text chunk.

    ``tEXt``  : <latin-1 keyword>\\0<latin-1 value>
    ``zTXt``  : <latin-1 keyword>\\0<compression-method byte><zlib-deflate text>
    ``iTXt``  : <UTF-8 keyword>\\0<compression flag><compression method>
                <language tag>\\0<translated keyword>\\0<UTF-8 text>

    For zTXt / iTXt the caller may want to see the decompressed text; we
    return it for the concealment scan to inspect.
    """
    if chunk_type == b"tEXt":
        # Spec says latin-1, but the concealment analyzer is inspecting
        # adversarial data — an attacker is free to write non-spec UTF-8
        # bytes into a tEXt value, and the concealment scan must still
        # see the TAG / zero-width / bidi codepoints. Prefer UTF-8; fall
        # back to latin-1 only when UTF-8 decoding strictly fails.
        if b"\x00" not in chunk_data:
            return ("", _decode_latin1_or_utf8(chunk_data))
        key, _, val = chunk_data.partition(b"\x00")
        return (
            key.decode("latin-1", errors="replace"),
            _decode_latin1_or_utf8(val),
        )
    if chunk_type == b"zTXt":
        if b"\x00" not in chunk_data:
            return ("", "")
        key, _, rest = chunk_data.partition(b"\x00")
        if not rest:
            return (key.decode("latin-1", errors="replace"), "")
        # rest[0] is compression method (0 = deflate); rest[1:] is zlib
        try:
            decompressed = zlib.decompress(rest[1:])
        except zlib.error:
            return (key.decode("latin-1", errors="replace"), "")
        return (
            key.decode("latin-1", errors="replace"),
            decompressed.decode("latin-1", errors="replace"),
        )
    if chunk_type == b"iTXt":
        # UTF-8 keyword
        if b"\x00" not in chunk_data:
            return ("", chunk_data.decode("utf-8", errors="replace"))
        key, _, rest = chunk_data.partition(b"\x00")
        # compression flag + compression method + language tag + \0 +
        # translated keyword + \0 + text
        if len(rest) < 2:
            return (key.decode("utf-8", errors="replace"), "")
        compression_flag = rest[0]
        # compression method = rest[1] (we ignore; only 0 defined)
        tail = rest[2:]
        # Consume language tag up to \0
        if b"\x00" not in tail:
            return (key.decode("utf-8", errors="replace"), "")
        _, _, tail = tail.partition(b"\x00")
        # Consume translated keyword up to \0
        if b"\x00" not in tail:
            return (key.decode("utf-8", errors="replace"), "")
        _, _, text_bytes = tail.partition(b"\x00")
        if compression_flag == 1:
            try:
                text_bytes = zlib.decompress(text_bytes)
            except zlib.error:
                pass
        return (
            key.decode("utf-8", errors="replace"),
            text_bytes.decode("utf-8", errors="replace"),
        )
    # Unknown text variant — return the raw bytes as best-effort text.
    return ("", _decode_latin1_or_utf8(chunk_data))


# ---------------------------------------------------------------------------
# JPEG parsing
# ---------------------------------------------------------------------------


def _iter_jpeg_segments(
    data: bytes,
) -> Iterator[tuple[int, bytes, int]]:
    """Yield ``(marker_byte, segment_data, offset)`` for each JPEG
    segment preceding the compressed-scan stream.

    JPEG segment layout:

        FF XX               marker (first byte always FF; multiple FFs
                            are fill bytes and are skipped)
        LL LL               big-endian length INCLUDING the length field
                            itself (so payload = LL LL - 2)
        payload...

    Segments without a payload (SOI, EOI, RSTn) have no length field.
    We stop iterating at SOS (start of scan) because everything after
    SOS is compressed image data up to EOI — there are no more
    ``suspicious_image_chunk``-relevant markers inside.

    ``offset`` is the byte offset in the buffer of the marker's leading
    ``FF``; kept so findings can surface a concrete location.
    """
    if not data.startswith(_JPEG_SOI):
        return
    i = 2  # skip SOI
    end = len(data)
    while i + 1 < end:
        if data[i] != 0xFF:
            # Not a marker. Either we ran off the end of the header or
            # we are inside compressed data. Stop yielding.
            return
        # Skip fill bytes: the JPEG spec allows FF FF FF ... before a
        # marker byte.
        j = i
        while j + 1 < end and data[j] == 0xFF and data[j + 1] == 0xFF:
            j += 1
        if j + 1 >= end:
            return
        marker = data[j + 1]
        marker_offset = j
        # SOI / EOI / TEM / RSTn have no length field.
        if marker == 0xD8 or marker == 0xD9 or marker == 0x01 or (
            0xD0 <= marker <= 0xD7
        ):
            yield marker, b"", marker_offset
            i = j + 2
            if marker == 0xD9:
                return
            continue
        # Every other marker carries a 2-byte big-endian length.
        if j + 4 > end:
            return
        length = struct.unpack(">H", data[j + 2 : j + 4])[0]
        if length < 2:
            return
        seg_end = j + 2 + length
        if seg_end > end:
            return
        payload = data[j + 4 : seg_end]
        yield marker, payload, marker_offset
        i = seg_end
        if marker == 0xDA:  # SOS — compressed data follows, stop.
            return


def _extract_jpeg_text(marker: int, payload: bytes) -> str | None:
    """Return a human-readable text payload from a JPEG segment, if any.

    The COM (0xFE) segment is plain text. APP1 (0xE1) is commonly EXIF
    or XMP; we return the raw UTF-8/ASCII decoding for the concealment
    scan to inspect — structural EXIF parsing is out of scope for v0.
    APP13 (0xED) is Photoshop IRB, often contains text metadata.
    Every other segment is skipped (returns None).
    """
    if marker == 0xFE:
        return _decode_latin1_or_utf8(payload)
    if marker == 0xE1:
        # EXIF starts with b"Exif\x00\x00"; XMP starts with
        # b"http://ns.adobe.com/xap/1.0/\x00". We return the raw decoding
        # in both cases — good enough to surface concealment in
        # UserComment or XMP <rdf:li>.
        return _decode_latin1_or_utf8(payload)
    if marker == 0xED:
        return _decode_latin1_or_utf8(payload)
    return None


# ---------------------------------------------------------------------------
# ImageAnalyzer
# ---------------------------------------------------------------------------


class ImageAnalyzer(BaseAnalyzer):
    """Detects trailing data, suspicious chunks, and concealed metadata
    text in PNG and JPEG files.

    The analyzer reads the file as raw bytes (no PIL / Pillow
    dependency) and walks the chunk/segment stream. Every finding
    carries its own ``source_layer`` — the analyzer's class-level
    layer is ``batin`` because the majority of mechanisms here live
    in the file's inner graph, but ``image_text_metadata`` and any
    Unicode concealment findings emitted from metadata strings are
    zahir.
    """

    name: ClassVar[str] = "image"
    error_prefix: ClassVar[str] = "Image scan error"
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({
        FileKind.IMAGE_PNG,
        FileKind.IMAGE_JPEG,
    })

    # ------------------------------------------------------------------
    # Public scan
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:  # noqa: D401
        """Scan the image at ``file_path`` for structural concealment."""
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            return self._scan_error_report(file_path, str(exc))

        if len(data) > _MAX_READ_BYTES:
            # Truncate, and record — a file bigger than the cap is
            # itself worth noting, but not a reason to fail the scan.
            data = data[:_MAX_READ_BYTES]

        if data.startswith(_PNG_SIGNATURE):
            findings = list(self._scan_png(data, file_path))
        elif data.startswith(_JPEG_SOI):
            findings = list(self._scan_jpeg(data, file_path))
        else:
            # Router sent us this file but the magic doesn't match.
            # Rather than silently pass, emit a scan_error so the final
            # report carries the discrepancy.
            return self._scan_error_report(
                file_path,
                "Not a recognised PNG or JPEG stream — router dispatched "
                "an image kind but the magic bytes do not match.",
            )

        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=compute_muwazana_score(findings),
            findings=findings,
        )

    # ------------------------------------------------------------------
    # PNG
    # ------------------------------------------------------------------

    def _scan_png(
        self, data: bytes, file_path: Path,
    ) -> Iterable[Finding]:
        saw_iend = False
        iend_end_offset: int | None = None

        # Phase 11 state: IDAT fragmentation tracking + IDAT accumulator
        # for LSB uniformity analysis.
        idat_run_state: int = 0
        # idat_run_state encodes a tiny FSM:
        #   0 — no IDAT seen yet
        #   1 — currently inside a contiguous IDAT run
        #   2 — inside IDAT run, but interrupted once (fragmentation seen)
        idat_fragmentation_offset: int | None = None
        idat_accumulator: list[bytes] = []

        # Re-walk the stream to track both the chunk list and the byte
        # offset at which IEND ends — we need both for trailing_data.
        offset = len(_PNG_SIGNATURE)
        for chunk_type, chunk_data, length, _crc in _iter_png_chunks(data):
            chunk_end = offset + 8 + length + 4  # 8 header + data + 4 CRC
            # Oversized chunk
            if length > IMAGE_METADATA_SIZE_LIMIT and chunk_type != b"IDAT":
                # IDAT can legitimately be large; every metadata chunk
                # has much tighter budgets.
                yield Finding(
                    mechanism="oversized_metadata",
                    tier=TIER["oversized_metadata"],
                    confidence=0.9,
                    description=(
                        f"PNG chunk {chunk_type.decode('latin-1', 'replace')!r} "
                        f"has payload size {length} bytes, exceeding the "
                        f"{IMAGE_METADATA_SIZE_LIMIT}-byte limit — "
                        "typical metadata fits comfortably well under this."
                    ),
                    location=f"{file_path}@chunk:{offset}",
                    surface=f"chunk type {chunk_type.decode('latin-1', 'replace')!r}",
                    concealed=f"{length}-byte payload",
                    source_layer="batin",
                )

            # Suspicious chunk type
            if chunk_type not in PNG_STANDARD_CHUNKS:
                type_repr = chunk_type.decode("latin-1", errors="replace")
                ancillary = bool(chunk_type[0] & 0x20)
                private = bool(chunk_type[1] & 0x20)
                yield Finding(
                    mechanism="suspicious_image_chunk",
                    tier=TIER["suspicious_image_chunk"],
                    confidence=0.75,
                    description=(
                        f"Non-standard PNG chunk type {type_repr!r} at "
                        f"offset {offset} "
                        f"(ancillary={ancillary}, private={private}) — "
                        "outside the standard PNG / APNG chunk set."
                    ),
                    location=f"{file_path}@chunk:{offset}",
                    surface="(invisible to image readers)",
                    concealed=f"{length} bytes under chunk type {type_repr!r}",
                    source_layer="batin",
                )

            # IDAT fragmentation tracking (Phase 11). A conforming PNG
            # encoder emits one contiguous run of IDATs; a non-IDAT chunk
            # interrupting the run (then more IDAT after it) is the
            # ``multiple_idat_streams`` pattern. We only record the first
            # interruption offset — one finding is enough to characterise.
            if chunk_type == b"IDAT":
                if idat_run_state == 0:
                    idat_run_state = 1
                elif idat_run_state == 2 and idat_fragmentation_offset is None:
                    idat_fragmentation_offset = offset
                idat_accumulator.append(chunk_data)
            else:
                if idat_run_state == 1 and chunk_type != b"IEND":
                    # A non-IEND chunk interrupts an IDAT run.
                    idat_run_state = 2

            # Text chunks — surface as zahir metadata + run concealment scan
            if chunk_type in PNG_TEXT_CHUNKS:
                keyword, value = _parse_png_text(chunk_type, chunk_data)
                yield from self._emit_text_metadata_findings(
                    text=value,
                    source=(
                        f"PNG {chunk_type.decode('latin-1')} chunk "
                        f"keyword={keyword!r}"
                    ),
                    file_path=file_path,
                    offset=offset,
                )
                # Phase 11 — entropy check on the raw chunk_data payload
                # (before text decoding). A tEXt keyword followed by a
                # base64/random payload is exactly the carrier shape.
                yield from self._emit_high_entropy_finding(
                    payload=chunk_data,
                    source=(
                        f"PNG {chunk_type.decode('latin-1')} chunk "
                        f"keyword={keyword!r}"
                    ),
                    file_path=file_path,
                    offset=offset,
                )

            if chunk_type == b"IEND":
                saw_iend = True
                iend_end_offset = chunk_end
                break

            offset = chunk_end

        # Phase 11 — multiple_idat_streams finding
        if idat_fragmentation_offset is not None:
            yield Finding(
                mechanism="multiple_idat_streams",
                tier=TIER["multiple_idat_streams"],
                confidence=0.8,
                description=(
                    "PNG IDAT sequence is interrupted by a non-IDAT chunk "
                    "and then resumes — structurally legal but diagnostically "
                    "unusual (standard encoders emit contiguous IDAT runs). "
                    "Fragmented IDAT layouts are a known carrier pattern "
                    "for interleaved private payloads."
                ),
                location=f"{file_path}@chunk:{idat_fragmentation_offset}",
                surface="(image decodes normally)",
                concealed="non-contiguous IDAT sequence",
                source_layer="batin",
            )

        # Phase 11 — LSB uniformity analysis on the concatenated IDAT
        # payload. We decompress to raw filtered scanlines (what the PNG
        # spec calls the "filtered image data"). If decompression fails,
        # we silently skip — this is an interpretive signal and we do not
        # want to fire scan_error on a format quirk.
        if idat_accumulator:
            joined = b"".join(idat_accumulator)
            try:
                pixel_bytes = zlib.decompress(joined)
            except zlib.error:
                pixel_bytes = b""
            anomaly = _detect_lsb_uniformity(pixel_bytes)
            if anomaly is not None:
                n_bytes, prop = anomaly
                yield Finding(
                    mechanism="suspected_lsb_steganography",
                    tier=TIER["suspected_lsb_steganography"],
                    confidence=0.5,
                    description=(
                        f"LSB distribution across {n_bytes} decompressed "
                        f"pixel bytes is suspiciously uniform "
                        f"(proportion of 1-bits = {prop:.4f}, within "
                        f"{LSB_UNIFORMITY_TOLERANCE:.2f} of 0.5). "
                        "This is the statistical signature of a message "
                        "embedded bit-by-bit into the least-significant-bit "
                        "plane. Tier-3 interpretive: the signature is "
                        "necessary but not sufficient."
                    ),
                    location=f"{file_path}@IDAT",
                    surface="(image renders normally)",
                    concealed="uniform LSB plane",
                    source_layer="batin",
                )

        # Trailing data after IEND
        if saw_iend and iend_end_offset is not None:
            trailing = len(data) - iend_end_offset
            if trailing >= _TRAILING_DATA_TOLERANCE:
                yield Finding(
                    mechanism="trailing_data",
                    tier=TIER["trailing_data"],
                    confidence=1.0,
                    description=(
                        f"{trailing} byte(s) appended after the PNG IEND "
                        "marker — invisible to every PNG renderer yet "
                        "preserved on disk for a non-image reader to "
                        "consume. A canonical polyglot/steganography shape."
                    ),
                    location=f"{file_path}@offset:{iend_end_offset}",
                    surface="(image renders normally)",
                    concealed=f"{trailing} byte(s) after IEND",
                    source_layer="batin",
                )

    # ------------------------------------------------------------------
    # JPEG
    # ------------------------------------------------------------------

    def _scan_jpeg(
        self, data: bytes, file_path: Path,
    ) -> Iterable[Finding]:
        saw_eoi = False
        eoi_end_offset: int | None = None

        for marker, payload, offset in _iter_jpeg_segments(data):
            # Oversized segment — EXIF / ICC / XMP all fit inside 64KB
            # comfortably. A payload beyond that is typically a carrier.
            if len(payload) > IMAGE_METADATA_SIZE_LIMIT:
                yield Finding(
                    mechanism="oversized_metadata",
                    tier=TIER["oversized_metadata"],
                    confidence=0.9,
                    description=(
                        f"JPEG segment 0xFF{marker:02X} at offset {offset} "
                        f"carries {len(payload)} bytes of payload, "
                        f"exceeding the {IMAGE_METADATA_SIZE_LIMIT}-byte "
                        "limit — unusual for standard EXIF/ICC/XMP."
                    ),
                    location=f"{file_path}@segment:{offset}",
                    surface=f"marker 0xFF{marker:02X}",
                    concealed=f"{len(payload)}-byte payload",
                    source_layer="batin",
                )

            # Suspicious marker — anything outside the standard set.
            if marker not in JPEG_STANDARD_MARKERS:
                yield Finding(
                    mechanism="suspicious_image_chunk",
                    tier=TIER["suspicious_image_chunk"],
                    confidence=0.75,
                    description=(
                        f"Non-standard JPEG marker 0xFF{marker:02X} at "
                        f"offset {offset} — outside the JPEG standard "
                        "marker set."
                    ),
                    location=f"{file_path}@segment:{offset}",
                    surface="(invisible to JPEG decoders)",
                    concealed=f"{len(payload)} bytes under marker 0xFF{marker:02X}",
                    source_layer="batin",
                )

            # Extract text from COM / APP1 (EXIF/XMP) / APP13
            text = _extract_jpeg_text(marker, payload)
            if text:
                yield from self._emit_text_metadata_findings(
                    text=text,
                    source=f"JPEG 0xFF{marker:02X} segment",
                    file_path=file_path,
                    offset=offset,
                )
                # Phase 11 — entropy check on the raw payload of every
                # text-carrying segment. A JPEG COM or APP1 chunk carrying
                # base64 / ciphertext inside a "plausible" text prefix is
                # exactly the generative-cryptography carrier shape.
                yield from self._emit_high_entropy_finding(
                    payload=payload,
                    source=f"JPEG 0xFF{marker:02X} segment",
                    file_path=file_path,
                    offset=offset,
                )

            if marker == 0xD9:
                saw_eoi = True
                eoi_end_offset = offset + 2
                break

        # If _iter_jpeg_segments stopped at SOS, the scan stream runs
        # until the first FF D9. Locate it.
        if not saw_eoi:
            eoi_idx = data.rfind(_JPEG_EOI)
            if eoi_idx != -1:
                saw_eoi = True
                eoi_end_offset = eoi_idx + 2

        if saw_eoi and eoi_end_offset is not None:
            trailing = len(data) - eoi_end_offset
            if trailing >= _TRAILING_DATA_TOLERANCE:
                yield Finding(
                    mechanism="trailing_data",
                    tier=TIER["trailing_data"],
                    confidence=1.0,
                    description=(
                        f"{trailing} byte(s) appended after the JPEG EOI "
                        "marker — invisible to every JPEG decoder yet "
                        "preserved on disk. A polyglot / stegano shape."
                    ),
                    location=f"{file_path}@offset:{eoi_end_offset}",
                    surface="(image renders normally)",
                    concealed=f"{trailing} byte(s) after EOI",
                    source_layer="batin",
                )

    # ------------------------------------------------------------------
    # Shared: text-metadata surfacing + Unicode concealment re-run
    # ------------------------------------------------------------------

    def _emit_text_metadata_findings(
        self,
        text: str,
        source: str,
        file_path: Path,
        offset: int,
    ) -> Iterable[Finding]:
        """Emit:
          * one ``image_text_metadata`` finding per non-empty text blob
          * per-mechanism findings for any Unicode concealment present.

        The report is deliberately duplicative: a reader scanning for
        ``tag_chars`` gets the same signal here as from a plain text
        file. The ``image_text_metadata`` finding names the fact that
        human-readable metadata text exists at all — not accusatory in
        itself, but load-bearing context for the concealment findings.
        """
        if not text:
            return

        # Only surface text that looks like human-readable content. A
        # binary ICC profile will decode to noise under latin-1; we don't
        # want to fire image_text_metadata on that. The heuristic: the
        # string contains at least one ASCII-printable run of length 4+.
        printable_run = 0
        longest_run = 0
        for ch in text:
            if 0x20 <= ord(ch) <= 0x7E:
                printable_run += 1
                longest_run = max(longest_run, printable_run)
            else:
                printable_run = 0
        if longest_run < 4:
            return

        # Preview: first 80 characters of printable content, whitespace
        # collapsed, no line breaks — enough for a human to recognise
        # the payload without dumping the full blob into the report.
        preview = " ".join(text.split())[:80]
        yield Finding(
            mechanism="image_text_metadata",
            tier=TIER["image_text_metadata"],
            confidence=0.6,
            description=(
                f"Human-readable text found in {source}: {preview!r}. "
                "Text in image metadata is routine; surfaced so the "
                "reader can judge whether the content is expected."
            ),
            location=f"{file_path}@segment:{offset}",
            surface="(not visible in the rendered image)",
            concealed=f"metadata text ({len(text)} chars)",
            source_layer="zahir",
        )

        # Re-run Unicode concealment catalogue against the extracted text.
        concealment = _has_unicode_concealment(text)
        for mechanism, codepoints in concealment.items():
            uniq = sorted(set(codepoints))
            yield Finding(
                mechanism=mechanism,
                tier=TIER[mechanism],
                confidence=0.9 if mechanism != "tag_chars" else 1.0,
                description=(
                    f"{len(codepoints)} {mechanism.replace('_', ' ')} "
                    f"codepoint(s) ({', '.join(uniq)}) embedded in "
                    f"{source}."
                ),
                location=f"{file_path}@segment:{offset}",
                surface="(no visible indication)",
                concealed=f"{len(codepoints)} codepoint(s)",
                source_layer="zahir",
            )

    # ------------------------------------------------------------------
    # Phase 11 — high-entropy metadata probe
    # ------------------------------------------------------------------

    def _emit_high_entropy_finding(
        self,
        payload: bytes,
        source: str,
        file_path: Path,
        offset: int,
    ) -> Iterable[Finding]:
        """Emit ``high_entropy_metadata`` when a metadata payload's byte
        distribution looks like base64 / ciphertext / packed random data.

        Two gates:
          * payload length must be at least ``HIGH_ENTROPY_MIN_BYTES``
            (short blobs are artificially high-entropy and would noise
            the report up).
          * Shannon entropy must exceed ``HIGH_ENTROPY_THRESHOLD`` bits
            per byte.
        """
        if len(payload) < HIGH_ENTROPY_MIN_BYTES:
            return
        entropy = _shannon_entropy(payload)
        if entropy <= HIGH_ENTROPY_THRESHOLD:
            return
        yield Finding(
            mechanism="high_entropy_metadata",
            tier=TIER["high_entropy_metadata"],
            confidence=0.7,
            description=(
                f"{source} carries a {len(payload)}-byte payload with "
                f"Shannon entropy {entropy:.3f} bits/byte "
                f"(> {HIGH_ENTROPY_THRESHOLD} threshold). "
                "This is the statistical signature of base64, compressed, "
                "or encrypted content — a generative-cryptography carrier "
                "shape that passes a naive text-metadata sniff."
            ),
            location=f"{file_path}@segment:{offset}",
            surface="(looks like ordinary metadata text)",
            concealed=(
                f"{len(payload)}-byte high-entropy payload "
                f"(H={entropy:.2f})"
            ),
            source_layer="batin",
        )

        # Phase 12 — generative_cipher_signature. A high-entropy payload
        # whose decoded text additionally matches a canonical
        # base64 / hex cipher shape narrows the reading from "dense"
        # to "looks like AI-generated / deposited ciphertext".
        if len(payload) < GENERATIVE_CIPHER_MIN_BYTES:
            return
        try:
            decoded = payload.decode("latin-1")
        except Exception:  # noqa: BLE001 — defensive; latin-1 never raises
            return
        cipher_match = _B64_RE.search(decoded) or _HEX_RE.search(decoded)
        if cipher_match is None:
            return
        match_slice = cipher_match.group(0)
        preview = (
            match_slice if len(match_slice) <= 60
            else match_slice[:57] + "..."
        )
        yield Finding(
            mechanism="generative_cipher_signature",
            tier=TIER["generative_cipher_signature"],
            confidence=0.85,
            description=(
                f"{source} payload matches a canonical cipher / packed-"
                f"payload shape ({len(match_slice)}-character "
                f"{'base64' if _B64_RE.search(decoded) else 'hex'} run) "
                f"at entropy {entropy:.3f} bits/byte. "
                "This is the specific shape generative-cryptography "
                "payloads take when deposited into image metadata — a "
                "base64-or-hex body wrapping ciphertext or packed weights."
            ),
            location=f"{file_path}@segment:{offset}",
            surface="(reads as metadata text)",
            concealed=f"cipher-shape payload: {preview!r}",
            source_layer="batin",
        )


__all__ = ["ImageAnalyzer"]
