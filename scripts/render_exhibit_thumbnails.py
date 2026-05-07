"""Render page-1 thumbnails of the demo exhibit fixtures.

The demo page at /demo shows three "exhibit" cards that one-click upload
a fixture PDF through the live scan-then-summarize pipeline. Each card
opens with a thumbnail of the fixture's first page so users see the
actual document substrate (or, for the encrypted exhibit, an inline
SVG placeholder) before clicking. Without the thumbnail the cards read
as abstract verdict descriptions; with it the firewall thesis is
visible at a glance, especially for the concealment fixture, whose
near-empty visible surface contrasts with its 16 deterministic findings.

This script is the build step. Re-run it after editing any fixture in
docs/demo/fixtures/ that has a corresponding entry in TARGETS below.
The encrypted fixture is intentionally absent: encrypted PDFs cannot
be rendered, which is the point, and the demo card uses an inline
SVG illustration instead.

Output: docs/landing-mock-v2/exhibit-thumbnails/<stem>.jpg

Run: python scripts/render_exhibit_thumbnails.py
"""
from __future__ import annotations

from pathlib import Path

import fitz  # pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "docs" / "demo" / "fixtures"
THUMBS_DIR = ROOT / "docs" / "landing-mock-v2" / "exhibit-thumbnails"

# Fixtures whose first page can be rendered. Stems match the fixture
# filename without the .pdf extension; the demo serves thumbnails as
# /demo/exhibit-thumbnails/<stem>.jpg (whitelist enforced server-side).
TARGETS = [
    "clean_q3_report",
    "adversarial_invisible_text",
]

# Width chosen for ~240px display at 2x device pixel ratio. JPEG quality
# 82 keeps the financial-table fixture under 40KB while remaining
# legible at the rendered card size. Aspect ratio is preserved from
# the source page.
THUMB_WIDTH = 480
JPEG_QUALITY = 82
RENDER_DPI_MATRIX = fitz.Matrix(1.5, 1.5)


def render_one(stem: str) -> tuple[int, int, int]:
    src = FIXTURES_DIR / f"{stem}.pdf"
    if not src.is_file():
        raise FileNotFoundError(f"Fixture not found: {src}")
    doc = fitz.open(str(src))
    try:
        page = doc[0]
        pix = page.get_pixmap(matrix=RENDER_DPI_MATRIX)
    finally:
        doc.close()
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("RGB")
    new_h = int(pix.height * THUMB_WIDTH / pix.width)
    img = img.resize((THUMB_WIDTH, new_h), Image.LANCZOS)
    out = THUMBS_DIR / f"{stem}.jpg"
    img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    return THUMB_WIDTH, new_h, out.stat().st_size


def main() -> int:
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Rendering exhibit thumbnails to {THUMBS_DIR}")
    for stem in TARGETS:
        w, h, n = render_one(stem)
        print(f"  {stem}.jpg  {w}x{h}  {n} bytes")
    print("Done. Encrypted exhibit uses inline SVG (see demo.html, no thumbnail rendered).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
