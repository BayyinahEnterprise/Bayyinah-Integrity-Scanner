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


def test_modular_to_dict_preserves_v01_keys() -> None:
    """v0.1 keys must remain in to_dict in the same order, with the same
    values. Modular may add additional keys after the v0.1 keys
    (parity-break, see PARITY.md). It must not remove or reorder v0.1
    keys.
    """
    d = _domain_report_with_findings().to_dict()
    v = _v01_report_with_findings().to_dict()
    v_keys = list(v.keys())
    d_keys = list(d.keys())
    # v0.1 key order must be preserved as a prefix.
    assert d_keys[:len(v_keys)] == v_keys, (
        f"v0.1 key order broken.\n  v0.1: {v_keys}\n  modular: {d_keys}"
    )
    # Values for shared keys must match. ``findings`` is tested
    # field-by-field in test_finding.py; comparing the whole list here
    # would re-test that surface and tightly couple this test to
    # Finding's serialisation shape.
    for k in v_keys:
        if k == "findings":
            continue
        assert d[k] == v[k], f"value drift on key {k!r}: {d[k]!r} vs {v[k]!r}"
    # The additive keys must be present and well-typed.
    assert "scan_complete" in d
    assert "coverage" in d
    assert isinstance(d["scan_complete"], bool)
    assert d["scan_complete"] is (not d["scan_incomplete"])
    assert d["coverage"] is None or isinstance(d["coverage"], dict)


def test_to_dict_is_v01_prefix_byte_identical() -> None:
    """v0.1 prefix of the modular to_dict output is byte-identical to
    bayyinah_v0_1.IntegrityReport.to_dict, when both are serialised
    over the same key set. Replaces the pre-v1.2.0 byte-for-byte test
    that compared the full dict (no longer applicable after the
    parity-break documented in PARITY.md and CHANGELOG.md).
    """
    d = _domain_report_with_findings().to_dict()
    v = _v01_report_with_findings().to_dict()
    # Restrict the modular output to v0.1's key set so the comparison
    # holds at the byte level on the shared prefix.
    d_v01_only = {k: d[k] for k in v.keys()}
    d_json = json.dumps(d_v01_only, sort_keys=True, default=str)
    v_json = json.dumps(v, sort_keys=True, default=str)
    assert d_json == v_json


def test_to_dict_roundtrip_empty_report() -> None:
    """Empty report: v0.1 prefix matches v0.1 byte-for-byte; modular
    output additionally carries scan_complete=True and the per-layer
    coverage default.
    """
    d = IntegrityReport(file_path="/tmp/x.pdf").to_dict()
    v = bayyinah_v0_1.IntegrityReport(file_path="/tmp/x.pdf").to_dict()
    d_v01_only = {k: d[k] for k in v.keys()}
    d_json = json.dumps(d_v01_only, sort_keys=True)
    v_json = json.dumps(v, sort_keys=True)
    assert d_json == v_json
    # Additive keys present, well-typed, and at the documented defaults
    # for an empty report.
    assert d["scan_complete"] is True
    assert d["coverage"] == {"zahir": None, "batin": None}


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
