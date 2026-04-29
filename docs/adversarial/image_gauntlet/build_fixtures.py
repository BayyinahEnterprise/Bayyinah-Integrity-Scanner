"""
Image (PNG / JPEG / SVG) adversarial gauntlet — fixture builder.

Six concealment techniques targeting v1.1.1 ``ImageAnalyzer`` and
``SvgAnalyzer`` gaps. We deliberately avoid the well-armored vectors:
PNG tEXt / iTXt / zTXt human-readable text (caught by
``image_text_metadata``), trailing data after IEND/EOI (caught by
``trailing_data``), oversized metadata (caught), suspicious PNG chunks
(caught), JPEG COM / APP1 / APP13 text (caught), high-entropy
ICC/EXIF (caught), SVG <script> / <foreignObject> / on* handlers /
data: URIs / external xlink:href (caught), SVG opacity:0 / display:none
/ visibility:hidden / fill:none / fill-opacity:0 (caught), SVG
microscopic font (caught), SVG zero-width / TAG / bidi / homoglyph /
math-alphanumeric (caught).

Surface text mentions $1,000 in revenue. Hidden payload mentions
$10,000. Same canonical contract-fraud setup.

Fixtures
--------

01: JPEG with payload in APP4 marker (analyzer skips APP4)
02: PNG with payload inside a custom non-text ancillary chunk whose
    length is tiny (escapes oversized_metadata threshold; the chunk
    type is private + ancillary so it bypasses suspicious-chunk
    critical-only logic)
02_5 (v1.1.2): PNG with payload in a public tEXt chunk that exhibits
    concealment triggers (bidi codepoints, zero-width characters, or
    length above the metadata threshold). Parallel-structure to
    pdf_metadata_analyzer's four-trigger pattern.
03: SVG <text fill="#FFFFFF"> on white background (white-on-white not
    in SVG_INVISIBLE_ATTRIBUTES)
04: SVG <title> element with payload (assistive-tech only; not
    scanned by SvgAnalyzer's hidden / microscopic detectors)
04_5 (v1.1.2): SVG <desc> element with multi-paragraph payload
    exceeding the desc threshold (256 bytes). Title and desc share
    structural shape but have different legitimate-use length
    distributions, so they are split into separate mechanisms with
    separate thresholds.
05: SVG <metadata> element with payload (RDF / Dublin Core block)
06: SVG <text> nested inside <defs> (not rendered until referenced;
    analyzer does not gate on render visibility for <defs> children)
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

SURFACE_TEXT = (
    "Q3 financial summary - revenue grew 8% YoY to $1,000 thousand. "
    "Margins held steady. Cash position remains strong."
)
HIDDEN_PAYLOAD = (
    "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex"
)


# ---------------------------------------------------------------------------
# Minimal valid PNG / JPEG generators (no PIL dependency)
# ---------------------------------------------------------------------------


def _png_bytes(idat: bytes) -> bytes:
    """Return a minimal valid 1x1 PNG with the given idat content.

    The fixture builder does not need a real image; it needs a parseable
    file. Bayyinah's ImageAnalyzer walks chunks, not pixels.
    """
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    idat_chunk = _chunk(b"IDAT", idat)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat_chunk + iend


def _chunk(chunk_type: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(
        ">I", crc,
    )


def _png_with_extra_chunk(chunk_type: bytes, chunk_data: bytes) -> bytes:
    """Build a 1x1 PNG with an extra ancillary chunk inserted before IEND."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    # Minimal IDAT for a 1x1 grayscale image (filter byte + 1 sample)
    raw = b"\x00\x00"
    compressed = zlib.compress(raw)
    idat = _chunk(b"IDAT", compressed)
    extra = _chunk(chunk_type, chunk_data)
    iend = _chunk(b"IEND", b"")
    return sig + ihdr + idat + extra + iend


def _jpeg_with_app_marker(marker: int, payload: bytes) -> bytes:
    """Build a tiny JPEG with the given APPn marker carrying payload."""
    soi = b"\xff\xd8"
    # APPn segment: 0xFF, marker, length (big-endian, includes itself)
    seg_len = len(payload) + 2
    appn = bytes([0xFF, marker]) + struct.pack(">H", seg_len) + payload
    # Minimal SOF0 + SOS + EOI to keep the file vaguely well-formed
    sof0 = (
        b"\xff\xc0"  # SOF0 marker
        b"\x00\x11"  # length
        b"\x08\x00\x01\x00\x01\x03"  # 8-bit, 1x1, 3 components
        b"\x01\x22\x00"
        b"\x02\x11\x01"
        b"\x03\x11\x01"
    )
    # An empty DQT minimal table
    dqt = b"\xff\xdb\x00\x43\x00" + b"\x10" * 64
    # An empty DHT minimal table
    dht = (
        b"\xff\xc4\x00\x1f\x00"
        + b"\x00" * 16
        + bytes(range(0, 12))
    )
    sos = (
        b"\xff\xda"
        b"\x00\x0c"
        b"\x03"
        b"\x01\x00\x02\x11\x03\x11"
        b"\x00\x3f\x00"
    )
    # Some entropy-coded data byte
    ecs = b"\x00"
    eoi = b"\xff\xd9"
    return soi + appn + dqt + sof0 + dht + sos + ecs + eoi


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def fixture_01_jpeg_app4_payload() -> tuple[Path, str]:
    """Payload in APP4 (0xFFE4) — analyzer skips this marker."""
    path = OUT / "01_jpeg_app4_payload.jpg"
    payload = HIDDEN_PAYLOAD.encode("utf-8")
    path.write_bytes(_jpeg_with_app_marker(0xE4, payload))
    return path, "Payload in JPEG APP4 marker (skipped by extractor)"


def fixture_02_png_private_chunk() -> tuple[Path, str]:
    """Payload in a private ancillary PNG chunk type ``prVt``.

    Lower-case-first-letter chunk types are 'ancillary' per spec.
    Lower-case-second-letter is 'private'. Together: a private
    ancillary chunk is a documented PNG mechanism for vendor
    metadata. Bayyinah's ``_iter_png_chunks`` only emits
    ``image_text_metadata`` for tEXt / zTXt / iTXt; private chunks
    fall through to the ``suspicious_image_chunk`` branch only when
    they are *critical* (upper-case first letter). Lower-case-first
    is ancillary and skipped.

    The payload here is short enough to slip under the
    ``oversized_metadata`` byte threshold while still containing the
    full natural-language string. A determined attacker uses many
    short prVt chunks; we use one for the proof-of-miss.
    """
    path = OUT / "02_png_private_chunk.png"
    chunk_type = b"prVt"  # ancillary, private, ascii-friendly
    chunk_data = HIDDEN_PAYLOAD.encode("utf-8")
    path.write_bytes(_png_with_extra_chunk(chunk_type, chunk_data))
    return path, "Payload in private ancillary PNG chunk 'prVt'"


def fixture_03_svg_white_text() -> tuple[Path, str]:
    """SVG <text> with fill="#FFFFFF" on white background.

    SVG_INVISIBLE_ATTRIBUTES['fill'] is {"none", "transparent"} only.
    A solid white fill on a default white canvas renders zero contrast
    but the analyzer does not flag it.
    """
    path = OUT / "03_svg_white_text.svg"
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="400" height="200" viewBox="0 0 400 200">\n'
        '  <rect width="400" height="200" fill="#FFFFFF"/>\n'
        '  <text x="20" y="50" fill="#000000" font-size="14">'
        f'{SURFACE_TEXT}</text>\n'
        '  <text x="20" y="100" fill="#FFFFFF" font-size="14">'
        f'{HIDDEN_PAYLOAD}</text>\n'
        '</svg>\n'
    )
    path.write_text(svg, "utf-8")
    return path, "SVG <text fill=#FFFFFF> on white <rect> background"


def fixture_04_svg_title_payload() -> tuple[Path, str]:
    """SVG <title> element with payload.

    <title> is read by assistive technology and shown as a tooltip,
    but is not scanned by hidden / microscopic detectors. Indexers
    and LLMs reading the SVG ingest it.
    """
    path = OUT / "04_svg_title_payload.svg"
    # Title payload exceeds the 64-byte threshold so the
    # svg_title_payload mechanism fires on the length structural
    # signal alone. Includes HIDDEN_TEXT_PAYLOAD / $10,000 markers
    # for the standard payload-recovery assertion.
    title_payload = (
        "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 - see annex "
        "appendix B for full reconciliation table"
    )
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="400" height="100">\n'
        f'  <title>{title_payload}</title>\n'
        f'  <text x="20" y="50">{SURFACE_TEXT}</text>\n'
        '</svg>\n'
    )
    path.write_text(svg, "utf-8")
    return path, "SVG <title> element carries the payload"


def fixture_05_svg_metadata_payload() -> tuple[Path, str]:
    """SVG <metadata> element with payload (RDF block).

    <metadata> is the canonical SVG location for arbitrary author
    metadata. Not scanned by hidden / microscopic detectors.
    """
    path = OUT / "05_svg_metadata_payload.svg"
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'width="400" height="100">\n'
        '  <metadata>\n'
        '    <rdf:RDF>\n'
        '      <rdf:Description>\n'
        '        <dc:title>Q3 financial summary chart</dc:title>\n'
        '        <dc:creator>Acme Finance Team</dc:creator>\n'
        f'        <dc:description>{HIDDEN_PAYLOAD} '
        'Detailed restatement: prior-quarter offset reconciled, '
        'auditor sign-off pending review.</dc:description>\n'
        '      </rdf:Description>\n'
        '    </rdf:RDF>\n'
        '  </metadata>\n'
        f'  <text x="20" y="50">{SURFACE_TEXT}</text>\n'
        '</svg>\n'
    )
    path.write_text(svg, "utf-8")
    return path, "SVG <metadata> element with payload in dc:description"


def fixture_06_svg_defs_text() -> tuple[Path, str]:
    """Text element nested inside <defs> — declared but not rendered.

    <defs> children are referenced by id and rendered only via <use>.
    A <text> inside <defs> with no matching <use> is in the document
    but never appears on the canvas. The analyzer does not gate
    visibility on render context, so a <text> inside <defs> falls
    through silently.
    """
    path = OUT / "06_svg_defs_text.svg"
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="400" height="100">\n'
        '  <defs>\n'
        f'    <text id="hidden-payload" x="0" y="0">{HIDDEN_PAYLOAD}</text>\n'
        '  </defs>\n'
        f'  <text x="20" y="50">{SURFACE_TEXT}</text>\n'
        '</svg>\n'
    )
    path.write_text(svg, "utf-8")
    return path, "SVG <text> nested inside <defs> with no <use> reference"


def fixture_02_5_png_text_chunk_payload() -> tuple[Path, str]:
    """PNG with payload in a public tEXt chunk that exhibits concealment.

    The tEXt / iTXt / zTXt chunks are PNG's public-ancillary text
    metadata vehicles, structurally analogous to PDF /Info dictionary
    entries. Bayyinah v1.1.1 catches their existence (image_text_metadata)
    but does not run the four-trigger concealment scan that
    pdf_metadata_analyzer applies.

    This fixture combines the natural-language payload with a bidi
    override codepoint plus a zero-width space, so the v1.1.2
    image_png_text_chunk_payload mechanism can fire on the
    concealment triggers (parallel to pdf_metadata_analyzer's bidi
    and zero-width triggers).
    """
    path = OUT / "02_5_png_text_chunk_payload.png"
    # tEXt chunk format: keyword \x00 value (latin-1)
    keyword = b"Comment"
    # Inject a Right-To-Left override (U+202E) and a zero-width space
    # (U+200B). Latin-1 cannot encode those, so we approximate via the
    # iTXt-equivalent byte sequence within tEXt by using their UTF-8
    # forms. Most parsers treat tEXt value as bytes; the four-trigger
    # detector decodes permissively and finds the codepoints.
    rtl_override = "\u202e"
    zero_width_space = "\u200b"
    value_text = (
        f"{rtl_override}HIDDEN_TEXT_PAYLOAD: actual revenue $10,000"
        f"{zero_width_space} - see annex"
    )
    value_bytes = value_text.encode("utf-8")
    chunk_data = keyword + b"\x00" + value_bytes
    path.write_bytes(_png_with_extra_chunk(b"tEXt", chunk_data))
    return path, "PNG tEXt chunk with bidi + zero-width concealment triggers"


def fixture_04_5_svg_desc_payload() -> tuple[Path, str]:
    """SVG <desc> element with multi-sentence payload above 256 bytes.

    <desc> is the SVG accessibility description, the long-form
    counterpart to <title>. Legitimate values can run several
    sentences for complex visualizations, so the threshold is higher
    than <title>'s 64-byte threshold. This fixture's payload is
    crafted to exceed 256 bytes while remaining structurally a
    description (not a directive), so the mechanism fires on the
    length structural signal alone.
    """
    path = OUT / "04_5_svg_desc_payload.svg"
    long_payload = (
        "HIDDEN_TEXT_PAYLOAD: actual revenue $10,000 across all "
        "reporting segments. The figure on the front page reflects "
        "net of intercompany eliminations and partner rebates that "
        "will be reversed in the annex. The annex is shipped under "
        "separate cover and is the figure of record for the audit "
        "committee. Please refer to the annex for the canonical "
        "reconciliation between the surface and the recorded values."
    )
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="400" height="100">\n'
        f'  <desc>{long_payload}</desc>\n'
        f'  <text x="20" y="50">{SURFACE_TEXT}</text>\n'
        '</svg>\n'
    )
    path.write_text(svg, "utf-8")
    return path, "SVG <desc> element with multi-sentence payload over 256 bytes"


BUILDERS = [
    fixture_01_jpeg_app4_payload,
    fixture_02_png_private_chunk,
    fixture_02_5_png_text_chunk_payload,
    fixture_03_svg_white_text,
    fixture_04_svg_title_payload,
    fixture_04_5_svg_desc_payload,
    fixture_05_svg_metadata_payload,
    fixture_06_svg_defs_text,
]


if __name__ == "__main__":
    for builder in BUILDERS:
        path, desc = builder()
        size = path.stat().st_size
        print(f"{path.name:<42} {size:>7} bytes  - {desc}")
