"""
Integration tests for /scan endpoint verdict emission.

Asserts that every routing-divergence fixture in the format_routing_gauntlet
surfaces verdict=mughlaq at the HTTP layer, and that the control fixture
does not.

This is the F4 falsifiability surface for the Day 1 Tier 0 layer at the
HTTP boundary. If a routing-divergence fixture passes through the scanner
and emerges with verdict != mughlaq, the published guarantee that
adversarial routing is publicly disclosed is falsified.

The Verdict type is Literal["sahih", "mushtabih", "mukhfi", "munafiq",
"mughlaq"]. A clean .pdf with valid magic returns "sahih"; the control
test asserts != "mughlaq" defensively rather than asserting the exact
positive value, so unrelated future changes to non-mughlaq scoring do
not falsify this test.
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import app


FIXTURES_DIR = Path(__file__).resolve().parents[2] / (
    "docs/adversarial/format_routing_gauntlet/fixtures"
)

ROUTING_DIVERGENCE_FIXTURES = [
    "01_polyglot.docx",
    "02_pdf_as_txt.txt",
    "03_empty.pdf",
    "04_truncated.pdf",
    "05_docx_as_xlsx.xlsx",
    "06_unanalyzed.txt",
]
CONTROL_FIXTURE = "07_control.pdf"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


@pytest.mark.parametrize("fixture_name", ROUTING_DIVERGENCE_FIXTURES)
def test_routing_divergence_fixture_returns_mughlaq(
    client: TestClient, fixture_name: str,
) -> None:
    fixture_path = FIXTURES_DIR / fixture_name
    assert fixture_path.exists(), f"Day 1 fixture missing: {fixture_path}"
    with open(fixture_path, "rb") as f:
        response = client.post(
            "/scan",
            files={"file": (fixture_name, f, "application/octet-stream")},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "verdict" in payload, "verdict field missing from /scan response"
    assert payload["verdict"] == "mughlaq", (
        f"{fixture_name} should floor at mughlaq via Tier 0 routing-divergence; "
        f"got {payload['verdict']}"
    )


def test_control_fixture_does_not_return_mughlaq(client: TestClient) -> None:
    fixture_path = FIXTURES_DIR / CONTROL_FIXTURE
    assert fixture_path.exists(), f"Control fixture missing: {fixture_path}"
    with open(fixture_path, "rb") as f:
        response = client.post(
            "/scan",
            files={"file": (CONTROL_FIXTURE, f, "application/pdf")},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "verdict" in payload, "verdict field missing from /scan response"
    assert payload["verdict"] != "mughlaq", (
        f"Control fixture {CONTROL_FIXTURE} must not floor at mughlaq; "
        f"a real .pdf with PDF magic should not trigger Tier 0. "
        f"Got verdict={payload['verdict']}"
    )
