#!/usr/bin/env python3
"""
Post-deploy verification for v1.1.4 on bayyinah.dev.

Usage (from any directory):
    python3 benchmarks/verify_v1_1_4_deploy.py

Probes:
    - GET /version: must return {"version": "1.1.4"}.
    - GET /healthz: must return {"status": "ok"}.

Exits 0 on all-green, 1 on any failure. Run after the Railway
deploy completes; do not run before merge.

Network access required. The script uses subprocess curl to keep
the dependency footprint at zero (no requests, no httpx). If
bayyinah.dev is unreachable the script prints the curl error and
exits 1.
"""
from __future__ import annotations

import json
import subprocess
import sys

EXPECTED_VERSION = "1.1.4"
EXPECTED_HEALTH = "ok"
TIMEOUT_S = 15

CHECKS: list[tuple[str, str]] = [
    ("Version", f"curl --max-time {TIMEOUT_S} -fsSL https://bayyinah.dev/version"),
    ("Health", f"curl --max-time {TIMEOUT_S} -fsSL https://bayyinah.dev/healthz"),
]


def run_check(name: str, cmd: str) -> tuple[bool, dict | str]:
    """Run cmd, parse JSON, return (ok, parsed-or-error-string)."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=TIMEOUT_S + 2
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {TIMEOUT_S}s"
    if result.returncode != 0:
        return False, f"curl failed (exit {result.returncode}): {result.stderr.strip()}"
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        return False, f"non-JSON response: {exc}; body: {result.stdout[:200]!r}"
    return True, data


def main() -> int:
    all_ok = True
    print("=" * 56)
    print("v1.1.4 post-deploy verification on bayyinah.dev")
    print("=" * 56)

    for name, cmd in CHECKS:
        ok, payload = run_check(name, cmd)
        if not ok:
            print(f"{name}: FAIL ({payload})")
            all_ok = False
            continue

        print(f"{name}: {payload}")

        if name == "Version":
            actual = payload.get("version") if isinstance(payload, dict) else None
            if actual != EXPECTED_VERSION:
                print(
                    f"  FAIL: expected version {EXPECTED_VERSION!r}, "
                    f"got {actual!r}"
                )
                all_ok = False

        if name == "Health":
            actual = payload.get("status") if isinstance(payload, dict) else None
            if actual != EXPECTED_HEALTH:
                print(
                    f"  FAIL: expected status {EXPECTED_HEALTH!r}, "
                    f"got {actual!r}"
                )
                all_ok = False

    print("=" * 56)
    if all_ok:
        print("All checks passed. v1.1.4 is live on bayyinah.dev.")
        return 0
    print("One or more checks failed. Investigate before announcing the ship.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
