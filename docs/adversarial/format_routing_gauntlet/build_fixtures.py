"""
Format-Routing adversarial gauntlet - fixture builder (v1.1.2).

Six fixtures probing whether the scanner is honest about its routing
decision when the file's claimed identity (extension) and actual
identity (magic bytes / internal structure) disagree, plus one
control fixture exercising the clean baseline.

Each fixture pairs one routing-divergence vector to one expected
Tier 0 trigger condition. The vectors are seeded by the 2026-04-27
Mughlaq Trap stress test (V1, V2, V3) and extended with three
additional shapes (V4 truncated, V5 OOXML internal divergence,
V6 unanalyzed text). The seventh fixture is the V4 control from the
Mughlaq Trap report - a real PDF with a real extension.

Build determinism: re-running this script produces byte-identical
output. CI can rebuild fixtures from this script and run the gauntlet
on every commit without drift.

> "Wa la talbisu al-haqqa bil-batil wa taktumu al-haqqa wa antum
>  ta'lamun." (Al-Baqarah 2:42)
"""
from __future__ import annotations

import os
import shutil
import zipfile
from io import BytesIO
from pathlib import Path

import pikepdf

REPO_ROOT = Path(__file__).resolve().parents[3]
GAUNTLET_DIR = Path(__file__).resolve().parent
OUT = GAUNTLET_DIR / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)

# Reuse the existing PDF gauntlet fixture as the polyglot/spoof source.
# The 01_white_on_white.pdf carries a real adversarial concealment
# payload, so the polyglot renames preserve a realistic adversarial
# byte stream behind the lying extension.
SEED_PDF = REPO_ROOT / "docs/adversarial/pdf_gauntlet/fixtures/01_white_on_white.pdf"

# Reuse an existing DOCX fixture for the OOXML internal-path divergence
# test. We rename a real DOCX to .xlsx; the ZIP head still declares
# word/document.xml (DOCX) rather than xl/workbook.xml (XLSX).
SEED_DOCX = REPO_ROOT / "docs/adversarial/docx_gauntlet/fixtures/04_comment_payload.docx"


def _copy(src: Path, dst: Path) -> None:
    """Deterministic file copy. Removes any prior dst first."""
    if dst.exists():
        dst.unlink()
    shutil.copyfile(src, dst)


def build_01_polyglot() -> None:
    """V1 - PDF magic bytes with .docx extension.

    Trigger: T0a (extension_mismatch fires in FileRouter; Tier 0
    detector translates that into format_routing_divergence with
    routing_decision='trusted_magic_bytes').
    """
    _copy(SEED_PDF, OUT / "01_polyglot.docx")


def build_02_pdf_as_txt() -> None:
    """V2 - PDF magic bytes with .txt extension.

    Trigger: T0a (FileRouter detects PDF magic, ext map says CODE,
    extension_mismatch=True).
    """
    _copy(SEED_PDF, OUT / "02_pdf_as_txt.txt")


def build_03_empty_pdf() -> None:
    """V3 - 4-byte file ('%PDF') with .pdf extension.

    Trigger: T0c (file_size 4 < CONTENT_DEPTH_FLOOR 16).
    """
    out = OUT / "03_empty.pdf"
    out.write_bytes(b"%PDF")


def build_04_truncated_pdf() -> None:
    """V4 - PDF header but no %%EOF, length below the depth floor.

    The fixture is exactly 12 bytes: '%PDF-1.4\\n%' is a typical PDF
    preamble, padded with one trailing byte to reach a length still
    below the 16-byte content-depth floor. The router will see PDF
    magic and the body will fail to parse; the Tier 0 layer fires on
    the size check before the analyzer attempts to read the trailer.
    """
    out = OUT / "04_truncated.pdf"
    # 12 bytes - intentionally below CONTENT_DEPTH_FLOOR=16.
    out.write_bytes(b"%PDF-1.4\n%a\n")


def build_05_docx_as_xlsx() -> None:
    """V5 - DOCX zip container with .xlsx extension.

    Trigger: T0d (the OOXML internal-path divergence check). The ZIP
    head declares word/document.xml (DOCX's canonical part) while the
    extension claims XLSX. The router's _detect_xlsx accepts the
    .xlsx extension on any ZIP and routes to XlsxAnalyzer; the Tier 0
    detector inspects the ZIP head and disagrees.
    """
    _copy(SEED_DOCX, OUT / "05_docx_as_xlsx.xlsx")


def build_06_unanalyzed_text() -> None:
    """V6 - 4-byte text file (the V5 case from the Mughlaq Trap report).

    Trigger: T0c (file_size 4 < CONTENT_DEPTH_FLOOR 16). On v1.1.1 a
    4-byte .txt produces score 1.0 sahih because TextFileAnalyzer
    finds no concealment patterns in 'aaaa'. The Tier 0 layer rejects
    the verdict on content-depth grounds - 4 bytes cannot honestly
    sustain a sahih claim regardless of which analyzer ran.
    """
    out = OUT / "06_unanalyzed.txt"
    out.write_bytes(b"aaaa")


def build_07_control() -> None:
    """V7 - real PDF with real .pdf extension.

    No trigger fires. This is the clean baseline: the verdict resolves
    via the existing tamyiz_verdict path (mukhfi via the seed PDF's
    white_on_white_text Tier 1 finding), not via Tier 0 routing
    floor. Verifying that no Tier 0 finding fires here is essential -
    the layer must not produce false positives on aligned files.
    """
    _copy(SEED_PDF, OUT / "07_control.pdf")


def main() -> None:
    if not SEED_PDF.exists():
        raise SystemExit(
            f"Seed PDF missing: {SEED_PDF}. Run "
            f"docs/adversarial/pdf_gauntlet/build_fixtures.py first."
        )
    if not SEED_DOCX.exists():
        raise SystemExit(
            f"Seed DOCX missing: {SEED_DOCX}. Run "
            f"docs/adversarial/docx_gauntlet/build_fixtures.py first."
        )

    build_01_polyglot()
    build_02_pdf_as_txt()
    build_03_empty_pdf()
    build_04_truncated_pdf()
    build_05_docx_as_xlsx()
    build_06_unanalyzed_text()
    build_07_control()

    # Report what was built so a human eyeballing CI output can confirm.
    for fixture in sorted(OUT.glob("*")):
        print(f"  {fixture.name}  {fixture.stat().st_size} bytes")


if __name__ == "__main__":
    main()
