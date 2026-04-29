"""
Tier 2 detector for sub-readable font sizes in DOCX runs (v1.1.2).

OOXML expresses run font size via ``<w:rPr><w:sz w:val="N"/></w:rPr>``
where ``N`` is in *half-points* (so ``w:val="2"`` renders at 1.0pt and
``w:val="22"`` is the Word default of 11.0pt). A run rendered at or
below ~2.0pt is below the human-readable threshold and is functionally
invisible against any background, but the text remains in the run's
``<w:t>`` stream and is consumed by every downstream extractor.

Mirrors the PDF analyzer's ``microscopic_font`` mechanism with the
corresponding tier-2 discipline: sub-readable font is *technically
representable* (some real-world documents use 0.5pt for invisible
fingerprinting watermarks; that use case is technically benign and
distinct from concealment intent), so the detector emits Tier 2 rather
than Tier 1. The verdict floor still trips because Tier 2 plus a
divergent payload string is enough to pull the score below sahih.

Closes docx_gauntlet fixture 02_microscopic_font.docx (run at 1.0pt).

Tier discipline: Tier 2 because the trigger (font size in half-points)
is byte-deterministic but the interpretation (concealment vs.
fingerprinting) is structural rather than verifiable from the file
alone. The threshold is chosen at ``w:sz <= 4`` (2.0pt) which sits
clearly below any legitimate human-readable use case (typesetting
software does not produce sub-2pt body text in real documents).
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.finding import Finding


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_T = f"{{{_W_NS}}}t"
_W_RPR = f"{{{_W_NS}}}rPr"
_W_SZ = f"{{{_W_NS}}}sz"
_W_VAL = f"{{{_W_NS}}}val"
_W_R = f"{{{_W_NS}}}r"
_W_P = f"{{{_W_NS}}}p"

# Threshold in OOXML half-points. ``w:sz w:val="4"`` renders at 2.0pt;
# anything at or below this is sub-readable for body text. Chosen
# conservatively: legitimate small-text uses (footnote numerals,
# accessibility annotations) cluster at 6.0pt and above (w:sz >= 12).
_MICROSCOPIC_HALFPT_THRESHOLD = 4

_PREVIEW_LIMIT = 240


def _run_size_halfpt(run: ET.Element) -> int | None:
    """Return the ``w:sz`` value (in half-points) for a run, or None
    if no explicit size is set.
    """
    rpr = run.find(_W_RPR)
    if rpr is None:
        return None
    sz = rpr.find(_W_SZ)
    if sz is None:
        return None
    raw = sz.get(_W_VAL)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def detect_docx_microscopic_font(file_path: Path) -> list[Finding]:
    """Return Tier 2 findings for runs whose size is at or below the
    sub-readable threshold (2.0pt).
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return findings
            xml_bytes = zf.read("word/document.xml")
    except (zipfile.BadZipFile, OSError, KeyError):
        return findings
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return findings

    paragraph_index = 0
    for paragraph in root.iter(_W_P):
        paragraph_index += 1
        run_index = 0
        for run in paragraph.iter(_W_R):
            run_index += 1
            halfpt = _run_size_halfpt(run)
            if halfpt is None or halfpt > _MICROSCOPIC_HALFPT_THRESHOLD:
                continue
            text_chunks: list[str] = []
            for t_el in run.iter(_W_T):
                if t_el.text:
                    text_chunks.append(t_el.text)
            text = "".join(text_chunks).strip()
            if not text:
                continue
            preview = (
                text if len(text) <= _PREVIEW_LIMIT
                else text[:_PREVIEW_LIMIT] + "..."
            )
            pt_value = halfpt / 2.0
            findings.append(Finding(
                mechanism="docx_microscopic_font",
                tier=2,
                confidence=1.0,
                description=(
                    f"Run at paragraph {paragraph_index}, run "
                    f"{run_index} renders at {pt_value}pt "
                    f"(w:sz={halfpt} half-points), at or below the "
                    f"2.0pt sub-readable threshold. Sub-readable "
                    f"runs are invisible to the eye but preserved in "
                    f"the run's <w:t> stream."
                ),
                location=(
                    f"{file_path}:word/document.xml:"
                    f"p{paragraph_index}:r{run_index}"
                ),
                surface=f"run rendered at {pt_value}pt",
                concealed=(
                    f"w:sz={halfpt} ({pt_value}pt); "
                    f"recovered text: {preview!r}"
                ),
                source_layer="zahir",
            ))
    return findings


__all__ = ["detect_docx_microscopic_font"]
