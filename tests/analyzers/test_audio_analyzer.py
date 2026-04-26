"""
Tests for analyzers.audio_analyzer.AudioAnalyzer.

Phase 24 — audio container decomposition (MP3, WAV, FLAC, M4A, Ogg).
The analyzer follows the stem-extractor-and-router pattern from Phase
23 video: mutagen extracts the stems the container already separates
(metadata tags, embedded pictures, PCM sample data), and each stem is
routed to the analyzer that already knows how to read that material:

  * Metadata text → ``ZahirTextAnalyzer._check_unicode`` + regex-based
    prompt-injection shape detectors for lyric fields.
  * Embedded pictures → ``ImageAnalyzer().scan``.
  * WAV / FLAC PCM sample LSBs → stdlib entropy statistics local to
    AudioAnalyzer.

These tests pin:

  * The BaseAnalyzer contract (inheritance, class attributes,
    supported_kinds, instantiability, return shape).
  * Each active audio mechanism fires on its dedicated fixture and
    only that mechanism (plus the always-on ``audio_stem_inventory``).
  * The composition path actually reaches the delegated analyzer —
    ``audio_metadata_injection`` uses the exact codepoint set
    ZahirTextAnalyzer operates on.
  * Negative / edge cases (missing file, zero-byte input, extension-
    only fallback, mis-magic) return well-formed reports without
    propagating exceptions.

Fixture walker at ``tests/test_audio_fixtures.py`` exercises the full
``ScanService`` dispatch path. The guardrails here stay at the
analyzer level.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from analyzers import AudioAnalyzer
from analyzers.base import BaseAnalyzer
from domain import IntegrityReport
from domain.config import (
    BIDI_CONTROL_CHARS,
    SEVERITY,
    TIER,
    ZAHIR_MECHANISMS,
    BATIN_MECHANISMS,
    ZERO_WIDTH_CHARS,
)
from infrastructure.file_router import FileKind


FIXTURES_DIR: Path = (
    Path(__file__).resolve().parent.parent / "fixtures" / "audio"
)


@pytest.fixture(scope="module", autouse=True)
def _ensure_audio_fixtures_built() -> None:
    from tests.make_audio_fixtures import (
        AUDIO_FIXTURE_EXPECTATIONS,
        generate_all,
    )
    missing = [
        FIXTURES_DIR / rel
        for rel in AUDIO_FIXTURE_EXPECTATIONS
        if not (FIXTURES_DIR / rel).exists()
    ]
    if missing:
        generate_all(FIXTURES_DIR)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(AudioAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert AudioAnalyzer.name == "audio"
    assert AudioAnalyzer.error_prefix == "Audio scan error"
    assert AudioAnalyzer.source_layer == "batin"


def test_supported_kinds_covers_five_audio_families() -> None:
    expected = frozenset({
        FileKind.AUDIO_MP3,
        FileKind.AUDIO_WAV,
        FileKind.AUDIO_FLAC,
        FileKind.AUDIO_M4A,
        FileKind.AUDIO_OGG,
    })
    assert AudioAnalyzer.supported_kinds == expected


def test_supported_kinds_excludes_non_audio_families() -> None:
    # Disjoint from every pre-Phase-24 analyzer's supported_kinds
    # and from VideoAnalyzer's (which lives in the same phase).
    for kind in (
        FileKind.PDF, FileKind.DOCX, FileKind.XLSX, FileKind.PPTX,
        FileKind.HTML, FileKind.EML, FileKind.CSV, FileKind.JSON,
        FileKind.IMAGE_PNG, FileKind.IMAGE_JPEG, FileKind.IMAGE_SVG,
        FileKind.MARKDOWN, FileKind.CODE, FileKind.UNKNOWN,
        FileKind.VIDEO_MP4, FileKind.VIDEO_MOV,
        FileKind.VIDEO_WEBM, FileKind.VIDEO_MKV,
    ):
        assert kind not in AudioAnalyzer.supported_kinds, (
            f"AudioAnalyzer must not advertise support for {kind}"
        )


def test_instantiable() -> None:
    a = AudioAnalyzer()
    assert a.name == "audio"
    assert "AudioAnalyzer" in repr(a)


# ---------------------------------------------------------------------------
# Mechanism registry coherence
# ---------------------------------------------------------------------------


_AUDIO_MECHANISMS: set[str] = {
    "audio_stem_inventory",
    "audio_metadata_identity_anomaly",
    "audio_lyrics_prompt_injection",
    "audio_metadata_injection",
    "audio_embedded_payload",
    "audio_lsb_stego_candidate",
    "audio_high_entropy_metadata",
    "audio_container_anomaly",
    "audio_cross_stem_divergence",
}


def test_every_audio_mechanism_is_registered() -> None:
    combined = ZAHIR_MECHANISMS | BATIN_MECHANISMS
    missing = _AUDIO_MECHANISMS - combined
    assert not missing, f"unregistered audio mechanisms: {missing}"


def test_every_audio_mechanism_has_severity_and_tier() -> None:
    for m in _AUDIO_MECHANISMS:
        assert m in SEVERITY, f"{m} missing SEVERITY"
        assert m in TIER, f"{m} missing TIER"
        assert 0.0 <= SEVERITY[m] <= 1.0
        assert TIER[m] in (1, 2, 3)


def test_audio_text_mechanisms_are_zahir() -> None:
    # Metadata / lyric concealment is zahir — the listener / ingestion
    # pipeline reads the text; the stream carries different codepoints.
    assert "audio_metadata_injection" in ZAHIR_MECHANISMS
    assert "audio_lyrics_prompt_injection" in ZAHIR_MECHANISMS


def test_audio_structural_mechanisms_are_batin() -> None:
    for m in (
        "audio_stem_inventory",
        "audio_metadata_identity_anomaly",
        "audio_embedded_payload",
        "audio_lsb_stego_candidate",
        "audio_high_entropy_metadata",
        "audio_container_anomaly",
        "audio_cross_stem_divergence",
    ):
        assert m in BATIN_MECHANISMS, f"{m} should be batin-classified"


def test_stem_inventory_is_non_deducting() -> None:
    assert SEVERITY["audio_stem_inventory"] == 0.0


def test_identity_anomaly_is_highest_severity() -> None:
    # Al-Nisa 4:112 — identity forgery is the gravest form of
    # falsehood. The mechanism that surfaces that shape carries the
    # highest severity in the audio family (tied with embedded-payload
    # at 0.40, both the highest deducting audio mechanisms).
    identity_sev = SEVERITY["audio_metadata_identity_anomaly"]
    payload_sev = SEVERITY["audio_embedded_payload"]
    assert identity_sev == max(
        SEVERITY[m] for m in _AUDIO_MECHANISMS
    )
    assert identity_sev == payload_sev  # tied


# ---------------------------------------------------------------------------
# Negative / edge cases
# ---------------------------------------------------------------------------


def test_missing_file_returns_scan_error_and_incomplete() -> None:
    r = AudioAnalyzer().scan(Path("/definitely/does/not/exist.mp3"))
    assert isinstance(r, IntegrityReport)
    assert r.scan_incomplete is True
    assert r.integrity_score == 0.0
    mechs = [f.mechanism for f in r.findings]
    assert mechs == ["scan_error"]
    assert r.error is not None
    assert "File not found" in r.error


def test_zero_byte_file_surfaces_container_anomaly(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp3"
    empty.write_bytes(b"")
    r = AudioAnalyzer().scan(empty)
    mechs = [f.mechanism for f in r.findings]
    assert "audio_container_anomaly" in mechs


def test_garbage_bytes_in_audio_extension_fires_anomaly(tmp_path: Path) -> None:
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not an audio file at all, just text")
    r = AudioAnalyzer().scan(junk)
    mechs = {f.mechanism for f in r.findings}
    assert "audio_container_anomaly" in mechs


# ---------------------------------------------------------------------------
# Clean fixtures
# ---------------------------------------------------------------------------


def test_clean_mp3_returns_only_inventory() -> None:
    r = AudioAnalyzer().scan(FIXTURES_DIR / "clean" / "clean.mp3")
    mechs = {f.mechanism for f in r.findings}
    assert mechs == {"audio_stem_inventory"}
    assert r.integrity_score == 1.0
    assert r.scan_incomplete is False


def test_clean_wav_returns_only_inventory() -> None:
    r = AudioAnalyzer().scan(FIXTURES_DIR / "clean" / "clean.wav")
    mechs = {f.mechanism for f in r.findings}
    assert mechs == {"audio_stem_inventory"}
    assert r.integrity_score == 1.0


def test_clean_flac_returns_only_inventory() -> None:
    r = AudioAnalyzer().scan(FIXTURES_DIR / "clean" / "clean.flac")
    mechs = {f.mechanism for f in r.findings}
    assert mechs == {"audio_stem_inventory"}
    assert r.integrity_score == 1.0


# ---------------------------------------------------------------------------
# Adversarial fixtures — one test per mechanism
# ---------------------------------------------------------------------------


def _scan_adversarial(name: str) -> IntegrityReport:
    return AudioAnalyzer().scan(FIXTURES_DIR / "adversarial" / name)


def test_metadata_injection_fires() -> None:
    r = _scan_adversarial("metadata_injection.mp3")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_metadata_injection" in mechs
    assert r.integrity_score < 1.0


def test_lyrics_prompt_injection_fires() -> None:
    r = _scan_adversarial("lyrics_injection.mp3")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_lyrics_prompt_injection" in mechs
    assert r.integrity_score < 1.0


def test_identity_anomaly_fires() -> None:
    r = _scan_adversarial("identity_anomaly.mp3")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_metadata_identity_anomaly" in mechs
    assert r.integrity_score < 1.0


def test_embedded_payload_fires_on_foreign_magic() -> None:
    r = _scan_adversarial("embedded_payload.mp3")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_embedded_payload" in mechs
    assert r.integrity_score < 1.0


def test_lsb_stego_candidate_fires_on_uniform_lsb() -> None:
    r = _scan_adversarial("lsb_stego_candidate.wav")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_lsb_stego_candidate" in mechs
    assert r.integrity_score < 1.0


def test_high_entropy_metadata_fires() -> None:
    r = _scan_adversarial("high_entropy.mp3")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_high_entropy_metadata" in mechs
    assert r.integrity_score < 1.0


def test_container_anomaly_fires_on_trailing_wav() -> None:
    r = _scan_adversarial("container_anomaly.wav")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_container_anomaly" in mechs
    assert r.integrity_score < 1.0


def test_cross_stem_divergence_fixture_does_not_false_positive() -> None:
    # The divergence detector is future work — the fixture exists to
    # prove the current analyzer does not fire spuriously on a file
    # with legitimate provenance differentiation.
    r = _scan_adversarial("cross_stem_divergence.mp3")
    mechs = {f.mechanism for f in r.findings}
    assert "audio_cross_stem_divergence" not in mechs
    assert r.integrity_score == 1.0


# ---------------------------------------------------------------------------
# Composition verification
# ---------------------------------------------------------------------------


def test_metadata_injection_routes_through_zahir_text_analyzer() -> None:
    """Composition invariant: audio_metadata_injection must use the
    same codepoint universe ZahirTextAnalyzer uses for PDF spans.

    Regression guard — if someone hardcodes a new zero-width set in
    AudioAnalyzer, the two analyzers can drift and the same bytes in
    a metadata tag vs a PDF would classify differently.
    """
    r = _scan_adversarial("metadata_injection.mp3")
    finding = next(
        (f for f in r.findings if f.mechanism == "audio_metadata_injection"),
        None,
    )
    assert finding is not None
    concealed = finding.concealed or ""
    zw_labels = {f"U+{ord(c):04X}" for c in ZERO_WIDTH_CHARS}
    bidi_labels = {f"U+{ord(c):04X}" for c in BIDI_CONTROL_CHARS}
    # Tag-character labels use 6-digit hex; include those too.
    assert any(
        lbl in concealed for lbl in zw_labels | bidi_labels
    ) or "E0" in concealed, (
        f"Expected a shared-universe codepoint label in: {concealed!r}"
    )


def test_embedded_payload_preserves_image_analyzer_evidence() -> None:
    """When cover-art delegation flows through ImageAnalyzer, the
    original image-layer mechanism must appear in the ``surface`` of
    the re-emerged audio_embedded_payload finding. For the PDF-
    payload fixture we verify the foreign-format label is surfaced
    instead.
    """
    r = _scan_adversarial("embedded_payload.mp3")
    finding = next(
        (f for f in r.findings if f.mechanism == "audio_embedded_payload"),
        None,
    )
    assert finding is not None
    # Our fixture uses a PDF magic prefix — the surface string names
    # the foreign format.
    assert (
        "PDF" in (finding.surface or "")
        or "PDF" in (finding.description or "")
    ), f"Expected PDF to be named in finding: surface={finding.surface!r}"


# ---------------------------------------------------------------------------
# Return-shape / structural guarantees
# ---------------------------------------------------------------------------


def test_scan_always_returns_integrity_report() -> None:
    cases = [
        FIXTURES_DIR / "clean" / "clean.mp3",
        FIXTURES_DIR / "clean" / "clean.wav",
        FIXTURES_DIR / "clean" / "clean.flac",
        FIXTURES_DIR / "adversarial" / "metadata_injection.mp3",
        FIXTURES_DIR / "adversarial" / "lsb_stego_candidate.wav",
        Path("/definitely/does/not/exist.mp3"),
    ]
    for p in cases:
        r = AudioAnalyzer().scan(p)
        assert isinstance(r, IntegrityReport)
        assert isinstance(r.integrity_score, float)
        assert 0.0 <= r.integrity_score <= 1.0
        assert isinstance(r.findings, list)
        for f in r.findings:
            assert f.mechanism in (ZAHIR_MECHANISMS | BATIN_MECHANISMS), (
                f"unregistered mechanism leaked: {f.mechanism}"
            )


def test_no_exceptions_propagate_for_adversarial_fixtures() -> None:
    for rel in (
        "adversarial/metadata_injection.mp3",
        "adversarial/lyrics_injection.mp3",
        "adversarial/identity_anomaly.mp3",
        "adversarial/embedded_payload.mp3",
        "adversarial/lsb_stego_candidate.wav",
        "adversarial/high_entropy.mp3",
        "adversarial/container_anomaly.wav",
        "adversarial/cross_stem_divergence.mp3",
    ):
        AudioAnalyzer().scan(FIXTURES_DIR / rel)
