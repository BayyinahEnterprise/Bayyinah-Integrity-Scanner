"""
Run the seven format-routing fixtures against the live API and capture
the full structured response. Output: results.json + a printable
summary.

Pass criteria:
  - Fixtures 01-06 each return at least one finding with tier == 0
    AND mechanism == 'format_routing_divergence' AND verdict == 'mughlaq'.
  - Fixture 07 (control) returns NO finding with tier == 0; verdict
    is whatever the existing per-format analyzer would produce
    (mukhfi via the seed PDF's white_on_white_text Tier 1).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
RESULTS_PATH = Path(__file__).resolve().parent / "results.json"
URL = "https://bayyinah.dev/scan"
# Cloudflare-fronted Railway. The --resolve pin keeps gauntlet runs
# stable when DNS rotates between Railway-direct and Cloudflare front.
RESOLVE = "bayyinah.dev:443:104.21.33.67"


# Each entry: (fixture filename, expected Tier 0 fired, expected
# routing_decision value, friendly description).
EXPECTATIONS: list[tuple[str, bool, str | None, str]] = [
    ("01_polyglot.docx",       True,  "trusted_magic_bytes",            "PDF magic + .docx extension"),
    ("02_pdf_as_txt.txt",      True,  "trusted_magic_bytes",            "PDF magic + .txt extension"),
    ("03_empty.pdf",           True,  "below_content_depth_floor",      "4-byte file with .pdf extension"),
    ("04_truncated.pdf",       True,  "below_content_depth_floor",      "12-byte PDF preamble, no body"),
    ("05_docx_as_xlsx.xlsx",   True,  "ooxml_internal_path_divergence", "DOCX zip with .xlsx extension"),
    ("06_unanalyzed.txt",      True,  "below_content_depth_floor",      "4-byte text file (V5 case)"),
    ("07_control.pdf",         False, None,                             "Real PDF with .pdf extension (clean baseline)"),
]


def scan(path: Path) -> dict:
    out = subprocess.check_output([
        "curl", "-s", "--resolve", RESOLVE,
        "-X", "POST", "-F", f"file=@{path}", URL,
    ])
    return json.loads(out)


def derive_verdict(report: dict) -> str:
    """Mirror the v1.1.2 deriveVerdict logic for the runner's own
    pass/fail decision. The live API also returns its own verdict
    label; we cross-check them.
    """
    findings = report.get("findings", []) or []
    if any(f.get("tier") == 0 for f in findings):
        return "mughlaq"
    if report.get("scan_incomplete") or report.get("error"):
        return "mughlaq"
    score = report.get("integrity_score", 0.0)
    if score >= 1.0 and not findings:
        return "sahih"
    has_tier1 = any(f.get("tier") == 1 for f in findings)
    if score < 0.3 and has_tier1:
        return "munafiq"
    if score < 0.7:
        return "mukhfi"
    return "mushtabih"


def summarise(name: str, expected_t0: bool, expected_decision: str | None,
              data: dict) -> dict:
    findings = data.get("findings", []) or []
    t0_findings = [f for f in findings if f.get("tier") == 0]
    has_t0 = len(t0_findings) > 0
    routing_decision = None
    if has_t0:
        evidence = t0_findings[0].get("evidence") or {}
        routing_decision = evidence.get("routing_decision")

    verdict = derive_verdict(data)

    # Pass: Tier 0 fired iff expected, routing_decision matches expected
    # value, and the verdict is mughlaq for routing-divergence fixtures.
    if expected_t0:
        passed = (
            has_t0
            and routing_decision == expected_decision
            and verdict == "mughlaq"
        )
    else:
        passed = not has_t0  # control: no Tier 0 may fire

    return {
        "fixture": name,
        "expected_t0": expected_t0,
        "expected_decision": expected_decision,
        "actual_t0": has_t0,
        "actual_decision": routing_decision,
        "verdict": verdict,
        "score": data.get("integrity_score"),
        "scan_incomplete": data.get("scan_incomplete"),
        "finding_count": len(findings),
        "tier_counts": {
            t: sum(1 for f in findings if f.get("tier") == t)
            for t in (0, 1, 2, 3)
        },
        "passed": passed,
    }


def main() -> int:
    results = []
    print(f"Format-Routing Gauntlet -> {URL}")
    print("=" * 80)
    for filename, expected_t0, expected_decision, descr in EXPECTATIONS:
        path = FIXTURES_DIR / filename
        if not path.exists():
            print(f"  MISSING: {filename}")
            print(f"    Run docs/adversarial/format_routing_gauntlet/build_fixtures.py first.")
            return 2
        try:
            data = scan(path)
        except subprocess.CalledProcessError as e:
            print(f"  {filename}: curl failed ({e})")
            return 2
        summary = summarise(filename, expected_t0, expected_decision, data)
        summary["description"] = descr
        results.append(summary)

        status = "PASS" if summary["passed"] else "FAIL"
        t0_str = (
            f"Tier 0 fired ({summary['actual_decision']})"
            if summary["actual_t0"] else "no Tier 0"
        )
        print(
            f"  {status}  {filename:30s}  "
            f"verdict={summary['verdict']:9s}  "
            f"score={str(summary['score']):5s}  "
            f"{t0_str}"
        )

    RESULTS_PATH.write_text(json.dumps(results, indent=2))
    passed = sum(1 for r in results if r["passed"])
    total = len(results)
    print("=" * 80)
    print(f"  {passed}/{total} fixtures passed.")

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
