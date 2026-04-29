"""
Tier 1 detector for hidden-text payloads in DOCX header/footer parts (v1.1.2).

OOXML stores running headers/footers in dedicated XML parts:
``word/header1.xml``, ``word/header2.xml``, ..., ``word/footer1.xml``,
etc. Each part is a self-contained run tree (``<w:hdr>`` or
``<w:ftr>`` root) with the same run-property grammar as
``word/document.xml``: a run can carry ``<w:rPr><w:color/></w:rPr>``
and ``<w:rPr><w:sz/></w:rPr>`` exactly as a body run does.

Adversarial use plants white-text or microscopic-font runs in a
header or footer part. Word renders the header/footer area visibly,
but the run is invisible (white-on-white) or unreadable (sub-pixel
font size) to a human reader. Every package walker, indexer, and LLM
extractor that visits the header/footer part still reads the payload
bytes verbatim from the run's ``<w:t>`` text node.

Mirrors the body-scoped detectors ``docx_white_text`` (Tier 1, zahir)
and ``docx_microscopic_font`` (Tier 2, zahir) but applies them to
every header and footer part discovered in the package. Closes
docx_gauntlet fixture 05_header_payload.docx.

Tier discipline: Tier 1, source layer zahir. Both triggers
(near-white run color on a white surface, microscopic ``w:sz``) are
byte-deterministic literal lookups. The header/footer dimension does
not change the determinism of the trigger; it only widens the
scan envelope. The mechanism stays at Tier 1 with severity 1.00 to
match the body-scoped white-text detector, since header/footer
concealment is the same shape of attack delivered through a
parallel package channel.

Page-background context: the same caveat as ``docx_white_text``
applies. Headers/footers can carry their own background fill in
exotic layouts, but the gauntlet fixture and overwhelming majority
of real-world adversarial documents render against the inherited
white page background. The detector reads the document-level
``<w:background>`` and stays silent against custom-background
documents to preserve the same false-positive discipline as the
body-scoped detector.
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.finding import Finding


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_T = f"{{{_W_NS}}}t"
_W_R = f"{{{_W_NS}}}r"
_W_P = f"{{{_W_NS}}}p"
_W_RPR = f"{{{_W_NS}}}rPr"
_W_COLOR = f"{{{_W_NS}}}color"
_W_SZ = f"{{{_W_NS}}}sz"
_W_VAL = f"{{{_W_NS}}}val"
_W_BACKGROUND = f"{{{_W_NS}}}background"

_NEAR_WHITE: frozenset[str] = frozenset(
    {"FFFFFF", "FEFEFE", "FDFDFD", "FCFCFC"}
)
_MICROSCOPIC_HALFPT_THRESHOLD = 4

_PREVIEW_LIMIT = 240

_HEADER_FOOTER_RE = re.compile(r"^word/(header|footer)\d*\.xml$")


def _is_near_white(hex_val: str) -> bool:
    if not hex_val or len(hex_val) != 6:
        return False
    return hex_val.upper() in _NEAR_WHITE


def _run_color(run: ET.Element) -> str | None:
    rpr = run.find(_W_RPR)
    if rpr is None:
        return None
    color = rpr.find(_W_COLOR)
    if color is None:
        return None
    return color.get(_W_VAL)


def _run_size_halfpt(run: ET.Element) -> int | None:
    rpr = run.find(_W_RPR)
    if rpr is None:
        return None
    sz = rpr.find(_W_SZ)
    if sz is None:
        return None
    raw = sz.get(_W_VAL)
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _run_text(run: ET.Element) -> str:
    chunks: list[str] = []
    for el in run.iter(_W_T):
        if el.text:
            chunks.append(el.text)
    return "".join(chunks).strip()


def _document_background_is_white(zf: zipfile.ZipFile) -> bool:
    """Return True if document.xml has no custom background or its
    custom background is itself white. Mirrors the body-scoped
    detector's policy so header/footer scanning inherits the same
    false-positive discipline.
    """
    if "word/document.xml" not in zf.namelist():
        return True
    try:
        xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (KeyError, ET.ParseError):
        return True
    bg = root.find(_W_BACKGROUND)
    if bg is None:
        return True
    color = bg.get(_W_VAL) or ""
    return _is_near_white(color)


def detect_docx_header_footer_payload(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for hidden-text payloads in
    ``word/header*.xml`` / ``word/footer*.xml`` parts.

    Two triggers, both Tier 1 / zahir / severity 1.00:
      1. Run color in the near-white set on a white page.
      2. Run ``w:sz`` <= 4 half-points (2.0pt and below).
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            names = zf.namelist()
            parts = sorted(
                n for n in names if _HEADER_FOOTER_RE.match(n)
            )
            if not parts:
                return findings
            if not _document_background_is_white(zf):
                return findings
            for part in parts:
                try:
                    xml_bytes = zf.read(part)
                except KeyError:
                    continue
                try:
                    root = ET.fromstring(xml_bytes)
                except ET.ParseError:
                    continue
                paragraph_index = 0
                for paragraph in root.iter(_W_P):
                    paragraph_index += 1
                    run_index = 0
                    for run in paragraph.iter(_W_R):
                        run_index += 1
                        text = _run_text(run)
                        if not text:
                            continue
                        preview = (
                            text if len(text) <= _PREVIEW_LIMIT
                            else text[:_PREVIEW_LIMIT] + "..."
                        )

                        # Trigger 1: near-white run color.
                        color = _run_color(run)
                        if color and _is_near_white(color):
                            findings.append(Finding(
                                mechanism="docx_header_footer_payload",
                                tier=1,
                                confidence=1.0,
                                description=(
                                    f"Run at {part} paragraph "
                                    f"{paragraph_index}, run "
                                    f"{run_index} has foreground "
                                    f"color #{color.upper()} on a "
                                    f"white page background. The "
                                    f"text is invisible in the "
                                    f"rendered header/footer area "
                                    f"but is preserved in the run's "
                                    f"<w:t> stream and read by "
                                    f"every downstream extractor."
                                ),
                                location=(
                                    f"{file_path}:{part}:"
                                    f"p{paragraph_index}:r{run_index}"
                                ),
                                surface=(
                                    f"{part} run with color "
                                    f"#{color.upper()}"
                                ),
                                concealed=(
                                    f"part={part}; "
                                    f"trigger=near_white_color; "
                                    f"color=#{color.upper()}; "
                                    f"recovered text: {preview!r}"
                                ),
                                source_layer="zahir",
                            ))
                            continue

                        # Trigger 2: microscopic font size.
                        halfpt = _run_size_halfpt(run)
                        if (
                            halfpt is not None
                            and halfpt <= _MICROSCOPIC_HALFPT_THRESHOLD
                        ):
                            pt_value = halfpt / 2.0
                            findings.append(Finding(
                                mechanism="docx_header_footer_payload",
                                tier=1,
                                confidence=1.0,
                                description=(
                                    f"Run at {part} paragraph "
                                    f"{paragraph_index}, run "
                                    f"{run_index} renders at "
                                    f"{pt_value}pt (w:sz={halfpt} "
                                    f"half-points), at or below the "
                                    f"microscopic threshold. The "
                                    f"text is unreadable in the "
                                    f"rendered header/footer area "
                                    f"but is preserved in the run's "
                                    f"<w:t> stream and read by "
                                    f"every downstream extractor."
                                ),
                                location=(
                                    f"{file_path}:{part}:"
                                    f"p{paragraph_index}:r{run_index}"
                                ),
                                surface=(
                                    f"{part} run at {pt_value}pt"
                                ),
                                concealed=(
                                    f"part={part}; "
                                    f"trigger=microscopic_font; "
                                    f"w:sz={halfpt} ({pt_value}pt); "
                                    f"recovered text: {preview!r}"
                                ),
                                source_layer="zahir",
                            ))
    except (zipfile.BadZipFile, OSError):
        return findings
    return findings


__all__ = ["detect_docx_header_footer_payload"]
