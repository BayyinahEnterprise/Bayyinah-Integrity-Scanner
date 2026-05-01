"""Record verbatim /scan responses for the three landing-mock-v2 fixtures.

Output: docs/landing-mock-v2/fixtures.json
Usage:  python scripts/record_landing_fixtures.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pikepdf  # noqa: E402
from bayyinah import __version__ as _BAYYINAH_VERSION  # noqa: E402
from bayyinah import scan_file  # noqa: E402


def make_encrypted(src: Path, dst: Path) -> None:
    """Encrypt a copy of src with a non-empty user password.

    A non-empty user password makes the content unreadable without the
    key, which is the condition Bayyinah's encrypted-PDF flow is meant
    to demonstrate.
    """
    with pikepdf.open(src) as pdf:
        pdf.save(
            dst,
            encryption=pikepdf.Encryption(
                owner="bayyinah-demo-owner",
                user="bayyinah-demo-user",
                R=4,
            ),
        )


def record(label: str, fixture_path: Path) -> dict:
    print(f"  scanning {label}: {fixture_path.name}")
    report = scan_file(str(fixture_path))
    payload = report.to_dict()
    payload["file_path"] = fixture_path.name
    # Add scanner_version so a curious reader can distinguish the
    # report-schema version (`version`, currently 0.1.0) from the
    # scanner package version that produced the report.
    payload["scanner_version"] = _BAYYINAH_VERSION
    return payload


def main() -> None:
    out_dir = ROOT / "docs" / "landing-mock-v2"
    out_dir.mkdir(parents=True, exist_ok=True)

    clean_pdf = ROOT / "tests" / "fixtures" / "clean.pdf"
    adversarial_pdf = ROOT / "tests" / "fixtures" / "positive_combined.pdf"

    with tempfile.TemporaryDirectory() as tmp:
        encrypted_path = Path(tmp) / "encrypted_demo.pdf"
        make_encrypted(clean_pdf, encrypted_path)

        recorded = {
            "clean": record("clean", clean_pdf),
            "adversarial": record("adversarial", adversarial_pdf),
            "encrypted": record("encrypted", encrypted_path),
        }

    out_path = out_dir / "fixtures.json"
    out_path.write_text(json.dumps(recorded, indent=2))
    print(f"\nwrote {out_path.relative_to(ROOT)}")
    for k, v in recorded.items():
        score = v.get("integrity_score", "?")
        n = len(v.get("findings", []))
        verdict = v.get("verdict", "?")
        print(f"  {k}: verdict={verdict} score={score} findings={n}")


if __name__ == "__main__":
    main()
