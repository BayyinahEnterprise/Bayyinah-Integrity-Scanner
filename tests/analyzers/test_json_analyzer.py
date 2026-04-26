"""
Tests for analyzers.json_analyzer.JsonAnalyzer.

Phase 9 guardrails. The analyzer is simultaneously a batin witness
(structural concealment: duplicate keys, excessive nesting) and a
zahir witness (embedded Unicode concealment in string values). Tests
cover both surfaces and the malformed-JSON error path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from analyzers import JsonAnalyzer
from analyzers.base import BaseAnalyzer
from domain import Finding, IntegrityReport
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


def test_is_base_analyzer_subclass() -> None:
    assert issubclass(JsonAnalyzer, BaseAnalyzer)


def test_class_attributes() -> None:
    assert JsonAnalyzer.name == "json_file"
    assert JsonAnalyzer.error_prefix == "JSON scan error"
    # The class-level source_layer is batin (for scan_error attribution);
    # per-finding zahir/batin is set explicitly when emitted.
    assert JsonAnalyzer.source_layer == "batin"


def test_supported_kinds_is_json_only() -> None:
    assert JsonAnalyzer.supported_kinds == frozenset({FileKind.JSON})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _scan(path: Path) -> IntegrityReport:
    return JsonAnalyzer().scan(path)


def _mechanisms(report: IntegrityReport) -> list[str]:
    return [f.mechanism for f in report.findings]


# ---------------------------------------------------------------------------
# Clean input
# ---------------------------------------------------------------------------


def test_clean_json_produces_no_findings(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.json", '{"hello": "world", "n": 1}')
    report = _scan(p)
    assert report.findings == []
    assert report.integrity_score == 1.0


# ---------------------------------------------------------------------------
# Duplicate keys (batin)
# ---------------------------------------------------------------------------


def test_duplicate_keys_fires(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.json", '{"admin": false, "admin": true}')
    report = _scan(p)
    assert "duplicate_keys" in _mechanisms(report)


def test_duplicate_keys_finding_is_batin(tmp_path: Path) -> None:
    p = _write(tmp_path, "a.json", '{"x": 1, "x": 2}')
    (f,) = [x for x in _scan(p).findings if x.mechanism == "duplicate_keys"]
    assert f.source_layer == "batin"
    assert f.tier == 2
    assert "'x'" in f.description


# ---------------------------------------------------------------------------
# Excessive nesting (batin)
# ---------------------------------------------------------------------------


def _nested(depth: int) -> str:
    p = "0"
    for _ in range(depth):
        p = "[" + p + "]"
    return p


def test_excessive_nesting_fires_above_threshold(tmp_path: Path) -> None:
    p = _write(tmp_path, "deep.json", _nested(40))
    assert "excessive_nesting" in _mechanisms(_scan(p))


def test_excessive_nesting_does_not_fire_at_small_depth(tmp_path: Path) -> None:
    p = _write(tmp_path, "shallow.json", _nested(5))
    assert "excessive_nesting" not in _mechanisms(_scan(p))


def test_excessive_nesting_finding_is_batin(tmp_path: Path) -> None:
    p = _write(tmp_path, "deep.json", _nested(40))
    (f,) = [
        x for x in _scan(p).findings if x.mechanism == "excessive_nesting"
    ]
    assert f.source_layer == "batin"


# ---------------------------------------------------------------------------
# Embedded zahir in string values
# ---------------------------------------------------------------------------


def test_zero_width_in_string_value(tmp_path: Path) -> None:
    payload = {"msg": "hi\u200bthere"}
    p = _write(tmp_path, "a.json", json.dumps(payload, ensure_ascii=False))
    mechs = _mechanisms(_scan(p))
    assert "zero_width_chars" in mechs


def test_tag_chars_in_string_value(tmp_path: Path) -> None:
    tag_payload = "".join(chr(0xE0000 + ord(c)) for c in "IGNORE")
    payload = {"instruction": "please help" + tag_payload}
    p = _write(tmp_path, "a.json", json.dumps(payload, ensure_ascii=False))
    mechs = _mechanisms(_scan(p))
    assert "tag_chars" in mechs


def test_embedded_string_finding_carries_json_pointer(tmp_path: Path) -> None:
    payload = {"key": "hi\u200bthere"}
    p = _write(tmp_path, "a.json", json.dumps(payload, ensure_ascii=False))
    (f,) = [x for x in _scan(p).findings if x.mechanism == "zero_width_chars"]
    assert "$.key" in f.location
    assert f.source_layer == "zahir"


def test_homoglyph_in_string_value(tmp_path: Path) -> None:
    payload = {"label": "\u0430dmin panel"}
    p = _write(tmp_path, "a.json", json.dumps(payload, ensure_ascii=False))
    assert "homoglyph" in _mechanisms(_scan(p))


def test_bidi_in_string_value(tmp_path: Path) -> None:
    payload = {"label": "user\u202Eadmin"}
    p = _write(tmp_path, "a.json", json.dumps(payload, ensure_ascii=False))
    assert "bidi_control" in _mechanisms(_scan(p))


# ---------------------------------------------------------------------------
# Nested container pointer paths
# ---------------------------------------------------------------------------


def test_string_pointer_into_nested_array(tmp_path: Path) -> None:
    payload = {"items": [{"name": "hi\u200bthere"}]}
    p = _write(tmp_path, "a.json", json.dumps(payload, ensure_ascii=False))
    (f,) = [x for x in _scan(p).findings if x.mechanism == "zero_width_chars"]
    assert "items" in f.location and "[0]" in f.location and "name" in f.location


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_malformed_json_returns_scan_error(tmp_path: Path) -> None:
    p = _write(tmp_path, "bad.json", "{not json at all")
    report = _scan(p)
    assert report.scan_incomplete
    assert report.error is not None
    assert report.error.startswith("JSON scan error")
    assert [f.mechanism for f in report.findings] == ["scan_error"]
    assert report.findings[0].source_layer == "batin"


def test_missing_file_returns_scan_error(tmp_path: Path) -> None:
    report = _scan(tmp_path / "nope.json")
    assert report.scan_incomplete
    assert report.error is not None
    assert "JSON scan error" in report.error


# ---------------------------------------------------------------------------
# Integration on Phase 9 fixtures
# ---------------------------------------------------------------------------


FIXTURE_ROOT = (
    Path(__file__).resolve().parents[1] / "fixtures" / "text_formats"
)


@pytest.mark.parametrize(
    "rel,expected",
    [
        ("clean/clean.json", []),
        ("adversarial/duplicate_keys.json", ["duplicate_keys"]),
        ("adversarial/excessive_nesting.json", ["excessive_nesting"]),
        ("adversarial/tag_in_json.json", ["tag_chars"]),
    ],
)
def test_fixture_fires_exactly_expected(rel: str, expected: list[str]) -> None:
    path = FIXTURE_ROOT / rel
    if not path.exists():
        pytest.skip(f"fixture {rel} not yet generated")
    observed = sorted({f.mechanism for f in _scan(path).findings})
    assert observed == sorted(expected), (
        f"{rel}: expected {expected}, got {observed}"
    )
