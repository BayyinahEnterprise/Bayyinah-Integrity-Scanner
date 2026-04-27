"""
Tests for analyzers.pdf_hidden_text_annotation (v1.1.2 Day 2,
mechanism 06).

Tier 1 mechanism: PDF /Text-family annotations with a suppression
bit set in /F (Hidden, NoView, or LockedContents per ISO 32000-1
Table 165) AND non-whitespace /Contents text. Closes pdf_gauntlet
fixture 06_optional_content_group.pdf.

Test slate per Day 2 prompt section 6.5 plus the v4 prompt's
mechanism-06 spec:

  1. Catch on fixture 06 (the canonical adversarial fixture).
  2. Clean on visible annotation (/F=0, no suppression bits).
  3. Clean on empty /Contents (content-threshold guard).
  4. Clean on /Link annotation (subtype-filter guard).
  5. Multi-annotation: two hidden annotations -> two findings.
  6. Clean on unparseable bytes (defensive parsing).

Tests 2-5 mutate the existing fixture 06 in tmp_path via pikepdf
to construct a deterministic variant. No binary fixtures are
committed; all variant PDFs live entirely inside the test
session's tmp directory.

References:
  - docs/adversarial/pdf_gauntlet/REPORT.md row 06
  - docs/scope/v1_1_2_claude_prompt.md section 6.5
"""
from __future__ import annotations

from pathlib import Path

import pikepdf

from analyzers.pdf_hidden_text_annotation import (
    detect_pdf_hidden_text_annotation,
)
from domain.config import BATIN_MECHANISMS, SEVERITY, TIER, ZAHIR_MECHANISMS


REPO_ROOT = Path(__file__).resolve().parents[2]
ADVERSARIAL_FIXTURE = (
    REPO_ROOT / "docs/adversarial/pdf_gauntlet/fixtures/"
    "06_optional_content_group.pdf"
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _mutate_fixture_06(
    tmp_path: Path,
    *,
    subtype: str,
    f_flag: int,
    contents: str,
) -> Path:
    """Open fixture 06, replace its sole annotation with a fresh
    annotation carrying the desired /Subtype, /F, and /Contents,
    save to tmp_path. Returns the new path. pikepdf's Array auto-
    dereferences indirect objects on access, so direct mutation of
    annots[0] is not as reliable as replacing the array entry; the
    safer pattern is to construct a fresh Dictionary and substitute
    it via pdf.make_indirect()."""
    dst = tmp_path / "variant.pdf"
    with pikepdf.open(ADVERSARIAL_FIXTURE) as pdf:
        page = pdf.pages[0]
        annots = page["/Annots"]
        new_annot = pikepdf.Dictionary(
            Type=pikepdf.Name("/Annot"),
            Subtype=pikepdf.Name(subtype),
            Rect=[100, 100, 200, 120],
            Contents=contents,
            F=f_flag,
        )
        annots[0] = pdf.make_indirect(new_annot)
        pdf.save(str(dst))
    return dst


def _add_second_hidden_annotation(
    tmp_path: Path, contents_a: str, contents_b: str,
) -> Path:
    """Open fixture 06, replace the existing annotation with one
    carrying contents_a, append a second hidden /Text annotation
    with contents_b. Returns the new path."""
    dst = tmp_path / "two_hidden.pdf"
    with pikepdf.open(ADVERSARIAL_FIXTURE) as pdf:
        page = pdf.pages[0]
        annots = page["/Annots"]
        annot_a = pikepdf.Dictionary(
            Type=pikepdf.Name("/Annot"),
            Subtype=pikepdf.Name("/Text"),
            Rect=[100, 100, 200, 120],
            Contents=contents_a,
            F=2,
        )
        annots[0] = pdf.make_indirect(annot_a)
        annot_b = pikepdf.Dictionary(
            Type=pikepdf.Name("/Annot"),
            Subtype=pikepdf.Name("/Text"),
            Rect=[300, 100, 400, 120],
            Contents=contents_b,
            F=2,
        )
        annots.append(pdf.make_indirect(annot_b))
        pdf.save(str(dst))
    return dst


# ---------------------------------------------------------------------------
# Registry pin
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_registered_in_zahir_mechanisms() -> None:
    """The mechanism classifies as zahir (the /F flag and /Contents
    string are surface-readable from a single /Annots walk with no
    hidden-state inference, paralleling pdf_off_page_text and the
    v1.1.1 off_page_text mechanism). TIER is 1 and SEVERITY is 1.0
    per Day 2 prompt section 6.6 step 2."""
    assert "pdf_hidden_text_annotation" in ZAHIR_MECHANISMS
    assert "pdf_hidden_text_annotation" not in BATIN_MECHANISMS
    assert TIER["pdf_hidden_text_annotation"] == 1
    assert SEVERITY["pdf_hidden_text_annotation"] == 1.0


# ---------------------------------------------------------------------------
# 1. Catch on fixture 06
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_fires_on_fixture_06() -> None:
    """Canonical adversarial fixture: one /Text annotation, /F=2,
    /Contents='HIDDEN_TEXT_PAYLOAD: actual revenue $10,000...'.
    Detector must produce exactly one Tier 1 finding with the
    payload string in evidence."""
    assert ADVERSARIAL_FIXTURE.exists(), (
        f"PDF gauntlet fixture missing: {ADVERSARIAL_FIXTURE}"
    )
    findings = detect_pdf_hidden_text_annotation(ADVERSARIAL_FIXTURE)
    matching = [
        f for f in findings
        if f.mechanism == "pdf_hidden_text_annotation"
    ]
    assert len(matching) == 1, (
        f"Expected exactly one pdf_hidden_text_annotation finding on "
        f"fixture 06; got {len(matching)}"
    )
    f = matching[0]
    assert f.tier == 1
    assert f.confidence == 1.0
    # Recovered payload must be present in concealed field.
    assert "HIDDEN_TEXT_PAYLOAD" in f.concealed
    # /F=2 (Hidden) signal recorded in surface or concealed field.
    assert "/F=2" in f.concealed or "Hidden" in f.concealed
    # Location includes page index AND annotation object reference.
    assert "page" in f.location
    assert "/Annot object" in f.location


# ---------------------------------------------------------------------------
# 2. Clean on visible annotation (/F=0)
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_clean_on_visible_annotation(
    tmp_path: Path,
) -> None:
    """An annotation with /F=0 has no suppression bit set. The
    detector must not fire even though the /Contents text is
    substantive."""
    pdf = _mutate_fixture_06(
        tmp_path,
        subtype="/Text",
        f_flag=0,
        contents="A normal sticky-note comment from a reviewer.",
    )
    findings = detect_pdf_hidden_text_annotation(pdf)
    assert findings == [], (
        f"Visible annotation (/F=0) wrongly fired the detector; got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )


# ---------------------------------------------------------------------------
# 3. Clean on empty /Contents
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_clean_on_empty_contents(
    tmp_path: Path,
) -> None:
    """An annotation with /F=2 (Hidden) but empty /Contents must not
    fire. Viewer-generated placeholder annotations sometimes set
    suppression bits without carrying a payload; the content-
    threshold guard prevents false positives there."""
    pdf = _mutate_fixture_06(
        tmp_path,
        subtype="/Text",
        f_flag=2,
        contents="",
    )
    findings = detect_pdf_hidden_text_annotation(pdf)
    assert findings == [], (
        f"Hidden annotation with empty /Contents wrongly fired; got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )


def test_pdf_hidden_text_annotation_clean_on_whitespace_only_contents(
    tmp_path: Path,
) -> None:
    """A whitespace-only /Contents counts as empty for the content
    threshold."""
    pdf = _mutate_fixture_06(
        tmp_path,
        subtype="/Text",
        f_flag=2,
        contents="   \n\t  ",
    )
    findings = detect_pdf_hidden_text_annotation(pdf)
    assert findings == [], (
        f"Hidden annotation with whitespace-only /Contents wrongly "
        f"fired; got {[(f.mechanism, f.location) for f in findings]}"
    )


# ---------------------------------------------------------------------------
# 4. Clean on /Link annotation (subtype filter)
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_clean_on_link_annotation(
    tmp_path: Path,
) -> None:
    """A /Link annotation with /F=2 and substantive /Contents must
    not fire: /Link is not a text-bearing subtype, even though /Link
    annotations can carry an optional /Contents description."""
    pdf = _mutate_fixture_06(
        tmp_path,
        subtype="/Link",
        f_flag=2,
        contents="HIDDEN_TEXT_PAYLOAD: actual revenue $10,000",
    )
    findings = detect_pdf_hidden_text_annotation(pdf)
    assert findings == [], (
        f"/Link annotation with /F=2 wrongly fired the detector "
        f"(subtype filter should have rejected it); got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )


# ---------------------------------------------------------------------------
# 5. Multi-annotation: two hidden annotations -> two findings
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_fires_on_multiple_hidden_annotations(
    tmp_path: Path,
) -> None:
    """Two hidden /Text annotations on the same page must both
    fire. The detector must not short-circuit on first match."""
    pdf = _add_second_hidden_annotation(
        tmp_path,
        contents_a="HIDDEN_PAYLOAD_A: first concealed message",
        contents_b="HIDDEN_PAYLOAD_B: second concealed message",
    )
    findings = detect_pdf_hidden_text_annotation(pdf)
    matching = [
        f for f in findings
        if f.mechanism == "pdf_hidden_text_annotation"
    ]
    assert len(matching) == 2, (
        f"Expected two pdf_hidden_text_annotation findings on a PDF "
        f"with two hidden annotations; got {len(matching)}"
    )
    payloads = {f.concealed for f in matching}
    assert any("HIDDEN_PAYLOAD_A" in p for p in payloads), (
        f"Did not surface first payload; got {payloads}"
    )
    assert any("HIDDEN_PAYLOAD_B" in p for p in payloads), (
        f"Did not surface second payload; got {payloads}"
    )


# ---------------------------------------------------------------------------
# 6. Defensive: unparseable bytes
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_clean_on_unparseable_pdf(
    tmp_path: Path,
) -> None:
    """A file that is not a valid PDF must produce zero findings;
    the detector must NOT raise."""
    bad = tmp_path / "garbage.pdf"
    bad.write_bytes(b"this is not a PDF, not even close")
    findings = detect_pdf_hidden_text_annotation(bad)
    assert findings == [], (
        f"Unparseable input wrongly produced findings: "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )


def test_pdf_hidden_text_annotation_clean_on_missing_file(
    tmp_path: Path,
) -> None:
    """A missing file must produce zero findings without raising
    (the host BatinObjectAnalyzer's other paths handle the
    file-not-found case at a different layer)."""
    missing = tmp_path / "does_not_exist.pdf"
    findings = detect_pdf_hidden_text_annotation(missing)
    assert findings == []


# ---------------------------------------------------------------------------
# Bit-mask coverage: NoView and LockedContents fire too
# ---------------------------------------------------------------------------

def test_pdf_hidden_text_annotation_fires_on_noview_bit(
    tmp_path: Path,
) -> None:
    """NoView (bit 6, value 32) is a suppression bit alongside
    Hidden. An annotation with /F=32 and substantive /Contents must
    fire."""
    pdf = _mutate_fixture_06(
        tmp_path,
        subtype="/Text",
        f_flag=32,  # NoView only
        contents="HIDDEN_PAYLOAD_NOVIEW: revenue actual $10,000",
    )
    findings = detect_pdf_hidden_text_annotation(pdf)
    matching = [
        f for f in findings
        if f.mechanism == "pdf_hidden_text_annotation"
    ]
    assert len(matching) == 1, (
        f"NoView bit (32) did not fire the detector; got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )
    assert "NoView" in matching[0].concealed


def test_pdf_hidden_text_annotation_fires_on_locked_contents_bit(
    tmp_path: Path,
) -> None:
    """LockedContents (bit 10, value 512) is a suppression bit
    alongside Hidden. An annotation with /F=512 and substantive
    /Contents must fire."""
    pdf = _mutate_fixture_06(
        tmp_path,
        subtype="/Text",
        f_flag=512,  # LockedContents only
        contents="HIDDEN_PAYLOAD_LOCKED: revenue actual $10,000",
    )
    findings = detect_pdf_hidden_text_annotation(pdf)
    matching = [
        f for f in findings
        if f.mechanism == "pdf_hidden_text_annotation"
    ]
    assert len(matching) == 1, (
        f"LockedContents bit (512) did not fire the detector; got "
        f"{[(f.mechanism, f.location) for f in findings]}"
    )
    assert "LockedContents" in matching[0].concealed
