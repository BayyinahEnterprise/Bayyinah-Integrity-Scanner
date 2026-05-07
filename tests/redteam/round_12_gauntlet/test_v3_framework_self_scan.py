"""Round 12 framework self-scan: assert the v3.0 framework PDF
returns sahih against the v1.2.4 scanner.

Per v3 section 9.7 (Cross-Document Accounting Drift) applied
recursively: the framework's own publication artifact must not
mushtabih against the framework's own scanner. The locked Round
12 prompt anticipated this would surface as a CRITICAL finding
on v1.2.3; empirically (LibreOffice-rendered docx, this clone),
the framework PDF returned sahih on BOTH v1.2.3 and v1.2.4. The
recursive failure mode the prompt anticipated did not manifest
for this artifact under this rendering path.

The fixture and this regression test are still load-bearing: a
future commit could regress the framework PDF's verdict
(producer-string change, encoding shift in the OpenAction
emission path, tier reclassification) and this pinning test
catches that.
"""
from __future__ import annotations
from pathlib import Path
import pytest
from bayyinah import scan_pdf

FIXTURE = (
    Path(__file__).parent / "fixture_v3_framework_self_scan.pdf"
)


def test_v3_framework_pdf_self_scans_clean() -> None:
    """The v3.0 framework PDF must verdict sahih against the
    scanner. If this fails, the framework's own publication
    artifact is being flagged by the framework's own scanner -
    a v3 section 9.7 instance to surface and close."""
    if not FIXTURE.exists():
        pytest.skip(
            "framework PDF not mounted in corpus; render the docx "
            "with `soffice --headless --convert-to pdf` and copy to "
            "fixture_v3_framework_self_scan.pdf"
        )
    rd = scan_pdf(FIXTURE).to_dict()
    fires = sorted({f.get("mechanism") for f in rd.get("findings", [])})
    assert rd.get("integrity_score") == 1.0, (
        f"framework PDF score should be 1.0, got "
        f"{rd.get('integrity_score')}; fires={fires}"
    )
    assert fires == [], (
        f"framework PDF fires findings: {fires}"
    )


def test_v3_framework_pdf_provenance_recorded() -> None:
    """The fixture's provenance is documented: LibreOffice-rendered
    from bayyinah_audit_framework_v3.docx (Round 12 build,
    2026-05-07). Future renderings (different LibreOffice version,
    pdfTeX rendering of the same source) may produce different
    PDFs; this test pins the structural property of the current
    fixture - a LibreOffice-produced PDF without an /OpenAction
    key should not fire any batin-layer mechanism."""
    if not FIXTURE.exists():
        pytest.skip("framework PDF not mounted")
    import pypdf
    r = pypdf.PdfReader(FIXTURE)
    producer = r.metadata.get("/Producer", "")
    assert "LibreOffice" in producer, (
        f"fixture producer drift: expected LibreOffice, got {producer!r}. "
        f"If the v3.0 framework was re-rendered with a different "
        f"producer (pdfTeX, etc.), update the fixture and re-verify "
        f"that test_v3_framework_pdf_self_scans_clean still passes."
    )
