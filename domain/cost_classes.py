"""Cost-class taxonomy for every mechanism in MECHANISM_REGISTRY.

The taxonomy describes the algorithmic shape of each detector with respect
to the document it inspects. The classes are:

  Class A (structural address, O(1) per address): the detector reads a
      single catalog or metadata field. Examples: a /OpenAction key on
      the catalog, a single CSV BOM byte, an EML From header. These
      detectors are essentially free once the address is known.

  Class B (indexed content walk, O(content) shared): the detector
      inspects every span, every annotation, every font, every row,
      every cell. The walk is shared across all class-B detectors via
      the content index: walk once, dispatch many.

  Class C (cross-correlation, O(n^2) bounded): the detector compares
      content addresses to each other. Examples: overlapping text spans,
      cross-modal correlation. Without spatial indexing this work grows
      quadratically. v1.1.5 adds spatial indexing to bound it.

  Class D (full re-parse, O(file_size)): the detector walks the raw
      byte stream. Examples: %%EOF position scan for incremental_update,
      trailing-byte signature scan. These are unavoidable; the cost is
      a single linear pass paid once per scan.

The taxonomy is per-document. It does NOT prescribe execution order
across documents (that is a horizontal-scaling concern, deferred to v1.2).
It DOES inform pass ordering within a single scan in production mode:
class A first, class B next, class C and D last, with early termination
on a Tier 1 severity 1.0 finding allowed in production mode (see
application/scan_service.py mode parameter).

For non-PDF analyzers (DOCX, XLSX, HTML, EML, CSV, JSON, image, audio,
video, SVG, PPTX, text-format, cross-modal), the cost class describes the
algorithmic shape even though the v1.1.4 ContentIndex does not yet serve
them. Non-PDF format indexing is a separate optimization deferred to
later versions.

Reference: docs/v1.1.4/SCALE_PLAN.md.
"""
from __future__ import annotations

from enum import Enum
from typing import Final


class CostClass(Enum):
    """Algorithmic shape of a mechanism with respect to one document."""

    A = "structural_address"   # O(1) per address
    B = "indexed_content"      # O(content) shared via content index
    C = "cross_correlation"    # O(n^2) bounded
    D = "full_reparse"         # O(file_size)


# ---------------------------------------------------------------------------
# Mechanism cost class assignments.
# ---------------------------------------------------------------------------
#
# Rules of thumb followed when assigning:
#
#   - "checks one catalog field, one trailer key, one header, one root
#     metadata block" -> A.
#   - "iterates every span, every annotation, every cell, every row,
#     every font, every block" -> B.
#   - "compares pairs of items, looks for overlap or cross-format
#     coordination" -> C.
#   - "scans raw byte stream for a marker, counts %%EOF, walks the full
#     trailing payload" -> D.
#
# When in doubt the assignment errs toward the more expensive class so
# pass ordering does not surprise. Re-classification is cheap (one
# entry in this dict); under-classifying a hot mechanism is a perf bug.

MECHANISM_COST_CLASS: Final[dict[str, "CostClass"]] = {
    # --- ROUTING (Tier 0) ---
    "format_routing_divergence": CostClass.A,  # extension vs sniffed format

    # --- PDF object/catalog (BATIN, class A: single catalog/trailer field) ---
    "additional_actions":     CostClass.A,
    "embedded_file":          CostClass.A,
    "extension_mismatch":     CostClass.A,
    "file_attachment_annot":  CostClass.B,  # walks annotation list
    "hidden_ocg":             CostClass.A,
    "high_entropy_metadata":  CostClass.A,
    "javascript":             CostClass.A,
    "launch_action":          CostClass.A,
    "metadata_anomaly":       CostClass.A,
    "openaction":             CostClass.A,
    "oversized_metadata":     CostClass.A,
    "pdf_metadata_analyzer":  CostClass.A,
    "pdf_trailer_analyzer":   CostClass.A,
    "duplicate_keys":         CostClass.A,
    "excessive_nesting":      CostClass.B,  # walks the object tree
    "incremental_update":     CostClass.D,  # %%EOF count over raw bytes
    "trailing_data":          CostClass.D,  # raw byte trailing payload

    # --- PDF text/span (ZAHIR, class B: inspects every span on every page) ---
    "bidi_control":           CostClass.B,
    "homoglyph":              CostClass.B,
    "invisible_render_mode":  CostClass.B,
    "mathematical_alphanumeric": CostClass.B,
    "microscopic_font":       CostClass.B,
    "off_page_text":          CostClass.B,
    "pdf_hidden_text_annotation": CostClass.B,
    "pdf_off_page_text":      CostClass.B,
    "tag_chars":              CostClass.B,
    "tounicode_anomaly":      CostClass.B,  # walks font ToUnicode CMaps
    "white_on_white_text":    CostClass.B,
    "zero_width_chars":       CostClass.B,

    # --- PDF cross-correlation (class C: O(n^2) span pairs) ---
    "overlapping_text":       CostClass.C,
    "cross_format_payload_match": CostClass.C,
    "coordinated_concealment": CostClass.C,
    "generative_cipher_signature": CostClass.C,

    # --- DOCX (BATIN class A unless walks content) ---
    "docx_alt_chunk":         CostClass.A,
    "docx_comment_payload":   CostClass.B,
    "docx_embedded_object":   CostClass.A,
    "docx_external_relationship": CostClass.A,
    "docx_header_footer_payload": CostClass.B,
    "docx_hidden_text":       CostClass.B,
    "docx_metadata_payload":  CostClass.A,
    "docx_microscopic_font":  CostClass.B,
    "docx_orphan_footnote":   CostClass.B,
    "docx_revision_history":  CostClass.A,
    "docx_vba_macros":        CostClass.A,
    "docx_white_text":        CostClass.B,

    # --- XLSX ---
    "xlsx_comment_payload":   CostClass.B,
    "xlsx_csv_injection_formula": CostClass.B,
    "xlsx_data_validation_formula": CostClass.B,
    "xlsx_defined_name_payload": CostClass.A,
    "xlsx_embedded_object":   CostClass.A,
    "xlsx_external_link":     CostClass.A,
    "xlsx_hidden_row_column": CostClass.B,
    "xlsx_hidden_sheet":      CostClass.A,
    "xlsx_metadata_payload":  CostClass.A,
    "xlsx_microscopic_font":  CostClass.B,
    "xlsx_revision_history":  CostClass.A,
    "xlsx_vba_macros":        CostClass.A,
    "xlsx_white_text":        CostClass.B,

    # --- PPTX ---
    "pptx_action_hyperlink":     CostClass.B,
    "pptx_custom_xml_payload":   CostClass.A,
    "pptx_embedded_object":      CostClass.A,
    "pptx_external_link":        CostClass.A,
    "pptx_hidden_slide":         CostClass.A,
    "pptx_revision_history":     CostClass.A,
    "pptx_slide_master_injection": CostClass.B,
    "pptx_speaker_notes_injection": CostClass.B,
    "pptx_vba_macros":           CostClass.A,

    # --- HTML ---
    "html_comment_payload":     CostClass.B,
    "html_data_attribute":      CostClass.B,
    "html_external_reference":  CostClass.B,
    "html_hidden_text":         CostClass.B,
    "html_inline_script":       CostClass.B,
    "html_meta_payload":        CostClass.A,
    "html_noscript_payload":    CostClass.B,
    "html_style_content_payload": CostClass.B,
    "html_template_payload":    CostClass.B,
    "html_title_text_divergence": CostClass.A,

    # --- EML ---
    "eml_attachment_present":      CostClass.A,
    "eml_base64_text_part":        CostClass.B,
    "eml_display_name_spoof":      CostClass.A,
    "eml_encoded_subject_anomaly": CostClass.A,
    "eml_executable_attachment":   CostClass.B,
    "eml_external_reference":      CostClass.B,
    "eml_from_replyto_mismatch":   CostClass.A,
    "eml_header_continuation_payload": CostClass.B,
    "eml_hidden_html_content":     CostClass.B,
    "eml_macro_attachment":        CostClass.B,
    "eml_mime_boundary_anomaly":   CostClass.B,
    "eml_multipart_alternative_divergence": CostClass.C,
    "eml_nested_eml":              CostClass.B,
    "eml_received_chain_anomaly":  CostClass.B,
    "eml_returnpath_from_mismatch": CostClass.A,
    "eml_smuggled_header":         CostClass.B,
    "eml_xheader_payload":         CostClass.B,

    # --- CSV ---
    "csv_bidi_payload":            CostClass.B,
    "csv_bom_anomaly":             CostClass.A,
    "csv_column_type_drift":       CostClass.B,
    "csv_comment_row":             CostClass.B,
    "csv_encoding_divergence":     CostClass.A,
    "csv_formula_injection":       CostClass.B,
    "csv_inconsistent_columns":    CostClass.B,
    "csv_mixed_delimiter":         CostClass.B,
    "csv_mixed_encoding":          CostClass.B,
    "csv_null_byte":               CostClass.D,  # raw byte scan
    "csv_oversized_field":         CostClass.B,
    "csv_oversized_freetext_cell": CostClass.B,  # v1.1.8 F2 item 2
    "csv_payload_in_adjacent_cell": CostClass.C,  # v1.1.8 F2 item 6
    "csv_quoted_newline_payload":  CostClass.B,
    "csv_quoting_anomaly":         CostClass.B,
    "csv_zero_width_payload":      CostClass.B,

    # --- JSON ---
    "json_comment_anomaly":          CostClass.D,  # raw byte scan
    "json_key_invisible_chars":      CostClass.B,  # v1.1.8 F2 item 3
    "json_nested_payload":           CostClass.B,
    "json_oversized_string_band":    CostClass.B,  # v1.1.8 F2 item 5
    "json_prototype_pollution_key":  CostClass.B,
    "json_trailing_payload":         CostClass.D,
    "json_unicode_escape_payload":   CostClass.B,

    # --- SVG ---
    "svg_defs_unreferenced_text":  CostClass.B,
    "svg_desc_payload":            CostClass.B,
    "svg_embedded_data_uri":       CostClass.B,
    "svg_embedded_script":         CostClass.B,
    "svg_event_handler":           CostClass.B,
    "svg_external_reference":      CostClass.B,
    "svg_foreign_object":          CostClass.B,
    "svg_hidden_text":             CostClass.B,
    "svg_metadata_payload":        CostClass.A,
    "svg_microscopic_text":        CostClass.B,
    "svg_title_payload":           CostClass.B,
    "svg_white_text":              CostClass.B,

    # --- IMAGE ---
    "image_jpeg_appn_payload":     CostClass.B,
    "image_png_private_chunk":     CostClass.B,
    "image_png_text_chunk_payload": CostClass.B,
    "image_text_metadata":         CostClass.A,
    "multiple_idat_streams":       CostClass.B,
    "suspected_lsb_steganography": CostClass.D,  # walks pixel bytes
    "suspicious_image_chunk":      CostClass.B,

    # --- AUDIO ---
    "audio_container_anomaly":         CostClass.A,
    "audio_cross_stem_divergence":     CostClass.C,
    "audio_embedded_payload":          CostClass.D,  # raw byte scan past header
    "audio_high_entropy_metadata":     CostClass.A,
    "audio_lsb_stego_candidate":       CostClass.D,
    "audio_lyrics_prompt_injection":   CostClass.B,
    "audio_metadata_identity_anomaly": CostClass.A,
    "audio_metadata_injection":        CostClass.A,
    "audio_stem_inventory":            CostClass.A,

    # --- VIDEO ---
    "video_container_anomaly":      CostClass.A,
    "video_cross_stem_divergence":  CostClass.C,
    "video_embedded_attachment":    CostClass.D,
    "video_frame_stego_candidate":  CostClass.D,
    "video_metadata_suspicious":    CostClass.A,
    "video_stream_inventory":       CostClass.A,
    "subtitle_injection":           CostClass.B,
    "subtitle_invisible_chars":     CostClass.B,

    # --- Cross-format (multi-document mechanisms) ---
    "cross_stem_inventory":        CostClass.B,
    "cross_stem_undeclared_text":  CostClass.C,

    # --- Infrastructure-only mechanisms (not concealment detectors) ---
    "scan_error":   CostClass.A,  # bookkeeping finding
    "scan_limited": CostClass.A,  # bookkeeping finding
    "unknown_format": CostClass.A,
}


# ---------------------------------------------------------------------------
# Import-time invariant: every registered mechanism has a cost class.
# ---------------------------------------------------------------------------

from domain.config import MECHANISM_REGISTRY  # noqa: E402

_unassigned = MECHANISM_REGISTRY - set(MECHANISM_COST_CLASS)
assert not _unassigned, (
    f"Mechanisms without a cost class: {sorted(_unassigned)}. "
    f"Every mechanism in MECHANISM_REGISTRY must appear in "
    f"MECHANISM_COST_CLASS."
)
_orphan = set(MECHANISM_COST_CLASS) - MECHANISM_REGISTRY
assert not _orphan, (
    f"Cost-class entries with no matching mechanism: {sorted(_orphan)}. "
    f"Every entry in MECHANISM_COST_CLASS must be a registered "
    f"mechanism."
)


def cost_class(mechanism: str) -> "CostClass":
    """Return the cost class for ``mechanism``.

    Raises KeyError if the mechanism is not registered. The import-time
    assertion guarantees every registered mechanism has a class, so a
    KeyError here means the caller passed a typo or an unregistered
    name.
    """
    return MECHANISM_COST_CLASS[mechanism]


__all__ = ["CostClass", "MECHANISM_COST_CLASS", "cost_class"]
