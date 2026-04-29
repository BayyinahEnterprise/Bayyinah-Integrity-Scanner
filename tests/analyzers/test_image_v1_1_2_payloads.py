"""
Tests for the v1.1.2 image format gauntlet (F1) hidden-text detectors.

Each mechanism gets the standard paired-fixture trio per
Differentiator Layer 7:

  - REGISTRY: classified into the right source layer with the
    expected TIER and SEVERITY.
  - CATCH: the matching image_gauntlet fixture produces at least
    one finding from that mechanism.
  - PAYLOAD RECOVERY: the catching finding's ``concealed`` field
    contains the canonical payload marker
    (``HIDDEN_TEXT_PAYLOAD`` / ``$10,000`` / ``actual revenue``).
  - CLEAN: the clean image baselines
    (``tests/fixtures/images/clean/clean.jpg``,
    ``clean.png``, ``clean.svg``) produce zero findings from that
    mechanism.

Mechanism table (matches docs/adversarial/image_gauntlet/REPORT.md
once F1 closes; updated incrementally as each step lands):

  | Mechanism                          | Tier | Layer | Sev  | Fixture |
  |------------------------------------|------|-------|------|---------|
  | image_jpeg_appn_payload            | 1    | batin | 0.20 | 01      |
  | image_png_private_chunk            | 2    | batin | 0.20 | 02      |
  | image_png_text_chunk_payload       | 1    | batin | 0.25 | 02_5    |
  | svg_white_text                     | 1    | zahir | 1.00 | 03      |
  | svg_title_payload                  | 1    | batin | 0.15 | 04      |
  | svg_desc_payload                   | 1    | batin | 0.15 | 04_5    |
  | svg_metadata_payload               | 1    | batin | 0.15 | 05      |
  | svg_defs_unreferenced_text         | 1    | batin | 0.20 | 06      |
"""
from __future__ import annotations

from pathlib import Path

import pytest

from analyzers.image_jpeg_appn_payload import detect_image_jpeg_appn_payload
from analyzers.image_png_private_chunk import detect_image_png_private_chunk
from analyzers.image_png_text_chunk_payload import (
    detect_image_png_text_chunk_payload,
)
from analyzers.svg_white_text import detect_svg_white_text
from analyzers.svg_title_payload import detect_svg_title_payload
from analyzers.svg_desc_payload import detect_svg_desc_payload
from analyzers.svg_metadata_payload import detect_svg_metadata_payload
from analyzers.svg_defs_unreferenced_text import (
    detect_svg_defs_unreferenced_text,
)
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
GAUNTLET_DIR = REPO_ROOT / "docs/adversarial/image_gauntlet/fixtures"
CLEAN_DIR = REPO_ROOT / "tests/fixtures/images/clean"
CLEAN_FIXTURES = (
    CLEAN_DIR / "clean.jpg",
    CLEAN_DIR / "clean.png",
    CLEAN_DIR / "clean.svg",
)

PAYLOAD_MARKERS = (
    "HIDDEN_TEXT_PAYLOAD",
    "$10,000",
    "10,000",
    "actual revenue",
)


def _payload_recovered(concealed: str) -> bool:
    """Return True when the concealed string contains any canonical
    payload marker.
    """
    if concealed is None:
        return False
    return any(marker in concealed for marker in PAYLOAD_MARKERS)


# ---------------------------------------------------------------------------
# Registry checks
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mechanism,layer,tier_value,severity_value",
    [
        ("image_jpeg_appn_payload", "batin", 1, 0.20),
        ("image_png_private_chunk", "batin", 2, 0.20),
        ("image_png_text_chunk_payload", "batin", 1, 0.25),
        ("svg_white_text", "zahir", 1, 1.00),
        ("svg_title_payload", "batin", 1, 0.15),
        ("svg_desc_payload", "batin", 1, 0.15),
        ("svg_metadata_payload", "batin", 1, 0.15),
        ("svg_defs_unreferenced_text", "batin", 1, 0.20),
    ],
)
def test_v1_1_2_image_mechanism_is_registered(
    mechanism: str,
    layer: str,
    tier_value: int,
    severity_value: float,
) -> None:
    """Every v1.1.2 image mechanism is registered in the right layer
    with the right tier and severity. A drift here means SEVERITY,
    TIER, or the layer set was edited without the matching update
    in the others.
    """
    if layer == "zahir":
        assert mechanism in ZAHIR_MECHANISMS
        assert mechanism not in BATIN_MECHANISMS
    else:
        assert mechanism in BATIN_MECHANISMS
        assert mechanism not in ZAHIR_MECHANISMS
    assert TIER[mechanism] == tier_value
    assert SEVERITY[mechanism] == severity_value


# ---------------------------------------------------------------------------
# image_jpeg_appn_payload - fixture 01
# ---------------------------------------------------------------------------


def test_image_jpeg_appn_payload_catches_fixture_01() -> None:
    fixture = GAUNTLET_DIR / "01_jpeg_app4_payload.jpg"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_image_jpeg_appn_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "image_jpeg_appn_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"image_jpeg_appn_payload did not fire on fixture 01; got "
        f"{[f.mechanism for f in findings]}"
    )


def test_image_jpeg_appn_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "01_jpeg_app4_payload.jpg"
    findings = list(detect_image_jpeg_appn_payload(fixture))
    assert any(
        f.mechanism == "image_jpeg_appn_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no image_jpeg_appn_payload finding recovered the concealed "
        "APP4 payload text; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_image_jpeg_appn_payload_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue  # not every clean control may exist
        findings = list(detect_image_jpeg_appn_payload(control))
        assert all(
            f.mechanism != "image_jpeg_appn_payload" for f in findings
        ), (
            f"image_jpeg_appn_payload fired on clean baseline "
            f"{control.name}; got {findings}"
        )


# ---------------------------------------------------------------------------
# Cross-mechanism over-firing checks (image gauntlet)
# ---------------------------------------------------------------------------
#
# Each detector should only fire on its target fixture among the
# eight image gauntlet fixtures. SVG-only and PNG-only fixtures are
# silently skipped by the JPEG detector since the magic bytes do not
# match; the test still asserts that no jpeg_appn finding is emitted.


# ---------------------------------------------------------------------------
# image_png_private_chunk - fixture 02
# ---------------------------------------------------------------------------


def test_image_png_private_chunk_catches_fixture_02() -> None:
    fixture = GAUNTLET_DIR / "02_png_private_chunk.png"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_image_png_private_chunk(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "image_png_private_chunk" and f.tier == 2
    ]
    assert len(matching) >= 1, (
        f"image_png_private_chunk did not fire on fixture 02; got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )


def test_image_png_private_chunk_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "02_png_private_chunk.png"
    findings = list(detect_image_png_private_chunk(fixture))
    assert any(
        f.mechanism == "image_png_private_chunk"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no image_png_private_chunk finding recovered the concealed "
        "private-chunk payload text; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_image_png_private_chunk_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue
        findings = list(detect_image_png_private_chunk(control))
        assert all(
            f.mechanism != "image_png_private_chunk" for f in findings
        ), (
            f"image_png_private_chunk fired on clean baseline "
            f"{control.name}; got {findings}"
        )


def test_image_png_private_chunk_does_not_escalate_without_triggers() -> None:
    """Fixture 02's prVt chunk carries no bidi codepoints, no zero-
    width characters, and is well below the 1024-byte long-payload
    threshold (the natural-language payload is ~55 bytes). The
    detector should emit exactly one Tier 2 baseline finding and zero
    Tier 1 escalation findings.
    """
    fixture = GAUNTLET_DIR / "02_png_private_chunk.png"
    findings = list(detect_image_png_private_chunk(fixture))
    own = [f for f in findings if f.mechanism == "image_png_private_chunk"]
    tier2 = [f for f in own if f.tier == 2]
    tier1 = [f for f in own if f.tier == 1]
    assert len(tier2) == 1, f"expected 1 Tier 2 finding, got {len(tier2)}"
    assert len(tier1) == 0, (
        f"expected 0 Tier 1 escalations on a low-entropy private "
        f"chunk, got {len(tier1)}"
    )


# ---------------------------------------------------------------------------
# image_png_text_chunk_payload - fixture 02_5
# ---------------------------------------------------------------------------


def test_image_png_text_chunk_payload_catches_fixture_02_5() -> None:
    fixture = GAUNTLET_DIR / "02_5_png_text_chunk_payload.png"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_image_png_text_chunk_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "image_png_text_chunk_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"image_png_text_chunk_payload did not fire on fixture 02_5; got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )


def test_image_png_text_chunk_payload_emits_per_trigger_findings() -> None:
    """Fixture 02_5's tEXt value carries a bidi override (U+202E),
    a zero-width space (U+200B), and the HIDDEN_TEXT_PAYLOAD divergence
    marker. Per-trigger model means each trigger emits its own Tier 1
    finding, parallel to pdf_metadata_analyzer. Length is not a
    trigger here (the value is well under 1024 bytes).
    """
    fixture = GAUNTLET_DIR / "02_5_png_text_chunk_payload.png"
    findings = list(detect_image_png_text_chunk_payload(fixture))
    own = [
        f for f in findings
        if f.mechanism == "image_png_text_chunk_payload"
    ]
    assert len(own) == 3, (
        f"expected 3 Tier 1 findings (bidi, zero-width, divergence), "
        f"got {len(own)}: {[f.description[:60] for f in own]}"
    )
    descriptions = " ".join(f.description for f in own)
    assert "bidirectional-override" in descriptions
    assert "zero-width" in descriptions
    assert "concealment markers" in descriptions


def test_image_png_text_chunk_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "02_5_png_text_chunk_payload.png"
    findings = list(detect_image_png_text_chunk_payload(fixture))
    assert any(
        f.mechanism == "image_png_text_chunk_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no image_png_text_chunk_payload finding recovered the "
        "concealed text chunk payload; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_image_png_text_chunk_payload_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue
        findings = list(detect_image_png_text_chunk_payload(control))
        assert all(
            f.mechanism != "image_png_text_chunk_payload" for f in findings
        ), (
            f"image_png_text_chunk_payload fired on clean baseline "
            f"{control.name}; got {findings}"
        )


def test_image_png_text_chunk_payload_does_not_fire_on_clean_text_chunk(
    tmp_path: Path,
) -> None:
    """A PNG carrying a benign tEXt chunk (no bidi, no zero-width, no
    markers, under 1024 bytes) must produce zero Tier 1 findings. The
    bare presence of a text chunk is documented PNG infrastructure;
    only concealment-shaped values are flagged.
    """
    import struct
    import zlib

    keyword = b"Title"
    value = b"Q3 financial summary chart"
    chunk_data = keyword + b"\x00" + value
    chunk_type = b"tEXt"
    chunk_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
    text_chunk = (
        struct.pack(">I", len(chunk_data))
        + chunk_type
        + chunk_data
        + struct.pack(">I", chunk_crc)
    )
    # Minimal valid PNG: signature + IHDR + IDAT + IEND with text
    # chunk inserted before IEND. Use the clean baseline as a base.
    clean_png = CLEAN_DIR / "clean.png"
    if not clean_png.exists():
        pytest.skip("clean.png baseline not present")
    raw = clean_png.read_bytes()
    iend_offset = raw.find(b"IEND")
    assert iend_offset > 0
    # Insert the new chunk before IEND's length prefix (4 bytes
    # before the IEND type marker).
    insert_at = iend_offset - 4
    out = raw[:insert_at] + text_chunk + raw[insert_at:]
    out_path = tmp_path / "clean_with_benign_text.png"
    out_path.write_bytes(out)
    findings = list(detect_image_png_text_chunk_payload(out_path))
    assert all(
        f.mechanism != "image_png_text_chunk_payload" for f in findings
    ), (
        "image_png_text_chunk_payload fired on a benign tEXt chunk "
        f"with no concealment triggers; got {findings}"
    )


# ---------------------------------------------------------------------------
# svg_white_text - fixture 03
# ---------------------------------------------------------------------------


def test_svg_white_text_catches_fixture_03() -> None:
    fixture = GAUNTLET_DIR / "03_svg_white_text.svg"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_svg_white_text(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "svg_white_text" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"svg_white_text did not fire on fixture 03; got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )


def test_svg_white_text_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "03_svg_white_text.svg"
    findings = list(detect_svg_white_text(fixture))
    assert any(
        f.mechanism == "svg_white_text"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no svg_white_text finding recovered the concealed white-on-"
        "white text content; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_svg_white_text_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue
        findings = list(detect_svg_white_text(control))
        assert all(
            f.mechanism != "svg_white_text" for f in findings
        ), (
            f"svg_white_text fired on clean baseline "
            f"{control.name}; got {findings}"
        )


def test_svg_white_text_silent_on_white_text_on_colored_background(
    tmp_path: Path,
) -> None:
    """White text on a non-white background is a legitimate styling
    pattern (white-on-blue header callouts, etc.). The detector must
    stay silent so it does not flag legitimate design choices.
    """
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="400" height="100">\n'
        '  <rect width="400" height="100" fill="#0033AA"/>\n'
        '  <text x="20" y="50" fill="#FFFFFF">Header callout</text>\n'
        '</svg>\n'
    )
    out_path = tmp_path / "white_on_blue.svg"
    out_path.write_text(svg, encoding="utf-8")
    findings = list(detect_svg_white_text(out_path))
    assert all(
        f.mechanism != "svg_white_text" for f in findings
    ), (
        f"svg_white_text fired on white-on-blue (legitimate styling); "
        f"got {findings}"
    )


# ---------------------------------------------------------------------------
# svg_title_payload - fixture 04
# ---------------------------------------------------------------------------


def test_svg_title_payload_catches_fixture_04() -> None:
    fixture = GAUNTLET_DIR / "04_svg_title_payload.svg"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_svg_title_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "svg_title_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"svg_title_payload did not fire on fixture 04; got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )


def test_svg_title_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "04_svg_title_payload.svg"
    findings = list(detect_svg_title_payload(fixture))
    assert any(
        f.mechanism == "svg_title_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no svg_title_payload finding recovered the concealed title "
        "payload; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_svg_title_payload_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue
        findings = list(detect_svg_title_payload(control))
        assert all(
            f.mechanism != "svg_title_payload" for f in findings
        ), (
            f"svg_title_payload fired on clean baseline "
            f"{control.name}; got {findings}"
        )


def test_svg_title_payload_silent_on_short_legitimate_title(
    tmp_path: Path,
) -> None:
    """A short <title> (chart label, icon name, accessibility tooltip)
    must not fire. The 64-byte threshold is calibrated so legitimate
    short titles pass silently.
    """
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="100" height="100">\n'
        '  <title>Q3 revenue chart</title>\n'
        '  <text x="20" y="50">Chart</text>\n'
        '</svg>\n'
    )
    out_path = tmp_path / "short_title.svg"
    out_path.write_text(svg, encoding="utf-8")
    findings = list(detect_svg_title_payload(out_path))
    assert all(
        f.mechanism != "svg_title_payload" for f in findings
    ), (
        f"svg_title_payload fired on a 17-byte legitimate title; "
        f"got {findings}"
    )


# ---------------------------------------------------------------------------
# svg_desc_payload - fixture 04_5
# ---------------------------------------------------------------------------


def test_svg_desc_payload_catches_fixture_04_5() -> None:
    fixture = GAUNTLET_DIR / "04_5_svg_desc_payload.svg"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_svg_desc_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "svg_desc_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"svg_desc_payload did not fire on fixture 04_5; got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )


def test_svg_desc_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "04_5_svg_desc_payload.svg"
    findings = list(detect_svg_desc_payload(fixture))
    assert any(
        f.mechanism == "svg_desc_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no svg_desc_payload finding recovered the concealed desc "
        "payload; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_svg_desc_payload_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue
        findings = list(detect_svg_desc_payload(control))
        assert all(
            f.mechanism != "svg_desc_payload" for f in findings
        ), (
            f"svg_desc_payload fired on clean baseline "
            f"{control.name}; got {findings}"
        )


def test_svg_desc_payload_silent_on_short_legitimate_desc(
    tmp_path: Path,
) -> None:
    """A legitimate accessibility description under 256 bytes (typical
    chart caption, icon long-form description) must not fire. The
    256-byte threshold is calibrated so multi-sentence legitimate
    descriptions of normal length pass silently; only long-form
    payloads exceeding the legitimate-use distribution trigger.
    """
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="100" height="100">\n'
        '  <title>Q3 chart</title>\n'
        '  <desc>Bar chart showing Q3 revenue growth across three '
        'product lines, indexed against the prior quarter baseline.'
        '</desc>\n'
        '  <text x="20" y="50">Chart</text>\n'
        '</svg>\n'
    )
    out_path = tmp_path / "short_desc.svg"
    out_path.write_text(svg, encoding="utf-8")
    findings = list(detect_svg_desc_payload(out_path))
    assert all(
        f.mechanism != "svg_desc_payload" for f in findings
    ), (
        f"svg_desc_payload fired on a short legitimate desc; "
        f"got {findings}"
    )


# ---------------------------------------------------------------------------
# svg_metadata_payload - fixture 05
# ---------------------------------------------------------------------------


def test_svg_metadata_payload_catches_fixture_05() -> None:
    fixture = GAUNTLET_DIR / "05_svg_metadata_payload.svg"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_svg_metadata_payload(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "svg_metadata_payload" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"svg_metadata_payload did not fire on fixture 05; got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )


def test_svg_metadata_payload_recovers_payload_into_concealed() -> None:
    fixture = GAUNTLET_DIR / "05_svg_metadata_payload.svg"
    findings = list(detect_svg_metadata_payload(fixture))
    assert any(
        f.mechanism == "svg_metadata_payload"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no svg_metadata_payload finding recovered the concealed "
        "metadata payload; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_svg_metadata_payload_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue
        findings = list(detect_svg_metadata_payload(control))
        assert all(
            f.mechanism != "svg_metadata_payload" for f in findings
        ), (
            f"svg_metadata_payload fired on clean baseline "
            f"{control.name}; got {findings}"
        )


def test_svg_metadata_payload_silent_on_short_legitimate_metadata(
    tmp_path: Path,
) -> None:
    """A legitimate <metadata> block carrying just a Creative Commons
    license URI and creator name (under 128 bytes) must not fire.
    The 128-byte threshold is calibrated so well-formed metadata
    annotations pass silently; only payload-bearing metadata
    crosses the threshold.
    """
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'width="100" height="100">\n'
        '  <metadata>\n'
        '    <rdf:RDF>\n'
        '      <rdf:Description>\n'
        '        <dc:title>Logo</dc:title>\n'
        '        <dc:creator>Acme</dc:creator>\n'
        '      </rdf:Description>\n'
        '    </rdf:RDF>\n'
        '  </metadata>\n'
        '  <text x="20" y="50">Logo</text>\n'
        '</svg>\n'
    )
    out_path = tmp_path / "short_metadata.svg"
    out_path.write_text(svg, encoding="utf-8")
    findings = list(detect_svg_metadata_payload(out_path))
    assert all(
        f.mechanism != "svg_metadata_payload" for f in findings
    ), (
        f"svg_metadata_payload fired on a short legitimate metadata "
        f"block; got {findings}"
    )


# ---------------------------------------------------------------------------
# svg_defs_unreferenced_text - fixture 06
# ---------------------------------------------------------------------------


def test_svg_defs_unreferenced_text_catches_fixture_06() -> None:
    fixture = GAUNTLET_DIR / "06_svg_defs_text.svg"
    assert fixture.exists(), f"missing fixture: {fixture}"
    findings = list(detect_svg_defs_unreferenced_text(fixture))
    matching = [
        f for f in findings
        if f.mechanism == "svg_defs_unreferenced_text" and f.tier == 1
    ]
    assert len(matching) >= 1, (
        f"svg_defs_unreferenced_text did not fire on fixture 06; got "
        f"{[(f.mechanism, f.tier) for f in findings]}"
    )


def test_svg_defs_unreferenced_text_recovers_payload() -> None:
    fixture = GAUNTLET_DIR / "06_svg_defs_text.svg"
    findings = list(detect_svg_defs_unreferenced_text(fixture))
    assert any(
        f.mechanism == "svg_defs_unreferenced_text"
        and _payload_recovered(f.concealed)
        for f in findings
    ), (
        "no svg_defs_unreferenced_text finding recovered the "
        "concealed defs/text payload; concealed values: "
        f"{[(f.concealed or '')[:80] for f in findings]}"
    )


def test_svg_defs_unreferenced_text_clean_on_controls() -> None:
    for control in CLEAN_FIXTURES:
        if not control.exists():
            continue
        findings = list(detect_svg_defs_unreferenced_text(control))
        assert all(
            f.mechanism != "svg_defs_unreferenced_text" for f in findings
        ), (
            f"svg_defs_unreferenced_text fired on clean baseline "
            f"{control.name}; got {findings}"
        )


def test_svg_defs_unreferenced_text_silent_when_use_references_id(
    tmp_path: Path,
) -> None:
    """Legitimate <defs>/<text> with id referenced by a <use>
    element must not fire. This is the canonical SVG template
    pattern: define a reusable text fragment in <defs> and
    instantiate it elsewhere via <use href="#id">.
    """
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="100" height="100">\n'
        '  <defs>\n'
        '    <text id="label" x="0" y="0">Reusable label</text>\n'
        '  </defs>\n'
        '  <use href="#label" x="20" y="50"/>\n'
        '</svg>\n'
    )
    out_path = tmp_path / "used_defs_text.svg"
    out_path.write_text(svg, encoding="utf-8")
    findings = list(detect_svg_defs_unreferenced_text(out_path))
    assert all(
        f.mechanism != "svg_defs_unreferenced_text" for f in findings
    ), (
        f"svg_defs_unreferenced_text fired on a legitimate <use>-"
        f"referenced <defs>/<text>; got {findings}"
    )


@pytest.mark.parametrize(
    "detector,target_fixture",
    [
        (detect_image_jpeg_appn_payload, "01_jpeg_app4_payload.jpg"),
        (detect_image_png_private_chunk, "02_png_private_chunk.png"),
        (
            detect_image_png_text_chunk_payload,
            "02_5_png_text_chunk_payload.png",
        ),
        (detect_svg_white_text, "03_svg_white_text.svg"),
        (detect_svg_title_payload, "04_svg_title_payload.svg"),
        (detect_svg_desc_payload, "04_5_svg_desc_payload.svg"),
        (detect_svg_metadata_payload, "05_svg_metadata_payload.svg"),
        (
            detect_svg_defs_unreferenced_text,
            "06_svg_defs_text.svg",
        ),
    ],
)
def test_v1_1_2_image_detectors_target_their_fixtures(
    detector,
    target_fixture: str,
) -> None:
    """Each detector fires on exactly its target fixture among the
    image gauntlet fixtures and does not over-fire on the others.
    """
    target_path = GAUNTLET_DIR / target_fixture
    own_mech = detector.__name__.replace("detect_", "")
    target_findings = list(detector(target_path))
    assert any(
        f.mechanism == own_mech for f in target_findings
    ), f"{detector.__name__} missed its target fixture {target_fixture}"

    other_fixtures = [
        f for f in sorted(GAUNTLET_DIR.iterdir())
        if f.is_file() and f.name != target_fixture
    ]
    for other in other_fixtures:
        other_findings = list(detector(other))
        assert all(f.mechanism != own_mech for f in other_findings), (
            f"{detector.__name__} over-fired on non-target {other.name}; "
            f"got {[f.mechanism for f in other_findings]}"
        )
