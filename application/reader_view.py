"""Reader's view: the text a person looking at the document could see.

Cleaning a PDF or an Office file in place means editing a format with
many places to hide things, and whatever the cleaner did not know to
look for stays. This module does the opposite. It keeps nothing of the
original container: it renders the pages and writes out only the text
that left a visible mark (``analyzers/pdf_render_oracle.py``).

PDF files are examined directly. Office and OpenDocument files are first
converted to PDF by LibreOffice, running headless with no network
access needed, and then examined the same way, so what is kept is what
LibreOffice would have shown or printed.

The result is plain text. Formatting, images, tables as tables, and
links are gone. It is a view for a pipeline or a careful reader, not a
replacement for the document, and the receipt says so.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

from analyzers.pdf_render_oracle import MAX_PAGES, examine_pdf

RECEIPT_SCHEMA: Final[str] = "bayyinah.reader-view-receipt/1"
OFFICE_SUFFIXES: Final[frozenset[str]] = frozenset({
    ".docx", ".doc", ".odt", ".rtf", ".pptx", ".ppt", ".odp",
    ".xlsx", ".xls", ".ods",
})
CONVERT_TIMEOUT_S: Final[int] = 120


class ReaderViewError(RuntimeError):
    """The reader's view could not be produced; the message says why."""


def _to_pdf(source: Path, workdir: Path) -> Path:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise ReaderViewError(
            "LibreOffice is needed to render Office files and was not found. "
            "Install it, or export the file to PDF yourself and run this on the PDF.")
    profile = workdir / "profile"
    try:
        subprocess.run(
            [soffice, f"-env:UserInstallation=file://{profile}", "--headless",
             "--convert-to", "pdf", "--outdir", str(workdir), str(source)],
            check=True, capture_output=True, timeout=CONVERT_TIMEOUT_S)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise ReaderViewError(f"LibreOffice could not convert {source.name}: {exc}") from exc
    out = workdir / (source.stem + ".pdf")
    if not out.is_file():
        raise ReaderViewError(f"LibreOffice produced no PDF for {source.name}")
    return out


def reader_view(
    source: Path, destination: Path | None = None, *,
    receipt_path: Path | None = None, max_pages: int = MAX_PAGES,
) -> dict:
    """Write the visible text of ``source`` and a receipt. Returns the receipt."""
    source = Path(source)
    suffix = source.suffix.lower()
    raw = source.read_bytes()
    with tempfile.TemporaryDirectory() as tmp:
        if suffix == ".pdf" or raw[:5] == b"%PDF-":
            pdf, via = source, "direct"
        elif suffix in OFFICE_SUFFIXES:
            pdf, via = _to_pdf(source, Path(tmp)), "libreoffice"
        else:
            raise ReaderViewError(
                f"{suffix or '(no extension)'} is not a PDF or Office format. "
                "For text files use `bayyinah clean`.")
        result = examine_pdf(pdf, max_pages)
    pages: list[str] = []
    for i in range(result.pages_checked):
        pages.append("\n".join(
            s.text for s in result.spans if s.page_index == i and s.seen))
    text = "\n\f\n".join(pages).rstrip() + "\n"
    out = text.encode("utf-8")
    destination = Path(destination) if destination else source.with_name(
        source.name + ".reader-view.txt")
    destination.write_bytes(out)
    unseen = result.unseen
    from bayyinah import __version__
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "tool": "bayyinah",
        "tool_version": __version__,
        "created_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": {"name": source.name, "bytes": len(raw),
                   "sha256": hashlib.sha256(raw).hexdigest()},
        "view": {"name": destination.name, "bytes": len(out),
                 "sha256": hashlib.sha256(out).hexdigest()},
        "rendered_via": via,
        "pages_total": result.pages_total,
        "pages_included": result.pages_checked,
        "spans_kept": len(result.seen),
        "spans_left_out": len(unseen),
        "left_out_preview": [s.text[:120] for s in unseen[:10]],
        "not_included": [
            "text that leaves no visible mark when the page is rendered",
            "text positioned off the page",
            "formatting, images, links, and anything in metadata or attachments",
        ] + ([f"pages after page {result.pages_checked} (page limit)"]
             if result.pages_total > result.pages_checked else []),
        "statement": (
            "This is the text one renderer displayed, not the original "
            "document. It is not a certificate that the text is safe to act "
            "on: an instruction written in plain sight is still here. The "
            "receipt is unsigned."
        ),
    }
    receipt_path = Path(receipt_path) if receipt_path else destination.with_name(
        destination.name + ".receipt.json")
    receipt_path.write_text(
        json.dumps(receipt, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    receipt["view_path"] = str(destination)
    receipt["receipt_path"] = str(receipt_path)
    return receipt


__all__ = ["OFFICE_SUFFIXES", "RECEIPT_SCHEMA", "ReaderViewError", "reader_view"]
