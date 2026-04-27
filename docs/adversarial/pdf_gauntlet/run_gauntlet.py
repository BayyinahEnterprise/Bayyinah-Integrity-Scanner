"""
Run the six PDF hidden-text fixtures against the live API and capture
the full structured response. Output: results.json + a printable summary.
"""
import json
import os
import subprocess
import sys

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__)) + "/fixtures"
RESULTS_PATH = os.path.dirname(os.path.abspath(__file__)) + "/results.json"
URL = "https://bayyinah.dev/scan"
RESOLVE = "bayyinah.dev:443:104.21.33.67"


def scan(path):
    out = subprocess.check_output([
        "curl", "-s", "--resolve", RESOLVE,
        "-X", "POST", "-F", f"file=@{path}", URL,
    ])
    return json.loads(out)


def summarise(name, data):
    score = data.get("integrity_score")
    incomplete = data.get("scan_incomplete")
    findings = data.get("findings", [])
    tier_counts = {1: 0, 2: 0, 3: 0}
    for f in findings:
        tier_counts[f.get("tier", 3)] += 1

    # Did any finding's inversion_recovery.concealed contain our payload?
    payload_recovered = False
    payload_recovered_via = None
    for f in findings:
        ir = f.get("inversion_recovery") or {}
        concealed = (ir.get("concealed") or "")
        if "HIDDEN_TEXT_PAYLOAD" in concealed or "10,000" in concealed:
            payload_recovered = True
            payload_recovered_via = f.get("mechanism")
            break

    # Or did any finding's location/description mention the payload?
    if not payload_recovered:
        for f in findings:
            blob = json.dumps(f)
            if "HIDDEN_TEXT_PAYLOAD" in blob or "actual revenue" in blob:
                payload_recovered = True
                payload_recovered_via = f.get("mechanism") + " (in description/location)"
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


def main():
    fixtures = sorted(os.listdir(FIXTURES_DIR))
    fixtures = [f for f in fixtures if f.endswith(".pdf")]
    results = []
    for fixture in fixtures:
        path = f"{FIXTURES_DIR}/{fixture}"
        print(f"==> scanning {fixture}", file=sys.stderr)
        try:
            data = scan(path)
            summary = summarise(fixture, data)
            summary["raw"] = data
            results.append(summary)
        except Exception as e:
            results.append({"fixture": fixture, "error": str(e)})

    with open(RESULTS_PATH, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n{'Fixture':<40} {'Score':<7} {'Findings':<10} {'Tier 1/2/3':<12} {'Recovered?':<10}")
    print("-" * 95)
    for r in results:
        if "error" in r:
            print(f"{r['fixture']:<40} ERROR: {r['error']}")
            continue
        tc = r["tier_counts"]
        tier_str = f"{tc[1]}/{tc[2]}/{tc[3]}"
        rec = "YES (" + (r["payload_recovered_via"] or "") + ")" if r["payload_recovered"] else "NO"
        print(f"{r['fixture']:<40} {r['score']:<7} {r['n_findings']:<10} {tier_str:<12} {rec}")


if __name__ == "__main__":
    main()
