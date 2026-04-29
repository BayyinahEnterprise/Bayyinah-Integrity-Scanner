"""
Bayyinah fixture generator — one PDF per detector, plus a clean reference
standard and a combined positive-test bundle.

This module is the entry point for Phase 0 of the Al-Baqarah refactor
roadmap: it builds the ground-truth corpus that every subsequent phase
will scan against. Each fixture is its own independent module (the
Differentiator Framework's Modular Approach): generate → verify fires
the intended detector only → log. Skip after 3 failed attempts per the
Termination Acceptance principle.

Qur'anic anchor for the fixture catalogue:

    clean.pdf          — "This is the Book, there is no doubt in it"
                          (al-Baqarah 2:1-2). Reference standard.
    text/*.pdf         — zahir ≠ batin: what the file displays is not
                          what it contains (al-Baqarah 2:8-10).
    object/*.pdf       — tahrif: distortion in the vessel that carries
                          the text (al-Baqarah 2:79).
    positive_combined  — the complete munafiq pattern
                          (al-Baqarah 2:204).

Usage:
    python -m tests.make_test_documents                 # build all
    python -m tests.make_test_documents clean           # build clean.pdf only
    python -m tests.make_test_documents text.zero_width # one specific
    python -m tests.make_test_documents --list          # show catalogue
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pymupdf as fitz


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
(FIXTURES_DIR / "text").mkdir(exist_ok=True)
(FIXTURES_DIR / "object").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Shared helpers — extracted from make_positive_test.py so each builder
# stays small and single-purpose.
# ---------------------------------------------------------------------------

def utf16be_hex_with_bom(s: str) -> str:
    """Encode `s` as the hex payload of a PDF string literal (UTF-16BE + BOM)."""
    return "FEFF" + s.encode("utf-16-be").hex().upper()


def _atomic_save(doc: "fitz.Document", out_path: Path) -> None:
    """Save doc via a tmp file then copy — tolerates FUSE mounts that
    refuse in-place unlink-for-replace."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_"))
    try:
        tmp = tmp_dir / out_path.name
        doc.save(str(tmp))
        doc.close()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(tmp), str(out_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


_CYRILLIC_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:\\Windows\\Fonts\\arial.ttf",
]


def _find_cyrillic_font() -> str:
    """Locate a system TTF that has Cyrillic glyphs. Required by the
    homoglyph fixture, which must produce text whose visible rendering
    contains Cyrillic lookalike characters."""
    for p in _CYRILLIC_FONT_CANDIDATES:
        if Path(p).exists():
            return p
    raise RuntimeError(
        "No Cyrillic-capable system font found. Install one of: "
        + ", ".join(_CYRILLIC_FONT_CANDIDATES)
    )


def _pypdf_finalise(in_path: Path, out_path: Path, mutate_fn: Callable) -> None:
    """Re-open a pymupdf-built PDF with pypdf, apply `mutate_fn(writer)`,
    then write the result to `out_path`. Used by object-layer fixtures
    that need features pymupdf cannot cleanly express (catalog entries,
    embedded files, etc.)."""
    import pypdf

    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_pypdf_"))
    try:
        reader = pypdf.PdfReader(str(in_path))
        writer = pypdf.PdfWriter(clone_from=reader)
        mutate_fn(writer)
        tmp = tmp_dir / out_path.name
        with open(tmp, "wb") as f:
            writer.write(f)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(tmp), str(out_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fixture registry
# ---------------------------------------------------------------------------

@dataclass
class Fixture:
    """One fixture = one PDF + the single detector it is designed to fire."""
    name: str
    out_path: Path
    builder: Callable[[Path], None]
    expected_mechanisms: list[str] = field(default_factory=list)
    quran_anchor: str = ""
    description: str = ""


FIXTURES: dict[str, Fixture] = {}


def register(
    name: str,
    out_path: Path,
    expected_mechanisms: list[str],
    quran_anchor: str,
    description: str,
):
    """Decorator: register a builder function in the FIXTURES registry."""
    def _wrap(fn: Callable[[Path], None]) -> Callable[[Path], None]:
        FIXTURES[name] = Fixture(
            name=name,
            out_path=out_path,
            builder=fn,
            expected_mechanisms=expected_mechanisms,
            quran_anchor=quran_anchor,
            description=description,
        )
        return fn
    return _wrap


# ---------------------------------------------------------------------------
# Phase 0.2 — clean.pdf (the reference standard, al-Baqarah 2:1-2)
# ---------------------------------------------------------------------------

@register(
    name="clean",
    out_path=FIXTURES_DIR / "clean.pdf",
    expected_mechanisms=[],
    quran_anchor="al-Baqarah 2:1-2",
    description=(
        "A plain, well-formed PDF. Zero concealment mechanisms. If any "
        "analyzer fires on this file, that detector has a false-positive "
        "problem. This is the Book about which there is no doubt."
    ),
)
def build_clean(out_path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text(
        (72, 72),
        "Bayyinah fixture — clean reference standard.",
        fontsize=14, color=(0, 0, 0),
    )
    page.insert_text(
        (72, 108),
        "This document contains no concealment mechanisms.",
        fontsize=12, color=(0, 0, 0),
    )
    page.insert_text(
        (72, 144),
        "It is the reference against which detectors are calibrated.",
        fontsize=12, color=(0, 0, 0),
    )
    page.insert_text(
        (72, 180),
        "If any Bayyinah detector fires on this file, that detector",
        fontsize=12, color=(0, 0, 0),
    )
    page.insert_text(
        (72, 200),
        "has a false-positive problem on plain, well-formed input.",
        fontsize=12, color=(0, 0, 0),
    )
    # Set innocuous metadata so the metadata_anomaly detector has nothing
    # to latch onto.
    doc.set_metadata({
        "title": "Bayyinah Clean Reference",
        "author": "Bayyinah test fixtures",
        "subject": "Reference standard",
        "creator": "make_test_documents.py",
        "producer": "pymupdf",
    })
    _atomic_save(doc, out_path)


# ---------------------------------------------------------------------------
# Phase 0.3 — Text-layer zahir/batin fixtures (al-Baqarah 2:8-10)
#
# MDL order (specific codepoint-level → broader heuristic):
#   1. zero_width         — U+200B ZWSP via /ActualText
#   2. tag_characters     — Unicode TAG block (U+E0000..) via /ActualText
#   3. bidi_control       — RLO/LRO override
#   4. homoglyph          — direct mixed-script Unicode in a text run
#   5. invisible_render   — text rendering mode 3 (invisible)
#   6. microscopic_font   — fontsize < 1
#   7. white_on_white     — color=(1,1,1) on white background
#   8. overlapping_text   — two text spans at identical coordinates
# ---------------------------------------------------------------------------

@register(
    name="text.zero_width",
    out_path=FIXTURES_DIR / "text" / "zero_width.pdf",
    expected_mechanisms=["zero_width_chars"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Zero-width characters (U+200B ZWSP) smuggled via /ActualText. "
        "Visible glyphs render 'Hello'; /ActualText carries H·ZWSP·e·ZWSP·l..."
    ),
)
def build_text_zero_width(out_path: Path) -> None:
    """U+200B ZWSP smuggled via /ActualText. Visible: 'Hello'.
    /ActualText payload: H·ZWSP·e·ZWSP·l·ZWSP·l·ZWSP·o."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Zero-width fixture — visible decoy:", fontsize=12)
    page.insert_text((72, 108), "Hello", fontsize=14, color=(0, 0, 0))

    zwsp = "\u200B"
    payload = "H" + zwsp + "e" + zwsp + "l" + zwsp + "l" + zwsp + "o"
    actualtext_hex = utf16be_hex_with_bom(payload)
    fragment = (
        "\nq\nBT\n/helv 0.1 Tf\n1 0 0 1 72 2000 Tm\n"
        f"/Span << /ActualText <{actualtext_hex}> >> BDC\n"
        "(Hello) Tj\nEMC\nET\nQ\n"
    ).encode("latin-1")
    xrefs = page.get_contents()
    existing = b"\n".join(doc.xref_stream(x) for x in xrefs)
    doc.update_stream(xrefs[0], existing + fragment)
    for x in xrefs[1:]:
        doc.update_stream(x, b"")
    _atomic_save(doc, out_path)


@register(
    name="text.tag_characters",
    out_path=FIXTURES_DIR / "text" / "tag_characters.pdf",
    expected_mechanisms=["tag_chars"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Unicode TAG characters (U+E0000..) smuggled via /ActualText. "
        "Visible glyphs render 'Caption'; /ActualText carries "
        "'Caption' + TAG('BAYYINAH')."
    ),
)
def build_text_tag_characters(out_path: Path) -> None:
    """Unicode TAG block (U+E0020..U+E007E) smuggled via /ActualText.
    Visible: 'Caption'. /ActualText: 'Caption' + TAG('BAYYINAH')."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Tag-characters fixture — visible decoy:", fontsize=12)
    page.insert_text((72, 108), "Caption", fontsize=14, color=(0, 0, 0))

    payload = "Caption" + "".join(chr(0xE0000 + ord(c)) for c in "BAYYINAH")
    actualtext_hex = utf16be_hex_with_bom(payload)
    fragment = (
        "\nq\nBT\n/helv 0.1 Tf\n1 0 0 1 72 2000 Tm\n"
        f"/Span << /ActualText <{actualtext_hex}> >> BDC\n"
        "(Caption) Tj\nEMC\nET\nQ\n"
    ).encode("latin-1")
    xrefs = page.get_contents()
    existing = b"\n".join(doc.xref_stream(x) for x in xrefs)
    doc.update_stream(xrefs[0], existing + fragment)
    for x in xrefs[1:]:
        doc.update_stream(x, b"")
    _atomic_save(doc, out_path)


@register(
    name="text.bidi_control",
    out_path=FIXTURES_DIR / "text" / "bidi_control.pdf",
    expected_mechanisms=["bidi_control"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Bidi override character (U+202E RLO) planted in a text span to "
        "reverse visible reading order. Canonical Trojan Source pattern."
    ),
)
def build_text_bidi_control(out_path: Path) -> None:
    """U+202E RLO smuggled via /ActualText. Visible: 'invoice_pdf.exe'.
    /ActualText: 'invoice_' + RLO + 'fdp.exe' (classic Trojan-Source
    filename reversal — looks like 'invoice_exe.pdf' when rendered)."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Bidi-control fixture — visible decoy:", fontsize=12)
    page.insert_text((72, 108), "invoice_pdf.exe", fontsize=14, color=(0, 0, 0))

    rlo = "\u202E"
    payload = "invoice_" + rlo + "fdp.exe"
    actualtext_hex = utf16be_hex_with_bom(payload)
    fragment = (
        "\nq\nBT\n/helv 0.1 Tf\n1 0 0 1 72 2000 Tm\n"
        f"/Span << /ActualText <{actualtext_hex}> >> BDC\n"
        "(invoice_pdf.exe) Tj\nEMC\nET\nQ\n"
    ).encode("latin-1")
    xrefs = page.get_contents()
    existing = b"\n".join(doc.xref_stream(x) for x in xrefs)
    doc.update_stream(xrefs[0], existing + fragment)
    for x in xrefs[1:]:
        doc.update_stream(x, b"")
    _atomic_save(doc, out_path)


@register(
    name="text.homoglyph",
    out_path=FIXTURES_DIR / "text" / "homoglyph.pdf",
    # Mixed-script Unicode in a PDF text run also trips the
    # ToUnicode CMap consistency check (the font CMap maps the
    # Cyrillic glyph to the Latin codepoint to render it). Both
    # mechanisms firing on this fixture is correct: homoglyph
    # surfaces the script-mixing surface, tounicode_anomaly
    # surfaces the underlying CMap divergence.
    expected_mechanisms=["homoglyph", "tounicode_anomaly"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Mixed-script text: a word where Latin letters are substituted "
        "with Cyrillic lookalikes (e.g. 'pаypal' where 'а' is U+0430). "
        "Direct Unicode in the text run — no ToUnicode CMap trick."
    ),
)
def build_text_homoglyph(out_path: Path) -> None:
    """Mixed-script phishing word: 'pаypal' where 'а' is Cyrillic U+0430.
    Rendered directly with a Unicode-capable TTF so pymupdf's get_text
    returns the Cyrillic codepoint in the span text layer. The visible
    glyph looks like a plain Latin 'a' — the canonical phishing spoof.
    /check_homoglyphs fires on the word mixing Latin letters with
    non-Latin confusables."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    # Plain Latin decoy at the top (pymupdf's default Helvetica is fine
    # for pure Latin — and we want the homoglyph detector to fire only
    # on the planted word below, not on this line).
    page.insert_text((72, 72), "Homoglyph fixture — visible decoy:", fontsize=12)

    # The planted line uses a Cyrillic-capable TTF so the adversarial
    # codepoint actually survives through rendering and extraction.
    font_path = _find_cyrillic_font()
    page.insert_font(fontname="uni", fontfile=font_path)
    # Cyrillic U+0430 ('а') swapped in for the Latin 'a' in "paypal".
    page.insert_text(
        (72, 108),
        "Click here to sign in to p\u0430ypal",
        fontsize=14, fontname="uni",
    )
    _atomic_save(doc, out_path)


@register(
    name="text.invisible_render",
    out_path=FIXTURES_DIR / "text" / "invisible_render.pdf",
    expected_mechanisms=["invisible_render_mode"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Text rendering mode 3 (invisible). The text is in the PDF content "
        "stream but the renderer is instructed not to draw glyphs."
    ),
)
def build_text_invisible_render(out_path: Path) -> None:
    """Text drawn under render mode 3 (invisible). The content stream
    contains the payload and the Tj operator, but mode 3 tells the
    renderer not to draw glyphs."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Invisible-render fixture — visible decoy:", fontsize=12)
    page.insert_text((72, 108), "Nothing to see here.", fontsize=14)

    fragment = (
        "\nq\nBT\n/helv 12 Tf\n1 0 0 1 72 400 Tm\n"
        "3 Tr\n"
        "(INVISIBLE PAYLOAD: meet at the clock tower at midnight) Tj\n"
        "ET\nQ\n"
    ).encode("latin-1")
    xrefs = page.get_contents()
    existing = b"\n".join(doc.xref_stream(x) for x in xrefs)
    doc.update_stream(xrefs[0], existing + fragment)
    for x in xrefs[1:]:
        doc.update_stream(x, b"")
    _atomic_save(doc, out_path)


@register(
    name="text.microscopic_font",
    out_path=FIXTURES_DIR / "text" / "microscopic_font.pdf",
    expected_mechanisms=["microscopic_font"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Text set at fontsize 0.3 — technically rendered but functionally "
        "invisible to a human reader at any reasonable zoom."
    ),
)
def build_text_microscopic_font(out_path: Path) -> None:
    """Text drawn at 0.3 pt — below MICROSCOPIC_FONT_THRESHOLD (1.0 pt).
    Technically rendered but functionally invisible to a human reader."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Microscopic-font fixture — visible decoy:", fontsize=12)
    page.insert_text((72, 108), "This page looks mostly empty.", fontsize=14)
    page.insert_text(
        (72, 200),
        "MICROSCOPIC PAYLOAD: the crow flies at dawn",
        fontsize=0.3, color=(0, 0, 0),
    )
    _atomic_save(doc, out_path)


@register(
    name="text.white_on_white",
    out_path=FIXTURES_DIR / "text" / "white_on_white.pdf",
    expected_mechanisms=["white_on_white_text"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Text coloured white against the default white page background — "
        "invisible to a human reader, recoverable by text extraction."
    ),
)
def build_text_white_on_white(out_path: Path) -> None:
    """Text coloured white (1,1,1) on the default white page background —
    invisible to a human reader, recoverable by text extraction."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "White-on-white fixture — visible decoy:", fontsize=12)
    page.insert_text((72, 108), "This page looks mostly empty.", fontsize=14)
    page.insert_text(
        (72, 200),
        "WHITE-ON-WHITE PAYLOAD: secret meeting at midnight",
        fontsize=12, color=(1, 1, 1),
    )
    _atomic_save(doc, out_path)


@register(
    name="text.overlapping",
    out_path=FIXTURES_DIR / "text" / "overlapping.pdf",
    expected_mechanisms=["overlapping_text"],
    quran_anchor="al-Baqarah 2:8-10",
    description=(
        "Two text spans drawn at the same baseline + x-origin. The second "
        "span wins visually; the first remains in the text layer."
    ),
)
def build_text_overlapping(out_path: Path) -> None:
    """Two spans drawn at identical (x, y) with identical fontsize.
    The second span wins visually; the first remains in the text
    layer. Extraction returns both — surface ≠ contents."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Overlapping-text fixture — visible decoy:", fontsize=12)
    page.insert_text(
        (72, 200), "trust me, please send money",
        fontsize=14, color=(0, 0, 0),
    )
    page.insert_text(
        (72, 200), "boring accounting memo      ",
        fontsize=14, color=(0, 0, 0),
    )
    _atomic_save(doc, out_path)


# ---------------------------------------------------------------------------
# Phase 0.4 — Object-layer tahrif fixtures (al-Baqarah 2:79)
#
#   1. embedded_javascript     — /OpenAction → /JavaScript
#   2. embedded_attachment     — /EmbeddedFiles name tree entry
#   3. hidden_ocg              — /OCProperties with hidden layers
#   4. metadata_injection      — /Info with suspicious metadata
#   5. tounicode_cmap          — /ToUnicode Latin→Cyrillic remap
#   6. incremental_update      — two saves, second with append=True
#   7. additional_actions      — /AA dict in catalog (event-triggered actions)
# ---------------------------------------------------------------------------

@register(
    name="object.embedded_javascript",
    out_path=FIXTURES_DIR / "object" / "embedded_javascript.pdf",
    expected_mechanisms=["javascript", "openaction"],
    quran_anchor="al-Baqarah 2:79",
    description=(
        "/OpenAction in the catalog pointing to a /JavaScript action. "
        "The canonical active-content vector."
    ),
)
def build_object_embedded_javascript(out_path: Path) -> None:
    """/OpenAction → /JavaScript action in catalog, plus /Names
    /JavaScript name tree. Fires both `openaction` and `javascript`."""
    import pypdf
    from pypdf.generic import (
        ArrayObject, DictionaryObject, NameObject, TextStringObject,
    )

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Embedded-JavaScript fixture.", fontsize=12)
    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_js_"))
    try:
        tmp_base = tmp_dir / "base.pdf"
        doc.save(str(tmp_base))
        doc.close()

        def _mutate(writer: "pypdf.PdfWriter") -> None:
            # /OpenAction → /JavaScript action
            open_act = DictionaryObject()
            open_act[NameObject("/Type")] = NameObject("/Action")
            open_act[NameObject("/S")] = NameObject("/JavaScript")
            open_act[NameObject("/JS")] = TextStringObject(
                "app.alert('Bayyinah fixture: JS would run here');"
            )
            writer._root_object[NameObject("/OpenAction")] = writer._add_object(open_act)

            # /Names /JavaScript tree
            name_act = DictionaryObject()
            name_act[NameObject("/Type")] = NameObject("/Action")
            name_act[NameObject("/S")] = NameObject("/JavaScript")
            name_act[NameObject("/JS")] = TextStringObject("app.alert('name-tree JS');")
            name_ref = writer._add_object(name_act)
            js_tree = DictionaryObject()
            js_tree[NameObject("/Names")] = ArrayObject(
                [TextStringObject("test_js"), name_ref]
            )
            names = DictionaryObject()
            names[NameObject("/JavaScript")] = js_tree
            writer._root_object[NameObject("/Names")] = names

        _pypdf_finalise(tmp_base, out_path, _mutate)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@register(
    name="object.embedded_attachment",
    out_path=FIXTURES_DIR / "object" / "embedded_attachment.pdf",
    expected_mechanisms=["embedded_file"],
    quran_anchor="al-Baqarah 2:79",
    description=(
        "A file attached via the /EmbeddedFiles name tree — a secondary "
        "payload that travels invisibly with the visible document."
    ),
)
def build_object_embedded_attachment(out_path: Path) -> None:
    """A file embedded via the /EmbeddedFiles name tree. Fires
    `embedded_file`."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Embedded-attachment fixture.", fontsize=12)

    # pymupdf has first-class support for attachments via Document.embfile_add.
    attachment_bytes = b"This is a concealed payload.\n"
    doc.embfile_add(
        "payload.txt",
        attachment_bytes,
        filename="payload.txt",
        desc="Bayyinah fixture payload",
    )
    _atomic_save(doc, out_path)


@register(
    name="object.hidden_ocg",
    out_path=FIXTURES_DIR / "object" / "hidden_ocg.pdf",
    expected_mechanisms=["hidden_ocg"],
    quran_anchor="al-Baqarah 2:79",
    description=(
        "Optional Content Groups (PDF layers) marked hidden by default — "
        "content that the document contains but does not display."
    ),
)
def build_object_hidden_ocg(out_path: Path) -> None:
    """Optional Content Group marked hidden in /OCProperties /D /OFF.
    Fires `hidden_ocg`."""
    import pypdf
    from pypdf.generic import (
        ArrayObject, DictionaryObject, NameObject, TextStringObject,
    )

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Hidden-OCG fixture — visible layer.", fontsize=12)
    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_ocg_"))
    try:
        tmp_base = tmp_dir / "base.pdf"
        doc.save(str(tmp_base))
        doc.close()

        def _mutate(writer: "pypdf.PdfWriter") -> None:
            # Define one OCG and mark it hidden by default.
            ocg = DictionaryObject()
            ocg[NameObject("/Type")] = NameObject("/OCG")
            ocg[NameObject("/Name")] = TextStringObject("HiddenLayer")
            ocg_ref = writer._add_object(ocg)

            d_dict = DictionaryObject()
            d_dict[NameObject("/Order")] = ArrayObject([ocg_ref])
            d_dict[NameObject("/OFF")] = ArrayObject([ocg_ref])
            d_dict[NameObject("/ON")] = ArrayObject([])

            oc_props = DictionaryObject()
            oc_props[NameObject("/OCGs")] = ArrayObject([ocg_ref])
            oc_props[NameObject("/D")] = d_dict

            writer._root_object[NameObject("/OCProperties")] = oc_props

        _pypdf_finalise(tmp_base, out_path, _mutate)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@register(
    name="object.metadata_injection",
    out_path=FIXTURES_DIR / "object" / "metadata_injection.pdf",
    expected_mechanisms=["metadata_anomaly"],
    quran_anchor="al-Baqarah 2:79",
    description=(
        "Document /Info dictionary carrying prompt-injection-style text "
        "in a metadata field (Title/Subject/Keywords)."
    ),
)
def build_object_metadata_injection(out_path: Path) -> None:
    """Document /Info with ModDate preceding CreationDate — a temporal
    impossibility that fires `metadata_anomaly`."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Metadata-injection fixture.", fontsize=12)
    # PDF date strings compared lexicographically by v0: "D:2025..." < "D:2026..."
    doc.set_metadata({
        "title": "Bayyinah metadata fixture",
        "author": "fixture",
        "creationDate": "D:20260101000000",
        "modDate":      "D:20250101000000",
    })
    _atomic_save(doc, out_path)


@register(
    name="object.tounicode_cmap",
    out_path=FIXTURES_DIR / "object" / "tounicode_cmap.pdf",
    expected_mechanisms=["tounicode_anomaly"],
    quran_anchor="al-Baqarah 2:79",
    description=(
        "A font whose /ToUnicode CMap maps Latin-looking glyphs to "
        "Cyrillic codepoints. Any conforming extractor returns the "
        "homoglyph string; the visible rendering looks Latin."
    ),
)
def build_object_tounicode_cmap(out_path: Path) -> None:
    """A font defined in page Resources whose /ToUnicode CMap maps Latin
    CIDs to Cyrillic homoglyphs. The font is DEFINED but never USED in
    the content stream — so no span-level homoglyph or zw firing can
    piggy-back. `_scan_tounicode_cmaps` walks page /Resources /Font and
    fires `tounicode_anomaly` on the CMap alone."""
    import pypdf
    from pypdf.generic import (
        DecodedStreamObject, DictionaryObject, NameObject, NumberObject,
    )

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "ToUnicode-CMap fixture — plain visible text.", fontsize=12)
    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_tu_"))
    try:
        tmp_base = tmp_dir / "base.pdf"
        doc.save(str(tmp_base))
        doc.close()

        def _mutate(writer: "pypdf.PdfWriter") -> None:
            # Adversarial ToUnicode CMap: CIDs for H, e, l, o mapped to
            # H, Cyrillic-е (U+0435), l, Cyrillic-о (U+043E).
            cmap_body = (
                b"/CIDInit /ProcSet findresource begin\n"
                b"12 dict begin\nbegincmap\n"
                b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) "
                b"/Supplement 0 >> def\n"
                b"/CMapName /Adversarial-UCS def\n/CMapType 2 def\n"
                b"1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
                b"4 beginbfchar\n"
                b"<48> <0048>\n<65> <0435>\n<6C> <006C>\n<6F> <043E>\n"
                b"endbfchar\nendcmap\n"
                b"CMapName currentdict /CMap defineresource pop\nend\nend\n"
            )
            tu = DecodedStreamObject()
            tu._data = cmap_body
            tu[NameObject("/Length")] = NumberObject(len(cmap_body))
            tu_ref = writer._add_object(tu)

            # Adversarial Type1 font pointing at the adversarial CMap.
            font = DictionaryObject()
            font[NameObject("/Type")] = NameObject("/Font")
            font[NameObject("/Subtype")] = NameObject("/Type1")
            font[NameObject("/BaseFont")] = NameObject("/Helvetica")
            font[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
            font[NameObject("/ToUnicode")] = tu_ref
            font_ref = writer._add_object(font)

            # Attach to page /Resources /Font. Do NOT emit any Tj using it.
            page0 = writer.pages[0]
            resources = page0["/Resources"]
            if hasattr(resources, "get_object"):
                resources = resources.get_object()
            fonts_dict = resources.get("/Font")
            if fonts_dict is None:
                fonts_dict = DictionaryObject()
                resources[NameObject("/Font")] = fonts_dict
            elif hasattr(fonts_dict, "get_object"):
                fonts_dict = fonts_dict.get_object()
            fonts_dict[NameObject("/Fadv")] = font_ref

        _pypdf_finalise(tmp_base, out_path, _mutate)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@register(
    name="object.incremental_update",
    out_path=FIXTURES_DIR / "object" / "incremental_update.pdf",
    expected_mechanisms=["incremental_update"],
    quran_anchor="al-Baqarah 2:79",
    description=(
        "A PDF saved twice — the second save with append=True, producing "
        "an incremental update. The earlier revision remains in the byte "
        "stream (the naskh pattern)."
    ),
)
def build_object_incremental_update(out_path: Path) -> None:
    """Save once, then re-open and save with incremental=True. The result
    has ≥ 2 %%EOF markers — `_scan_incremental_updates` fires."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Incremental-update fixture — revision 1.", fontsize=12)
    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_incr_"))
    try:
        tmp_base = tmp_dir / "base.pdf"
        doc.save(str(tmp_base))
        doc.close()

        # Re-open and append a second revision as an incremental save.
        doc2 = fitz.open(str(tmp_base))
        doc2[0].insert_text(
            (72, 108),
            "Revision 2 added via incremental update.",
            fontsize=12,
        )
        doc2.save(
            str(tmp_base),
            incremental=True,
            encryption=fitz.PDF_ENCRYPT_KEEP,
        )
        doc2.close()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(tmp_base), str(out_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@register(
    name="object.additional_actions",
    out_path=FIXTURES_DIR / "object" / "additional_actions.pdf",
    expected_mechanisms=["additional_actions"],
    quran_anchor="al-Baqarah 2:79",
    description=(
        "/AA (Additional Actions) dictionary in the catalog — declares "
        "actions triggered by document-level events (open, close, save, "
        "print). A concealment surface invisible at render time."
    ),
)
def build_object_additional_actions(out_path: Path) -> None:
    """/AA (Additional Actions) dictionary in the catalog — declares
    actions fired on document-level events. Fires `additional_actions`.

    To avoid secondary firings we use a /GoTo action (no JavaScript, no
    launch) so only the /AA presence flag trips."""
    import pypdf
    from pypdf.generic import (
        ArrayObject, DictionaryObject, NameObject, NumberObject,
    )

    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 72), "Additional-actions fixture.", fontsize=12)
    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_aa_"))
    try:
        tmp_base = tmp_dir / "base.pdf"
        doc.save(str(tmp_base))
        doc.close()

        def _mutate(writer: "pypdf.PdfWriter") -> None:
            # A benign-looking GoTo-first-page action. The trigger is what
            # matters — /AA presence — not the target.
            page0 = writer.pages[0]
            dest = ArrayObject([page0.indirect_reference, NameObject("/Fit")])
            goto_act = DictionaryObject()
            goto_act[NameObject("/Type")] = NameObject("/Action")
            goto_act[NameObject("/S")] = NameObject("/GoTo")
            goto_act[NameObject("/D")] = dest
            goto_ref = writer._add_object(goto_act)

            aa = DictionaryObject()
            # /WC = Will-Close, /WS = Will-Save, /DS = Did-Save, /WP = Will-Print
            aa[NameObject("/WC")] = goto_ref
            writer._root_object[NameObject("/AA")] = aa

        _pypdf_finalise(tmp_base, out_path, _mutate)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Phase 0.5 — positive_combined.pdf (the complete munafiq pattern, 2:204)
# ---------------------------------------------------------------------------

@register(
    name="positive_combined",
    out_path=FIXTURES_DIR / "positive_combined.pdf",
    expected_mechanisms=[
        # Text-layer (8)
        "zero_width_chars", "tag_chars", "bidi_control", "homoglyph",
        "invisible_render_mode", "microscopic_font",
        "white_on_white_text", "overlapping_text",
        # Object-layer (8)
        "javascript", "openaction", "embedded_file", "hidden_ocg",
        "metadata_anomaly", "tounicode_anomaly", "additional_actions",
        "incremental_update",
    ],
    quran_anchor="al-Baqarah 2:204",
    description=(
        "The complete munafiq pattern: every concealment mechanism in "
        "one document. Pages and catalog carry the union of every "
        "single-mechanism fixture. 'His speech about worldly life "
        "pleases you — but he is the fiercest of opponents.'"
    ),
)
def build_positive_combined(out_path: Path) -> None:
    """Compose every single-mechanism fixture into one document, keeping
    them on separate pages / in separate catalog entries so they don't
    interact. Each mechanism lives in isolation to preserve the 1:1
    fixture↔detector correspondence at the combined level too."""
    import pypdf
    from pypdf.generic import (
        ArrayObject, DecodedStreamObject, DictionaryObject, NameObject,
        NumberObject, TextStringObject,
    )

    doc = fitz.open()

    # ----- Page 1: zero-width, tag, bidi via /ActualText ------------------
    page1 = doc.new_page(width=612, height=792)
    page1.insert_text((72, 72), "Combined fixture — page 1.", fontsize=12)
    page1.insert_text((72, 108), "Hello", fontsize=14)
    page1.insert_text((72, 140), "Caption", fontsize=14)
    page1.insert_text((72, 172), "invoice_pdf.exe", fontsize=14)

    zwsp = "\u200B"
    zw_payload = "H" + zwsp + "e" + zwsp + "l" + zwsp + "l" + zwsp + "o"
    tag_payload = "Caption" + "".join(chr(0xE0000 + ord(c)) for c in "BAYYINAH")
    rlo_payload = "invoice_\u202Efdp.exe"
    frag_p1 = (
        "\nq\nBT\n/helv 0.1 Tf\n1 0 0 1 72 2000 Tm\n"
        f"/Span << /ActualText <{utf16be_hex_with_bom(zw_payload)}> >> BDC\n"
        "(Hello) Tj\nEMC\nET\nQ\n"
        "q\nBT\n/helv 0.1 Tf\n1 0 0 1 72 2020 Tm\n"
        f"/Span << /ActualText <{utf16be_hex_with_bom(tag_payload)}> >> BDC\n"
        "(Caption) Tj\nEMC\nET\nQ\n"
        "q\nBT\n/helv 0.1 Tf\n1 0 0 1 72 2040 Tm\n"
        f"/Span << /ActualText <{utf16be_hex_with_bom(rlo_payload)}> >> BDC\n"
        "(invoice_pdf.exe) Tj\nEMC\nET\nQ\n"
    ).encode("latin-1")
    xrefs = page1.get_contents()
    existing = b"\n".join(doc.xref_stream(x) for x in xrefs)
    doc.update_stream(xrefs[0], existing + frag_p1)
    for x in xrefs[1:]:
        doc.update_stream(x, b"")

    # ----- Page 2: homoglyph via Cyrillic-capable font --------------------
    page2 = doc.new_page(width=612, height=792)
    page2.insert_text((72, 72), "Combined fixture — page 2 (homoglyph).", fontsize=12)
    page2.insert_font(fontname="uni", fontfile=_find_cyrillic_font())
    page2.insert_text(
        (72, 108),
        "Click here to sign in to p\u0430ypal",
        fontsize=14, fontname="uni",
    )

    # ----- Page 3: invisible render, microscopic, white-on-white, overlap
    page3 = doc.new_page(width=612, height=792)
    page3.insert_text((72, 72), "Combined fixture — page 3.", fontsize=12)
    # microscopic font
    page3.insert_text(
        (72, 140), "MICROSCOPIC PAYLOAD: dawn",
        fontsize=0.3, color=(0, 0, 0),
    )
    # white-on-white
    page3.insert_text(
        (72, 180), "WHITE-ON-WHITE PAYLOAD: midnight",
        fontsize=12, color=(1, 1, 1),
    )
    # overlapping spans
    page3.insert_text((72, 260), "trust me, please send money", fontsize=14)
    page3.insert_text((72, 260), "boring accounting memo      ", fontsize=14)
    # invisible render mode via appended content stream
    frag_p3 = (
        "\nq\nBT\n/helv 12 Tf\n1 0 0 1 72 400 Tm\n3 Tr\n"
        "(INVISIBLE PAYLOAD: meet at clock tower) Tj\nET\nQ\n"
    ).encode("latin-1")
    xrefs3 = page3.get_contents()
    existing3 = b"\n".join(doc.xref_stream(x) for x in xrefs3)
    doc.update_stream(xrefs3[0], existing3 + frag_p3)
    for x in xrefs3[1:]:
        doc.update_stream(x, b"")

    # ----- Metadata anomaly -----------------------------------------------
    doc.set_metadata({
        "title": "Bayyinah positive_combined",
        "author": "fixture",
        "creationDate": "D:20260101000000",
        "modDate":      "D:20250101000000",
    })

    # ----- Embedded file attachment ---------------------------------------
    doc.embfile_add(
        "payload.txt",
        b"This is a concealed payload.\n",
        filename="payload.txt",
        desc="Bayyinah fixture payload",
    )

    tmp_dir = Path(tempfile.mkdtemp(prefix="bayyinah_fx_combined_"))
    try:
        tmp_base = tmp_dir / "base.pdf"
        doc.save(str(tmp_base))
        doc.close()

        def _mutate(writer: "pypdf.PdfWriter") -> None:
            # /OpenAction → /JavaScript
            open_act = DictionaryObject()
            open_act[NameObject("/Type")] = NameObject("/Action")
            open_act[NameObject("/S")] = NameObject("/JavaScript")
            open_act[NameObject("/JS")] = TextStringObject(
                "app.alert('combined fixture JS');"
            )
            writer._root_object[NameObject("/OpenAction")] = writer._add_object(open_act)

            # /Names /JavaScript
            name_act = DictionaryObject()
            name_act[NameObject("/Type")] = NameObject("/Action")
            name_act[NameObject("/S")] = NameObject("/JavaScript")
            name_act[NameObject("/JS")] = TextStringObject("app.alert('name tree');")
            name_ref = writer._add_object(name_act)
            js_tree = DictionaryObject()
            js_tree[NameObject("/Names")] = ArrayObject(
                [TextStringObject("test_js"), name_ref]
            )
            # Preserve existing /Names tree (holds /EmbeddedFiles from pymupdf).
            existing_names = writer._root_object.get("/Names")
            if existing_names is not None:
                existing_names_obj = (
                    existing_names.get_object()
                    if hasattr(existing_names, "get_object") else existing_names
                )
                existing_names_obj[NameObject("/JavaScript")] = js_tree
            else:
                names = DictionaryObject()
                names[NameObject("/JavaScript")] = js_tree
                writer._root_object[NameObject("/Names")] = names

            # Additional actions (/AA) — GoTo first page on Will-Close
            page0 = writer.pages[0]
            dest = ArrayObject([page0.indirect_reference, NameObject("/Fit")])
            goto_act = DictionaryObject()
            goto_act[NameObject("/Type")] = NameObject("/Action")
            goto_act[NameObject("/S")] = NameObject("/GoTo")
            goto_act[NameObject("/D")] = dest
            goto_ref = writer._add_object(goto_act)
            aa = DictionaryObject()
            aa[NameObject("/WC")] = goto_ref
            writer._root_object[NameObject("/AA")] = aa

            # Hidden OCG
            ocg = DictionaryObject()
            ocg[NameObject("/Type")] = NameObject("/OCG")
            ocg[NameObject("/Name")] = TextStringObject("HiddenLayer")
            ocg_ref = writer._add_object(ocg)
            d_dict = DictionaryObject()
            d_dict[NameObject("/Order")] = ArrayObject([ocg_ref])
            d_dict[NameObject("/OFF")] = ArrayObject([ocg_ref])
            d_dict[NameObject("/ON")] = ArrayObject([])
            oc_props = DictionaryObject()
            oc_props[NameObject("/OCGs")] = ArrayObject([ocg_ref])
            oc_props[NameObject("/D")] = d_dict
            writer._root_object[NameObject("/OCProperties")] = oc_props

            # Adversarial ToUnicode CMap font, attached to page-1 resources,
            # never referenced by a Tj — triggers only tounicode_anomaly.
            cmap_body = (
                b"/CIDInit /ProcSet findresource begin\n"
                b"12 dict begin\nbegincmap\n"
                b"/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) "
                b"/Supplement 0 >> def\n"
                b"/CMapName /Adversarial-UCS def\n/CMapType 2 def\n"
                b"1 begincodespacerange\n<00> <FF>\nendcodespacerange\n"
                b"4 beginbfchar\n"
                b"<48> <0048>\n<65> <0435>\n<6C> <006C>\n<6F> <043E>\n"
                b"endbfchar\nendcmap\n"
                b"CMapName currentdict /CMap defineresource pop\nend\nend\n"
            )
            tu = DecodedStreamObject()
            tu._data = cmap_body
            tu[NameObject("/Length")] = NumberObject(len(cmap_body))
            tu_ref = writer._add_object(tu)
            font = DictionaryObject()
            font[NameObject("/Type")] = NameObject("/Font")
            font[NameObject("/Subtype")] = NameObject("/Type1")
            font[NameObject("/BaseFont")] = NameObject("/Helvetica")
            font[NameObject("/Encoding")] = NameObject("/WinAnsiEncoding")
            font[NameObject("/ToUnicode")] = tu_ref
            font_ref = writer._add_object(font)
            resources = writer.pages[0]["/Resources"]
            if hasattr(resources, "get_object"):
                resources = resources.get_object()
            fonts_dict = resources.get("/Font")
            if fonts_dict is None:
                fonts_dict = DictionaryObject()
                resources[NameObject("/Font")] = fonts_dict
            elif hasattr(fonts_dict, "get_object"):
                fonts_dict = fonts_dict.get_object()
            fonts_dict[NameObject("/Fadv")] = font_ref

        # Apply catalog mutations, then re-open for an incremental update.
        tmp_with_catalog = tmp_dir / "with_catalog.pdf"
        _pypdf_finalise(tmp_base, tmp_with_catalog, _mutate)

        doc3 = fitz.open(str(tmp_with_catalog))
        doc3[0].insert_text(
            (400, 72), "Rev 2 (incremental)", fontsize=10,
        )
        doc3.save(
            str(tmp_with_catalog),
            incremental=True,
            encryption=fitz.PDF_ENCRYPT_KEEP,
        )
        doc3.close()

        out_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(tmp_with_catalog), str(out_path))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_catalogue() -> None:
    print(f"{'name':<32} {'expected':<44} {'anchor':<20}")
    print("-" * 96)
    for name, fx in FIXTURES.items():
        if fx.expected_mechanisms:
            mechs = ", ".join(fx.expected_mechanisms)
        elif name == "clean":
            mechs = "(none — reference standard)"
        else:
            mechs = "(pending — expected list TBD)"
        print(f"{name:<32} {mechs:<44} {fx.quran_anchor:<20}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "names",
        nargs="*",
        help="Fixture names to build. Omit to build all.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the fixture catalogue and exit.",
    )
    args = parser.parse_args(argv)

    if args.list:
        _print_catalogue()
        return 0

    targets = args.names if args.names else list(FIXTURES)
    unknown = [n for n in targets if n not in FIXTURES]
    if unknown:
        print(f"ERROR: unknown fixture(s): {', '.join(unknown)}", file=sys.stderr)
        print(f"Run with --list to see available names.", file=sys.stderr)
        return 2

    built, skipped, failed = [], [], []
    for name in targets:
        fx = FIXTURES[name]
        try:
            fx.builder(fx.out_path)
        except NotImplementedError as exc:
            print(f"  SKIP  {name:<32} {exc}")
            skipped.append(name)
            continue
        except Exception as exc:
            print(f"  FAIL  {name:<32} {type(exc).__name__}: {exc}")
            failed.append(name)
            continue
        print(f"  OK    {name:<32} -> {fx.out_path.relative_to(FIXTURES_DIR.parent)}")
        built.append(name)

    print()
    print(f"Built {len(built)}, skipped {len(skipped)}, failed {len(failed)}.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
