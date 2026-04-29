"""
Tier 1 detector for white-on-white text in DOCX runs (v1.1.2).

OOXML expresses run color via ``<w:rPr><w:color w:val="HHHHHH"/></w:rPr>``
where the 6-hex value is the run's foreground color. A run rendered in
``FFFFFF`` (or near-white) on a white page is invisible to a human
reading the document but is preserved verbatim in the run's ``<w:t>``
text node, so every downstream extractor (Word's accessibility view,
indexers, LLMs, copy-paste) reads the payload.

Mirrors the PDF analyzer's ``white_on_white_text`` mechanism. Closes
docx_gauntlet fixture 01_white_on_white.docx and the white-text
component of fixture 05_header_payload.docx (header part is scanned by
the parallel detector ``docx_header_footer_payload``; this module
focuses on document.xml).

Tier discipline: this is Tier 1 because the trigger is byte-deterministic
(the ``w:val`` attribute is a hex string; comparing it against the
near-white set is a literal lookup, no statistical claim, no heuristic
threshold). Source layer is zahir because color is a surface-rendering
attribute observable from a single walk of ``word/document.xml``.

Page-background context: OOXML allows a custom page background via
``<w:background>``. Detecting white text against a non-white background
is *legitimate* (white-on-blue header callouts, etc.). For v1.1.2 the
detector only fires when the page background is white or unset, since
the gauntlet fixture has no custom background and that is the
overwhelmingly common case in real-world phishing/contract-fraud
documents. Custom-background-aware logic is queued as future work.

The "near-white" set covers exact ``FFFFFF`` plus three common
near-white variations seen in real-world adversarial fixtures
(``FEFEFE``, ``FDFDFD``, ``FCFCFC``). Anything darker than ``FCFCFC``
is treated as legitimate light-gray formatting and not flagged.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.finding import Finding


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_T = f"{{{_W_NS}}}t"
_W_RPR = f"{{{_W_NS}}}rPr"
_W_COLOR = f"{{{_W_NS}}}color"
_W_VAL = f"{{{_W_NS}}}val"
_W_BACKGROUND = f"{{{_W_NS}}}background"
_W_BODY = f"{{{_W_NS}}}body"
_W_R = f"{{{_W_NS}}}r"
_W_P = f"{{{_W_NS}}}p"

# Near-white hex values. The fixture uses ``FFFFFF`` exactly; the four
# off-white values cover the common "almost invisible" tactic where an
# attacker lightens by one or two units to defeat naive equality
# checks. Anything darker (``FBFBFB`` and below) is treated as legit
# light-gray formatting.
_NEAR_WHITE: frozenset[str] = frozenset(
    {"FFFFFF", "FEFEFE", "FDFDFD", "FCFCFC"}
)

_PREVIEW_LIMIT = 240  # chars; bounds inversion_recovery output


def _is_near_white(hex_val: str) -> bool:
    """Return True for a 6-hex value within the near-white set.

    Case-insensitive; non-conforming values (``auto``, ``none``,
    short forms, malformed strings) return False so a partially-broken
    color spec is not flagged as concealment.
    """
    if not hex_val or len(hex_val) != 6:
        return False
    return hex_val.upper() in _NEAR_WHITE


def _page_background_is_white(root: ET.Element) -> bool:
    """Return True if the document has no custom page background, or
    if the custom background is itself white. Anything else is treated
    as a legitimate styled background and the detector stays silent
    against it.
    """
    bg = root.find(_W_BACKGROUND)
    if bg is None:
        return True  # default white
    color = bg.get(_W_VAL) or ""
    return _is_near_white(color)


def _run_color(run: ET.Element) -> str | None:
    """Return the ``w:val`` of a run's ``<w:color>`` if present."""
    rpr = run.find(_W_RPR)
    if rpr is None:
        return None
    color = rpr.find(_W_COLOR)
    if color is None:
        return None
    return color.get(_W_VAL)


def detect_docx_white_text(file_path: Path) -> list[Finding]:
    """Return Tier 1 findings for runs in document.xml whose foreground
    color renders the text invisible against the (white) page
    background.
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
    if not _page_background_is_white(root):
        return findings

    paragraph_index = 0
    for paragraph in root.iter(_W_P):
        paragraph_index += 1
        run_index = 0
        for run in paragraph.iter(_W_R):
            run_index += 1
            color = _run_color(run)
            if not color or not _is_near_white(color):
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
            findings.append(Finding(
                mechanism="docx_white_text",
                tier=1,
                confidence=1.0,
                description=(
                    f"Run at paragraph {paragraph_index}, run "
                    f"{run_index} has foreground color "
                    f"#{color.upper()} on a white page "
                    f"background. The text is invisible to a human "
                    f"reading the document but is preserved in the "
                    f"run's <w:t> stream and read by every downstream "
                    f"extractor."
                ),
                location=(
                    f"{file_path}:word/document.xml:"
                    f"p{paragraph_index}:r{run_index}"
                ),
                surface=(
                    f"run with color #{color.upper()} on white page"
                ),
                concealed=(
                    f"color=#{color.upper()}; "
                    f"recovered text: {preview!r}"
                ),
                source_layer="zahir",
            ))
    return findings


__all__ = ["detect_docx_white_text"]
