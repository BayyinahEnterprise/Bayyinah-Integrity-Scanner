"""
Tests for analyzers.image_analyzer.ImageAnalyzer.

Phase 10 guardrails. The analyzer walks the PNG chunk stream and the
JPEG segment stream looking for: bytes after the declared end marker
(``trailing_data``), non-standard chunks/segments
(``suspicious_image_chunk``), oversized metadata payloads
(``oversized_metadata``), and human-readable text in metadata
(``image_text_metadata`` plus re-run Unicode concealment on the text).

Tests live at the analyzer level. End-to-end dispatch is covered by
``tests/test_image_fixtures.py`` and the application-level
``tests/application/test_scan_service.py``.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

import pytest

from analyzers import ImageAnalyzer
from analyzers.base import BaseAnalyzer
from domain import IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(ImageAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert ImageAnalyzer.name == "image"
    assert ImageAnalyzer.error_prefix == "Image scan error"
    assert ImageAnalyzer.source_layer == "batin"


def test_supported_kinds_covers_raster_images() -> None:
    expected = frozenset({FileKind.IMAGE_PNG, FileKind.IMAGE_JPEG})
    assert ImageAnalyzer.supported_kinds == expected


def test_supported_kinds_excludes_svg_and_pdf() -> None:
    # SvgAnalyzer owns SVG; PDF remains the legacy pipeline's scope.
    assert FileKind.IMAGE_SVG not in ImageAnalyzer.supported_kinds
    assert FileKind.PDF not in ImageAnalyzer.supported_kinds


def test_instantiable() -> None:
    a = ImageAnalyzer()
    assert a.name == "image"
    assert "ImageAnalyzer" in repr(a)


# ---------------------------------------------------------------------------
# PNG helpers
# ---------------------------------------------------------------------------


_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    length = struct.pack(">I", len(data))
    crc = struct.pack(">I", zlib.crc32(chunk_type + data) & 0xFFFFFFFF)
    return length + chunk_type + data + crc


def _minimal_png() -> bytes:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    return (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _write_png(tmp_path: Path, name: str, content: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(content)
    return p


def _scan(path: Path) -> IntegrityReport:
    return ImageAnalyzer().scan(path)


def _mechanisms(report: IntegrityReport) -> list[str]:
    return [f.mechanism for f in report.findings]


# ---------------------------------------------------------------------------
# Clean input
# ---------------------------------------------------------------------------


def test_clean_png_produces_no_findings(tmp_path: Path) -> None:
    p = _write_png(tmp_path, "clean.png", _minimal_png())
    report = _scan(p)
    assert report.findings == []
    assert report.integrity_score == 1.0
    assert not report.scan_incomplete


def test_clean_jpeg_produces_no_findings(tmp_path: Path) -> None:
    # Re-use the generator's canonical minimal JPEG.
    from tests.make_image_fixtures import _MINIMAL_JPEG
    p = tmp_path / "clean.jpg"
    p.write_bytes(_MINIMAL_JPEG)
    report = _scan(p)
    assert report.findings == []
    assert report.integrity_score == 1.0


# ---------------------------------------------------------------------------
# Trailing data
# ---------------------------------------------------------------------------


def test_trailing_data_after_png_iend_fires(tmp_path: Path) -> None:
    p = _write_png(tmp_path, "trailing.png", _minimal_png() + b"EXTRA-PAYLOAD-TAIL")
    report = _scan(p)
    assert "trailing_data" in _mechanisms(report)
    td = next(f for f in report.findings if f.mechanism == "trailing_data")
    assert td.source_layer == "batin"
    assert td.tier == 2
    assert "IEND" in td.description


def test_trailing_data_after_jpeg_eoi_fires(tmp_path: Path) -> None:
    from tests.make_image_fixtures import _MINIMAL_JPEG
    p = tmp_path / "trailing.jpg"
    p.write_bytes(_MINIMAL_JPEG + b"PAYLOAD-AFTER-EOI")
    report = _scan(p)
    assert "trailing_data" in _mechanisms(report)
    td = next(f for f in report.findings if f.mechanism == "trailing_data")
    assert "EOI" in td.description


def test_tiny_trailing_byte_count_is_tolerated(tmp_path: Path) -> None:
    # 1–3 bytes of trailing whitespace/newline is below threshold.
    p = _write_png(tmp_path, "nl.png", _minimal_png() + b"\n")
    report = _scan(p)
    assert "trailing_data" not in _mechanisms(report)


# ---------------------------------------------------------------------------
# Suspicious chunk
# ---------------------------------------------------------------------------


def test_non_standard_png_chunk_fires_suspicious(tmp_path: Path) -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"prVt", b"private-payload")
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "private.png", body)
    mechs = _mechanisms(_scan(p))
    assert "suspicious_image_chunk" in mechs


def test_standard_chunks_do_not_fire_suspicious(tmp_path: Path) -> None:
    # iCCP is a standard chunk — should not fire suspicious.
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    iccp_payload = b"profile\x00\x00" + zlib.compress(b"iccbody")
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"iCCP", iccp_payload)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "iccp.png", body)
    mechs = _mechanisms(_scan(p))
    assert "suspicious_image_chunk" not in mechs


# ---------------------------------------------------------------------------
# Text metadata + Unicode concealment
# ---------------------------------------------------------------------------


def test_png_tEXt_chunk_surfaces_as_image_text_metadata(tmp_path: Path) -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    text = _png_chunk(
        b"tEXt", b"Comment\x00Bayyinah test comment visible in metadata",
    )
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + text
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "text.png", body)
    mechs = _mechanisms(_scan(p))
    assert "image_text_metadata" in mechs
    f = next(x for x in _scan(p).findings if x.mechanism == "image_text_metadata")
    assert f.source_layer == "zahir"


def test_png_tEXt_carrying_tag_chars_fires_tag_chars(tmp_path: Path) -> None:
    payload = "".join(chr(0xE0000 + ord(c)) for c in "PWND")
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    # The fixture generator emits tEXt with UTF-8 bytes (non-spec but
    # in-the-wild); the analyzer's decoder prefers UTF-8 so the TAG
    # codepoints survive and fire.
    value = ("Hello" + payload).encode("utf-8")
    text = _png_chunk(b"tEXt", b"Comment\x00" + value)
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + text
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "tag.png", body)
    mechs = _mechanisms(_scan(p))
    assert "tag_chars" in mechs
    assert "image_text_metadata" in mechs


def test_jpeg_com_segment_surfaces_as_image_text_metadata(tmp_path: Path) -> None:
    from tests.make_image_fixtures import _jpeg_with_com_segment
    p = tmp_path / "com.jpg"
    p.write_bytes(_jpeg_with_com_segment("Bayyinah phase10 comment"))
    mechs = _mechanisms(_scan(p))
    assert "image_text_metadata" in mechs


# ---------------------------------------------------------------------------
# Oversized metadata
# ---------------------------------------------------------------------------


def test_oversized_png_text_chunk_fires(tmp_path: Path) -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    # 70 KB of text — beyond the 64 KB limit.
    huge = b"A" * (70 * 1024)
    text = _png_chunk(b"tEXt", b"Comment\x00" + huge)
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + text
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "huge.png", body)
    mechs = _mechanisms(_scan(p))
    assert "oversized_metadata" in mechs


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_file_returns_scan_error_report(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.png"
    report = _scan(missing)
    assert report.scan_incomplete
    assert report.error is not None
    assert report.error.startswith("Image scan error")
    assert [f.mechanism for f in report.findings] == ["scan_error"]
    assert report.findings[0].source_layer == "batin"


def test_not_a_png_or_jpeg_returns_scan_error(tmp_path: Path) -> None:
    # Some other bytes that the router might hand us by mistake.
    p = tmp_path / "garbage.png"
    p.write_bytes(b"definitely not a png")
    report = _scan(p)
    assert report.scan_incomplete
    assert [f.mechanism for f in report.findings] == ["scan_error"]


# ---------------------------------------------------------------------------
# Integration on Phase 10 fixtures
# ---------------------------------------------------------------------------


FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "images"


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("clean/clean.png", []),
        ("clean/clean.jpg", []),
        ("adversarial/trailing_data.png", ["trailing_data"]),
        ("adversarial/text_metadata.png", ["image_text_metadata"]),
        ("adversarial/suspicious_chunk.png", ["suspicious_image_chunk"]),
        ("adversarial/tag_chars_in_png.png",
         ["image_text_metadata", "tag_chars"]),
        ("adversarial/trailing_data.jpg", ["trailing_data"]),
        ("adversarial/jpeg_comment.jpg", ["image_text_metadata"]),
    ],
)
def test_fixture_fires_exactly_expected(
    rel: str, expected: list[str],
) -> None:
    path = FIXTURE_ROOT / rel
    if not path.exists():
        pytest.skip(f"fixture {rel} not yet generated")
    report = _scan(path)
    observed = sorted({f.mechanism for f in report.findings})
    assert observed == sorted(expected), (
        f"{rel}: expected {expected}, got {observed}"
    )


# ---------------------------------------------------------------------------
# Phase 11 — advanced PNG detectors
# ---------------------------------------------------------------------------


def test_shannon_entropy_helper_on_uniform_random_is_high() -> None:
    from analyzers.image_analyzer import _shannon_entropy
    # Deterministic pseudo-random via SHA-256 chain — high-entropy.
    import hashlib
    h = b"phase-11-entropy-helper-seed"
    buf = bytearray()
    while len(buf) < 1024:
        h = hashlib.sha256(h).digest()
        buf.extend(h)
    entropy = _shannon_entropy(bytes(buf[:1024]))
    assert entropy > 7.0


def test_shannon_entropy_helper_on_repeating_is_low() -> None:
    from analyzers.image_analyzer import _shannon_entropy
    assert _shannon_entropy(b"A" * 1024) == 0.0


def test_shannon_entropy_helper_on_empty_returns_zero() -> None:
    from analyzers.image_analyzer import _shannon_entropy
    assert _shannon_entropy(b"") == 0.0


def test_lsb_uniformity_skips_when_sample_too_small() -> None:
    from analyzers.image_analyzer import _detect_lsb_uniformity
    # 1 KB — below LSB_MIN_SAMPLES (2048).
    assert _detect_lsb_uniformity(b"\x00\x01" * 512) is None


def test_lsb_uniformity_fires_when_balanced_and_large() -> None:
    from analyzers.image_analyzer import _detect_lsb_uniformity
    sample = bytes([i & 1 for i in range(4096)])
    result = _detect_lsb_uniformity(sample)
    assert result is not None
    n, prop = result
    assert n == 4096
    assert abs(prop - 0.5) <= 0.01


def test_lsb_uniformity_silent_on_skewed() -> None:
    from analyzers.image_analyzer import _detect_lsb_uniformity
    # All-zero LSBs — natural ordered/constant image.
    assert _detect_lsb_uniformity(b"\x00" * 4096) is None


def test_multiple_idat_streams_fires_on_split_idat(tmp_path: Path) -> None:
    from tests.make_image_fixtures import _multiple_idat_png
    p = _write_png(tmp_path, "split_idat.png", _multiple_idat_png())
    mechs = _mechanisms(_scan(p))
    assert "multiple_idat_streams" in mechs


def test_contiguous_idats_do_not_fire_fragmentation(tmp_path: Path) -> None:
    # Two back-to-back IDAT chunks (no intervening non-IDAT) is NOT
    # fragmentation — contiguous IDATs are standard PNG.
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    compressed = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    half = max(1, len(compressed) // 2)
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", compressed[:half])
        + _png_chunk(b"IDAT", compressed[half:])
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "contig_idat.png", body)
    mechs = _mechanisms(_scan(p))
    assert "multiple_idat_streams" not in mechs


def test_lsb_steganography_fires_on_balanced_pixel_plane(tmp_path: Path) -> None:
    from tests.make_image_fixtures import _lsb_steganography_png
    p = _write_png(tmp_path, "lsb.png", _lsb_steganography_png())
    mechs = _mechanisms(_scan(p))
    assert "suspected_lsb_steganography" in mechs


def test_high_entropy_text_chunk_fires(tmp_path: Path) -> None:
    from tests.make_image_fixtures import _high_entropy_png
    p = _write_png(tmp_path, "entropy.png", _high_entropy_png())
    mechs = _mechanisms(_scan(p))
    assert "high_entropy_metadata" in mechs


def test_short_text_chunk_does_not_fire_entropy(tmp_path: Path) -> None:
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    text = _png_chunk(b"tEXt", b"Comment\x00short value")
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + text
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "short_text.png", body)
    mechs = _mechanisms(_scan(p))
    assert "high_entropy_metadata" not in mechs


def test_math_alphanumeric_in_png_tEXt_fires(tmp_path: Path) -> None:
    # Mathematical Alphanumeric Symbols (U+1D400..) smuggled inside
    # a metadata text chunk.
    math_payload = "\U0001D400\U0001D401\U0001D402"  # 𝐀𝐁𝐂
    value = ("Hello " + math_payload + " world").encode("utf-8")
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
    text = _png_chunk(b"tEXt", b"Comment\x00" + value)
    body = (
        _PNG_SIGNATURE
        + _png_chunk(b"IHDR", ihdr)
        + text
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )
    p = _write_png(tmp_path, "math.png", body)
    mechs = _mechanisms(_scan(p))
    assert "mathematical_alphanumeric" in mechs


# ---------------------------------------------------------------------------
# Phase 12 — generative_cipher_signature
# ---------------------------------------------------------------------------


class TestGenerativeCipherSignature:
    """The Phase 12 cipher-signature emit is gated on (1) high entropy
    being already detected, (2) payload length >= 64 bytes, and (3) the
    latin-1 decoding of the payload containing a canonical base64 or
    hex cipher-shape substring of at least 40 / 64 chars respectively.

    These tests exercise each gate independently, then the happy path
    end-to-end against the dedicated fixture builder.
    """

    def test_fires_on_generative_cipher_png_fixture(
        self, tmp_path: Path,
    ) -> None:
        """End-to-end: the Phase 12 fixture builder produces a file
        whose payload passes all three gates."""
        from tests.make_image_fixtures import _generative_cipher_png
        p = _write_png(tmp_path, "gen_cipher.png", _generative_cipher_png())
        mechs = _mechanisms(_scan(p))
        assert "generative_cipher_signature" in mechs
        # High-entropy is the prerequisite; it must co-fire.
        assert "high_entropy_metadata" in mechs

    def test_does_not_fire_without_high_entropy(
        self, tmp_path: Path,
    ) -> None:
        """Low-entropy base64 (e.g. all-A) fails the entropy gate even
        though it contains a 64-char base64 run."""
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
        idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
        # Deliberately low-entropy payload: repeated base64 char.
        low_entropy_payload = b"A" * 128
        text = _png_chunk(b"tEXt", b"Payload\x00" + low_entropy_payload)
        body = (
            _PNG_SIGNATURE
            + _png_chunk(b"IHDR", ihdr)
            + text
            + _png_chunk(b"IDAT", idat)
            + _png_chunk(b"IEND", b"")
        )
        p = _write_png(tmp_path, "low_entropy.png", body)
        mechs = _mechanisms(_scan(p))
        assert "generative_cipher_signature" not in mechs

    def test_does_not_fire_on_high_entropy_without_cipher_shape(
        self, tmp_path: Path,
    ) -> None:
        """High-entropy random bytes with no concentrated base64/hex
        run must not trigger the cipher-signature finding — entropy
        alone is not sufficient evidence of a packed payload."""
        from tests.make_image_fixtures import _high_entropy_png
        p = _write_png(tmp_path, "entropy_only.png", _high_entropy_png())
        mechs = _mechanisms(_scan(p))
        # High entropy fires, but the random byte soup does not present
        # a long consecutive base64-alphabet run, so cipher-signature
        # must stay silent.
        assert "high_entropy_metadata" in mechs
        assert "generative_cipher_signature" not in mechs

    def test_fires_on_hex_cipher_shape(self, tmp_path: Path) -> None:
        """A 64-char hex run embedded inside a high-entropy payload
        must trigger the signature via the hex regex branch.

        Uses 512 bytes of random with a 64-char hex run overlaid at
        bytes [400:464] — the random majority keeps combined Shannon
        entropy well above the 7.0 gate (empirically ~7.42 bits/byte)
        while the hex run is long enough to match ``_HEX_RE``. Placing
        the hex late in the payload also keeps it out of the
        ``image_text_metadata`` preview window.
        """
        import hashlib
        ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
        idat = zlib.compress(b"\x00" + b"\x00\x00\x00\xff")
        random_bytes = bytearray()
        seed = b"bayyinah-test-hex-cipher-seed"
        while len(random_bytes) < 512:
            seed = hashlib.sha256(seed).digest()
            random_bytes.extend(seed)
        random_bytes = bytearray(random_bytes[:512])
        hex_run = hashlib.sha256(b"hex-cipher-body").hexdigest().encode("ascii")
        assert len(hex_run) == 64
        random_bytes[400:464] = hex_run
        payload = bytes(random_bytes)
        text = _png_chunk(b"tEXt", b"Payload\x00" + payload)
        body = (
            _PNG_SIGNATURE
            + _png_chunk(b"IHDR", ihdr)
            + text
            + _png_chunk(b"IDAT", idat)
            + _png_chunk(b"IEND", b"")
        )
        p = _write_png(tmp_path, "hex_cipher.png", body)
        mechs = _mechanisms(_scan(p))
        assert "generative_cipher_signature" in mechs

    def test_concealed_field_carries_cipher_shape_payload_prefix(
        self, tmp_path: Path,
    ) -> None:
        """The emitted finding's ``concealed`` field must start with
        ``cipher-shape payload:`` — the correlation engine's extractor
        relies on that exact framing."""
        from tests.make_image_fixtures import _generative_cipher_png
        p = _write_png(tmp_path, "gen_cipher2.png", _generative_cipher_png())
        report = _scan(p)
        cipher_findings = [
            f for f in report.findings
            if f.mechanism == "generative_cipher_signature"
        ]
        assert cipher_findings
        for f in cipher_findings:
            assert f.concealed.startswith("cipher-shape payload:")

    def test_source_layer_is_batin(self, tmp_path: Path) -> None:
        """The cipher-signature finding is a structural shape, not a
        surface one — it must carry source_layer='batin'."""
        from tests.make_image_fixtures import _generative_cipher_png
        p = _write_png(tmp_path, "gen_cipher3.png", _generative_cipher_png())
        report = _scan(p)
        for f in report.findings:
            if f.mechanism == "generative_cipher_signature":
                assert f.source_layer == "batin"
