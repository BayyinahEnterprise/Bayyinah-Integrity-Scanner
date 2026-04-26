"""
Video fixture generator — Phase 24 paired clean + adversarial corpus.

Produces small (~1-5 KB) ISO BMFF (MP4) files and one Matroska (MKV)
file that exercise every new video mechanism registered in
``domain/config.py``:

  video_stream_inventory       clean.mp4 + every adversarial fixture
  subtitle_injection           subtitle_injection.mp4
  subtitle_invisible_chars     subtitle_invisible_chars.mp4
  video_metadata_suspicious    metadata_suspicious.mp4
  video_embedded_attachment    embedded_attachment.mp4, attachments.mkv
  video_frame_stego_candidate  cover_art_stego.mp4
  video_container_anomaly      trailing_data.mp4, mdat_polyglot.mp4
  video_cross_stem_divergence  cross_stem_divergence.mp4

Stdlib-only: every fixture is synthesised with ``struct`` + raw bytes.
No ffmpeg, no pymediainfo. The resulting files are not playable media
(they have no coded frames), but they are byte-valid ISO BMFF / EBML
as far as the analyzer's container walk is concerned, which is the
only surface under test.

Run as a module from the repo root::

    python -m tests.make_video_fixtures
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "video"


# ---------------------------------------------------------------------------
# ISO BMFF box helpers
# ---------------------------------------------------------------------------

def _box(box_type: bytes, payload: bytes) -> bytes:
    """Build one ISO BMFF box: 4-byte size + 4-byte type + payload."""
    size = 8 + len(payload)
    return struct.pack(">I", size) + box_type + payload


def _ftyp(major_brand: bytes = b"isom") -> bytes:
    """Minimal ftyp box with the common ``isom``/``mp41`` brand set."""
    payload = major_brand + struct.pack(">I", 512) + b"isom" + b"mp41"
    return _box(b"ftyp", payload)


def _mvhd() -> bytes:
    """Minimal movie header — 32-bit version, zero timestamps, duration 1s."""
    payload = struct.pack(
        ">BBBBIIIII",
        0, 0, 0, 0,          # version + 3 bytes flags
        0,                   # creation_time
        0,                   # modification_time
        1000,                # timescale
        1000,                # duration
        0x00010000,          # rate (1.0)
    )
    # volume (2 bytes) + reserved (2+2*4=10) + matrix (9*4=36) + pre_defined (6*4=24) + next_track_ID
    payload += struct.pack(">H", 0x0100)  # volume
    payload += b"\x00" * 10
    payload += struct.pack(">9I", 0x00010000, 0, 0, 0, 0x00010000, 0, 0, 0, 0x40000000)
    payload += b"\x00" * 24
    payload += struct.pack(">I", 2)  # next_track_ID
    return _box(b"mvhd", payload)


def _hdlr(handler_type: bytes, name: bytes = b"Bayyinah Fixture") -> bytes:
    """Handler reference box — declares the track's handler_type."""
    payload = struct.pack(
        ">BBBBI4sIII",
        0, 0, 0, 0,          # version + flags
        0,                   # pre_defined
        handler_type,        # handler_type (4 bytes)
        0, 0, 0,             # reserved[3]
    )
    payload += name + b"\x00"
    return _box(b"hdlr", payload)


def _trak_subtitle(subtitle_text: str, handler: bytes = b"sbtl") -> bytes:
    """Build a minimal trak box for a subtitle track.

    For fixture purposes the subtitle text is stored inline in the trak
    payload so VideoAnalyzer's best-effort text extractor picks it up.
    Real-world tx3g streams store samples in mdat referenced by the
    sample table; the analyzer's heuristic handles both because it
    scans for UTF-8 text runs anywhere in the trak payload.
    """
    mdia = _box(b"mdia", _hdlr(handler) + subtitle_text.encode("utf-8"))
    return _box(b"trak", mdia)


def _udta_qt_title(text: str) -> bytes:
    """QuickTime-style udta/©nam title atom with the given text."""
    # ©nam atom: 2-byte size, 2-byte lang (0x55C4 = und), text bytes.
    encoded = text.encode("utf-8")
    nam_payload = struct.pack(">HH", len(encoded), 0x55C4) + encoded
    nam = _box(b"\xA9nam", nam_payload)
    return _box(b"udta", nam)


def _udta_with_cover_art(title: str, cover_art_png: bytes) -> bytes:
    """udta containing meta/ilst with a title and an embedded cover art."""
    # meta: 4 bytes (version+flags), then hdlr + ilst.
    meta_prefix = b"\x00\x00\x00\x00"
    # hdlr for meta: handler_type 'mdir' (metadata), pre_defined, name 'appl'
    meta_hdlr = _hdlr(b"mdir")
    # ilst / ©nam / data
    title_encoded = title.encode("utf-8")
    # data box: 4-byte type_flags (UTF-8 = 1), 4-byte locale, value.
    title_data_box = _box(
        b"data",
        struct.pack(">II", 1, 0) + title_encoded,
    )
    nam_item = _box(b"\xA9nam", title_data_box)
    # cover art: type_flags 14 = PNG.
    cover_data_box = _box(
        b"data",
        struct.pack(">II", 14, 0) + cover_art_png,
    )
    covr_item = _box(b"covr", cover_data_box)
    ilst = _box(b"ilst", nam_item + covr_item)
    meta = _box(b"meta", meta_prefix + meta_hdlr + ilst)
    return _box(b"udta", meta)


def _moov(trak_boxes: list[bytes], udta_box: bytes = b"") -> bytes:
    """Build a moov box containing mvhd + each trak + optional udta."""
    payload = _mvhd()
    for t in trak_boxes:
        payload += t
    payload += udta_box
    return _box(b"moov", payload)


def _mdat(payload: bytes) -> bytes:
    """Media data box (intentionally empty or with test payload)."""
    return _box(b"mdat", payload)


def _free(payload: bytes) -> bytes:
    """Free / skip padding box."""
    return _box(b"free", payload)


# ---------------------------------------------------------------------------
# Minimal PNG synthesiser (for cover-art fixtures)
# ---------------------------------------------------------------------------

def _minimal_png(trailing_junk: bytes = b"") -> bytes:
    """Build a minimal 1x1 transparent PNG plus optional trailing junk.

    The cover-art fixture uses ``trailing_junk`` to provoke
    ImageAnalyzer's ``trailing_data`` detector, which VideoAnalyzer
    re-emerges as ``video_frame_stego_candidate``.
    """
    def _chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    # 1-pixel transparent scanline: filter(0) + 4 bytes RGBA.
    raw_row = b"\x00\x00\x00\x00\x00"
    idat = zlib.compress(raw_row)
    return (
        signature
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
        + trailing_junk
    )


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def build_clean_mp4() -> bytes:
    """Minimal valid MP4 with one video-like trak and benign udta title."""
    ftyp = _ftyp(b"isom")
    trak = _trak_subtitle("Bayyinah fixture test subtitle\n", handler=b"vide")
    udta = _udta_qt_title("Clean Fixture")
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 64)
    return ftyp + moov + mdat


def build_subtitle_invisible_chars_mp4() -> bytes:
    """MP4 whose subtitle track contains U+200B + U+202E codepoints."""
    ftyp = _ftyp(b"isom")
    subtitle = "Hello\u200b world\u202e reversed"
    trak = _trak_subtitle(subtitle, handler=b"sbtl")
    udta = _udta_qt_title("subtitle invisible chars")
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + mdat


def build_subtitle_injection_mp4() -> bytes:
    """MP4 whose subtitle track carries ``<script>`` injection."""
    ftyp = _ftyp(b"isom")
    subtitle = "Normal line\nanother line\n<script>alert('x')</script>\nmore text"
    trak = _trak_subtitle(subtitle, handler=b"sbtl")
    udta = _udta_qt_title("subtitle injection")
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + mdat


def build_metadata_suspicious_mp4() -> bytes:
    """MP4 whose udta title carries a zero-width char + TAG char payload."""
    ftyp = _ftyp(b"isom")
    suspicious_title = "Totally\u200b Normal\u202e Title\U000E0041"
    trak = _trak_subtitle("clean subtitle text", handler=b"vide")
    udta = _udta_qt_title(suspicious_title)
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + mdat


def build_embedded_attachment_mp4() -> bytes:
    """MP4 with a free box carrying a foreign %PDF- magic payload."""
    ftyp = _ftyp(b"isom")
    trak = _trak_subtitle("clean subtitle", handler=b"vide")
    udta = _udta_qt_title("embedded attachment fixture")
    moov = _moov([trak], udta)
    # free box payload starts with PDF magic — the polyglot shape.
    pdf_payload = b"%PDF-1.4\n% fake pdf for fixture\n" + b"\x00" * 64
    free = _free(pdf_payload)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + free + mdat


def build_cover_art_stego_mp4() -> bytes:
    """MP4 with udta/meta/covr PNG that has trailing data after IEND."""
    ftyp = _ftyp(b"isom")
    trak = _trak_subtitle("clean subtitle", handler=b"vide")
    # 128 bytes of trailing junk after PNG IEND — ImageAnalyzer catches this.
    tampered_png = _minimal_png(trailing_junk=b"HIDDEN-PAYLOAD-" + b"X" * 128)
    udta = _udta_with_cover_art("cover art stego", tampered_png)
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + mdat


def build_trailing_data_mp4() -> bytes:
    """MP4 followed by 256 bytes of trailing garbage past the last box."""
    ftyp = _ftyp(b"isom")
    trak = _trak_subtitle("clean subtitle", handler=b"vide")
    udta = _udta_qt_title("trailing data fixture")
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 16)
    # 256 bytes of non-box garbage after the final mdat.
    trailing = b"TRAIL" + b"\xEF" * 251
    return ftyp + moov + mdat + trailing


def build_mdat_polyglot_mp4() -> bytes:
    """MP4 whose mdat payload begins with the PNG magic signature."""
    ftyp = _ftyp(b"isom")
    trak = _trak_subtitle("clean subtitle", handler=b"vide")
    udta = _udta_qt_title("mdat polyglot fixture")
    moov = _moov([trak], udta)
    # mdat begins with PNG magic bytes — polyglot shape.
    mdat = _mdat(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    return ftyp + moov + mdat


def build_cross_stem_divergence_mp4() -> bytes:
    """MP4 whose subtitle track language disagrees with its container title.

    1.1 shortcut: we use a subtitle text that claims one language and
    a udta title in a visibly different script — the analyzer currently
    does not detect linguistic divergence, so this fixture provokes a
    simpler shape: two distinct titles carried in udta vs a per-track
    text hint. The cross-stem divergence mechanism is registered in
    config; adversarial detection for it is registered as FUTURE WORK
    in tests/test_video_fixtures.py.

    The file itself is still a valid MP4; the analyzer's current
    detectors will fire ``video_metadata_suspicious`` (if concealment
    is present) but not the divergence mechanism itself. The fixture
    therefore tests the NULL path (cross-stem divergence should NOT
    fire spuriously on a normally divergent fixture).
    """
    ftyp = _ftyp(b"isom")
    trak_en = _trak_subtitle("English subtitle track", handler=b"sbtl")
    trak_fr = _trak_subtitle("Sous-titre francais", handler=b"sbtl")
    udta = _udta_qt_title("Multilingual Video Title")
    moov = _moov([trak_en, trak_fr], udta)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + mdat


# ---------------------------------------------------------------------------
# Phase 25+ — correlation fixtures for CrossModalCorrelationEngine.
# ---------------------------------------------------------------------------
#
# These two fixtures exist to prove the ``cross_stem_undeclared_text``
# rule behaves correctly across the aligned / divergent axis. They are
# scanned by the existing fixture walker against the BASE video
# mechanisms (each fixture fires exactly what the upstream analyzer
# detects), and separately by the correlation-engine tests that
# post-process each fixture's report.
#
# Aligned case: subtitle stem carries invisible-char concealment AND
# the metadata stem ALSO carries concealment whose content declares
# that the file contains textual material ("caption"). When the
# correlation engine reads these stems together it sees that the
# metadata *acknowledges* textual content — the stems agree on the
# outward surface, even though each independently carries concealment
# the reader should see. The correlation rule therefore stays silent.
#
# Undeclared case: subtitle stem carries invisible-char concealment
# BUT the metadata stem is completely silent (clean title, no
# concealment finding). The correlation engine sees subtitle
# evidence + empty metadata stem → cross_stem_undeclared_text fires.


def build_correlation_aligned_mp4() -> bytes:
    """MP4 whose subtitle and metadata stems are both non-silent and
    whose metadata declares textual content.

    Built so that:
      * subtitle_invisible_chars fires (subtitle track contains ZWSP).
      * video_metadata_suspicious fires (udta title contains ZWSP +
        a caption-declaration keyword that also gets flagged as an
        unusual codepoint payload).
      * The metadata surface includes the word "captions", so the
        correlation rule sees that the metadata declares text and
        stays silent on cross_stem_undeclared_text.
    """
    ftyp = _ftyp(b"isom")
    subtitle_text = "Hello\u200b world — captioned dialog"
    trak = _trak_subtitle(subtitle_text, handler=b"sbtl")
    # Metadata title contains a zero-width char so video_metadata_
    # suspicious fires (its surface/concealed will contain the literal
    # title, which includes the word "captions") — the analyzer's
    # description also mentions "caption" indirectly through the
    # preserved title, satisfying the alignment keyword.
    suspicious_title = "Captions Included\u200b — Subtitles On"
    udta = _udta_qt_title(suspicious_title)
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + mdat


def build_correlation_undeclared_mp4() -> bytes:
    """MP4 whose subtitle stem carries substantive concealment but
    whose metadata stem is completely silent.

    Built so that:
      * subtitle_invisible_chars fires (subtitle track contains ZWSP +
        a RLO bidi override).
      * video_metadata_suspicious does NOT fire (clean udta title).
      * The file has a subtitle track with real text, but the metadata
        gives no warning of textual content — the correlation engine
        sees subtitle evidence with no metadata-stem activity and
        fires cross_stem_undeclared_text.
    """
    ftyp = _ftyp(b"isom")
    subtitle_text = "Hidden payload\u200b in subtitle\u202e reversed"
    trak = _trak_subtitle(subtitle_text, handler=b"sbtl")
    # Clean title — no zero-width, no TAG, no bidi.
    udta = _udta_qt_title("Nature Documentary Episode 3")
    moov = _moov([trak], udta)
    mdat = _mdat(b"\x00" * 32)
    return ftyp + moov + mdat


# ---------------------------------------------------------------------------
# Minimal Matroska (WEBM/MKV) with Attachments element ID
# ---------------------------------------------------------------------------

def build_attachments_mkv() -> bytes:
    """Bare EBML magic + Attachments element ID at an easily-scannable offset.

    The analyzer's MKV path in 1.1 is a byte-level scan for the
    ``Attachments`` element ID (``19 41 A4 69``). A minimal file that
    carries EBML magic followed by the attachment ID a short distance
    in is enough to fire ``video_embedded_attachment``.
    """
    return (
        b"\x1A\x45\xDF\xA3"            # EBML master magic
        + b"\x01" * 20                  # EBML header body placeholder
        + b"\x18\x53\x80\x67"           # Segment ID (not used but realistic)
        + b"\x01" * 16                  # Segment body placeholder
        + b"\x19\x41\xA4\x69"           # Attachments element ID (the signal)
        + b"\x01" * 64                  # Attachments body placeholder
    )


# ---------------------------------------------------------------------------
# Fixture catalogue + dispatch
# ---------------------------------------------------------------------------

FIXTURES: dict[str, tuple[str, callable]] = {
    "clean/clean.mp4":
        ("Minimal valid MP4 with benign title and subtitle.", build_clean_mp4),
    "adversarial/subtitle_invisible_chars.mp4":
        ("MP4 with U+200B + U+202E in subtitle text.", build_subtitle_invisible_chars_mp4),
    "adversarial/subtitle_injection.mp4":
        ("MP4 with <script> in subtitle text.", build_subtitle_injection_mp4),
    "adversarial/metadata_suspicious.mp4":
        ("MP4 with zero-width + TAG chars in udta title.", build_metadata_suspicious_mp4),
    "adversarial/embedded_attachment.mp4":
        ("MP4 with %PDF- payload inside a free box.", build_embedded_attachment_mp4),
    "adversarial/cover_art_stego.mp4":
        ("MP4 with cover-art PNG that has trailing data.", build_cover_art_stego_mp4),
    "adversarial/trailing_data.mp4":
        ("MP4 with 256 bytes of garbage after the last box.", build_trailing_data_mp4),
    "adversarial/mdat_polyglot.mp4":
        ("MP4 whose mdat begins with PNG magic.", build_mdat_polyglot_mp4),
    "adversarial/cross_stem_divergence.mp4":
        ("MP4 with two subtitle tracks in different languages.", build_cross_stem_divergence_mp4),
    "adversarial/attachments.mkv":
        ("MKV bytes including Attachments element ID.", build_attachments_mkv),
    # Phase 25+ — correlation fixtures. Both files carry upstream
    # concealment findings; they differ in the metadata stem's
    # content and are used by the correlation-engine test file to
    # verify the cross_stem_undeclared_text rule's
    # aligned-vs-divergent behaviour.
    "adversarial/correlation_aligned.mp4":
        ("Both subtitle + metadata stems non-silent; metadata "
         "declares captions — correlation rule stays silent.",
         build_correlation_aligned_mp4),
    "adversarial/correlation_undeclared.mp4":
        ("Subtitle stem loud; metadata stem silent — correlation "
         "rule fires cross_stem_undeclared_text.",
         build_correlation_undeclared_mp4),
}


# ---------------------------------------------------------------------------
# Expectations table — the single source of truth for what each fixture proves.
#
# Mirrors ``IMAGE_FIXTURE_EXPECTATIONS`` in ``make_image_fixtures.py``. Maps
# relative fixture path to the set of mechanisms that MUST fire on that
# fixture when scanned through the full ``ScanService`` pipeline. The
# always-on ``video_stream_inventory`` is listed for every fixture because
# the analyzer emits it unconditionally as the decomposition log.
#
# ``cross_stem_divergence.mp4`` deliberately expects ONLY the inventory
# finding — the divergence detector itself is registered as future work
# (see VideoAnalyzer docstring). The fixture therefore tests the NULL
# path: the divergence mechanism must not fire spuriously on a legally
# multilingual video.
# ---------------------------------------------------------------------------

VIDEO_FIXTURE_EXPECTATIONS: dict[str, set[str]] = {
    "clean/clean.mp4": {
        "video_stream_inventory",
    },
    "adversarial/subtitle_invisible_chars.mp4": {
        "video_stream_inventory",
        "subtitle_invisible_chars",
    },
    "adversarial/subtitle_injection.mp4": {
        "video_stream_inventory",
        "subtitle_injection",
    },
    "adversarial/metadata_suspicious.mp4": {
        "video_stream_inventory",
        "video_metadata_suspicious",
    },
    "adversarial/embedded_attachment.mp4": {
        "video_stream_inventory",
        "video_embedded_attachment",
    },
    "adversarial/cover_art_stego.mp4": {
        "video_stream_inventory",
        "video_frame_stego_candidate",
    },
    "adversarial/trailing_data.mp4": {
        "video_stream_inventory",
        "video_container_anomaly",
    },
    "adversarial/mdat_polyglot.mp4": {
        "video_stream_inventory",
        "video_container_anomaly",
    },
    "adversarial/cross_stem_divergence.mp4": {
        # NULL case — the divergence detector is future work; the
        # fixture proves the analyzer does not fire spuriously on a
        # normally multilingual file.
        "video_stream_inventory",
    },
    "adversarial/attachments.mkv": {
        "video_stream_inventory",
        "video_embedded_attachment",
    },
    # Phase 25+ correlation fixtures — the fixture walker runs the
    # BASE analyzer only, so each fixture's expected base-mechanism
    # set is declared here. The cross-modal rule behaviour is tested
    # separately in tests/analyzers/test_cross_modal_correlation.py.
    "adversarial/correlation_aligned.mp4": {
        "video_stream_inventory",
        "subtitle_invisible_chars",
        "video_metadata_suspicious",
    },
    "adversarial/correlation_undeclared.mp4": {
        "video_stream_inventory",
        "subtitle_invisible_chars",
    },
}


def generate_all(root: Path | None = None) -> None:
    """Rebuild every fixture under ``root`` (defaults to FIXTURE_ROOT).

    Mirrors the shape of ``tests.make_image_fixtures.generate_all`` so
    ``tests/test_video_fixtures.py`` can invoke it as a session-scoped
    auto-fixture when any file is missing.
    """
    target = Path(root) if root is not None else FIXTURE_ROOT
    target.mkdir(parents=True, exist_ok=True)
    (target / "clean").mkdir(exist_ok=True)
    (target / "adversarial").mkdir(exist_ok=True)
    for rel, (_desc, fn) in FIXTURES.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fn())


def main() -> None:
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    (FIXTURE_ROOT / "clean").mkdir(exist_ok=True)
    (FIXTURE_ROOT / "adversarial").mkdir(exist_ok=True)

    built = 0
    for rel, (_desc, fn) in FIXTURES.items():
        path = FIXTURE_ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(fn())
        built += 1
        print(f"  OK    video.{path.stem:<30s} -> {path.relative_to(FIXTURE_ROOT.parent.parent)}")
    print(f"\nBuilt {built} video fixtures.")


if __name__ == "__main__":
    main()
