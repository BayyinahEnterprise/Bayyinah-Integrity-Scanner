#!/usr/bin/env python3
"""Build a clean PDF carrying a bare destination-array /OpenAction
([page_ref /XYZ null null null]) without any active content.

Reproduces Bug 1 (openaction false positive on benign navigation).
LibreOffice naturally emits this shape when re-exporting a document
with an "open at page N" hint; we synthesise it for determinism
because LibreOffice's export behavior varies across versions.

The producer string is set to LibreOffice for the Round 12 fixture's
producer-family coverage check.

Output: fixture_clean_libreoffice_destination_oa.pdf
"""
from __future__ import annotations
import io
from pathlib import Path
import pypdf
from pypdf.generic import (
    ArrayObject, NameObject, NullObject,
)

HERE = Path(__file__).parent
HTML_SOURCE = b"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Round 12 LibreOffice Fixture</title></head>
<body><h1>Round 12 Reproducer (LibreOffice synthetic OpenAction)</h1>
<p>This document carries a bare destination-array /OpenAction
that LibreOffice naturally emits. ISO 32000-1 section 12.6.3 defines
this as a navigation hint, not executable content.</p>
</body></html>
"""


def _build_seed_pdf(workdir: Path) -> Path:
    """Render minimal HTML to PDF via LibreOffice for the seed."""
    import os
    import subprocess
    seed_html = workdir / "seed.html"
    seed_html.write_bytes(HTML_SOURCE)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = "0"
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "seed.html",
         "--outdir", str(workdir)],
        cwd=workdir, env=env, check=True, capture_output=True,
    )
    return workdir / "seed.pdf"


def build(output_path: Path) -> None:
    workdir = output_path.parent / "_build_libreoffice_oa"
    workdir.mkdir(parents=True, exist_ok=True)
    seed_pdf = _build_seed_pdf(workdir)

    reader = pypdf.PdfReader(seed_pdf)
    writer = pypdf.PdfWriter(clone_from=reader)
    first_page = writer.pages[0].indirect_reference
    destination = ArrayObject([
        first_page,
        NameObject("/XYZ"),
        NullObject(),
        NullObject(),
        NullObject(),
    ])
    writer._root_object[NameObject("/OpenAction")] = destination

    buf = io.BytesIO()
    writer.write(buf)
    output_path.write_bytes(buf.getvalue())

    for f in workdir.glob("*"):
        f.unlink(missing_ok=True)
    workdir.rmdir()


if __name__ == "__main__":
    out = HERE / "fixture_clean_libreoffice_destination_oa.pdf"
    build(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
