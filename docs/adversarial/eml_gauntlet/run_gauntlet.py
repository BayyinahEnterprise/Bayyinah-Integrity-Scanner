"""
Run the six DOCX hidden-text fixtures against either the local
``ScanService`` orchestrator or the live API at https://bayyinah.dev/scan
and capture the full structured response.

Usage:
    python run_gauntlet.py local   # in-process scan via ScanService
    python run_gauntlet.py live    # POST to https://bayyinah.dev/scan
    python run_gauntlet.py both    # run both, prints both summaries

Output: results_local.json / results_live.json (and a printable summary).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURES_DIR = HERE / "fixtures"
URL = "https://bayyinah.dev/scan"
RESOLVE = "bayyinah.dev:443:104.21.33.67"

# Add repo root to path so ScanService imports work in local mode.
REPO_ROOT = HERE.parents[2]
sys.path.insert(0, str(REPO_ROOT))


def scan_live(path: Path) -> dict:
    out = subprocess.check_output([
        "curl", "-s", "--resolve", RESOLVE,
        "-X", "POST", "-F", f"file=@{path}", URL,
    ])
    return json.loads(out)


def scan_local(path: Path) -> dict:
    """In-process scan via the orchestrator. No network."""
    from application.scan_service import ScanService

    svc = ScanService()
    report = svc.scan(path)
    # Convert the IntegrityReport dataclass to a dict identical in shape
    # to the API response.
    return _report_to_dict(report)


def _report_to_dict(report) -> dict:
    findings = []
    for f in report.findings:
        ir = getattr(f, "inversion_recovery", None) or {}
        if hasattr(ir, "__dict__"):
            ir_dict = {
                "surface": getattr(ir, "surface", None),
                "concealed": getattr(ir, "concealed", None),
            }
        elif isinstance(ir, dict):
            ir_dict = ir
        else:
            ir_dict = {"surface": getattr(f, "surface", None),
                       "concealed": getattr(f, "concealed", None)}
        findings.append({
            "mechanism": f.mechanism,
            "tier": f.tier,
            "confidence": f.confidence,
            "description": f.description,
            "location": f.location,
            "surface": getattr(f, "surface", None),
            "concealed": getattr(f, "concealed", None),
            "source_layer": getattr(f, "source_layer", None),
            "inversion_recovery": ir_dict,
        })
    return {
        "file_path": report.file_path,
        "integrity_score": report.integrity_score,
        "scan_incomplete": getattr(report, "scan_incomplete", False),
        "findings": findings,
    }


def summarise(name: str, data: dict) -> dict:
    score = data.get("integrity_score")
    incomplete = data.get("scan_incomplete")
    findings = data.get("findings", [])
    tier_counts = {1: 0, 2: 0, 3: 0}
    for f in findings:
        tier_counts[f.get("tier", 3)] = tier_counts.get(f.get("tier", 3), 0) + 1

    # The EML gauntlet recovers two payload shapes:
    #   * hidden-text payloads (fixtures 04 / 05 / 06) carry canonical
    #     ``HIDDEN_TEXT_PAYLOAD`` / ``actual revenue`` / ``$10,000`` markers
    #     - same recovery contract as DOCX / PDF / XLSX / HTML.
    #   * hidden-identity payloads (fixtures 01 / 02 / 03) carry an
    #     adversary-domain marker (``attacker-controlled.example``,
    #     ``attacker-bulk.example``, ``attacker.example``). The detector
    #     surfaces the concealed routing target as the payload string.
    HIDDEN_TEXT_MARKERS = ("HIDDEN_TEXT_PAYLOAD", "10,000", "actual revenue")
    HIDDEN_IDENTITY_MARKERS = (
        "attacker-controlled",
        "attacker-bulk",
        "attacker.example",
    )
    ALL_MARKERS = HIDDEN_TEXT_MARKERS + HIDDEN_IDENTITY_MARKERS

    payload_recovered = False
    payload_recovered_via = None
    for f in findings:
        ir = f.get("inversion_recovery") or {}
        concealed = (ir.get("concealed") or "")
        if any(m in concealed for m in ALL_MARKERS):
            payload_recovered = True
            payload_recovered_via = f.get("mechanism")
            break

    if not payload_recovered:
        for f in findings:
            blob = json.dumps(f)
            if any(m in blob for m in ALL_MARKERS):
                payload_recovered = True
                payload_recovered_via = (
                    f.get("mechanism", "?") + " (in description/location)"
                )
                break

    return {
        "fixture": name,
        "score": score,
        "scan_incomplete": incomplete,
        "n_findings": len(findings),
        "tier_counts": tier_counts,
        "mechanisms": sorted({f.get("mechanism", "?") for f in findings}),
        "payload_recovered": payload_recovered,
        "payload_recovered_via": payload_recovered_via,
    }


def run(mode: str) -> list[dict]:
    fixtures = sorted(
        f for f in os.listdir(FIXTURES_DIR) if f.endswith(".eml")
    )
    results = []
    scanner = scan_local if mode == "local" else scan_live
    for fixture in fixtures:
        path = FIXTURES_DIR / fixture
        print(f"==> [{mode}] scanning {fixture}", file=sys.stderr)
        try:
            data = scanner(path)
            summary = summarise(fixture, data)
            summary["raw"] = data
            results.append(summary)
        except Exception as e:
            results.append({"fixture": fixture, "error": str(e)})

    out_path = HERE / f"results_{mode}.json"
    out_path.write_text(json.dumps(results, indent=2))

    print(
        f"\n[{mode}]  {'Fixture':<38} {'Score':<7} {'Findings':<10} "
        f"{'T1/T2/T3':<10} {'Recovered?':<10}"
    )
    print("-" * 95)
    for r in results:
        if "error" in r:
            print(f"{r['fixture']:<38} ERROR: {r['error']}")
            continue
        tc = r["tier_counts"]
        tier_str = f"{tc.get(1,0)}/{tc.get(2,0)}/{tc.get(3,0)}"
        if r["payload_recovered"]:
            rec = f"YES ({r['payload_recovered_via']})"
        else:
            rec = "NO"
        print(
            f"        {r['fixture']:<38} {str(r['score']):<7} "
            f"{r['n_findings']:<10} {tier_str:<10} {rec}"
        )
    return results


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "local"
    if mode == "both":
        run("local")
        run("live")
    else:
        run(mode)


if __name__ == "__main__":
    main()
