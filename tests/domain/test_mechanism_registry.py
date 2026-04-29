"""
Tests for ``domain.config.MECHANISM_REGISTRY``.

The registry is the single auditable union of every mechanism Bayyinah
emits. Three properties are pinned:

  1. The count is exact (108 at v1.1): anyone who reads the public
     docs and counts can verify the number with a single import.
  2. The registry is the union of ZAHIR_MECHANISMS and BATIN_MECHANISMS,
     and the two source-layer sets are disjoint.
  3. The SEVERITY and TIER tables are coherent with the registry:
     every mechanism has both, and no orphan severity / tier entries
     exist for nonexistent mechanisms.

The strongest claim is property 3: the same coherence the
``domain/config.py`` module enforces at import time is also asserted
by the test suite, so a regression that bypasses the import-time check
(by, say, deleting the assertion line) is still caught here.
"""

from __future__ import annotations

import pytest

from domain.config import (
    BATIN_MECHANISMS,
    MECHANISM_REGISTRY,
    SEVERITY,
    TIER,
    ZAHIR_MECHANISMS,
)
from domain.config import ROUTING_MECHANISMS


def test_registry_is_frozenset() -> None:
    assert isinstance(MECHANISM_REGISTRY, frozenset)


def test_registry_count_is_exact_145() -> None:
    """Pin the count. Adding a mechanism must update this number;
    that is itself a structural reminder to update SEVERITY + TIER +
    the source-layer set in the same commit.

    Progression for v1.1.2:
      - Day 1 added format_routing_divergence (routing): 108 -> 109.
      - Day 2 mechanism 03 (pdf_off_page_text, zahir): 109 -> 110.
      - Day 2 mechanism 04 (pdf_metadata_analyzer, batin): 110 -> 111.
      - Day 2 mechanism 05 (pdf_trailer_analyzer, batin): 111 -> 112.
      - Day 2 mechanism 06 (pdf_hidden_text_annotation, zahir): 112 -> 113.
      - Format-gauntlet DOCX closure (6 mechanisms): 113 -> 119.
        zahir: docx_white_text, docx_microscopic_font,
               docx_header_footer_payload (113 -> 116).
        batin: docx_metadata_payload, docx_comment_payload,
               docx_orphan_footnote (116 -> 119).
      - Format-gauntlet XLSX closure (6 mechanisms): 119 -> 125.
        zahir: xlsx_white_text, xlsx_microscopic_font,
               xlsx_csv_injection_formula (119 -> 122).
        batin: xlsx_metadata_payload, xlsx_defined_name_payload,
               xlsx_comment_payload (122 -> 125).
    With the XLSX format gauntlet closure all 6 xlsx_gauntlet
    fixtures show full catch + payload recovery.

    With the HTML format gauntlet closure all 6 html_gauntlet
    fixtures show full catch + payload recovery, adding 6 mechanisms
    (1 zahir, 5 batin) to the registry: 125 -> 131.

    With the EML format gauntlet closure all 6 eml_gauntlet fixtures
    show full catch + payload recovery, adding 6 mechanisms (2 zahir,
    4 batin) to the registry: 131 -> 137.

    With the v1.1.2 image format gauntlet (F1) in progress, mechanisms
    are being added incrementally. Step 1 adds image_jpeg_appn_payload
    (batin) for JPEG APP4-15 segments carrying readable text payload:
    137 -> 138. Step 2 adds image_png_private_chunk (batin) for PNG
    private ancillary chunks carrying readable text, with Tier 2
    baseline plus per-trigger Tier 1 escalation: 138 -> 139.

    Step 3 adds image_png_text_chunk_payload, surfacing PNG public
    text chunks (tEXt, iTXt, zTXt) whose value field exhibits any of
    four byte-deterministic concealment triggers (length, bidi,
    zero-width, divergence markers) parallel to
    pdf_metadata_analyzer. 139 -> 140.

    Step 4 adds svg_white_text, the single zahir mechanism in F1.
    SVG <text> with fill=#FFFFFF (or near-white) on a default-or-
    white canvas mirrors the white-on-white text family across PDF,
    DOCX, and XLSX. 140 -> 141.

    Step 5 adds svg_title_payload, surfacing SVG <title> elements
    whose text content exceeds 64 bytes. <title> is the accessibility
    tooltip surface, scanned by indexers and LLMs but not rendered
    as glyph content. 141 -> 142.

    Step 6 adds svg_desc_payload, surfacing SVG <desc> elements
    whose text content exceeds 256 bytes. The 256-byte threshold is
    higher than svg_title_payload's 64-byte threshold because <desc>
    is the long-form accessibility description; multi-sentence chart
    legends and scientific diagram captions are legitimate.
    142 -> 143.

    Step 7 adds svg_metadata_payload, surfacing SVG <metadata>
    blocks whose aggregate text content exceeds 128 bytes.
    <metadata> carries machine-readable annotations (RDF, Dublin
    Core, Creative Commons license) read by indexers and LLMs but
    not rendered as glyph content. The 128-byte threshold sits
    between svg_title_payload (64) and svg_desc_payload (256)
    because well-formed metadata blocks holding only license URI
    and creator name fall well below 128 bytes, while payload-
    bearing metadata (multi-sentence dc:description) crosses it.
    143 -> 144.

    Step 8 adds svg_defs_unreferenced_text, surfacing SVG <text>
    elements nested inside <defs> whose id is never referenced by
    any <use> element (or which lack an id entirely and therefore
    cannot be instantiated by <use> at all). <defs> is the SVG
    template surface; its children render only when instantiated
    via <use href="#id">. Unreferenced text in <defs> is fully
    readable by indexers and LLMs but never appears as glyph
    content for the human reader. 144 -> 145.
    """
    assert len(MECHANISM_REGISTRY) == 145, (
        f"Mechanism count drift: expected 145 "
        f"(39 zahir + 105 batin + 1 routing), "
        f"got {len(MECHANISM_REGISTRY)} "
        f"(zahir={len(ZAHIR_MECHANISMS)}, batin={len(BATIN_MECHANISMS)}, "
        f"routing={len(ROUTING_MECHANISMS)})"
    )


def test_zahir_count_is_exact_39() -> None:
    """v1.1.2 Day 2 mechanisms 03 (pdf_off_page_text) and 06
    (pdf_hidden_text_annotation) both classify as zahir; the count
    moves from 27 (v1.0 baseline) through 28 (after mechanism 03)
    to 29 (after mechanism 06). Both signals are surface-readable
    once the parser walks the relevant object-graph slice (content
    stream for mechanism 03, /Annots for mechanism 06) with no
    hidden-state inference.

    Format-gauntlet DOCX closure adds three zahir mechanisms
    (docx_white_text, docx_microscopic_font,
    docx_header_footer_payload), all surface-readable from a single
    walk of the relevant OOXML part: 29 -> 32.

    Format-gauntlet XLSX closure adds three zahir mechanisms
    (xlsx_white_text, xlsx_microscopic_font,
    xlsx_csv_injection_formula). xlsx_white_text and
    xlsx_microscopic_font are surface-readable from the cell-style
    chain; xlsx_csv_injection_formula reads the formula text in the
    worksheet part. 32 -> 35.

    Format-gauntlet HTML closure adds one zahir mechanism
    (html_title_text_divergence). The title is a rendered surface
    (browser tab, bookmarks, search results); divergence between the
    title and the rendered body is a zahir-on-zahir mismatch parallel
    to the surface_text_divergence family. 35 -> 36.

    Format-gauntlet EML closure adds two zahir mechanisms
    (eml_from_replyto_mismatch, eml_base64_text_part). Sender identity
    is the rendered surface readers act on, so Reply-To divergence is
    zahir; base64 wrapping of a text part is content-scanner evasion
    against the rendered text body, also zahir. 36 -> 38.

    Format-gauntlet image (F1) step 4 adds one zahir mechanism
    (svg_white_text). The SVG <text> element lives on the rendered
    surface; painting it in the canvas color (white on default white
    canvas) hides it from a human reader while the bytes remain in
    the document tree. Mirrors pdf white_on_white_text,
    docx_white_text, and xlsx_white_text on the SVG axis. 38 -> 39."""
    assert len(ZAHIR_MECHANISMS) == 39


def test_batin_count_is_exact_105() -> None:
    """v1.1.2 Day 2 mechanisms 04 (pdf_metadata_analyzer) and 05
    (pdf_trailer_analyzer) both classify as batin; the count moves
    from 81 (v1.0 baseline) through 82 (after mechanism 04) to 83
    (after mechanism 05). Mechanism 06 (pdf_hidden_text_annotation)
    classifies as zahir, so the batin count remains at 83 after
    Day 2.

    Format-gauntlet DOCX closure adds three batin mechanisms
    (docx_metadata_payload, docx_comment_payload,
    docx_orphan_footnote), all of which inspect a package part
    that is not part of the rendered text surface: 83 -> 86.

    Format-gauntlet XLSX closure adds three batin mechanisms
    (xlsx_metadata_payload, xlsx_defined_name_payload,
    xlsx_comment_payload), each inspecting a package part
    (docProps/*, xl/workbook.xml definedNames, xl/comments/*) that
    is not part of the rendered grid surface. 86 -> 89.

    Format-gauntlet HTML closure adds five batin mechanisms
    (html_noscript_payload, html_template_payload,
    html_comment_payload, html_meta_payload,
    html_style_content_payload), each surfacing a payload locus the
    HtmlAnalyzer walker intentionally skips: non-visible containers
    (<noscript>, <template>), HTML comments, <meta> content
    attributes, and CSS pseudo-element content strings inside
    <style> blocks. 89 -> 94.

    Format-gauntlet EML closure adds four batin mechanisms
    (eml_returnpath_from_mismatch, eml_received_chain_anomaly,
    eml_header_continuation_payload, eml_xheader_payload). Each
    surfaces a routing- or header-layer shape that is concealed from
    the reader by default - mail clients render none of Return-Path,
    the Received chain, folded continuation lines, or X-* annotation
    values to the user, but parsers, downstream filters, and
    automation pipelines all read them. 94 -> 98.

    Format-gauntlet image (F1) step 1 adds one batin mechanism
    (image_jpeg_appn_payload), surfacing JPEG APP4-15 segments that
    carry readable UTF-8 text. APP0/1/2/3 are excluded as load-bearing
    metadata markers; APP4-15 have no standardised use in office or
    financial document workflows. 98 -> 99.

    Step 2 adds one batin mechanism (image_png_private_chunk),
    surfacing PNG private ancillary chunks (lowercase first and
    second bytes per RFC 2083) that carry readable text. Tier 2
    structural baseline plus per-trigger Tier 1 escalation
    findings (bidi, zero-width, length) parallel
    pdf_metadata_analyzer. 99 -> 100.

    Step 3 adds one batin mechanism (image_png_text_chunk_payload),
    surfacing PNG public text chunks (tEXt, iTXt, zTXt) whose value
    field exhibits any of four byte-deterministic triggers (length,
    bidi, zero-width, divergence markers) parallel to
    pdf_metadata_analyzer. Closes the parallel-structure gap with the
    PDF metadata analyzer for the public PNG text chunk namespace.
    100 -> 101.

    Step 5 adds one batin mechanism (svg_title_payload), surfacing
    SVG <title> elements whose text content exceeds 64 bytes. <title>
    is the accessibility tooltip surface, scanned by indexers and
    LLMs but not rendered as glyph content. 101 -> 102.

    Step 6 adds one batin mechanism (svg_desc_payload), surfacing
    SVG <desc> elements whose text content exceeds 256 bytes. <desc>
    is the SVG long-form accessibility description surface; the
    256-byte threshold is split from svg_title_payload's 64-byte
    threshold because <desc> has a different legitimate-use
    distribution. 102 -> 103."""
    assert len(BATIN_MECHANISMS) == 105


def test_registry_is_union_of_zahir_batin_and_routing() -> None:
    """v1.1.2 - the registry is the union of three layers:
    ZAHIR_MECHANISMS, BATIN_MECHANISMS, ROUTING_MECHANISMS."""
    assert MECHANISM_REGISTRY == (
        ZAHIR_MECHANISMS | BATIN_MECHANISMS | ROUTING_MECHANISMS
    )


def test_zahir_batin_and_routing_are_pairwise_disjoint() -> None:
    """Every mechanism belongs to exactly one source layer."""
    zb = ZAHIR_MECHANISMS & BATIN_MECHANISMS
    zr = ZAHIR_MECHANISMS & ROUTING_MECHANISMS
    br = BATIN_MECHANISMS & ROUTING_MECHANISMS
    assert zb == set(), f"Mechanisms in both ZAHIR and BATIN: {sorted(zb)}"
    assert zr == set(), f"Mechanisms in both ZAHIR and ROUTING: {sorted(zr)}"
    assert br == set(), f"Mechanisms in both BATIN and ROUTING: {sorted(br)}"


def test_severity_keys_match_registry() -> None:
    """Every mechanism has a SEVERITY entry; no orphan entries."""
    sev_keys = set(SEVERITY.keys())
    missing = MECHANISM_REGISTRY - sev_keys
    orphan = sev_keys - MECHANISM_REGISTRY
    assert not missing, f"Mechanisms without SEVERITY: {sorted(missing)}"
    assert not orphan, f"Orphan SEVERITY entries: {sorted(orphan)}"


def test_tier_keys_match_registry() -> None:
    """Every mechanism has a TIER entry; no orphan entries."""
    tier_keys = set(TIER.keys())
    missing = MECHANISM_REGISTRY - tier_keys
    orphan = tier_keys - MECHANISM_REGISTRY
    assert not missing, f"Mechanisms without TIER: {sorted(missing)}"
    assert not orphan, f"Orphan TIER entries: {sorted(orphan)}"


def test_every_severity_value_in_unit_interval() -> None:
    for mech, sev in SEVERITY.items():
        assert 0.0 <= sev <= 1.0, (
            f"Severity out of [0,1] range for {mech!r}: {sev}"
        )


def test_every_tier_value_is_zero_one_two_or_three() -> None:
    """v1.1.2 - tier 0 (routing transparency) is now legal for
    mechanisms in ROUTING_MECHANISMS. Tiers 1/2/3 remain the legal
    set for ZAHIR/BATIN concealment mechanisms."""
    for mech, tier in TIER.items():
        assert tier in (0, 1, 2, 3), (
            f"Tier out of {{0,1,2,3}} for {mech!r}: {tier}"
        )
        if tier == 0:
            assert mech in ROUTING_MECHANISMS, (
                f"Tier 0 found on non-routing mechanism {mech!r} - "
                f"Tier 0 is reserved for ROUTING_MECHANISMS"
            )


def test_registry_exposed_via_bayyinah_top_level() -> None:
    """The reviewer's load-bearing usage pattern must work:

        >>> from bayyinah import MECHANISM_REGISTRY

    The registry is part of the additive-only public surface
    (declared in ``bayyinah.__all__`` and asserted by the CI workflow).
    """
    import bayyinah
    assert "MECHANISM_REGISTRY" in bayyinah.__all__
    assert hasattr(bayyinah, "MECHANISM_REGISTRY")
    assert bayyinah.MECHANISM_REGISTRY is MECHANISM_REGISTRY
