"""
Tests for domain.integrity_report.IntegrityReport.

Coverage targets:
  * shape parity with v0/v0.1 (same fields, same defaults)
  * to_dict is byte-identical to bayyinah_v0_1.IntegrityReport.to_dict
  * zahir_findings / batin_findings partition the findings list
"""

from __future__ import annotations

import json

import bayyinah_v0_1
from domain.finding import Finding
from domain.integrity_report import IntegrityReport


# ---------------------------------------------------------------------------
# Construction & defaults
# ---------------------------------------------------------------------------

def test_default_construction() -> None:
    r = IntegrityReport(file_path="/tmp/x.pdf")
    assert r.integrity_score == 1.0
    assert r.findings == []
    assert r.error is None
    assert r.scan_incomplete is False


# ---------------------------------------------------------------------------
# to_dict parity
# ---------------------------------------------------------------------------

def _domain_report_with_findings() -> IntegrityReport:
    return IntegrityReport(
        file_path="/tmp/x.pdf",
        integrity_score=0.55,
        findings=[
            Finding(mechanism="zero_width_chars", tier=2, confidence=0.9,
                    description="zwsp", location="page 1",
                    surface="Hello", concealed="H\u200Bello"),
            Finding(mechanism="javascript", tier=1, confidence=1.0,
                    description="js action", location="catalog /OpenAction"),
        ],
        scan_incomplete=False,
    )


def _v01_report_with_findings() -> bayyinah_v0_1.IntegrityReport:
    return bayyinah_v0_1.IntegrityReport(
        file_path="/tmp/x.pdf",
        integrity_score=0.55,
        findings=[
            bayyinah_v0_1.Finding(
                mechanism="zero_width_chars", tier=2, confidence=0.9,
                description="zwsp", location="page 1",
                surface="Hello", concealed="H\u200Bello"),
            bayyinah_v0_1.Finding(
                mechanism="javascript", tier=1, confidence=1.0,
                description="js action", location="catalog /OpenAction"),
        ],
        scan_incomplete=False,
    )


def test_to_dict_keys_match_v01() -> None:
    assert list(_domain_report_with_findings().to_dict().keys()) == \
           list(_v01_report_with_findings().to_dict().keys())


def test_to_dict_is_byte_identical_to_v01() -> None:
    """The headline Phase 1 invariant: IntegrityReport.to_dict output
    matches bayyinah_v0_1.IntegrityReport.to_dict byte-for-byte."""
    d_json = json.dumps(_domain_report_with_findings().to_dict(),
                        sort_keys=True, default=str)
    v_json = json.dumps(_v01_report_with_findings().to_dict(),
                        sort_keys=True, default=str)
    assert d_json == v_json


def test_to_dict_roundtrip_empty_report() -> None:
    d_json = json.dumps(IntegrityReport(file_path="/tmp/x.pdf").to_dict(),
                        sort_keys=True)
    v_json = json.dumps(bayyinah_v0_1.IntegrityReport(file_path="/tmp/x.pdf").to_dict(),
                        sort_keys=True)
    assert d_json == v_json


def test_to_dict_emits_scan_incomplete_flag() -> None:
    r = IntegrityReport(file_path="/tmp/x.pdf", scan_incomplete=True,
                        error="text layer scan failed",
                        integrity_score=0.5)
    d = r.to_dict()
    assert d["scan_incomplete"] is True
    assert d["error"] == "text layer scan failed"
    assert d["integrity_score"] == 0.5


def test_to_dict_does_not_leak_source_layer() -> None:
    r = _domain_report_with_findings()
    for f_dict in r.to_dict()["findings"]:
        assert "source_layer" not in f_dict


# ---------------------------------------------------------------------------
# Zahir / batin partition
# ---------------------------------------------------------------------------

def test_zahir_batin_partition() -> None:
    r = _domain_report_with_findings()
    zahir = r.zahir_findings
    batin = r.batin_findings
    assert [f.mechanism for f in zahir] == ["zero_width_chars"]
    assert [f.mechanism for f in batin] == ["javascript"]
    # Every finding lives in exactly one bucket.
    assert len(zahir) + len(batin) == len(r.findings)


def test_zahir_batin_empty_for_empty_report() -> None:
    r = IntegrityReport(file_path="/tmp/x.pdf")
    assert r.zahir_findings == []
    assert r.batin_findings == []
