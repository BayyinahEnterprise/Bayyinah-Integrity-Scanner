"""
AudioAnalyzer — the hearing that must precede obedience (Al-Baqarah 2:93).

    خُذُوا۟ مَآ ءَاتَيْنَـٰكُم بِقُوَّةٍۢ وَٱسْمَعُوا۟ ۖ قَالُوا۟ سَمِعْنَا وَعَصَيْنَا

    "Take what We have given you with determination and listen."
    They said: "We hear and disobey."

The architectural reading: audio declares compliance at its surface
(what the listener hears) while the container's stems — metadata
atoms, embedded pictures, PCM sample LSBs, trailing bytes — carry
payloads the ear cannot reach. Identity theft through voice cloning
is *tazwir* and *iftira'* (Al-Nisa 4:112): fabricated speech attributed
to a speaker who never uttered it, among the gravest forms of
falsehood. AudioAnalyzer decomposes the container into stems and
routes each stem to the analyzer that already knows how to read that
material.

Composition, not duplication (Phase 23 pattern):

  * Metadata text (ID3 TIT2/TPE1/USLT, Vorbis TITLE/ARTIST/LYRICS,
    iTunes ©nam/©ART/©lyr) → ``ZahirTextAnalyzer._check_unicode`` for
    codepoint-level concealment (zero-width / bidi / TAG / homoglyph).
    Lyrics fields additionally scan for prompt-injection shapes.
  * Embedded pictures (ID3 APIC, Vorbis METADATA_BLOCK_PICTURE, iTunes
    covr) → ``ImageAnalyzer().scan`` for LSB steganography, trailing
    data, and EXIF text concealment.
  * WAV / FLAC PCM sample data → stdlib LSB entropy statistics for
    ``audio_lsb_stego_candidate``.
  * Everything else (container walk, identity-field cross-check,
    trailing-data scan) stays local because no other analyzer knows
    the container grammar.

Scope
-----
Supported containers: MP3 (ID3v1/v2 tagged and tagless sync-frame),
WAV (RIFF/WAVE), FLAC, M4A / M4B (ISO BMFF audio-only), Ogg Vorbis /
Opus.

Out of scope (deliberate): speech-to-text, music classification,
real-time analysis, signal-level source separation (the last is
registered in ``domain/config.py`` as ``audio_signal_stem_separation``
with status=future and an explicit dependency note — it requires a
neural model below 50 MB that opens detection surface the container
walk cannot reach). ``audio_deepfake_detection`` and
``audio_hidden_voice_command`` are likewise reserved future-work
names; this phase does not emit them.

Dependency policy
-----------------
Mutagen (pure-Python, ~300 KB) handles metadata parsing across ID3,
Vorbis comments, and iTunes metadata atoms. Implementing ID3v2.4 and
Vorbis comment parsing from scratch in a session budget would produce
a larger, less-audited surface than mutagen itself. AudioAnalyzer
retains stdlib fallbacks for WAV (``wave``) and FLAC
(``struct``-based METADATA_BLOCK walk) so coverage does not collapse
if mutagen is absent. If mutagen cannot be imported, the analyzer
emits a clean ``scan_error`` finding with remediation guidance; it
does not silently degrade.
"""

from __future__ import annotations

import math
import re
import struct
import wave
from pathlib import Path
from typing import Any, ClassVar, Iterable

from analyzers.base import BaseAnalyzer
from analyzers.image_analyzer import ImageAnalyzer
from analyzers.text_analyzer import ZahirTextAnalyzer
from domain import (
    Finding,
    IntegrityReport,
    SourceLayer,
    compute_muwazana_score,
)
from domain.config import (
    BIDI_CONTROL_CHARS,
    CONFUSABLE_TO_LATIN,
    SEVERITY,
    TAG_CHAR_RANGE,
    TIER,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Mutagen — imported defensively so a missing dependency surfaces cleanly.
# ---------------------------------------------------------------------------

try:
    import mutagen  # type: ignore[import-not-found]
    from mutagen.id3 import ID3, ID3NoHeaderError  # type: ignore[import-not-found]
    from mutagen.flac import FLAC, Picture  # type: ignore[import-not-found]
    from mutagen.oggvorbis import OggVorbis  # type: ignore[import-not-found]
    from mutagen.mp4 import MP4  # type: ignore[import-not-found]
    _MUTAGEN_AVAILABLE = True
except ImportError:  # pragma: no cover — environment-specific
    _MUTAGEN_AVAILABLE = False


# ---------------------------------------------------------------------------
# Shape constants
# ---------------------------------------------------------------------------

# Metadata tag keys whose value field is semantically "free text the
# listener or an ingestion pipeline might read". These are the keys
# AudioAnalyzer routes to ZahirTextAnalyzer's codepoint detectors.
# The list covers ID3 frame IDs, Vorbis comment keys, and iTunes atom
# names. Case-insensitive comparison.
_TEXT_TAG_KEYS: frozenset[str] = frozenset({
    # ID3v2 frames (4-char frame IDs).
    "tit2", "tit1", "tit3",         # titles
    "tpe1", "tpe2", "tpe3", "tpe4", # performer / band
    "talb", "tope",                  # album / original performer
    "tcop", "tcom", "text",          # copyright / composer / lyricist
    "tenc",                          # encoded by
    "txxx",                          # user-defined
    "comm",                          # comment
    "uslt",                          # unsynchronised lyrics
    "tdrc", "tyer",                  # recording year / date
    "tpos", "trck",                  # disc / track
    # Vorbis comment keys.
    "title", "artist", "album", "comment", "description",
    "composer", "lyricist", "lyrics", "copyright", "encoder",
    "albumartist", "performer",
    # iTunes ©-prefixed atom names are handled with the raw prefix.
    "\xa9nam", "\xa9art", "\xa9alb", "\xa9cmt", "\xa9lyr",
    "\xa9wrt", "\xa9too", "\xa9gen",
})

# Lyric-equivalent tag keys. Separate from generic text keys so we
# can scan them additionally for prompt-injection shapes.
_LYRIC_TAG_KEYS: frozenset[str] = frozenset({
    "uslt",                          # ID3 unsynchronised lyrics
    "lyrics",                        # Vorbis LYRICS
    "unsyncedlyrics",                # FLAC variant
    "\xa9lyr",                       # iTunes lyric atom
})

# Identity-provenance tag keys (Al-Nisa 4:112 — speaker attribution).
# Cross-stem divergence here is the highest-priority concealment shape
# because it is the exact form of tazwir the verse describes.
_IDENTITY_TAG_KEYS: frozenset[str] = frozenset({
    "tpe1", "tpe2",                  # ID3 performer / band
    "tcom",                          # ID3 composer
    "artist", "albumartist", "composer", "performer",  # Vorbis
    "\xa9art", "\xa9alb", "\xa9wrt",                    # iTunes
})

# Prompt-injection shapes looked for in lyric / comment fields.
_LYRIC_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"\bon(?:click|load|error|mouseover)\s*=", re.IGNORECASE),
    re.compile(r"ignore (?:all )?previous instruction", re.IGNORECASE),
    re.compile(r"disregard (?:all )?previous", re.IGNORECASE),
    re.compile(r"system\s*:\s*you (?:are|must)", re.IGNORECASE),
    re.compile(r"data:text/html", re.IGNORECASE),
)

# Foreign magic prefixes that should never appear inside an audio
# embedded-payload field. Presence indicates a non-image payload
# riding as metadata.
_FOREIGN_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-",                 "PDF"),
    (b"PK\x03\x04",            "ZIP"),
    (b"<!DOCTYPE html",        "HTML"),
    (b"<script",               "HTML-script"),
    (b"MZ",                    "Windows PE executable"),
    (b"\x7fELF",               "ELF executable"),
    (b"#!/",                   "Shell script shebang"),
)

# Image magic prefixes the audio container legitimately uses for cover
# art. Embedded bytes starting with one of these are routed to the
# ImageAnalyzer.
_IMAGE_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "PNG"),
    (b"\xff\xd8\xff",      "JPEG"),
    (b"GIF87a",            "GIF"),
    (b"GIF89a",            "GIF"),
)

# Entropy threshold above which a metadata field value is flagged as
# high-entropy. 6.0 bits/byte catches base64 / compressed / encrypted
# payloads without flagging normal multilingual text (which runs
# 4.5-5.5 bits/byte on typical corpora).
_HIGH_ENTROPY_THRESHOLD_BITS: float = 6.0
_HIGH_ENTROPY_MIN_LENGTH: int = 128

# LSB-stego statistical threshold. A uniform random LSB distribution
# produces Σ|ratio - 0.5| near zero; a genuine silent stretch also
# does. The threshold is tuned so only very long (>=2048 samples)
# near-uniform runs trigger — i.e. longer than any silent interval
# that would occur in a fixture.
_LSB_MIN_SAMPLES: int = 2048
_LSB_UNIFORMITY_THRESHOLD: float = 0.02  # |observed_ratio - 0.5|

# FLAC block-type constants (from FLAC format specification §9).
_FLAC_BLOCK_STREAMINFO = 0
_FLAC_BLOCK_PADDING = 1
_FLAC_BLOCK_APPLICATION = 2
_FLAC_BLOCK_SEEKTABLE = 3
_FLAC_BLOCK_VORBIS_COMMENT = 4
_FLAC_BLOCK_CUESHEET = 5
_FLAC_BLOCK_PICTURE = 6


# ---------------------------------------------------------------------------
# AudioAnalyzer
# ---------------------------------------------------------------------------

class AudioAnalyzer(BaseAnalyzer):
    """Decompose audio containers into stems and detect concealment.

    Supports MP3, WAV, FLAC, M4A, Ogg Vorbis / Opus.

    Composition:
      * Text-valued metadata tags → ``ZahirTextAnalyzer._check_unicode``
        for codepoint concealment + regex injection patterns for lyric
        fields.
      * Embedded pictures → ``ImageAnalyzer().scan`` for LSB / trailing
        data / EXIF text concealment; results re-emerge under
        ``audio_embedded_payload``.
      * WAV / FLAC PCM LSBs → local entropy statistic for
        ``audio_lsb_stego_candidate``.

    Out of scope: signal-level source separation (future work), speech
    recognition, music classification, real-time analysis.
    """

    name: ClassVar[str] = "audio"
    error_prefix: ClassVar[str] = "Audio scan error"
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({
        FileKind.AUDIO_MP3,
        FileKind.AUDIO_WAV,
        FileKind.AUDIO_FLAC,
        FileKind.AUDIO_M4A,
        FileKind.AUDIO_OGG,
    })

    # ------------------------------------------------------------------
    # Public scan entry
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:
        """Decompose the audio file at ``file_path`` into stems, inspect each.

        Missing / unreadable files short-circuit with ``scan_error`` +
        ``scan_incomplete=True`` per the BaseAnalyzer contract. A
        missing mutagen dependency is surfaced the same way so the
        caller does not silently degrade.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            return self._scan_error_report(
                file_path,
                f"File not found: {file_path}",
            )

        try:
            data = file_path.read_bytes()
        except OSError as exc:
            return self._scan_error_report(file_path, f"Read failed: {exc}")

        if not _MUTAGEN_AVAILABLE:  # pragma: no cover — environment-specific
            return self._scan_error_report(
                file_path,
                "mutagen not installed — run: pip install mutagen",
            )

        findings: list[Finding] = []
        findings.extend(self._scan_container(data, file_path))

        score = compute_muwazana_score(findings)
        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=score,
            findings=findings,
            scan_incomplete=False,
        )

    # ==================================================================
    # Container dispatch — decide which parser path + which stem walk.
    # ==================================================================

    def _scan_container(self, data: bytes, file_path: Path) -> list[Finding]:
        head = data[:16]
        # MP3 — ID3 preamble or raw frame sync.
        if head.startswith(b"ID3") or (
            len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xF0) == 0xF0
        ):
            return self._scan_mp3(data, file_path)
        # WAV — RIFF/WAVE shape.
        if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
            return self._scan_wav(data, file_path)
        # FLAC — fLaC magic.
        if head[:4] == b"fLaC":
            return self._scan_flac(data, file_path)
        # M4A — ISO BMFF ftyp with audio brand.
        if len(head) >= 12 and head[4:8] == b"ftyp":
            return self._scan_m4a(data, file_path)
        # Ogg — OggS capture pattern.
        if head[:4] == b"OggS":
            return self._scan_ogg(data, file_path)
        # Extension-only fallback: bytes do not match any recognised
        # audio magic. Emit container anomaly rather than silent-clean.
        return [self._make_container_anomaly_finding(
            file_path,
            reason=(
                "File extension indicates audio, but the header bytes "
                "do not match any recognised audio container magic."
            ),
            surface=f"header bytes: {head.hex()}",
        )]

    # ==================================================================
    # MP3 scan
    # ==================================================================

    def _scan_mp3(self, data: bytes, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []

        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = None
        except Exception as exc:  # noqa: BLE001 — malformed tag should degrade
            findings.append(self._make_scan_error(
                file_path, f"ID3 parse failed: {exc}",
            ))
            tags = None

        # Stream inventory — always emitted, non-deducting.
        tag_keys: list[str] = list(tags.keys()) if tags is not None else []
        findings.append(self._make_inventory_finding(
            file_path,
            container="MP3",
            inventory=(
                f"container=MP3 bytes={len(data)} "
                f"id3_tags={len(tag_keys)} frames={self._count_mp3_frames(data)}"
            ),
        ))

        if tags is not None:
            text_fields = self._extract_text_fields_from_id3(tags)
            identity_fields = {
                k: v for k, v in text_fields.items()
                if k.lower() in _IDENTITY_TAG_KEYS
            }
            findings.extend(self._scan_text_fields(text_fields, file_path))
            findings.extend(self._scan_lyric_fields(text_fields, file_path))
            findings.extend(self._scan_identity_fields(identity_fields, file_path))
            findings.extend(self._scan_high_entropy_fields(text_fields, file_path))
            findings.extend(self._scan_embedded_pictures_id3(tags, file_path))

        # Container-anomaly: trailing bytes past the last sync frame.
        findings.extend(self._scan_mp3_trailing(data, file_path))

        return findings

    def _extract_text_fields_from_id3(self, tags: Any) -> dict[str, str]:
        """Flatten an ID3 tag set into a dict of ``{frame_id: text_value}``.

        ID3 frames carry text as a list of strings (multi-value) or
        complex objects for USLT / TXXX. We decode to a plain string
        value per key; multiple values are joined with `` | ``.
        """
        fields: dict[str, str] = {}
        for key, frame in tags.items():
            # ``key`` is like ``TIT2`` or ``TIT2::en``; normalise to the
            # 4-char frame ID for keys lookup, keep the full key for
            # location reporting.
            frame_id = key.split(":", 1)[0].lower()
            try:
                if frame_id == "uslt":
                    # USLT has a ``text`` attribute.
                    text = getattr(frame, "text", "") or ""
                elif frame_id == "comm":
                    text = getattr(frame, "text", [""])[0] or ""
                elif frame_id == "txxx":
                    # TXXX: description + text.
                    desc = getattr(frame, "desc", "") or ""
                    text_list = getattr(frame, "text", [""]) or [""]
                    text = f"{desc}: {text_list[0]}"
                elif hasattr(frame, "text"):
                    text_list = frame.text if isinstance(frame.text, list) else [frame.text]
                    text = " | ".join(str(t) for t in text_list)
                else:
                    text = str(frame)
            except Exception:  # noqa: BLE001 — defensive per-frame
                continue
            if text:
                fields[frame_id] = text
        return fields

    def _count_mp3_frames(self, data: bytes) -> int:
        """Count sync frames starting at 0xFFF in the MP3 byte stream.

        Bounded scan — we stop once we have counted 16 frames or
        walked 256 KB of data, whichever comes first. Inventory does
        not need the exact frame count, only a rough shape indicator.
        """
        limit = min(len(data), 256 * 1024)
        count = 0
        i = 0
        while i < limit - 1 and count < 16:
            if data[i] == 0xFF and (data[i + 1] & 0xF0) == 0xF0:
                count += 1
                i += 144  # average frame size; we just want a rough count
            else:
                i += 1
        return count

    def _scan_mp3_trailing(self, data: bytes, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []
        # MP3 files frequently carry an ID3v1 128-byte trailer or APEv2
        # tag at the end; both are legitimate. Only flag if the file
        # ends with bytes that don't match any of those trailers AND
        # don't match a continued sync-frame shape.
        if len(data) < 128:
            return findings
        tail = data[-128:]
        # ID3v1 trailer starts with "TAG".
        if tail.startswith(b"TAG"):
            return findings
        # APEv2 trailer signature at the last 32 bytes.
        if b"APETAGEX" in data[-32:]:
            return findings
        # If the last 32 bytes are all ASCII printable, that's
        # suspicious for an MP3.
        if all(0x20 <= b < 0x7F or b in (0x09, 0x0A, 0x0D) for b in data[-32:]):
            findings.append(Finding(
                mechanism="audio_container_anomaly",
                tier=TIER["audio_container_anomaly"],
                confidence=0.7,
                severity_override=SEVERITY["audio_container_anomaly"],
                description=(
                    "MP3 file ends with an ASCII-text trailer that is "
                    "neither ID3v1 nor APEv2 — trailing textual payload "
                    "past the audio frame stream."
                ),
                location=f"{file_path} @ offset {len(data) - 32}",
                surface=f"last 32 bytes: {tail[-32:]!r}",
                concealed="",
            ))
        return findings

    # ==================================================================
    # WAV scan
    # ==================================================================

    def _scan_wav(self, data: bytes, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []

        # Parse chunk inventory and look for LIST/INFO / id3 / trailing.
        chunks, post_riff_tail = self._walk_riff_chunks(data)

        findings.append(self._make_inventory_finding(
            file_path,
            container="WAV",
            inventory=(
                f"container=WAV bytes={len(data)} "
                f"chunks={','.join(c[0] for c in chunks)}"
            ),
        ))

        # LSB sample-data scan for stego candidate.
        try:
            with wave.open(str(file_path), "rb") as wav:
                n_channels = wav.getnchannels()
                sampwidth = wav.getsampwidth()
                n_frames = wav.getnframes()
                if n_frames >= _LSB_MIN_SAMPLES and sampwidth in (1, 2):
                    raw = wav.readframes(
                        min(n_frames, 65536)  # sample up to 64k frames
                    )
                    findings.extend(
                        self._scan_pcm_lsb(raw, sampwidth, file_path)
                    )
        except wave.Error:
            # A parse failure while the magic declared WAV is itself
            # a container anomaly.
            findings.append(self._make_container_anomaly_finding(
                file_path,
                reason=(
                    "WAV header present but chunk structure is unparseable "
                    "by stdlib wave module."
                ),
                surface="",
            ))

        # INFO / id3 chunks carry text tags; route them the same way
        # as ID3 frames.
        info_fields = self._extract_wav_text_tags(chunks, data)
        findings.extend(self._scan_text_fields(info_fields, file_path))
        findings.extend(self._scan_high_entropy_fields(info_fields, file_path))

        # Trailing-data anomaly.
        if post_riff_tail > 0:
            findings.append(Finding(
                mechanism="audio_container_anomaly",
                tier=TIER["audio_container_anomaly"],
                confidence=0.9,
                severity_override=SEVERITY["audio_container_anomaly"],
                description=(
                    f"{post_riff_tail} byte(s) of trailing data after the "
                    "declared RIFF chunk size. A well-formed WAV ends at "
                    "the declared size; extra bytes indicate polyglot "
                    "concatenation or appended payload."
                ),
                location=f"{file_path} @ end",
                surface=f"trailing {post_riff_tail} bytes",
                concealed="",
            ))

        return findings

    def _walk_riff_chunks(self, data: bytes) -> tuple[list[tuple[str, int, int]], int]:
        """Walk the RIFF chunk stream. Returns (chunks, trailing_bytes).

        Each chunk entry is ``(fourcc, offset, size)``. Trailing bytes
        is the count of bytes past the declared RIFF chunk size.
        """
        chunks: list[tuple[str, int, int]] = []
        if len(data) < 12 or data[:4] != b"RIFF":
            return chunks, 0
        riff_size = struct.unpack("<I", data[4:8])[0]
        declared_end = 8 + riff_size
        trailing = max(0, len(data) - declared_end)
        pos = 12  # past "RIFF xxxx WAVE"
        end = min(declared_end, len(data))
        while pos + 8 <= end:
            fourcc = data[pos:pos + 4].decode("latin-1", errors="replace")
            size = struct.unpack("<I", data[pos + 4:pos + 8])[0]
            if size > end - pos - 8:
                break
            chunks.append((fourcc, pos, size))
            pos += 8 + size + (size % 2)  # chunks are word-aligned
        return chunks, trailing

    def _extract_wav_text_tags(
        self, chunks: list[tuple[str, int, int]], data: bytes,
    ) -> dict[str, str]:
        """Extract text-valued metadata from LIST/INFO and id3 chunks."""
        fields: dict[str, str] = {}
        for fourcc, offset, size in chunks:
            if fourcc == "LIST":
                # LIST chunk with INFO subtype carries 4-char keys +
                # null-terminated values.
                payload = data[offset + 8:offset + 8 + size]
                if payload[:4] != b"INFO":
                    continue
                p = 4
                while p + 8 <= len(payload):
                    key = payload[p:p + 4].decode("latin-1", errors="replace")
                    ksize = struct.unpack("<I", payload[p + 4:p + 8])[0]
                    if ksize > len(payload) - p - 8:
                        break
                    value = payload[p + 8:p + 8 + ksize].rstrip(b"\x00").decode(
                        "utf-8", errors="replace"
                    )
                    if value:
                        fields[key.lower()] = value
                    p += 8 + ksize + (ksize % 2)
        return fields

    # ==================================================================
    # FLAC scan
    # ==================================================================

    def _scan_flac(self, data: bytes, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []

        try:
            flac = FLAC(file_path)
        except Exception as exc:  # noqa: BLE001
            findings.append(self._make_container_anomaly_finding(
                file_path,
                reason=f"FLAC parse failed: {exc}",
                surface="",
            ))
            return findings

        text_fields = {k.lower(): " | ".join(v) for k, v in flac.items()}
        block_types = self._walk_flac_blocks(data)

        findings.append(self._make_inventory_finding(
            file_path,
            container="FLAC",
            inventory=(
                f"container=FLAC bytes={len(data)} "
                f"blocks=[{','.join(self._flac_block_name(b) for b in block_types)}] "
                f"vorbis_tags={len(text_fields)} pictures={len(flac.pictures)}"
            ),
        ))

        findings.extend(self._scan_text_fields(text_fields, file_path))
        findings.extend(self._scan_lyric_fields(text_fields, file_path))
        findings.extend(self._scan_identity_fields(
            {k: v for k, v in text_fields.items() if k in _IDENTITY_TAG_KEYS},
            file_path,
        ))
        findings.extend(self._scan_high_entropy_fields(text_fields, file_path))

        # Pictures — route to ImageAnalyzer.
        for i, pic in enumerate(flac.pictures):
            findings.extend(
                self._scan_picture_bytes(pic.data, file_path, i, "FLAC picture")
            )

        # Trailing-data past final block. We trust mutagen's block
        # iteration; any bytes after the last block end and before
        # the audio frames are flagged.
        return findings

    def _walk_flac_blocks(self, data: bytes) -> list[int]:
        """Return a list of FLAC METADATA_BLOCK types in order.

        Walks the block header stream past the fLaC magic. Each block
        header is 4 bytes: 1 bit last-block flag + 7 bits type +
        24 bits length. Stops at the last block (flag=1) or at the
        end of data.
        """
        types: list[int] = []
        if data[:4] != b"fLaC":
            return types
        p = 4
        while p + 4 <= len(data):
            header = data[p]
            last = (header & 0x80) != 0
            btype = header & 0x7F
            length = int.from_bytes(data[p + 1:p + 4], "big")
            types.append(btype)
            p += 4 + length
            if last:
                break
            if len(types) > 64:  # defensive
                break
        return types

    @staticmethod
    def _flac_block_name(btype: int) -> str:
        names = {
            _FLAC_BLOCK_STREAMINFO: "STREAMINFO",
            _FLAC_BLOCK_PADDING: "PADDING",
            _FLAC_BLOCK_APPLICATION: "APPLICATION",
            _FLAC_BLOCK_SEEKTABLE: "SEEKTABLE",
            _FLAC_BLOCK_VORBIS_COMMENT: "VORBIS_COMMENT",
            _FLAC_BLOCK_CUESHEET: "CUESHEET",
            _FLAC_BLOCK_PICTURE: "PICTURE",
        }
        return names.get(btype, f"RESERVED_{btype}")

    # ==================================================================
    # M4A scan (ISO BMFF audio-only)
    # ==================================================================

    def _scan_m4a(self, data: bytes, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []

        try:
            mp4 = MP4(file_path)
        except Exception as exc:  # noqa: BLE001
            findings.append(self._make_container_anomaly_finding(
                file_path,
                reason=f"M4A parse failed: {exc}",
                surface="",
            ))
            return findings

        text_fields: dict[str, str] = {}
        pictures: list[bytes] = []
        for key, value in mp4.items():
            kl = key.lower()
            if kl == "covr":
                for cov in value:
                    pictures.append(bytes(cov))
            else:
                if isinstance(value, list):
                    text_fields[kl] = " | ".join(
                        str(v) for v in value if v is not None
                    )
                else:
                    text_fields[kl] = str(value)

        findings.append(self._make_inventory_finding(
            file_path,
            container="M4A",
            inventory=(
                f"container=M4A bytes={len(data)} "
                f"itunes_atoms={len(text_fields)} pictures={len(pictures)}"
            ),
        ))

        findings.extend(self._scan_text_fields(text_fields, file_path))
        findings.extend(self._scan_lyric_fields(text_fields, file_path))
        findings.extend(self._scan_identity_fields(
            {k: v for k, v in text_fields.items() if k in _IDENTITY_TAG_KEYS},
            file_path,
        ))
        findings.extend(self._scan_high_entropy_fields(text_fields, file_path))

        for i, pic in enumerate(pictures):
            findings.extend(
                self._scan_picture_bytes(pic, file_path, i, "M4A cover art")
            )

        return findings

    # ==================================================================
    # Ogg scan
    # ==================================================================

    def _scan_ogg(self, data: bytes, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []

        try:
            ogg = OggVorbis(file_path)
        except Exception as exc:  # noqa: BLE001
            # OggOpus / OggFlac fall through mutagen.File; retry with
            # the generic entry point.
            try:
                ogg = mutagen.File(file_path)  # type: ignore[call-arg]
            except Exception as exc2:  # noqa: BLE001
                findings.append(self._make_container_anomaly_finding(
                    file_path,
                    reason=f"Ogg parse failed: {exc2}",
                    surface="",
                ))
                return findings

        text_fields: dict[str, str] = {}
        if ogg is not None and hasattr(ogg, "tags") and ogg.tags is not None:
            for k, vlist in ogg.tags:
                lv = k.lower()
                if lv in text_fields:
                    text_fields[lv] += " | " + str(vlist)
                else:
                    text_fields[lv] = str(vlist)

        findings.append(self._make_inventory_finding(
            file_path,
            container="OGG",
            inventory=(
                f"container=OGG bytes={len(data)} "
                f"vorbis_tags={len(text_fields)}"
            ),
        ))

        findings.extend(self._scan_text_fields(text_fields, file_path))
        findings.extend(self._scan_lyric_fields(text_fields, file_path))
        findings.extend(self._scan_identity_fields(
            {k: v for k, v in text_fields.items() if k in _IDENTITY_TAG_KEYS},
            file_path,
        ))
        findings.extend(self._scan_high_entropy_fields(text_fields, file_path))

        return findings

    # ==================================================================
    # Per-stem detectors
    # ==================================================================

    def _scan_text_fields(
        self, fields: dict[str, str], file_path: Path,
    ) -> list[Finding]:
        """Route every text-valued tag through ZahirTextAnalyzer's
        codepoint detectors. Emits audio_metadata_injection per field
        with concealment.
        """
        findings: list[Finding] = []
        for key, text in fields.items():
            if not text:
                continue
            zahir_findings = ZahirTextAnalyzer._check_unicode(
                text, bbox=(0.0, 0.0, 0.0, 0.0), page_idx=0,
            )
            if zahir_findings:
                labels = sorted({f.mechanism for f in zahir_findings})
                findings.append(Finding(
                    mechanism="audio_metadata_injection",
                    tier=TIER["audio_metadata_injection"],
                    confidence=0.95,
                    severity_override=SEVERITY["audio_metadata_injection"],
                    description=(
                        f"Metadata tag {key!r} carries codepoint-level "
                        f"concealment: {', '.join(labels)}. Reader-visible "
                        "text differs from the codepoints in the stream."
                    ),
                    location=f"{file_path} tag={key}",
                    surface=text[:200],
                    concealed=" | ".join(
                        zf.concealed for zf in zahir_findings if zf.concealed
                    )[:400],
                ))
        return findings

    def _scan_lyric_fields(
        self, fields: dict[str, str], file_path: Path,
    ) -> list[Finding]:
        """Lyric / comment fields additionally scan for prompt-injection
        shapes. The same field may fire both audio_metadata_injection
        (codepoint) and audio_lyrics_prompt_injection (script-shape).
        """
        findings: list[Finding] = []
        for key, text in fields.items():
            if key not in _LYRIC_TAG_KEYS:
                continue
            for pat in _LYRIC_INJECTION_PATTERNS:
                m = pat.search(text)
                if m:
                    findings.append(Finding(
                        mechanism="audio_lyrics_prompt_injection",
                        tier=TIER["audio_lyrics_prompt_injection"],
                        confidence=0.92,
                        severity_override=SEVERITY["audio_lyrics_prompt_injection"],
                        description=(
                            f"Lyric/comment tag {key!r} carries a prompt-"
                            "injection or script shape. Lyrics are the "
                            "subtitle of audio — an ingestion pipeline "
                            "reads them."
                        ),
                        location=f"{file_path} tag={key}",
                        surface=text[:200],
                        concealed=f"matched: {m.group(0)!r}",
                    ))
                    break  # one finding per field
        return findings

    def _scan_identity_fields(
        self, identity_fields: dict[str, str], file_path: Path,
    ) -> list[Finding]:
        """Detect identity-provenance anomalies (Al-Nisa 4:112).

        Calibrated conservatively in 1.1 (FRaZ: normalization destroys
        signal). Compare raw field values first:

        * Duplicate speaker/performer values across fields that should
          disagree (e.g. TPE1 == TPE2 == TCOM identical) is a subtle
          forge pattern in voice-clone pipelines that auto-fill every
          provenance slot with the target speaker's name.
        * A performer field containing codepoint concealment is
          surfaced separately by audio_metadata_injection; the
          identity-anomaly finding only fires on structural provenance
          shape.
        * Explicit fabrication markers — value matching common voice-
          cloning tool signatures ("generated by", "synthesized",
          "clonedvoice", etc.) — fire this mechanism.
        """
        findings: list[Finding] = []
        if not identity_fields:
            return findings

        # Explicit fabrication markers.
        fabrication_markers = re.compile(
            r"\b(?:generated by|synthesi[sz]ed|cloned(?:\s+voice)?|ai[\s_-]*voice|"
            r"text[\s_-]*to[\s_-]*speech|tts[\s_-]+engine)\b",
            re.IGNORECASE,
        )
        for key, value in identity_fields.items():
            if fabrication_markers.search(value):
                findings.append(Finding(
                    mechanism="audio_metadata_identity_anomaly",
                    tier=TIER["audio_metadata_identity_anomaly"],
                    confidence=0.95,
                    severity_override=SEVERITY["audio_metadata_identity_anomaly"],
                    description=(
                        f"Identity/provenance tag {key!r} carries an explicit "
                        "synthesis / TTS / voice-cloning marker. Attribution "
                        "of synthesised speech to a human speaker is tazwir "
                        "(Al-Nisa 4:112)."
                    ),
                    location=f"{file_path} tag={key}",
                    surface=value[:200],
                    concealed=f"fabrication marker in provenance field",
                ))
                return findings  # one finding per file is sufficient

        # Duplicate-across-slots pattern.
        if len(identity_fields) >= 2:
            values = list(identity_fields.values())
            # Normalise whitespace only; do NOT case-fold or strip
            # punctuation (FRaZ lesson — signal lives in the raw form).
            stripped = [v.strip() for v in values]
            if len(set(stripped)) == 1 and len(stripped[0]) > 0:
                findings.append(Finding(
                    mechanism="audio_metadata_identity_anomaly",
                    tier=TIER["audio_metadata_identity_anomaly"],
                    confidence=0.75,
                    severity_override=SEVERITY["audio_metadata_identity_anomaly"],
                    description=(
                        f"Identity/provenance tags ({', '.join(identity_fields)}) "
                        "all carry the identical value. Auto-filled provenance "
                        "across every slot is a known shape for pipeline-"
                        "generated audio (legitimate productions differentiate "
                        "performer / band / composer)."
                    ),
                    location=f"{file_path} identity-tag block",
                    surface=f"all fields = {stripped[0]!r}",
                    concealed="; ".join(identity_fields.keys()),
                ))

        return findings

    def _scan_high_entropy_fields(
        self, fields: dict[str, str], file_path: Path,
    ) -> list[Finding]:
        """Any field whose text has near-random byte entropy and length
        ≥ _HIGH_ENTROPY_MIN_LENGTH is flagged. Catches base64 /
        compressed / encrypted payloads riding as metadata.
        """
        findings: list[Finding] = []
        for key, text in fields.items():
            if len(text) < _HIGH_ENTROPY_MIN_LENGTH:
                continue
            entropy = self._shannon_entropy(text.encode("utf-8"))
            if entropy >= _HIGH_ENTROPY_THRESHOLD_BITS:
                findings.append(Finding(
                    mechanism="audio_high_entropy_metadata",
                    tier=TIER["audio_high_entropy_metadata"],
                    confidence=0.85,
                    severity_override=SEVERITY["audio_high_entropy_metadata"],
                    description=(
                        f"Metadata tag {key!r} has Shannon entropy "
                        f"{entropy:.2f} bits/byte across {len(text)} bytes — "
                        "shape of base64 / compressed / encrypted payload."
                    ),
                    location=f"{file_path} tag={key}",
                    surface=f"{text[:80]}... (length {len(text)})",
                    concealed=f"entropy={entropy:.2f} bits/byte",
                ))
        return findings

    @staticmethod
    def _shannon_entropy(data: bytes) -> float:
        if not data:
            return 0.0
        counts: dict[int, int] = {}
        for b in data:
            counts[b] = counts.get(b, 0) + 1
        total = len(data)
        return -sum(
            (c / total) * math.log2(c / total) for c in counts.values()
        )

    def _scan_embedded_pictures_id3(
        self, tags: Any, file_path: Path,
    ) -> list[Finding]:
        findings: list[Finding] = []
        for key in list(tags.keys()):
            if not key.upper().startswith("APIC"):
                continue
            try:
                frame = tags[key]
                pic_bytes = frame.data
                mime = getattr(frame, "mime", "unknown")
            except Exception:  # noqa: BLE001
                continue
            findings.extend(self._scan_picture_bytes(
                pic_bytes, file_path, 0, f"ID3 APIC ({mime})",
            ))
        return findings

    def _scan_picture_bytes(
        self, pic_bytes: bytes, file_path: Path, idx: int, source_label: str,
    ) -> list[Finding]:
        """Route embedded picture bytes through ImageAnalyzer.

        Every image-layer finding re-emerges under audio_embedded_payload
        so the evidence is attributed to the audio surface.
        """
        findings: list[Finding] = []
        # Non-image payload check — if the bytes do not start with a
        # known image magic, it is a foreign embedding.
        matched_image = any(
            pic_bytes.startswith(magic)
            for magic, _fmt in _IMAGE_MAGIC_PREFIXES
        )
        if not matched_image:
            for magic, fmt in _FOREIGN_MAGIC_PREFIXES:
                if pic_bytes.startswith(magic):
                    findings.append(Finding(
                        mechanism="audio_embedded_payload",
                        tier=TIER["audio_embedded_payload"],
                        confidence=0.95,
                        severity_override=SEVERITY["audio_embedded_payload"],
                        description=(
                            f"Audio embedded-picture slot ({source_label}) "
                            f"contains a {fmt} payload rather than an image. "
                            "Container's picture stem is being used as a "
                            "payload carrier."
                        ),
                        location=f"{file_path} {source_label} #{idx}",
                        surface=f"{source_label} carries {fmt} bytes",
                        concealed=f"{fmt} magic at picture payload",
                    ))
                    return findings
            # Unknown non-image: flag the mismatch without naming a
            # specific foreign format.
            findings.append(Finding(
                mechanism="audio_embedded_payload",
                tier=TIER["audio_embedded_payload"],
                confidence=0.75,
                severity_override=SEVERITY["audio_embedded_payload"],
                description=(
                    f"Audio embedded-picture slot ({source_label}) "
                    "contains bytes that do not match any known image "
                    "magic. The slot is being used for a non-image "
                    "embedding."
                ),
                location=f"{file_path} {source_label} #{idx}",
                surface=f"first 8 bytes: {pic_bytes[:8].hex()}",
                concealed="no image magic detected",
            ))
            return findings

        # Valid image — delegate to ImageAnalyzer.
        import tempfile, os
        suffix = ".png" if pic_bytes.startswith(b"\x89PNG") else ".jpg"
        with tempfile.NamedTemporaryFile(
            prefix="bayyinah_audio_pic_", suffix=suffix, delete=False,
        ) as fh:
            fh.write(pic_bytes)
            tmp_path = Path(fh.name)
        try:
            report = ImageAnalyzer().scan(tmp_path)
        except Exception as exc:  # noqa: BLE001
            findings.append(self._make_scan_error(
                file_path, f"Embedded picture scan failed: {exc}",
            ))
            return findings
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        for f in report.findings:
            findings.append(Finding(
                mechanism="audio_embedded_payload",
                tier=TIER["audio_embedded_payload"],
                confidence=f.confidence,
                severity_override=SEVERITY["audio_embedded_payload"],
                description=(
                    f"Embedded picture ({source_label}) carries image-layer "
                    f"concealment ({f.mechanism}). Audio containers that "
                    "embed cover art ride image-level payloads under a "
                    "surface the listener typically does not inspect."
                ),
                location=f"{file_path} {source_label} #{idx}",
                surface=f"inherited from ImageAnalyzer: {f.mechanism}",
                concealed=(f.concealed or "")[:400],
            ))
        return findings

    def _scan_pcm_lsb(
        self, raw: bytes, sampwidth: int, file_path: Path,
    ) -> list[Finding]:
        """Compute LSB uniformity over the PCM sample bytes.

        For 8-bit samples the LSB is bit 0 of each byte. For 16-bit
        little-endian samples we sample bit 0 of each low byte. A
        long run of near-50/50 LSB values is either genuine silence
        OR an LSB stego channel; the finding is labelled "candidate"
        because the analyzer cannot distinguish them without the
        signal-level stem separation registered as future work.
        """
        findings: list[Finding] = []
        if sampwidth not in (1, 2):
            return findings
        # Count LSB ones.
        if sampwidth == 1:
            lsb_bits = [b & 1 for b in raw]
        else:
            # 16-bit LE — low byte is bytes[::2].
            lsb_bits = [b & 1 for b in raw[::2]]
        n = len(lsb_bits)
        if n < _LSB_MIN_SAMPLES:
            return findings
        ones = sum(lsb_bits)
        ratio = ones / n
        deviation = abs(ratio - 0.5)
        # Also require sample entropy > 0 — a completely constant byte
        # stream (e.g. all-zero) is NOT a stego candidate, it's silence.
        unique_bytes = len(set(raw[:2048]))
        if deviation < _LSB_UNIFORMITY_THRESHOLD and unique_bytes > 32:
            findings.append(Finding(
                mechanism="audio_lsb_stego_candidate",
                tier=TIER["audio_lsb_stego_candidate"],
                confidence=0.65,  # probabilistic — not a verdict
                severity_override=SEVERITY["audio_lsb_stego_candidate"],
                description=(
                    f"PCM sample stream ({n} sampled LSBs) shows uniform "
                    f"LSB ratio {ratio:.4f} — either a genuine recording "
                    "with rich content or an LSB steganography channel. "
                    "Container-level inspection cannot distinguish the two; "
                    "signal-level source separation (future work) is "
                    "required for a verdict."
                ),
                location=f"{file_path} PCM sample data",
                surface=f"{n} LSBs sampled, ratio {ratio:.4f}",
                concealed=f"unique bytes in first 2K: {unique_bytes}",
            ))
        return findings

    # ==================================================================
    # Finding builders
    # ==================================================================

    def _make_inventory_finding(
        self, file_path: Path, container: str, inventory: str,
    ) -> Finding:
        return Finding(
            mechanism="audio_stem_inventory",
            tier=TIER["audio_stem_inventory"],
            confidence=1.0,
            severity_override=0.0,
            description=(
                f"{container} container: stem inventory enumerated "
                "during decompose pass."
            ),
            location=str(file_path),
            surface=f"container={container}",
            concealed=inventory,
        )

    def _make_container_anomaly_finding(
        self, file_path: Path, reason: str, surface: str,
    ) -> Finding:
        return Finding(
            mechanism="audio_container_anomaly",
            tier=TIER["audio_container_anomaly"],
            confidence=0.85,
            severity_override=SEVERITY["audio_container_anomaly"],
            description=reason,
            location=str(file_path),
            surface=surface,
            concealed="",
        )

    def _make_scan_error(self, file_path: Path, message: str) -> Finding:
        return Finding(
            mechanism="scan_error",
            tier=3,
            confidence=1.0,
            severity_override=0.0,
            description=message,
            location=f"analyzer:{self.name}",
            surface="",
            concealed="",
        )

    # ==================================================================
    # Error helper (BaseAnalyzer pattern — matches VideoAnalyzer)
    # ==================================================================

    def _scan_error_report(self, file_path: Path, message: str) -> IntegrityReport:
        finding = self._make_scan_error(file_path, message)
        report = IntegrityReport(
            file_path=str(file_path),
            integrity_score=0.0,
            findings=[finding],
            scan_incomplete=True,
        )
        report.error = f"{self.error_prefix}: {message}"
        return report
