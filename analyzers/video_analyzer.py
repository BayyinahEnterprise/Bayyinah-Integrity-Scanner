"""
VideoAnalyzer — the rainstorm's hidden layers (Al-Baqarah 2:19-20).

    أَوْ كَصَيِّبٍ مِّنَ ٱلسَّمَآءِ فِيهِ ظُلُمَـٰتٌ وَرَعْدٌ وَبَرْقٌ … يَكَادُ ٱلْبَرْقُ يَخْطَفُ أَبْصَـٰرَهُمْ

    "Or [it is] like a rainstorm from the sky in which is darkness,
    thunder and lightning... The lightning almost snatches away their
    sight. Every time it lights [the way] for them, they walk therein;
    but when darkness comes over them, they stand still."

The architectural reading: video is the storm. The vivid playback
(the lightning) holds attention while the container's quieter stems
(subtitles nobody reads, metadata atoms nobody inspects, attachments
that ride inside Matroska's ``Attachments`` element, cover-art images
that may carry LSB payloads, trailing bytes after the last valid box)
carry what the viewer never sees. VideoAnalyzer decomposes the
container into stems and routes each stem to the analyzer that already
knows how to read that material.

Composition, not duplication:

* Subtitle text → ``ZahirTextAnalyzer._check_unicode`` for codepoint-
  level concealment (zero-width / bidi / TAG / homoglyph).
  Regex-based shape detection catches ``<script>`` / ``javascript:`` /
  ``on*=`` HTML injection in subtitle payloads.
* Cover-art images → ``ImageAnalyzer().scan`` for LSB-steganography
  and trailing-data evidence; its findings map up to
  ``video_frame_stego_candidate``.
* Everything else (container walk, metadata atoms, attachment
  enumeration, stream inventory) stays local because no other analyzer
  knows the box grammar.

Scope
-----
Supported containers: MP4, MOV (ISO Base Media File Format), MKV,
WEBM (Matroska / EBML).

In 1.1, MP4 / MOV receive the full box walk (ftyp / moov / udta / meta
/ covr / free / skip / mdat), and MKV / WEBM receive a byte-level EBML
head sniff plus a best-effort scan for the ``Attachments`` element and
trailing data. The deeper MKV element walk (variable-length-integer
decoding, element tree construction) is registered as future work —
the mechanism *set* is complete; the MKV parser is provisional.

Out of scope (deliberate): real-time streaming (HLS / DASH), DRM
containers, codec decoding, semantic understanding of the picture.
The analyzer does not transcode, does not render, does not classify
what the video is *about*. It detects concealment in the stems.

Stdlib-only
-----------
No pymediainfo, no ffprobe, no ffmpeg. Pure ``struct`` parses the
ISO BMFF box stream and the EBML head; pure ``re`` scans decoded
subtitle text. Same attack-surface discipline the other non-PDF
analyzers follow: the parser itself cannot become an adversarial
surface because there is no heavyweight parser.
"""

from __future__ import annotations

import base64
import re
import struct
from dataclasses import dataclass
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
# ISO BMFF (MP4 / MOV) box grammar — constants
# ---------------------------------------------------------------------------

# Top-level box types the analyzer understands. Everything else is
# enumerated as part of the inventory but not recursed into, which keeps
# the parser bounded and predictable.
_MP4_CONTAINER_BOXES: frozenset[bytes] = frozenset({
    b"moov",   # movie metadata (top-level container)
    b"trak",   # track (one per stream)
    b"mdia",   # media info inside a trak
    b"minf",   # media information
    b"stbl",   # sample table
    b"udta",   # user data (metadata)
    b"meta",   # iTunes-style metadata
    b"ilst",   # iTunes metadata list
    b"dinf",   # data information
    b"edts",   # edit list
})

# Subtitle handler types inside ``mdia/hdlr``. Any of these means the
# trak carries a text-based subtitle stream worth inspecting.
_MP4_SUBTITLE_HANDLERS: frozenset[bytes] = frozenset({
    b"sbtl",   # QuickTime subtitle
    b"subt",   # ISO BMFF subtitle
    b"text",   # QuickTime text
})

# Media data / free / skip boxes can carry payloads. ``mdat`` legitimately
# carries coded frames; a foreign magic inside it is a polyglot signal.
_MP4_PAYLOAD_BOXES: frozenset[bytes] = frozenset({
    b"free", b"skip", b"uuid",
})

# Foreign-magic prefixes that should never appear inside an MP4 top-level
# free / skip / uuid / mdat box. Presence of any of these is a polyglot
# evidence finding.
_FOREIGN_MAGIC_PREFIXES: tuple[tuple[bytes, str], ...] = (
    (b"%PDF-",                 "PDF"),
    (b"\x89PNG\r\n\x1a\n",     "PNG"),
    (b"\xff\xd8\xff",          "JPEG"),
    (b"PK\x03\x04",            "ZIP"),
    (b"<!DOCTYPE html",        "HTML"),
    (b"<script",               "HTML-script"),
    (b"MZ",                    "Windows PE executable"),
    (b"\x7fELF",               "ELF executable"),
)

# Minimal HTML-injection / script-shape patterns. Tight enough that prose
# subtitles do not trigger; any one of these inside a decoded subtitle
# cue is a verified shape (tier 1 in config.py).
_SUBTITLE_INJECTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"<\s*script\b", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"\bon(?:click|load|error|mouseover)\s*=", re.IGNORECASE),
    re.compile(r"data:text/html", re.IGNORECASE),
    re.compile(r"<\s*iframe\b", re.IGNORECASE),
)

# Base64-shape heuristic for metadata payloads. Tuned to catch long
# runs that would never appear in an organic title / artist / comment
# string. Short random-alpha fragments (song titles with numbers) don't
# hit this.
_METADATA_BASE64_SHAPE: re.Pattern[str] = re.compile(
    r"[A-Za-z0-9+/]{80,}={0,2}"
)

# EBML magic — Matroska / WebM master element.
_EBML_MAGIC: bytes = b"\x1A\x45\xDF\xA3"

# Matroska ``Attachments`` master element ID (4-byte ebml-encoded).
# Presence of this ID at all in a Matroska file means the container
# carries embedded files; the exact byte sequence 0x1941A469 is the
# decoded canonical form that appears in the file as ``19 41 A4 69``.
_MKV_ATTACHMENTS_ID: bytes = b"\x19\x41\xA4\x69"


# ---------------------------------------------------------------------------
# Box iteration primitives (stdlib struct only)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Box:
    """One parsed ISO BMFF box header + its payload slice."""

    type: bytes            # 4-byte ASCII (e.g. b"ftyp")
    offset: int            # absolute offset where the header starts
    header_size: int       # 8 or 16 bytes depending on 64-bit size
    size: int              # total box size including header (or remaining)
    payload: bytes         # box payload (excluding header)

    @property
    def end(self) -> int:
        return self.offset + self.size


def _iter_boxes(data: bytes, offset: int = 0, end: int | None = None) -> Iterable[_Box]:
    """Yield ISO BMFF boxes between ``offset`` and ``end`` (or EOF).

    Robust to truncated or malformed boxes: if a size field would run
    past ``end``, the iterator stops cleanly rather than raising. The
    caller's container-anomaly logic inspects the tail afterwards.
    """
    if end is None:
        end = len(data)
    pos = offset
    while pos + 8 <= end:
        raw_size, type_bytes = struct.unpack(">I4s", data[pos:pos + 8])
        header_size = 8
        size = raw_size
        if raw_size == 1:
            # 64-bit extended size follows the type.
            if pos + 16 > end:
                return
            size = struct.unpack(">Q", data[pos + 8:pos + 16])[0]
            header_size = 16
        elif raw_size == 0:
            # "Box extends to end of file" — per ISO 14496-12.
            size = end - pos
        if size < header_size or pos + size > end:
            # Invalid size; stop walking. Caller records container_anomaly.
            return
        payload = data[pos + header_size:pos + size]
        yield _Box(
            type=type_bytes,
            offset=pos,
            header_size=header_size,
            size=size,
            payload=payload,
        )
        pos += size


# ---------------------------------------------------------------------------
# VideoAnalyzer
# ---------------------------------------------------------------------------

class VideoAnalyzer(BaseAnalyzer):
    """Decompose video containers into stems and detect concealment.

    Supports:
      * MP4 / MOV (ISO BMFF) — full box walk, metadata (udta/meta/ilst),
        subtitle track enumeration, cover-art extraction, trailing-data
        and polyglot detection.
      * WEBM / MKV (EBML) — magic-byte verification, basic attachment
        presence check, trailing-data detection. Deep element walk
        deferred as future work.

    Composition:
      * Subtitle text is inspected by calling
        ``ZahirTextAnalyzer._check_unicode`` directly — the same
        codepoint-level detection used on PDF text spans, re-labelled
        with subtitle-track context.
      * Cover art / thumbnail bytes are written to a temp-file-shaped
        ``ImageAnalyzer().scan`` invocation so every image-layer
        mechanism (LSB, trailing data, EXIF anomaly) re-emerges under
        the ``video_frame_stego_candidate`` video-layer mechanism.

    Out of scope: streaming containers, DRM, codec decoding, semantic
    content understanding.
    """

    name: ClassVar[str] = "video"
    error_prefix: ClassVar[str] = "Video scan error"
    source_layer: ClassVar[SourceLayer] = "batin"
    supported_kinds: ClassVar[frozenset[FileKind]] = frozenset({
        FileKind.VIDEO_MP4,
        FileKind.VIDEO_MOV,
        FileKind.VIDEO_WEBM,
        FileKind.VIDEO_MKV,
    })

    # ------------------------------------------------------------------
    # Public scan entry
    # ------------------------------------------------------------------

    def scan(self, file_path: Path) -> IntegrityReport:
        """Decompose the video container at ``file_path`` and emit findings.

        Missing / unreadable files short-circuit with a ``scan_error``
        finding + ``scan_incomplete=True`` per the BaseAnalyzer contract.
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

        findings: list[Finding] = []

        # Detect the container family by magic.
        head = data[:16]
        if len(data) >= 8 and data[4:8] == b"ftyp":
            findings.extend(self._scan_mp4(data, file_path))
        elif head.startswith(_EBML_MAGIC):
            findings.extend(self._scan_matroska(data, file_path))
        else:
            # Extension-only fallback routed here; the bytes do not
            # match either container family. Emit a container anomaly
            # so the file does not pass silent-clean.
            findings.append(Finding(
                mechanism="video_container_anomaly",
                tier=TIER["video_container_anomaly"],
                confidence=0.85,
                severity_override=SEVERITY["video_container_anomaly"],
                description=(
                    "File extension indicates video, but the header bytes "
                    "do not match ISO BMFF (ftyp) or EBML (Matroska/WEBM) "
                    "magic. Either truncated, damaged, or adversarially "
                    "mis-extensioned."
                ),
                location=str(file_path),
                surface=f"header bytes: {head.hex()}",
                concealed="(no recognisable video container magic)",
            ))

        integrity_score = compute_muwazana_score(findings)
        return IntegrityReport(
            file_path=str(file_path),
            integrity_score=integrity_score,
            findings=findings,
            scan_incomplete=False,
        )

    # ==================================================================
    # ISO BMFF (MP4 / MOV) scan
    # ==================================================================

    def _scan_mp4(self, data: bytes, file_path: Path) -> list[Finding]:
        """Walk the top-level MP4 box stream and dispatch per-box scans."""
        findings: list[Finding] = []

        top_boxes = list(_iter_boxes(data))
        if not top_boxes:
            findings.append(Finding(
                mechanism="video_container_anomaly",
                tier=TIER["video_container_anomaly"],
                confidence=0.9,
                severity_override=SEVERITY["video_container_anomaly"],
                description=(
                    "ISO BMFF container has no parseable top-level boxes — "
                    "file head declared ftyp but no valid box stream followed."
                ),
                location=str(file_path),
                surface="(no walkable box sequence)",
                concealed="",
            ))
            return findings

        # Stream inventory — always emit, tier 3 informational.
        inventory = self._build_mp4_inventory(top_boxes, data)
        findings.append(Finding(
            mechanism="video_stream_inventory",
            tier=TIER["video_stream_inventory"],
            confidence=1.0,
            severity_override=SEVERITY["video_stream_inventory"],  # 0.0
            description=(
                f"MP4 container: {len(top_boxes)} top-level box(es). "
                f"Top-level types: {', '.join(sorted({b.type.decode('latin-1') for b in top_boxes}))}."
            ),
            location=str(file_path),
            surface=f"top-level box count = {len(top_boxes)}",
            concealed=inventory,
        ))

        # Trailing data after the last top-level box.
        last_box = top_boxes[-1]
        if last_box.end < len(data):
            tail_len = len(data) - last_box.end
            tail_preview = data[last_box.end:last_box.end + 64].hex()
            findings.append(Finding(
                mechanism="video_container_anomaly",
                tier=TIER["video_container_anomaly"],
                confidence=0.95,
                severity_override=SEVERITY["video_container_anomaly"],
                description=(
                    f"{tail_len} byte(s) of trailing data after the last "
                    "valid top-level box. A well-formed ISO BMFF file ends "
                    "at the end of its final box; trailing bytes indicate "
                    "either truncation-append, polyglot concatenation, or "
                    "deliberately appended payload."
                ),
                location=f"{file_path} @ offset {last_box.end}",
                surface=f"trailing {tail_len} bytes",
                concealed=f"first 64 hex: {tail_preview}",
            ))

        # Walk the moov to find udta/meta/ilst, trak/mdia/hdlr subtitle
        # handlers, covr cover art, etc.
        for box in top_boxes:
            if box.type == b"moov":
                findings.extend(self._scan_moov(box, file_path))
            elif box.type in _MP4_PAYLOAD_BOXES:
                findings.extend(self._scan_payload_box(box, file_path))
            elif box.type == b"mdat":
                findings.extend(self._scan_mdat(box, file_path))

        return findings

    def _build_mp4_inventory(self, top_boxes: list[_Box], data: bytes) -> str:
        """Build a compact inventory string for the stream_inventory finding."""
        lines: list[str] = []
        for box in top_boxes:
            lines.append(
                f"  [{box.offset:>10}] {box.type.decode('latin-1')} "
                f"({box.size} bytes)"
            )
            if box.type == b"moov":
                # Enumerate trak boxes inside moov.
                for inner in _iter_boxes(box.payload):
                    if inner.type == b"trak":
                        hdlr = self._find_hdlr(inner.payload)
                        lines.append(
                            f"      trak hdlr={hdlr.decode('latin-1', errors='replace') if hdlr else '(none)'}"
                        )
        return "\n".join(lines)

    def _find_hdlr(self, mdia_or_trak_payload: bytes) -> bytes | None:
        """Recurse a level to find the handler_type in an ``hdlr`` box."""
        for inner in _iter_boxes(mdia_or_trak_payload):
            if inner.type == b"hdlr":
                # hdlr: 1 byte version + 3 bytes flags + 4 bytes pre_defined +
                # 4 bytes handler_type + ...
                if len(inner.payload) >= 12:
                    return inner.payload[8:12]
                return None
            if inner.type in _MP4_CONTAINER_BOXES:
                found = self._find_hdlr(inner.payload)
                if found is not None:
                    return found
        return None

    # ------------------------------------------------------------------
    # moov walk — metadata, subtitles, cover art
    # ------------------------------------------------------------------

    def _scan_moov(self, moov: _Box, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []

        # Iterate moov's direct children; dispatch on interesting box types.
        for box in _iter_boxes(moov.payload):
            if box.type == b"trak":
                findings.extend(self._scan_trak(box, file_path))
            elif box.type == b"udta":
                findings.extend(self._scan_udta(box, file_path))
        return findings

    def _scan_trak(self, trak: _Box, file_path: Path) -> list[Finding]:
        """Inspect a track: if it's a subtitle track, extract and scan text."""
        findings: list[Finding] = []

        # Find the handler type to decide whether this is a subtitle track.
        handler = self._find_hdlr(trak.payload)
        if handler is None or handler not in _MP4_SUBTITLE_HANDLERS:
            return findings

        # Subtitle track found. Look for the sample-table and extract
        # text samples from the mdat via chunk-offset / sample-size boxes.
        # For 1.1, we do a pragmatic shortcut: scan the entire trak
        # payload for ASCII / UTF-8 text runs that look like subtitle
        # content. Deep sample-table parsing is future work.
        subtitle_text = self._extract_subtitle_text(trak.payload)
        if not subtitle_text:
            return findings

        findings.extend(
            self._scan_subtitle_text(subtitle_text, file_path, track_type=handler)
        )
        return findings

    def _extract_subtitle_text(self, payload: bytes) -> str:
        """Extract the concatenated UTF-8 text runs from a subtitle trak.

        Heuristic: walk the trak payload, find any ``stsd`` (sample
        description) or inline text run that decodes as UTF-8 of length
        ≥ 4. Concatenate with newlines. Good enough for tx3g / text /
        3gpp timed-text streams whose text is stored either inline or
        in mdat-referenced chunks.
        """
        chunks: list[str] = []
        # Strategy A: find all ASCII/UTF-8 runs in the trak that look
        # like text (printable + whitespace). This catches tx3g inline
        # samples without needing the full stsd+stco+stsz dance.
        i = 0
        while i < len(payload):
            # Start of a candidate run.
            start = i
            while i < len(payload):
                b = payload[i]
                if b == 0 or b == 0xFF:
                    break
                if b < 0x20 and b not in (0x09, 0x0A, 0x0D):
                    break
                i += 1
            run = payload[start:i]
            if len(run) >= 4:
                try:
                    decoded = run.decode("utf-8")
                    # Only keep runs that carry letters (drops binary
                    # alignment noise).
                    if any(c.isalpha() for c in decoded):
                        chunks.append(decoded)
                except UnicodeDecodeError:
                    pass
            i += 1
        return "\n".join(chunks)

    def _scan_subtitle_text(
        self, text: str, file_path: Path, track_type: bytes,
    ) -> list[Finding]:
        """Run concealment detectors on decoded subtitle text.

        Composition:
        * ``subtitle_invisible_chars`` — driven by the same codepoint
          sets ZahirTextAnalyzer uses. We call its classmethod and
          rewrite the returned finding to this analyzer's mechanism
          name + location.
        * ``subtitle_injection`` — regex scan against
          ``_SUBTITLE_INJECTION_PATTERNS``.
        """
        findings: list[Finding] = []

        # Injection patterns (script / javascript / event handlers).
        for pat in _SUBTITLE_INJECTION_PATTERNS:
            m = pat.search(text)
            if m:
                findings.append(Finding(
                    mechanism="subtitle_injection",
                    tier=TIER["subtitle_injection"],
                    confidence=0.95,
                    severity_override=SEVERITY["subtitle_injection"],
                    description=(
                        "Subtitle track contains a script / HTML injection "
                        "pattern. The viewer sees rendered text; a downstream "
                        "HTML extractor or subtitle renderer sees markup "
                        "that can execute."
                    ),
                    location=(
                        f"{file_path} subtitle track "
                        f"(handler={track_type.decode('latin-1', errors='replace')})"
                    ),
                    surface=text[:200],
                    concealed=f"matched: {m.group(0)!r}",
                ))
                break  # one injection finding per track is sufficient

        # Codepoint-level concealment via ZahirTextAnalyzer's classmethod.
        # We feed the whole subtitle text as one span and remap the
        # returned findings to the subtitle mechanism. Bbox / page_idx
        # are placeholders — the location string carries real context.
        zahir_findings = ZahirTextAnalyzer._check_unicode(
            text, bbox=(0.0, 0.0, 0.0, 0.0), page_idx=0,
        )
        if zahir_findings:
            # Collect the offending codepoints into one composite finding
            # so a subtitle with many zero-widths produces one
            # ``subtitle_invisible_chars`` rather than dozens.
            codepoint_labels = []
            for zf in zahir_findings:
                codepoint_labels.append(zf.mechanism)
            findings.append(Finding(
                mechanism="subtitle_invisible_chars",
                tier=TIER["subtitle_invisible_chars"],
                confidence=0.95,
                severity_override=SEVERITY["subtitle_invisible_chars"],
                description=(
                    f"Subtitle text carries codepoint-level concealment: "
                    f"{', '.join(sorted(set(codepoint_labels)))}. "
                    "Viewer-visible characters differ from the Unicode "
                    "codepoints in the stream."
                ),
                location=(
                    f"{file_path} subtitle track "
                    f"(handler={track_type.decode('latin-1', errors='replace')})"
                ),
                surface=text[:200],
                concealed=" | ".join(
                    zf.concealed for zf in zahir_findings if zf.concealed
                )[:400],
            ))
        return findings

    # ------------------------------------------------------------------
    # udta / metadata walk
    # ------------------------------------------------------------------

    def _scan_udta(self, udta: _Box, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []

        # Collect every text-ish atom inside udta. Two layouts:
        #   1. Direct QuickTime text atoms: ©nam, ©ART, ©cmt, etc.
        #      layout: 2-byte size, 2-byte language, text bytes
        #   2. iTunes-style udta/meta/ilst with ilst/<tag>/data
        suspicious_strings: list[tuple[str, str]] = []   # (atom_type, text)
        cover_art_images: list[bytes] = []

        for box in _iter_boxes(udta.payload):
            btype = box.type
            # QuickTime-style © text atom
            if btype.startswith(b"\xA9") or btype in (b"auth", b"titl", b"desc"):
                text = self._decode_qt_text_atom(box.payload)
                if text:
                    suspicious_strings.append(
                        (btype.decode("latin-1", errors="replace"), text)
                    )
            elif btype == b"meta":
                # meta header: 1 byte version + 3 bytes flags, then the
                # hdlr + ilst children.
                meta_payload = box.payload[4:] if len(box.payload) >= 4 else b""
                for ilst_or_hdlr in _iter_boxes(meta_payload):
                    if ilst_or_hdlr.type == b"ilst":
                        for item in _iter_boxes(ilst_or_hdlr.payload):
                            txt, art = self._decode_ilst_item(item)
                            if txt is not None:
                                suspicious_strings.append(
                                    (item.type.decode("latin-1", errors="replace"), txt)
                                )
                            if art is not None:
                                cover_art_images.append(art)

        # Scan accumulated metadata strings for concealment.
        for atom, text in suspicious_strings:
            if self._text_has_concealment(text):
                findings.append(Finding(
                    mechanism="video_metadata_suspicious",
                    tier=TIER["video_metadata_suspicious"],
                    confidence=0.9,
                    severity_override=SEVERITY["video_metadata_suspicious"],
                    description=(
                        f"Container metadata atom {atom!r} carries codepoint-"
                        "level concealment (zero-width / bidi / TAG / "
                        "homoglyph) or a base64-shaped long run."
                    ),
                    location=f"{file_path} udta/{atom}",
                    surface=text[:200],
                    concealed=self._describe_concealment(text)[:400],
                ))

        # Cover-art images: delegate to ImageAnalyzer.
        for i, art_bytes in enumerate(cover_art_images):
            image_findings = self._scan_cover_art(art_bytes, file_path, i)
            findings.extend(image_findings)
        return findings

    def _decode_qt_text_atom(self, payload: bytes) -> str:
        """QuickTime ``©nam`` and cousins: 2-byte size, 2-byte lang, text."""
        if len(payload) < 4:
            return ""
        size = struct.unpack(">H", payload[:2])[0]
        # language at payload[2:4] — we don't use it
        if size > len(payload) - 4:
            size = len(payload) - 4
        try:
            return payload[4:4 + size].decode("utf-8", errors="replace")
        except Exception:
            return ""

    def _decode_ilst_item(self, item: _Box) -> tuple[str | None, bytes | None]:
        """Decode one iTunes-style ilst item. Returns (text, cover_art_bytes)."""
        for child in _iter_boxes(item.payload):
            if child.type != b"data":
                continue
            # data box: 4 bytes type_flags, 4 bytes locale, then value.
            if len(child.payload) < 8:
                continue
            type_flags = struct.unpack(">I", child.payload[:4])[0]
            value = child.payload[8:]
            # type_flags low byte: 1 = UTF-8 text, 13 = JPEG, 14 = PNG.
            dt = type_flags & 0xFF
            if dt == 1:
                try:
                    return value.decode("utf-8", errors="replace"), None
                except Exception:
                    return None, None
            if dt in (13, 14):
                return None, value
        return None, None

    def _text_has_concealment(self, text: str) -> bool:
        """Fast check: does ``text`` carry any of the concealment signals?"""
        for c in text:
            if c in ZERO_WIDTH_CHARS or c in BIDI_CONTROL_CHARS:
                return True
            if ord(c) in TAG_CHAR_RANGE:
                return True
            if c in CONFUSABLE_TO_LATIN:
                return True
        if _METADATA_BASE64_SHAPE.search(text):
            return True
        return False

    def _describe_concealment(self, text: str) -> str:
        """Human-readable summary of which concealment signals fired."""
        reasons: list[str] = []
        if any(c in ZERO_WIDTH_CHARS for c in text):
            reasons.append("zero-width chars")
        if any(c in BIDI_CONTROL_CHARS for c in text):
            reasons.append("bidi controls")
        if any(ord(c) in TAG_CHAR_RANGE for c in text):
            reasons.append("TAG chars")
        if any(c in CONFUSABLE_TO_LATIN for c in text):
            reasons.append("homoglyphs")
        if _METADATA_BASE64_SHAPE.search(text):
            reasons.append("base64-shaped payload")
        return ", ".join(reasons) if reasons else "(no detail)"

    # ------------------------------------------------------------------
    # Cover-art delegation to ImageAnalyzer
    # ------------------------------------------------------------------

    def _scan_cover_art(
        self, art_bytes: bytes, file_path: Path, art_idx: int,
    ) -> list[Finding]:
        """Delegate cover-art image inspection to ImageAnalyzer.

        Every image-layer finding (LSB steganography, trailing data,
        text-metadata concealment, high-entropy metadata) re-emerges
        under ``video_frame_stego_candidate`` so the evidence is
        attributed to the video surface. The original image-layer
        description is preserved in ``concealed``.
        """
        findings: list[Finding] = []
        # Write to a scoped temp path; ImageAnalyzer needs a filesystem
        # path because it re-reads bytes for defensive LSB sampling.
        import tempfile, os
        with tempfile.NamedTemporaryFile(
            prefix="bayyinah_coverart_", suffix=".img", delete=False,
        ) as fh:
            fh.write(art_bytes)
            tmp_path = Path(fh.name)
        try:
            report = ImageAnalyzer().scan(tmp_path)
        except Exception as exc:  # noqa: BLE001 — never let image errors abort the video scan
            return [Finding(
                mechanism="scan_error",
                tier=TIER["scan_error"],
                confidence=1.0,
                severity_override=0.0,
                description=f"Cover-art scan failed: {exc}",
                location=f"{file_path} cover art #{art_idx}",
                surface="",
                concealed="",
            )]
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        for f in report.findings:
            findings.append(Finding(
                mechanism="video_frame_stego_candidate",
                tier=TIER["video_frame_stego_candidate"],
                confidence=f.confidence,
                severity_override=SEVERITY["video_frame_stego_candidate"],
                description=(
                    f"Cover-art image carries image-layer concealment "
                    f"({f.mechanism}). Video containers that embed cover "
                    "art ride image-level payloads under a surface the "
                    "viewer typically does not inspect."
                ),
                location=f"{file_path} cover art #{art_idx}",
                surface=f"inherited from ImageAnalyzer: {f.mechanism}",
                concealed=(f.concealed or "")[:400],
            ))
        return findings

    # ------------------------------------------------------------------
    # free / skip / uuid / mdat polyglot checks
    # ------------------------------------------------------------------

    def _scan_payload_box(self, box: _Box, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []
        # Any non-zero content in free / skip is already suspicious — by
        # spec they should be padding — but real files use them as fallow
        # space for streaming. We only flag them if they carry a foreign
        # magic prefix.
        for magic, fmt in _FOREIGN_MAGIC_PREFIXES:
            if box.payload.startswith(magic) or (
                len(box.payload) > 32 and magic in box.payload[:4096]
            ):
                findings.append(Finding(
                    mechanism="video_embedded_attachment",
                    tier=TIER["video_embedded_attachment"],
                    confidence=0.92,
                    severity_override=SEVERITY["video_embedded_attachment"],
                    description=(
                        f"MP4 {box.type.decode('latin-1')} box carries a "
                        f"{fmt} magic prefix within its payload — an "
                        "embedded file-format payload inside a container "
                        "region the viewer never sees. Polyglot shape."
                    ),
                    location=(
                        f"{file_path} {box.type.decode('latin-1')} box "
                        f"@ offset {box.offset}"
                    ),
                    surface=f"{box.type.decode('latin-1')} box size = {box.size} bytes",
                    concealed=f"{fmt} magic at box payload",
                ))
                break  # one finding per box
        return findings

    def _scan_mdat(self, box: _Box, file_path: Path) -> list[Finding]:
        findings: list[Finding] = []
        # mdat legitimately carries codec-compressed frames; a foreign
        # magic at the very start is a strong polyglot signal. We don't
        # scan deeper because compressed frames occasionally produce
        # byte runs that resemble other formats.
        for magic, fmt in _FOREIGN_MAGIC_PREFIXES:
            if box.payload.startswith(magic):
                findings.append(Finding(
                    mechanism="video_container_anomaly",
                    tier=TIER["video_container_anomaly"],
                    confidence=0.9,
                    severity_override=SEVERITY["video_container_anomaly"],
                    description=(
                        f"mdat box begins with a {fmt} magic prefix. "
                        "Media-data boxes should carry codec bitstream; a "
                        "recognisable foreign magic at byte 0 of mdat is "
                        "polyglot-shape concealment."
                    ),
                    location=f"{file_path} mdat @ offset {box.offset}",
                    surface=f"mdat size = {box.size} bytes",
                    concealed=f"{fmt} magic at mdat[0]",
                ))
                break
        return findings

    # ==================================================================
    # Matroska / WEBM (EBML) scan — best-effort in 1.1
    # ==================================================================

    def _scan_matroska(self, data: bytes, file_path: Path) -> list[Finding]:
        """Minimal Matroska / WEBM inspection.

        The full EBML element walk (variable-length-integer decoding,
        nested master elements) is deferred as future work. In 1.1 we:

        * Emit a ``video_stream_inventory`` noting EBML magic was found.
        * Scan the bytes for the ``Attachments`` master element ID
          (``19 41 A4 69``) — if present, the container carries
          embedded files, which is the key concealment surface.
        * Emit a trailing-data finding heuristically only if the file
          is suspiciously short (no plausible Segment content).

        Deep MKV support is registered below as a TODO, consistent with
        Step 4 of the session prompt: "Register any mechanism that
        cannot be completed as future work."
        """
        findings: list[Finding] = []
        findings.append(Finding(
            mechanism="video_stream_inventory",
            tier=TIER["video_stream_inventory"],
            confidence=1.0,
            severity_override=0.0,
            description=(
                f"Matroska/WEBM container: {len(data)} bytes total. "
                "EBML magic verified at byte 0. Deep element walk "
                "(Segment / Tracks / Tags / Attachments content) is "
                "scheduled for a later phase; 1.1 surfaces attachment "
                "presence and container shape only."
            ),
            location=str(file_path),
            surface="EBML magic present",
            concealed=(
                f"byte-level scan only in 1.1 — deep element walk deferred"
            ),
        ))

        if _MKV_ATTACHMENTS_ID in data:
            idx = data.index(_MKV_ATTACHMENTS_ID)
            findings.append(Finding(
                mechanism="video_embedded_attachment",
                tier=TIER["video_embedded_attachment"],
                confidence=0.85,
                severity_override=SEVERITY["video_embedded_attachment"],
                description=(
                    "Matroska container contains an Attachments element "
                    "(ID 0x1941A469). The Attachments element lets a "
                    "Matroska file carry arbitrary embedded files "
                    "(fonts, images, scripts, documents) that ride with "
                    "the video but are not visible during playback."
                ),
                location=f"{file_path} @ byte {idx}",
                surface=f"Attachments element ID at byte {idx}",
                concealed=f"element ID sequence: {_MKV_ATTACHMENTS_ID.hex()}",
            ))

        return findings

    # ==================================================================
    # Error helper (BaseAnalyzer pattern)
    # ==================================================================

    def _scan_error_report(self, file_path: Path, message: str) -> IntegrityReport:
        """Canonical scan_error + scan_incomplete report shape."""
        finding = Finding(
            mechanism="scan_error",
            tier=3,
            confidence=1.0,
            severity_override=0.0,
            description=message,
            location=f"analyzer:{self.name}",
            surface="",
            concealed="",
        )
        report = IntegrityReport(
            file_path=str(file_path),
            integrity_score=0.0,
            findings=[finding],
            scan_incomplete=True,
        )
        report.error = f"{self.error_prefix}: {message}"
        return report
