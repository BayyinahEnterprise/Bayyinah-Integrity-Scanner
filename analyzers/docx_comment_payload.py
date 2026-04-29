"""
Tier 2 detector for hidden-text payloads in DOCX comment parts (v1.1.2).

OOXML stores comments in ``word/comments.xml``, with each comment
referenced from ``word/document.xml`` via ``<w:commentRangeStart>`` /
``<w:commentReference>`` markers. Word displays comments in the review
pane; printed and exported views often suppress them; LLM ingestion
behaviour depends on the extractor (some include comments in the text
stream, some don't, some treat them as separate channels).

Adversarial use stores a payload as a comment whose reference is
omitted from document.xml. Word still loads the comments part (it's
declared in [Content_Types].xml and registered as a relationship), so
any indexer or extractor that walks the package tree finds the
payload, while the rendered document shows no review-pane indicator
because document.xml has no commentRangeStart pointing at it.

Mirrors the PDF analyzer's ``pdf_hidden_text_annotation`` mechanism in
spirit: a content channel that exists in the package but is not
referenced from the visible-content part.

Closes docx_gauntlet fixture 04_comment_payload.docx.

Tier discipline: Tier 2 because comments are a legitimate content
channel (review workflows are normal), and the trigger is "comment
exists but no document.xml reference points at it." That is
byte-deterministic on its own (referenced or not), but the
interpretation (legitimate orphan after a track-changes accept vs.
adversarial concealment) is structural rather than semantic. Tier 2
is the right home for that ambiguity.

The detector is permissive: a comment with a w:id that document.xml
does not reference fires; a comment whose w:id IS referenced does not
fire. Long divergent comment text is also flagged at Tier 2 with the
same threshold convention as the metadata analyzer (>= 16 chars, not
appearing in document.xml).
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from domain.finding import Finding


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_W_COMMENT = f"{{{_W_NS}}}comment"
_W_COMMENT_REFERENCE = f"{{{_W_NS}}}commentReference"
_W_COMMENT_RANGE_START = f"{{{_W_NS}}}commentRangeStart"
_W_COMMENT_RANGE_END = f"{{{_W_NS}}}commentRangeEnd"
_W_T = f"{{{_W_NS}}}t"
_W_ID = f"{{{_W_NS}}}id"

_PREVIEW_LIMIT = 240
_DIVERGENCE_MIN_CHARS = 16

_NS_TAG = re.compile(r"^\{[^}]*\}")


def _local_name(tag: str) -> str:
    return _NS_TAG.sub("", tag)


def _extract_rendered_text(zf: zipfile.ZipFile) -> str:
    if "word/document.xml" not in zf.namelist():
        return ""
    try:
        xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (KeyError, ET.ParseError):
        return ""
    chunks: list[str] = []
    for el in root.iter(_W_T):
        if el.text:
            chunks.append(el.text)
    return "\n".join(chunks)


def _referenced_comment_ids(zf: zipfile.ZipFile) -> set[str]:
    """Return the set of comment w:ids referenced from document.xml.

    A comment whose id is not in this set is structurally orphaned.
    """
    if "word/document.xml" not in zf.namelist():
        return set()
    try:
        xml_bytes = zf.read("word/document.xml")
        root = ET.fromstring(xml_bytes)
    except (KeyError, ET.ParseError):
        return set()
    ids: set[str] = set()
    # Any of three reference markers count: commentReference,
    # commentRangeStart, commentRangeEnd. Document compliance with
    # all three is what makes a comment user-visible in Word.
    for tag in (
        _W_COMMENT_REFERENCE,
        _W_COMMENT_RANGE_START,
        _W_COMMENT_RANGE_END,
    ):
        for el in root.iter(tag):
            wid = el.get(_W_ID)
            if wid is not None:
                ids.add(wid)
    return ids


def _comment_text(comment_el: ET.Element) -> str:
    """Concatenate every <w:t> text node inside a comment element."""
    chunks: list[str] = []
    for el in comment_el.iter(_W_T):
        if el.text:
            chunks.append(el.text)
    return "".join(chunks).strip()


def detect_docx_comment_payload(file_path: Path) -> list[Finding]:
    """Return Tier 2 findings for comments whose w:id is not
    referenced from document.xml, OR whose text is long and divergent
    from rendered content.
    """
    findings: list[Finding] = []
    try:
        with zipfile.ZipFile(str(file_path), "r") as zf:
            names = zf.namelist()
            if "word/comments.xml" not in names:
                return findings
            try:
                xml_bytes = zf.read("word/comments.xml")
            except KeyError:
                return findings
            try:
                root = ET.fromstring(xml_bytes)
            except ET.ParseError:
                return findings

            referenced_ids = _referenced_comment_ids(zf)
            rendered = _extract_rendered_text(zf)

            for comment in root.iter(_W_COMMENT):
                wid = comment.get(_W_ID, "?")
                text = _comment_text(comment)
                if not text:
                    continue
                preview = (
                    text if len(text) <= _PREVIEW_LIMIT
                    else text[:_PREVIEW_LIMIT] + "..."
                )

                # Trigger 1: orphan reference. Comment has content
                # but document.xml never points at it.
                if wid not in referenced_ids:
                    findings.append(Finding(
                        mechanism="docx_comment_payload",
                        tier=2,
                        confidence=1.0,
                        description=(
                            f"Comment w:id={wid} carries text "
                            f"({len(text)} chars) but is not "
                            f"referenced from document.xml. The "
                            f"comments part is loaded by Word and "
                            f"by package walkers, but the review "
                            f"pane shows no marker. Likely "
                            f"adversarial concealment of payload "
                            f"in the comments channel."
                        ),
                        location=f"word/comments.xml#{wid}",
                        surface=f"comment id={wid} (orphaned)",
                        concealed=(
                            f"orphan comment ({len(text)} chars); "
                            f"recovered text: {preview!r}"
                        ),
                        source_layer="batin",
                    ))
                    continue

                # Trigger 2: divergent text. Comment is referenced,
                # but its body is long and does not appear in the
                # rendered document text. Mirrors the metadata
                # analyzer's divergence threshold.
                if (
                    len(text) >= _DIVERGENCE_MIN_CHARS
                    and text not in rendered
                ):
                    findings.append(Finding(
                        mechanism="docx_comment_payload",
                        tier=2,
                        confidence=0.9,
                        description=(
                            f"Comment w:id={wid} is referenced "
                            f"from document.xml but its body "
                            f"({len(text)} chars) does not appear "
                            f"in the rendered text. Comments are a "
                            f"legitimate review channel, but a long "
                            f"divergent body warrants Tier 2 review "
                            f"for payload concealment."
                        ),
                        location=f"word/comments.xml#{wid}",
                        surface=f"comment id={wid} (divergent body)",
                        concealed=(
                            f"comment body ({len(text)} chars) not "
                            f"present in rendered document; "
                            f"recovered text: {preview!r}"
                        ),
                        source_layer="batin",
                    ))
    except (zipfile.BadZipFile, OSError):
        return findings

    return findings


__all__ = ["detect_docx_comment_payload"]
