#!/usr/bin/env python3
"""
Bayyinah v0 — PDF File Integrity Scanner
========================================

Detects hidden, concealed, or adversarial content in PDF documents by
extracting all content layers — visible and invisible — and reporting
whether what the file DISPLAYS matches what the file CONTAINS.

Operationalizes Section 9 (input-level performed alignment) of the
Munafiq Protocol (DOI: 10.5281/zenodo.19677111).

Scope (v0):
    - Rule-based only (no feature-learned detection).
    - Single-artifact, PDF-only.
    - Text layer + object layer.

Report format:
    - APS-style continuous integrity score in [0.0, 1.0].
    - Per-finding: mechanism, validity tier (1/2/3), confidence [0.0, 1.0], location.
    - Inversion recovery: surface vs concealed representation, side-by-side.
    - Plain-language summary.

Godel constraint:
    This scanner does NOT self-validate a verdict. It surfaces observed
    mechanisms and their tiers. The reader performs the recognition.

Usage:
    python bayyinah_v0.py <pdf_path>
    python bayyinah_v0.py <pdf_path> --json
    python bayyinah_v0.py <pdf_path> --quiet

Dependencies (pip):
    pymupdf>=1.23
    pypdf>=4.0

Exit codes:
    0 — scan complete, no findings (integrity score 1.0)
    1 — scan complete, findings present (integrity score < 1.0)
    2 — scan error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import pymupdf as fitz  # pymupdf >= 1.24 exposes the 'pymupdf' module name
except ImportError:
    try:
        import fitz  # older pymupdf
    except ImportError:
        sys.stderr.write("ERROR: pymupdf not installed. Run: pip install pymupdf\n")
        sys.exit(2)

try:
    import pypdf
except ImportError:
    sys.stderr.write("ERROR: pypdf not installed. Run: pip install pypdf\n")
    sys.exit(2)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ZERO_WIDTH_CHARS = frozenset([
    "\u200B",  # ZWSP
    "\u200C",  # ZWNJ
    "\u200D",  # ZWJ
    "\u2060",  # WORD JOINER
    "\uFEFF",  # BOM / ZWNBSP
])

BIDI_CONTROL_CHARS = frozenset([
    "\u202A", "\u202B", "\u202C", "\u202D", "\u202E",  # embedding / override
    "\u2066", "\u2067", "\u2068", "\u2069",            # isolates
])

# Unicode TAG block — used for smuggling payloads through model input pipelines
TAG_CHAR_RANGE = range(0xE0000, 0xE0080)

# Most common confusable characters that look like Latin letters but are not.
# (Curated subset of the Unicode Consortium's confusables.txt, biased toward
# letters with high impersonation value — the ones you see in phishing domain
# attacks.) Mapping is from lookalike codepoint -> Latin glyph it imitates.
CONFUSABLE_TO_LATIN: dict[str, str] = {
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

INVISIBLE_RENDER_MODE = 3

MICROSCOPIC_FONT_THRESHOLD = 1.0  # points; anything below is sub-visual
BACKGROUND_LUMINANCE_WHITE = 1.0
COLOR_CONTRAST_THRESHOLD = 0.05  # delta luminance below which text blends with white bg
SPAN_OVERLAP_THRESHOLD = 0.5     # bbox IoU above which overlapping spans are flagged

# Severity weights — how much each mechanism subtracts from the base 1.0 score.
# APS-style: continuous contribution, not a binary verdict.
SEVERITY = {
    # Text layer
    "invisible_render_mode": 0.25,
    "white_on_white_text":   0.20,
    "microscopic_font":      0.10,
    "off_page_text":         0.15,
    "zero_width_chars":      0.10,
    "bidi_control":          0.15,
    "tag_chars":             0.30,
    "overlapping_text":      0.25,
    "homoglyph":             0.20,
    # Object layer
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
    "scan_error":            0.00,  # reported but does not deduct
}

# Validity tier by mechanism:
#   1 — Verified: mechanism unambiguously identifiable; presence = concealment
#   2 — Structural: pattern of concealment, could be benign in rare cases
#   3 — Interpretive: suspicious, heavily context-dependent
TIER = {
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
    "scan_error":            3,
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class Finding:
    """A single observed concealment mechanism with inversion recovery."""
    mechanism: str
    tier: int
    confidence: float
    description: str
    location: str
    surface: str = ""       # what the file displays at this location
    concealed: str = ""     # what the file contains at this location
    severity_override: float | None = None  # per-finding sev override for sub-variants

    @property
    def severity(self) -> float:
        if self.severity_override is not None:
            return self.severity_override
        return SEVERITY.get(self.mechanism, 0.05)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mechanism": self.mechanism,
            "tier": self.tier,
            "confidence": round(self.confidence, 3),
            "severity": self.severity,
            "description": self.description,
            "location": self.location,
            "inversion_recovery": {
                "surface":   self.surface,
                "concealed": self.concealed,
            },
        }


@dataclass
class IntegrityReport:
    file_path: str
    integrity_score: float = 1.0
    findings: list[Finding] = field(default_factory=list)
    error: str | None = None
    scan_incomplete: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": "bayyinah",
            "version": "0.1.0",
            "file_path": self.file_path,
            "integrity_score": round(self.integrity_score, 3),
            "scan_incomplete": self.scan_incomplete,
            "verdict_disclaimer": (
                "This report presents observed mechanisms and their validity "
                "tiers. It does NOT self-validate a moral or malicious verdict. "
                "The scanner makes the invisible visible; the reader performs "
                "the recognition."
            ),
            "tier_legend": {
                "1": "Verified — unambiguous concealment",
                "2": "Structural — pattern of concealment, context may justify",
                "3": "Interpretive — suspicious, context-dependent",
            },
            "findings": [f.to_dict() for f in self.findings],
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Text-Layer Scanner
# ---------------------------------------------------------------------------

class TextLayerScanner:
    """Detects concealment at the text / rendering layer.

    Mechanisms:
        - Invisible render mode 3 (content-stream 'Tr 3' operator).
        - White-on-white (or near-background) text color.
        - Microscopic fonts.
        - Off-page text positioning.
        - Zero-width / bidi-control / Unicode TAG characters in text.
    """

    def __init__(self, doc: fitz.Document):
        self.doc = doc

    def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        for page_idx in range(len(self.doc)):
            page = self.doc[page_idx]
            findings.extend(self._scan_render_modes(page, page_idx))
            span_findings = self._scan_spans(page, page_idx)
            findings.extend(span_findings)
            # pymupdf's text extraction normalises away some adversarial
            # Unicode (zero-width, TAG chars, bidi controls) that were
            # smuggled via /ActualText marked content or hex strings with a
            # ToUnicode CMap. Scan the raw content stream for what the
            # span-level pass could have missed, deduping per-page.
            span_unicode_mechs = {
                f.mechanism for f in span_findings
                if f.mechanism in ("zero_width_chars", "bidi_control", "tag_chars")
            }
            findings.extend(
                self._scan_raw_unicode(page, page_idx, span_unicode_mechs)
            )
            findings.extend(self._scan_overlapping_spans(page, page_idx))
        return findings

    # -- render mode 3 -----------------------------------------------------

    def _scan_render_modes(self, page, page_idx: int) -> list[Finding]:
        """Parse content stream for 'N Tr' operators with N == 3."""
        findings: list[Finding] = []
        try:
            raw = page.read_contents()
            if not raw:
                return findings
            stream = raw.decode("latin-1", errors="ignore")
        except Exception:
            return findings

        stripped = self._strip_literal_strings(stream)
        tr_matches = list(re.finditer(r"(?<![A-Za-z0-9_])(\d+)\s+Tr\b", stripped))
        if not tr_matches:
            return findings

        # Reconstruct Tr-mode regions on the STRIPPED stream (start, end, mode)
        regions: list[tuple[int, int, int]] = []
        mode = 0
        mode_start = 0
        for m in tr_matches:
            new_mode = int(m.group(1))
            regions.append((mode_start, m.start(), mode))
            mode = new_mode
            mode_start = m.end()
        regions.append((mode_start, len(stripped), mode))

        invisible_regions = [(s, e) for (s, e, m) in regions
                             if m == INVISIBLE_RENDER_MODE and e > s]
        if not invisible_regions:
            return findings

        # For each invisible region, pull Tj/TJ strings from the corresponding
        # slice of the ORIGINAL stream (using positions — they match because
        # _strip_literal_strings preserves offsets).
        for (start, end) in invisible_regions:
            segment = stream[start:end]
            concealed = self._extract_tj_strings(segment)
            if concealed:
                concealed_preview = concealed[:500]
                findings.append(Finding(
                    mechanism="invisible_render_mode",
                    tier=TIER["invisible_render_mode"],
                    confidence=0.95,
                    description=(
                        f"Text rendered with render mode 3 (invisible). "
                        f"{len(concealed)} character(s) of hidden text extracted."
                    ),
                    location=f"page {page_idx + 1}",
                    surface="(nothing visible at this location)",
                    concealed=concealed_preview,
                ))
            else:
                # Capability-only sub-variant: render-mode-3 is armed but no
                # Tj/TJ operators draw text in the invisible region. This is
                # the Internet-Archive-OCR pattern on scanned PDFs — the
                # capability is structurally present without a payload. Keep
                # the mechanism name stable but down-tier: Tier 3 / sev 0.05.
                findings.append(Finding(
                    mechanism="invisible_render_mode",
                    tier=3,
                    confidence=0.6,
                    description=(
                        "Content stream activates text render mode 3 (invisible) "
                        "but no text-drawing operators were found in the region. "
                        "Concealment capability present without payload."
                    ),
                    location=f"page {page_idx + 1}",
                    surface="(nothing visible)",
                    concealed="(capability only; no text drawn)",
                    severity_override=0.05,
                ))
        return findings

    @staticmethod
    def _strip_literal_strings(s: str) -> str:
        """Replace ( ... ) and < ... > string literals with spaces of equal
        length. Preserves byte offsets so region indices stay aligned with
        the original stream."""
        out = list(s)
        n = len(s)
        i = 0
        while i < n:
            c = s[i]
            if c == "(":
                depth = 1
                j = i + 1
                while j < n and depth > 0:
                    if s[j] == "\\" and j + 1 < n:
                        j += 2
                        continue
                    if s[j] == "(":
                        depth += 1
                    elif s[j] == ")":
                        depth -= 1
                    j += 1
                for k in range(i, min(j, n)):
                    out[k] = " "
                i = j
            elif c == "<":
                j = i + 1
                while j < n and s[j] != ">":
                    j += 1
                for k in range(i, min(j + 1, n)):
                    out[k] = " "
                i = j + 1
            else:
                i += 1
        return "".join(out)

    @staticmethod
    def _extract_tj_strings(segment: str) -> str:
        """Extract and decode text drawn by Tj / TJ operators within a segment."""
        pieces: list[str] = []
        # Tj: single literal string
        for m in re.finditer(r"\((.*?)(?<!\\)\)\s*Tj", segment, re.DOTALL):
            pieces.append(TextLayerScanner._decode_pdf_literal(m.group(1)))
        # TJ: array of strings and numeric kerning offsets
        for m in re.finditer(r"\[(.*?)\]\s*TJ", segment, re.DOTALL):
            arr = m.group(1)
            for lit in re.finditer(r"\((.*?)(?<!\\)\)", arr, re.DOTALL):
                pieces.append(TextLayerScanner._decode_pdf_literal(lit.group(1)))
        return "".join(pieces)

    @staticmethod
    def _decode_pdf_literal(s: str) -> str:
        """Best-effort decode of escape sequences in a PDF literal string."""
        # Octal escapes
        s = re.sub(
            r"\\([0-7]{1,3})",
            lambda m: chr(int(m.group(1), 8)),
            s,
        )
        # Named escapes
        s = (
            s.replace(r"\n", "\n")
             .replace(r"\r", "\r")
             .replace(r"\t", "\t")
             .replace(r"\b", "\b")
             .replace(r"\f", "\f")
             .replace(r"\(", "(")
             .replace(r"\)", ")")
             .replace(r"\\", "\\")
        )
        return s

    # -- overlapping / stacked text ---------------------------------------

    def _scan_overlapping_spans(self, page, page_idx: int) -> list[Finding]:
        """Flag cases where two text spans have substantially overlapping
        bounding boxes but different text content. In PDF rendering the
        later-drawn glyphs paint over the earlier ones, so a reader sees
        only the top layer while text extraction returns both — a
        canonical surface/content divergence."""
        try:
            page_dict = page.get_text("dict")
        except Exception:
            return []
        spans: list[tuple[tuple[float, float, float, float], str]] = []
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = (span.get("text") or "").strip()
                    if not text:
                        continue
                    bbox = tuple(span.get("bbox", (0, 0, 0, 0)))
                    # Ignore degenerate / zero-area spans.
                    if (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]) <= 0:
                        continue
                    spans.append((bbox, text))
        if len(spans) < 2:
            return []

        findings: list[Finding] = []
        seen_pairs: set[tuple[int, int]] = set()
        for i, (b1, t1) in enumerate(spans):
            for j in range(i + 1, len(spans)):
                b2, t2 = spans[j]
                iou = self._bbox_iou(b1, b2)
                if iou < SPAN_OVERLAP_THRESHOLD:
                    continue
                if t1 == t2:
                    # Same text drawn twice (bold emulation, stroked+filled
                    # rendering, etc.). No information-theoretic divergence.
                    continue
                pair_key = (id(t1) & 0xFFFF, id(t2) & 0xFFFF)
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                findings.append(Finding(
                    mechanism="overlapping_text",
                    tier=TIER["overlapping_text"],
                    confidence=0.75,
                    description=(
                        f"Two text spans share {iou:.0%} of their bounding-box area "
                        "but contain different text. The later-drawn span "
                        "occludes the other visually; both survive in the text layer."
                    ),
                    location=f"page {page_idx + 1}, bbox {b1}",
                    surface=t2[:200],
                    concealed=t1[:200],
                ))
        return findings

    @staticmethod
    def _bbox_iou(a, b) -> float:
        ax0, ay0, ax1, ay1 = a
        bx0, by0, bx1, by1 = b
        ox0, oy0 = max(ax0, bx0), max(ay0, by0)
        ox1, oy1 = min(ax1, bx1), min(ay1, by1)
        if ox1 <= ox0 or oy1 <= oy0:
            return 0.0
        inter = (ox1 - ox0) * (oy1 - oy0)
        area_a = max((ax1 - ax0) * (ay1 - ay0), 1e-9)
        area_b = max((bx1 - bx0) * (by1 - by0), 1e-9)
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    # -- raw-stream unicode scan -------------------------------------------

    def _scan_raw_unicode(
        self, page, page_idx: int, skip_mechs: set[str] | None = None,
    ) -> list[Finding]:
        """Scan the raw content stream for zero-width / bidi / TAG chars
        that a normalised text extractor (pymupdf get_text) may have
        stripped. Looks inside:

            - Tj / TJ literal strings `(...)`, interpreting as Latin-1 and
              as UTF-8 (the latter catches e.g. a UTF-8 ZWSP `\\xe2\\x80\\x8b`
              typed directly into a font that happens to pass it through).
            - Tj / TJ hex strings `<...>`, interpreting as UTF-16BE (with or
              without a leading FEFF BOM) — the standard encoding for
              non-latin or non-BMP codepoints in PDF text-showing operators
              when paired with a ToUnicode CMap.
            - `/ActualText (...)` and `/ActualText <...>` entries inside
              marked-content sequences — the common smuggling vector:
              visible glyphs draw harmless text, while the /ActualText
              property (returned by conforming text extractors) carries the
              adversarial payload.
        """
        skip = skip_mechs or set()
        try:
            raw = page.read_contents()
            if not raw:
                return []
        except Exception:
            return []

        stream = raw.decode("latin-1", errors="ignore")

        # We aggregate per-mechanism across the page so a page with many
        # injected ZWSPs produces one finding, not dozens.
        zw_hits: list[tuple[str, str]] = []    # (visible, codepoints)
        bidi_hits: list[tuple[str, str]] = []
        tag_hits: list[tuple[str, str]] = []

        def accumulate(decoded: str, source_label: str) -> None:
            zw = [c for c in decoded if c in ZERO_WIDTH_CHARS]
            if zw:
                visible = decoded
                for c in ZERO_WIDTH_CHARS:
                    visible = visible.replace(c, "")
                zw_hits.append((
                    f"{source_label}: {visible[:120]}",
                    " | ".join(f"U+{ord(c):04X}" for c in zw[:24]) +
                    (" ..." if len(zw) > 24 else ""),
                ))
            bidi = [c for c in decoded if c in BIDI_CONTROL_CHARS]
            if bidi:
                bidi_hits.append((
                    f"{source_label}: {decoded[:120]}",
                    " | ".join(f"U+{ord(c):04X}" for c in bidi[:24]) +
                    (" ..." if len(bidi) > 24 else ""),
                ))
            tag = [c for c in decoded if ord(c) in TAG_CHAR_RANGE]
            if tag:
                decoded_ascii = "".join(
                    chr(ord(c) - 0xE0000) for c in tag
                    if 0xE0020 <= ord(c) <= 0xE007E
                )
                visible = re.sub(r"[\U000E0000-\U000E007F]", "", decoded)
                tag_hits.append((
                    f"{source_label}: {visible[:120]}",
                    " | ".join(f"U+{ord(c):06X}" for c in tag[:12]) +
                    (" ..." if len(tag) > 12 else "") +
                    (f"  decoded: {decoded_ascii!r}" if decoded_ascii else ""),
                ))

        # 1. /ActualText (...) literal form
        for m in re.finditer(
            r"/ActualText\s*\((.*?)(?<!\\)\)", stream, re.DOTALL,
        ):
            body = self._decode_pdf_literal(m.group(1))
            # Literal-string /ActualText is typically PDFDocEncoding but may
            # carry UTF-8 bytes. Try the latin-1 view first, then a UTF-8
            # re-decode of the same bytes in case the PDF writer used UTF-8.
            accumulate(body, "/ActualText literal")
            try:
                body_utf8 = body.encode("latin-1").decode("utf-8")
                if body_utf8 != body:
                    accumulate(body_utf8, "/ActualText literal (utf-8)")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # 2. /ActualText <...> hex form — canonical UTF-16BE per PDF spec.
        for m in re.finditer(
            r"/ActualText\s*<([0-9A-Fa-f\s]+)>", stream,
        ):
            decoded = self._decode_hex_text(m.group(1), prefer_utf16be=True)
            if decoded:
                accumulate(decoded, "/ActualText hex")

        # 3. Bare hex text strings `<...> Tj` or `<...> TJ`.
        #
        #    Plain Tj/TJ hex strings are encoded per the current font's
        #    encoding — typically single-byte (WinAnsi / MacRoman) for the
        #    standard fonts, or two-byte CIDs for composite (Identity-H)
        #    fonts. Without parsing the ToUnicode CMap we cannot know which
        #    applies, so we default to Latin-1 (the safe, low-false-
        #    positive interpretation for WinAnsi text). We only try UTF-16BE
        #    when a leading FEFF BOM makes the intent unambiguous.
        for m in re.finditer(
            r"<([0-9A-Fa-f\s]+)>\s*T[jJ]", stream,
        ):
            decoded = self._decode_hex_text(m.group(1), prefer_utf16be=False)
            if decoded:
                accumulate(decoded, "hex text string")

        # 4. TJ arrays — hex / literal fragments interleaved with kerning.
        for m in re.finditer(r"\[(.*?)\]\s*TJ", stream, re.DOTALL):
            arr = m.group(1)
            for hm in re.finditer(r"<([0-9A-Fa-f\s]+)>", arr):
                decoded = self._decode_hex_text(hm.group(1), prefer_utf16be=False)
                if decoded:
                    accumulate(decoded, "TJ hex fragment")
            for lm in re.finditer(r"\((.*?)(?<!\\)\)", arr, re.DOTALL):
                body = self._decode_pdf_literal(lm.group(1))
                accumulate(body, "TJ literal fragment")
                try:
                    body_utf8 = body.encode("latin-1").decode("utf-8")
                    if body_utf8 != body:
                        accumulate(body_utf8, "TJ literal (utf-8)")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass

        # 5. Bare Tj literal strings `(...) Tj`
        for m in re.finditer(
            r"\((.*?)(?<!\\)\)\s*Tj", stream, re.DOTALL,
        ):
            body = self._decode_pdf_literal(m.group(1))
            accumulate(body, "Tj literal")
            try:
                body_utf8 = body.encode("latin-1").decode("utf-8")
                if body_utf8 != body:
                    accumulate(body_utf8, "Tj literal (utf-8)")
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass

        # Build findings, skipping any mechanism already caught at span level
        findings: list[Finding] = []
        if zw_hits and "zero_width_chars" not in skip:
            visible = "; ".join(v for v, _ in zw_hits)[:280]
            concealed = "; ".join(c for _, c in zw_hits)[:280]
            findings.append(Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.85,
                description=(
                    f"{len(zw_hits)} content-stream region(s) contain zero-width "
                    "character(s). These are not rendered but are preserved "
                    "through conforming text extraction."
                ),
                location=f"page {page_idx + 1}, raw content stream",
                surface=visible,
                concealed=concealed,
            ))
        if bidi_hits and "bidi_control" not in skip:
            visible = "; ".join(v for v, _ in bidi_hits)[:280]
            concealed = "; ".join(c for _, c in bidi_hits)[:280]
            findings.append(Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.9,
                description=(
                    f"{len(bidi_hits)} content-stream region(s) contain "
                    "bidirectional control character(s). These can reorder "
                    "displayed text without changing its underlying byte order."
                ),
                location=f"page {page_idx + 1}, raw content stream",
                surface=visible,
                concealed=concealed,
            ))
        if tag_hits and "tag_chars" not in skip:
            visible = "; ".join(v for v, _ in tag_hits)[:280]
            concealed = "; ".join(c for _, c in tag_hits)[:280]
            findings.append(Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=0.99,
                description=(
                    f"{len(tag_hits)} content-stream region(s) contain Unicode "
                    "TAG character(s) (U+E0000-U+E007F). TAG characters do not "
                    "render but carry ASCII payloads preserved through text "
                    "extraction — a known prompt-injection vector."
                ),
                location=f"page {page_idx + 1}, raw content stream",
                surface=visible,
                concealed=concealed,
            ))
        return findings

    @staticmethod
    def _decode_hex_text(hex_blob: str, prefer_utf16be: bool = False) -> str:
        """Decode a PDF hex text string. PDF pads an odd-length hex string
        with a trailing 0.

        PDF text-showing operators can hold bytes under any of several
        encodings (WinAnsi, MacRoman, PDFDocEncoding, UTF-16BE under
        ToUnicode CMaps, or 2-byte CIDs for composite fonts). Without
        parsing the current font's encoding we cannot decode authoritatively.

        Strategy:
            - If a leading FEFF BOM is present, the encoding is
              unambiguously UTF-16BE.
            - Else if `prefer_utf16be=True` (only for /ActualText, whose
              encoding is UTF-16BE by PDF-spec mandate), use UTF-16BE.
            - Else default to Latin-1 — the conservative choice that
              avoids spurious bidi/ZWSP hits when ASCII byte pairs like
              0x20 0x66 (space + 'f') would otherwise surface as U+2066.
        """
        h = re.sub(r"\s+", "", hex_blob)
        if not h:
            return ""
        if len(h) % 2 != 0:
            h += "0"
        try:
            data = bytes.fromhex(h)
        except ValueError:
            return ""
        if len(data) >= 2 and data[:2] == b"\xfe\xff" and len(data) % 2 == 0:
            try:
                return data[2:].decode("utf-16-be", errors="replace")
            except Exception:
                pass
        if prefer_utf16be and len(data) >= 2 and len(data) % 2 == 0:
            try:
                return data.decode("utf-16-be", errors="replace")
            except Exception:
                pass
        return data.decode("latin-1", errors="ignore")

    # -- span-level checks -------------------------------------------------

    def _scan_spans(self, page, page_idx: int) -> list[Finding]:
        findings: list[Finding] = []
        try:
            page_dict = page.get_text("dict")
        except Exception:
            return findings

        # Collect filled drawings on this page so we can check whether a
        # white-coloured text span actually sits on a coloured fill (table
        # header, callout box, etc.) rather than on the white page.
        try:
            page_fills = [
                d for d in page.get_drawings()
                if d.get("fill") is not None
            ]
        except Exception:
            page_fills = []

        page_rect = page.rect
        for block in page_dict.get("blocks", []):
            if block.get("type") != 0:  # 0 == text block
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if not text:
                        continue
                    color_int = span.get("color", 0) or 0
                    size = float(span.get("size", 0.0) or 0.0)
                    bbox = tuple(span.get("bbox", (0, 0, 0, 0)))

                    findings.extend(self._check_color(
                        text, color_int, bbox, page_idx, page_fills
                    ))
                    findings.extend(self._check_size(text, size, bbox, page_idx))
                    findings.extend(self._check_offpage(text, bbox, page_rect, page_idx))
                    findings.extend(self._check_unicode(text, bbox, page_idx))
        return findings

    @staticmethod
    def _unpack_color(color_int: int) -> tuple[float, float, float]:
        r = ((color_int >> 16) & 0xFF) / 255.0
        g = ((color_int >> 8) & 0xFF) / 255.0
        b = (color_int & 0xFF) / 255.0
        return r, g, b

    @classmethod
    def _check_color(cls, text, color_int, bbox, page_idx, page_fills=None) -> list[Finding]:
        r, g, b = cls._unpack_color(color_int)
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if lum < (BACKGROUND_LUMINANCE_WHITE - COLOR_CONTRAST_THRESHOLD):
            return []
        # Text colour is near-white. Check if there's a coloured fill drawn
        # behind the span — in that case the text is legitimately visible
        # against a dark/coloured background (e.g. a table-header bar).
        if page_fills and cls._has_dark_fill_behind(bbox, page_fills):
            return []
        return [Finding(
            mechanism="white_on_white_text",
            tier=TIER["white_on_white_text"],
            confidence=0.9,
            description=(
                f"Text color RGB({r:.2f}, {g:.2f}, {b:.2f}) matches page "
                f"background luminance (delta {BACKGROUND_LUMINANCE_WHITE - lum:.3f}), "
                "and no coloured fill is drawn behind the span."
            ),
            location=f"page {page_idx + 1}, bbox {bbox}",
            surface="(indistinguishable from page background)",
            concealed=text[:300],
        )]

    @staticmethod
    def _has_dark_fill_behind(bbox, page_fills) -> bool:
        """True if any coloured (non-white) fill rectangle meaningfully
        covers the given text bbox."""
        x0, y0, x1, y1 = bbox
        bbox_area = max((x1 - x0) * (y1 - y0), 1e-6)
        for d in page_fills:
            fill = d.get("fill")
            if fill is None:
                continue
            try:
                if len(fill) >= 3:
                    fr, fg, fb = float(fill[0]), float(fill[1]), float(fill[2])
                else:
                    continue
            except (ValueError, TypeError):
                continue
            flum = 0.2126 * fr + 0.7152 * fg + 0.0722 * fb
            # If the fill is itself white, it doesn't rescue the text.
            if flum >= (BACKGROUND_LUMINANCE_WHITE - COLOR_CONTRAST_THRESHOLD):
                continue
            rect = d.get("rect")
            if rect is None:
                continue
            try:
                dx0, dy0, dx1, dy1 = rect.x0, rect.y0, rect.x1, rect.y1
            except AttributeError:
                try:
                    dx0, dy0, dx1, dy1 = rect
                except (ValueError, TypeError):
                    continue
            # Overlap with text bbox
            ox0, oy0 = max(dx0, x0), max(dy0, y0)
            ox1, oy1 = min(dx1, x1), min(dy1, y1)
            if ox1 > ox0 and oy1 > oy0:
                overlap = (ox1 - ox0) * (oy1 - oy0)
                if overlap / bbox_area > 0.5:
                    return True
        return False

    @staticmethod
    def _check_size(text, size, bbox, page_idx) -> list[Finding]:
        if 0 < size < MICROSCOPIC_FONT_THRESHOLD:
            return [Finding(
                mechanism="microscopic_font",
                tier=TIER["microscopic_font"],
                confidence=0.8,
                description=(
                    f"Font size {size:.3f}pt is below human-readable threshold "
                    f"({MICROSCOPIC_FONT_THRESHOLD}pt)."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=f"(effectively invisible at {size:.3f}pt)",
                concealed=text[:300],
            )]
        return []

    @staticmethod
    def _check_offpage(text, bbox, page_rect, page_idx) -> list[Finding]:
        x0, y0, x1, y1 = bbox
        margin = 1.0  # 1pt tolerance
        off = (x1 < page_rect.x0 - margin or
               x0 > page_rect.x1 + margin or
               y1 < page_rect.y0 - margin or
               y0 > page_rect.y1 + margin)
        if off:
            return [Finding(
                mechanism="off_page_text",
                tier=TIER["off_page_text"],
                confidence=0.9,
                description=(
                    f"Span positioned outside page MediaBox "
                    f"(page rect: {tuple(page_rect)})."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface="(outside visible page region)",
                concealed=text[:300],
            )]
        return []

    @staticmethod
    def _check_unicode(text, bbox, page_idx) -> list[Finding]:
        findings: list[Finding] = []
        zw = [c for c in text if c in ZERO_WIDTH_CHARS]
        if zw:
            visible = text
            for c in ZERO_WIDTH_CHARS:
                visible = visible.replace(c, "")
            findings.append(Finding(
                mechanism="zero_width_chars",
                tier=TIER["zero_width_chars"],
                confidence=0.8,
                description=f"{len(zw)} zero-width character(s) embedded in visible text.",
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=visible[:200],
                concealed=" | ".join(f"U+{ord(c):04X}" for c in zw),
            ))
        bidi = [c for c in text if c in BIDI_CONTROL_CHARS]
        if bidi:
            findings.append(Finding(
                mechanism="bidi_control",
                tier=TIER["bidi_control"],
                confidence=0.85,
                description=(
                    f"{len(bidi)} bidirectional control character(s) found. These can "
                    "reorder display without changing underlying text."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=text[:200],
                concealed=" | ".join(f"U+{ord(c):04X}" for c in bidi),
            ))
        tag = [c for c in text if ord(c) in TAG_CHAR_RANGE]
        if tag:
            decoded_ascii = "".join(
                chr(ord(c) - 0xE0000) for c in tag if 0xE0020 <= ord(c) <= 0xE007E
            )
            findings.append(Finding(
                mechanism="tag_chars",
                tier=TIER["tag_chars"],
                confidence=0.99,
                description=(
                    f"{len(tag)} Unicode TAG character(s) (U+E0000-U+E007F) found. "
                    "TAG characters are not rendered but carry ASCII payloads invisible "
                    "to human readers — a known prompt-injection vector."
                ),
                location=f"page {page_idx + 1}, bbox {bbox}",
                surface=re.sub(r"[\U000E0000-\U000E007F]", "", text)[:200],
                concealed=(
                    " | ".join(f"U+{ord(c):06X}" for c in tag[:12]) +
                    (" ..." if len(tag) > 12 else "") +
                    (f"  decoded: {decoded_ascii!r}" if decoded_ascii else "")
                ),
            ))
        findings.extend(TextLayerScanner._check_homoglyphs(text, bbox, page_idx))
        return findings

    @staticmethod
    def _check_homoglyphs(text: str, bbox, page_idx: int) -> list[Finding]:
        """Flag words that mix Latin letters with script-confusable characters
        from other Unicode blocks. Firing criterion: a word (tokenised on
        whitespace) contains at least one confusable AND at least one plain
        Latin letter, OR the entire word is confusables masquerading as
        Latin. This catches e.g. `PayPaӏ` (Cyrillic palochka) or `ɑpple`
        (Latin alpha). Single-char confusables in otherwise-plain-Latin text
        are the canonical phishing/spoofing pattern."""
        if not text.strip():
            return []
        hits: list[tuple[str, list[tuple[str, str]]]] = []
        for word in re.split(r"\s+", text):
            if not word:
                continue
            confusables_in_word = [
                (c, CONFUSABLE_TO_LATIN[c]) for c in word
                if c in CONFUSABLE_TO_LATIN
            ]
            if not confusables_in_word:
                continue
            has_plain_latin = any(
                ("a" <= c.lower() <= "z") for c in word
            )
            # Fire if the word mixes plain Latin with confusables (classic
            # spoof: "PayPaӏ") OR if the word is entirely confusables
            # masquerading as a Latin word (≥ 2 chars — single stray symbols
            # are noise).
            if has_plain_latin or len(confusables_in_word) >= 2:
                hits.append((word, confusables_in_word))
        if not hits:
            return []
        surface_preview = "; ".join(w for w, _ in hits[:6])[:220]
        concealed_detail = "; ".join(
            f"{w!r}: " + ", ".join(
                f"U+{ord(c):04X}(looks like '{latin}')"
                for c, latin in pairs[:4]
            )
            for w, pairs in hits[:6]
        )[:320]
        return [Finding(
            mechanism="homoglyph",
            tier=TIER["homoglyph"],
            confidence=0.8,
            description=(
                f"{len(hits)} word(s) contain characters from non-Latin Unicode "
                "blocks that visually impersonate Latin letters (Cyrillic/Greek/"
                "Armenian/Cherokee/fullwidth/mathematical). Common in "
                "phishing spoofs and prompt-injection label swaps."
            ),
            location=f"page {page_idx + 1}, bbox {bbox}",
            surface=surface_preview,
            concealed=concealed_detail,
        )]


# ---------------------------------------------------------------------------
# Object-Layer Scanner
# ---------------------------------------------------------------------------

class ObjectLayerScanner:
    """Detects concealment at the PDF object / structure layer.

    Mechanisms:
        - /OpenAction, /AA (additional actions) in catalog.
        - JavaScript (in /Names tree, in annotations, or in actions).
        - Embedded files (/EmbeddedFiles, /FileAttachment annotations).
        - Launch actions on annotations.
        - Optional Content Groups hidden by default.
        - Metadata anomalies (e.g., ModDate < CreationDate).
        - Incremental updates (multiple %%EOF markers).
    """

    def __init__(self, path: Path):
        self.path = path

    def scan(self) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._scan_incremental_updates())
        try:
            reader = pypdf.PdfReader(str(self.path))
        except Exception as e:
            findings.append(Finding(
                mechanism="scan_error",
                tier=3,
                confidence=0.5,
                description=f"pypdf could not open the document: {e}",
                location="document",
                surface="(object walk skipped)",
                concealed=str(e),
            ))
            return findings

        findings.extend(self._scan_catalog(reader))
        findings.extend(self._scan_metadata(reader))
        findings.extend(self._scan_annotations(reader))
        findings.extend(self._scan_embedded_files(reader))
        findings.extend(self._scan_tounicode_cmaps(reader))
        return findings

    # -- raw bytes ---------------------------------------------------------

    def _scan_incremental_updates(self) -> list[Finding]:
        try:
            data = self.path.read_bytes()
        except Exception:
            return []
        eof_positions = [m.start() for m in re.finditer(rb"%%EOF", data)]
        if len(eof_positions) <= 1:
            return []
        return [Finding(
            mechanism="incremental_update",
            tier=TIER["incremental_update"],
            confidence=0.7,
            description=(
                f"Document contains {len(eof_positions)} %%EOF markers, indicating "
                f"{len(eof_positions) - 1} incremental update(s). Prior revisions may "
                "contain content not rendered in the current view."
            ),
            location=f"byte offsets {eof_positions}",
            surface="(current rendering shows single version)",
            concealed=f"({len(eof_positions)} document revisions present in file)",
        )]

    # -- catalog -----------------------------------------------------------

    def _scan_catalog(self, reader) -> list[Finding]:
        findings: list[Finding] = []
        try:
            catalog = reader.trailer["/Root"]
        except Exception:
            return findings

        if "/OpenAction" in catalog:
            action = catalog["/OpenAction"]
            findings.append(Finding(
                mechanism="openaction",
                tier=TIER["openaction"],
                confidence=0.9,
                description=(
                    "Document declares /OpenAction — action triggered on document open. "
                    f"Action subtype: {self._describe_action_subtype(action)}."
                ),
                location="catalog /OpenAction",
                surface="(no visible indication on open)",
                concealed=self._safe_str(action)[:500],
            ))

        if "/AA" in catalog:
            findings.append(Finding(
                mechanism="additional_actions",
                tier=TIER["additional_actions"],
                confidence=0.85,
                description=(
                    "Document declares /AA — additional actions triggered by document "
                    "events (open, close, save, print, etc.)."
                ),
                location="catalog /AA",
                surface="(no visible indication)",
                concealed=self._safe_str(catalog["/AA"])[:500],
            ))

        # /Names /JavaScript tree
        try:
            names = catalog.get("/Names")
            if names is not None:
                names_obj = names.get_object() if hasattr(names, "get_object") else names
                js = names_obj.get("/JavaScript") if hasattr(names_obj, "get") else None
                if js is not None:
                    findings.append(Finding(
                        mechanism="javascript",
                        tier=TIER["javascript"],
                        confidence=0.99,
                        description=(
                            "Document declares a /JavaScript name tree in the catalog. "
                            "JavaScript can execute on open, on user action, or in "
                            "response to form events."
                        ),
                        location="catalog /Names /JavaScript",
                        surface="(no visible indication)",
                        concealed=self._safe_str(js)[:500],
                    ))
        except Exception:
            pass

        # Optional Content Groups hidden by default
        try:
            oc = catalog.get("/OCProperties")
            if oc is not None:
                oc_obj = oc.get_object() if hasattr(oc, "get_object") else oc
                d = oc_obj.get("/D") if hasattr(oc_obj, "get") else None
                if d is not None:
                    d_obj = d.get_object() if hasattr(d, "get_object") else d
                    off = d_obj.get("/OFF") if hasattr(d_obj, "get") else None
                    if off:
                        try:
                            n_off = len(off)
                        except TypeError:
                            n_off = 1
                        findings.append(Finding(
                            mechanism="hidden_ocg",
                            tier=TIER["hidden_ocg"],
                            confidence=0.8,
                            description=(
                                f"{n_off} Optional Content Group(s) hidden by default. "
                                "Content present in file but not rendered in default view."
                            ),
                            location="catalog /OCProperties /D /OFF",
                            surface="(layer not shown in default rendering)",
                            concealed=self._safe_str(off)[:300],
                        ))
        except Exception:
            pass

        return findings

    @staticmethod
    def _describe_action_subtype(action) -> str:
        try:
            obj = action.get_object() if hasattr(action, "get_object") else action
            if hasattr(obj, "get"):
                s = obj.get("/S")
                return str(s) if s else "unknown"
        except Exception:
            pass
        return "unknown"

    # -- metadata ----------------------------------------------------------

    def _scan_metadata(self, reader) -> list[Finding]:
        findings: list[Finding] = []
        try:
            info = reader.metadata
        except Exception:
            return findings
        if info is None:
            return findings
        try:
            cd = info.get("/CreationDate")
            md = info.get("/ModDate")
            if cd and md and str(md) < str(cd):
                findings.append(Finding(
                    mechanism="metadata_anomaly",
                    tier=TIER["metadata_anomaly"],
                    confidence=0.6,
                    description="Modification date precedes creation date.",
                    location="/Info",
                    surface=f"(CreationDate: {cd})",
                    concealed=f"(ModDate:      {md})",
                ))
        except Exception:
            pass
        return findings

    # -- annotations -------------------------------------------------------

    def _scan_annotations(self, reader) -> list[Finding]:
        findings: list[Finding] = []
        for page_idx, page in enumerate(reader.pages):
            try:
                annots = page.get("/Annots")
            except Exception:
                continue
            if annots is None:
                continue
            try:
                annots_list = list(annots)
            except Exception:
                continue
            for annot_ref in annots_list:
                try:
                    annot = (annot_ref.get_object()
                             if hasattr(annot_ref, "get_object") else annot_ref)
                    subtype = str(annot.get("/Subtype", "") or "")
                    if subtype == "/FileAttachment":
                        fs = annot.get("/FS")
                        findings.append(Finding(
                            mechanism="file_attachment_annot",
                            tier=TIER["file_attachment_annot"],
                            confidence=0.95,
                            description=(
                                "File-attachment annotation contains an embedded file."
                            ),
                            location=f"page {page_idx + 1}",
                            surface="(attachment icon or nothing visible)",
                            concealed=self._safe_str(fs)[:300],
                        ))
                    a = annot.get("/A") if hasattr(annot, "get") else None
                    if a is not None:
                        a_obj = a.get_object() if hasattr(a, "get_object") else a
                        s_type = (str(a_obj.get("/S", "") or "")
                                  if hasattr(a_obj, "get") else "")
                        if s_type == "/Launch":
                            findings.append(Finding(
                                mechanism="launch_action",
                                tier=TIER["launch_action"],
                                confidence=0.95,
                                description=(
                                    "Annotation triggers /Launch action — can execute "
                                    "a program or open an external file."
                                ),
                                location=f"page {page_idx + 1}",
                                surface="(click target appears normal)",
                                concealed=self._safe_str(a_obj)[:400],
                            ))
                        elif s_type == "/JavaScript":
                            findings.append(Finding(
                                mechanism="javascript",
                                tier=TIER["javascript"],
                                confidence=0.99,
                                description="Annotation triggers JavaScript action.",
                                location=f"page {page_idx + 1}",
                                surface="(click target appears normal)",
                                concealed=self._safe_str(a_obj)[:500],
                            ))
                except Exception:
                    continue
        return findings

    # -- embedded files ----------------------------------------------------

    def _scan_embedded_files(self, reader) -> list[Finding]:
        findings: list[Finding] = []
        try:
            catalog = reader.trailer["/Root"]
            names = catalog.get("/Names")
            if names is None:
                return findings
            names_obj = names.get_object() if hasattr(names, "get_object") else names
            ef = names_obj.get("/EmbeddedFiles") if hasattr(names_obj, "get") else None
            if ef is None:
                return findings
            for name, fspec in self._walk_names_tree(ef):
                findings.append(Finding(
                    mechanism="embedded_file",
                    tier=TIER["embedded_file"],
                    confidence=0.95,
                    description=f"Embedded file '{name}' present in document.",
                    location="catalog /Names /EmbeddedFiles",
                    surface="(no visible indication unless annotation present)",
                    concealed=f"embedded file: {name}",
                ))
        except Exception:
            pass
        return findings

    # -- ToUnicode CMap analysis ------------------------------------------

    def _scan_tounicode_cmaps(self, reader) -> list[Finding]:
        """Parse every /Font's /ToUnicode stream and flag mappings whose
        Unicode target is adversarial (zero-width, bidi control, TAG char,
        or a Latin homoglyph).

        ToUnicode CMaps specify what Unicode codepoints a conforming text
        extractor should return for each font CID. A PDF whose visible
        glyphs spell "Hello" but whose ToUnicode CMap maps those CIDs to
        zero-width chars (or to Cyrillic 'Hеllо') is the exact attack
        /ActualText performs — but at the font-resource level rather than
        the marked-content level. Both routes land concealed Unicode in a
        downstream extractor's output while preserving visible integrity.
        """
        findings: list[Finding] = []
        seen_xrefs: set[int] = set()
        for page_idx, page in enumerate(reader.pages):
            try:
                resources = page.get("/Resources")
                if resources is None:
                    continue
                res_obj = (resources.get_object()
                           if hasattr(resources, "get_object") else resources)
                fonts = res_obj.get("/Font") if hasattr(res_obj, "get") else None
                if fonts is None:
                    continue
                fonts_obj = (fonts.get_object()
                             if hasattr(fonts, "get_object") else fonts)
            except Exception:
                continue
            try:
                font_keys = list(fonts_obj.keys())
            except Exception:
                continue
            for font_key in font_keys:
                try:
                    font_ref = fonts_obj[font_key]
                    font = (font_ref.get_object()
                            if hasattr(font_ref, "get_object") else font_ref)
                    to_unicode = (font.get("/ToUnicode")
                                  if hasattr(font, "get") else None)
                    if to_unicode is None:
                        continue
                    tu = (to_unicode.get_object()
                          if hasattr(to_unicode, "get_object") else to_unicode)
                    # Dedup by xref so the same shared ToUnicode stream
                    # referenced from many pages only fires once.
                    xref = getattr(to_unicode, "idnum", None)
                    if xref is not None:
                        if xref in seen_xrefs:
                            continue
                        seen_xrefs.add(xref)
                    try:
                        cmap_bytes = tu.get_data()
                    except Exception:
                        continue
                    cmap_text = cmap_bytes.decode("latin-1", errors="ignore")
                    anomalies = self._parse_tounicode_cmap(cmap_text)
                    if anomalies:
                        previews = anomalies[:6]
                        findings.append(Finding(
                            mechanism="tounicode_anomaly",
                            tier=TIER["tounicode_anomaly"],
                            confidence=0.9,
                            description=(
                                f"Font {font_key!s} on page {page_idx + 1} carries a "
                                f"ToUnicode CMap with {len(anomalies)} entr(y/ies) that "
                                "map visible glyph CIDs to adversarial Unicode targets "
                                "(zero-width, bidi control, TAG, or Latin homoglyph). "
                                "Visible text and extracted text will diverge."
                            ),
                            location=(
                                f"page {page_idx + 1}, font {font_key!s}, /ToUnicode"
                            ),
                            surface="(rendered glyphs look legitimate)",
                            concealed="; ".join(previews)[:400],
                        ))
                except Exception:
                    continue
        return findings

    @staticmethod
    def _parse_tounicode_cmap(cmap_text: str) -> list[str]:
        """Find every bfchar / bfrange entry in a ToUnicode CMap and return
        a list of anomalous source→target descriptions (where the target
        contains a zero-width / bidi / TAG / homoglyph codepoint).

        bfchar syntax:
            N beginbfchar
              <src1> <tgt1>
              ...
            endbfchar

        bfrange syntax:
            N beginbfrange
              <srcLow> <srcHigh> <tgtLow>
              <srcLow> <srcHigh> [<tgt1> <tgt2> ...]
              ...
            endbfrange

        Targets are UTF-16BE hex strings (possibly multi-codepoint, for
        ligatures / precomposed forms).
        """
        def hex_to_text(h: str) -> str:
            h = re.sub(r"\s+", "", h)
            if not h or len(h) % 2 != 0:
                return ""
            try:
                data = bytes.fromhex(h)
            except ValueError:
                return ""
            try:
                return data.decode("utf-16-be", errors="replace")
            except Exception:
                return ""

        def is_anomalous(text: str) -> tuple[bool, str]:
            for c in text:
                if c in ZERO_WIDTH_CHARS:
                    return True, f"zero-width U+{ord(c):04X}"
                if c in BIDI_CONTROL_CHARS:
                    return True, f"bidi U+{ord(c):04X}"
                if ord(c) in TAG_CHAR_RANGE:
                    return True, f"TAG U+{ord(c):06X}"
                if c in CONFUSABLE_TO_LATIN:
                    return True, (
                        f"homoglyph U+{ord(c):04X} (looks like "
                        f"'{CONFUSABLE_TO_LATIN[c]}')"
                    )
            return False, ""

        anomalies: list[str] = []

        # bfchar blocks
        for m in re.finditer(
            r"beginbfchar(.*?)endbfchar", cmap_text, re.DOTALL,
        ):
            block = m.group(1)
            for entry in re.finditer(
                r"<\s*([0-9A-Fa-f]+)\s*>\s*<\s*([0-9A-Fa-f]+)\s*>", block,
            ):
                src_hex, tgt_hex = entry.group(1), entry.group(2)
                tgt_text = hex_to_text(tgt_hex)
                bad, reason = is_anomalous(tgt_text)
                if bad:
                    anomalies.append(
                        f"CID<{src_hex}> → {tgt_text!r}  [{reason}]"
                    )

        # bfrange blocks (simple form: <srcLow> <srcHigh> <tgtLow>)
        for m in re.finditer(
            r"beginbfrange(.*?)endbfrange", cmap_text, re.DOTALL,
        ):
            block = m.group(1)
            for entry in re.finditer(
                r"<\s*([0-9A-Fa-f]+)\s*>\s*<\s*([0-9A-Fa-f]+)\s*>\s*"
                r"(<\s*[0-9A-Fa-f]+\s*>|\[[^\]]*\])",
                block,
            ):
                src_lo_hex, src_hi_hex, tgt_part = entry.group(1), entry.group(2), entry.group(3)
                if tgt_part.startswith("<"):
                    tgt_text = hex_to_text(tgt_part.strip("<> \t\n\r"))
                    bad, reason = is_anomalous(tgt_text)
                    if bad:
                        anomalies.append(
                            f"CIDs<{src_lo_hex}>-<{src_hi_hex}> start→ {tgt_text!r}  "
                            f"[{reason}]"
                        )
                else:
                    # Explicit array: check each target
                    for tm in re.finditer(r"<\s*([0-9A-Fa-f]+)\s*>", tgt_part):
                        tgt_text = hex_to_text(tm.group(1))
                        bad, reason = is_anomalous(tgt_text)
                        if bad:
                            anomalies.append(
                                f"CIDs<{src_lo_hex}>-<{src_hi_hex}> entry→ "
                                f"{tgt_text!r}  [{reason}]"
                            )
        return anomalies

    def _walk_names_tree(self, node) -> list[tuple[str, Any]]:
        out: list[tuple[str, Any]] = []
        try:
            obj = node.get_object() if hasattr(node, "get_object") else node
            if hasattr(obj, "get"):
                ns = obj.get("/Names")
                if ns:
                    seq = list(ns)
                    for i in range(0, len(seq) - 1, 2):
                        out.append((str(seq[i]), seq[i + 1]))
                kids = obj.get("/Kids")
                if kids:
                    for kid in kids:
                        out.extend(self._walk_names_tree(kid))
        except Exception:
            pass
        return out

    # -- utility -----------------------------------------------------------

    @staticmethod
    def _safe_str(obj) -> str:
        try:
            return str(obj)
        except Exception:
            return repr(obj)


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def compute_integrity_score(findings: list[Finding]) -> float:
    """APS-style continuous score in [0.0, 1.0].

    Start at 1.0. Each finding subtracts (severity * confidence).
    Clamp to [0.0, 1.0]. Does NOT self-validate a verdict.
    """
    score = 1.0
    for f in findings:
        score -= f.severity * f.confidence
    return max(0.0, min(1.0, score))


def plain_language_summary(report: IntegrityReport) -> str:
    incomplete_note = ""
    if report.scan_incomplete:
        incomplete_note = (
            "NOTE: scan_incomplete=true — one or more scanner paths reported an "
            "error or could not complete. The integrity score has been clamped "
            "to a maximum of 0.50 because portions of the document were not "
            "inspected; absence of findings in the uninspected regions cannot "
            "be taken as evidence of cleanness. "
        )
    if report.error:
        return incomplete_note + f"Scan did not complete cleanly: {report.error}"
    n = len(report.findings)
    s = report.integrity_score
    if n == 0:
        return incomplete_note + (
            f"Integrity score: {s:.2f}/1.00. No concealment mechanisms detected. "
            "What the file displays and what the file contains appear to match."
        )
    counts: dict[str, int] = {}
    for f in report.findings:
        counts[f.mechanism] = counts.get(f.mechanism, 0) + 1
    mech_list = ", ".join(
        f"{mech} ({n})" for mech, n in sorted(counts.items(), key=lambda x: -x[1])
    )
    by_tier = {1: 0, 2: 0, 3: 0}
    for f in report.findings:
        by_tier[f.tier] = by_tier.get(f.tier, 0) + 1
    return incomplete_note + (
        f"Integrity score: {s:.2f}/1.00. {n} finding(s) across "
        f"{len(counts)} mechanism(s): {mech_list}. "
        f"Validity tiers — Tier 1 (verified): {by_tier[1]}, "
        f"Tier 2 (structural): {by_tier[2]}, "
        f"Tier 3 (interpretive): {by_tier[3]}. "
        "What this means: the file displays one thing and contains additional "
        "content not visible in normal viewing. This report does NOT assert "
        "the file is malicious — it surfaces the gap between display and content. "
        "The reader performs the recognition."
    )


def format_text_report(report: IntegrityReport) -> str:
    lines: list[str] = []
    bar = "=" * 76
    subbar = "-" * 76
    lines.append(bar)
    lines.append(" BAYYINAH v0 — PDF FILE INTEGRITY REPORT")
    lines.append(bar)
    lines.append(f" File: {report.file_path}")
    lines.append(f" Integrity score: {report.integrity_score:.3f} / 1.000  (APS-continuous)")
    lines.append("")
    lines.append(" Validity disclaimer (Godel constraint):")
    lines.append("   This report presents observed mechanisms and their validity tiers.")
    lines.append("   It does NOT self-validate a moral or malicious verdict. Bayyinah")
    lines.append("   makes the invisible visible; the reader performs the recognition.")
    lines.append("")
    lines.append(subbar)
    lines.append(" PLAIN-LANGUAGE SUMMARY")
    lines.append(subbar)
    lines.append(" " + plain_language_summary(report))
    lines.append("")

    if report.findings:
        lines.append(subbar)
        lines.append(f" FINDINGS  ({len(report.findings)})")
        lines.append(subbar)
        for i, f in enumerate(report.findings, 1):
            lines.append(f" [{i}] {f.mechanism}   Tier {f.tier}   confidence {f.confidence:.2f}   severity {f.severity:.2f}")
            lines.append(f"     Location:    {f.location}")
            lines.append(f"     Description: {f.description}")
            lines.append( "     Inversion recovery:")
            lines.append(f"       Surface   : {f.surface[:240]}")
            lines.append(f"       Concealed : {f.concealed[:240]}")
            lines.append("")

    if report.error:
        lines.append(f" ERROR: {report.error}")

    lines.append(bar)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def scan_pdf(pdf_path: Path) -> IntegrityReport:
    report = IntegrityReport(file_path=str(pdf_path), integrity_score=1.0)
    if not pdf_path.exists():
        report.error = f"File not found: {pdf_path}"
        report.integrity_score = 0.0
        report.scan_incomplete = True
        return report

    text_findings: list[Finding] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as e:
        report.error = f"Could not open PDF: {e}"
        report.integrity_score = 0.0
        report.scan_incomplete = True
        return report
    try:
        text_findings = TextLayerScanner(doc).scan()
    except Exception as e:
        report.error = f"Text layer scan error: {e}"
    finally:
        try:
            doc.close()
        except Exception:
            pass

    object_findings: list[Finding] = []
    try:
        object_findings = ObjectLayerScanner(pdf_path).scan()
    except Exception as e:
        report.error = (
            f"{report.error}; Object layer scan error: {e}"
            if report.error else f"Object layer scan error: {e}"
        )

    report.findings = text_findings + object_findings
    report.integrity_score = compute_integrity_score(report.findings)

    # v0.1 scan_incomplete clamp: whenever a scanner path reported an error or
    # emitted a scan_error finding, the document was not fully inspected —
    # clamp the score to a maximum of 0.50 and expose the flag at the top level
    # so downstream consumers cannot mistake incomplete coverage for cleanness.
    has_scan_error = any(f.mechanism == "scan_error" for f in report.findings)
    if report.error is not None or has_scan_error:
        report.scan_incomplete = True
        if report.integrity_score > 0.5:
            report.integrity_score = 0.5

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="bayyinah_v0",
        description=(
            "Bayyinah v0 — PDF file integrity scanner. Detects concealment "
            "mechanisms and reports the gap between what the file displays "
            "and what the file contains."
        ),
    )
    parser.add_argument("pdf", help="Path to PDF file")
    parser.add_argument("--json", action="store_true",
                        help="Emit JSON report instead of human-readable text")
    parser.add_argument("--quiet", action="store_true",
                        help="Suppress the text report (exit code still reflects findings)")
    args = parser.parse_args(argv)

    path = Path(args.pdf)
    report = scan_pdf(path)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    elif not args.quiet:
        print(format_text_report(report))

    if report.error:
        return 2
    if report.findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
