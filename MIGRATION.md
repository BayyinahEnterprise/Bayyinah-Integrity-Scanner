# Migration Notes

Bayyinah follows semver. Minor-version bumps may carry parity-break
ceremonies (per `PARITY.md`); each is documented in `CHANGELOG.md` under
a `Parity-break` heading and in `PARITY.md` "Parity-break ledger".

## v1.2.x -> v1.3.0

### tounicode_anomaly tier reclassification 1 -> 2

The `tounicode_anomaly` mechanism's tier classification changed from 1
(high-confidence concealment) to 2 (structural pattern with intent-
ambiguity) per the v1.3.0 PARITY-break ceremony. The mechanism's
detection logic is unchanged.

**Downstream impact:** consumers pinned to tier=1 for tounicode_anomaly
must update triage workflows to expect tier=2. Workflows partitioning
findings by tier route tounicode_anomaly to the tier-2 bucket starting
at v1.3.0.

**Reference scanners (`bayyinah_v0.py`, `bayyinah_v0_1.py`):** unchanged.
These continue emitting tier=1 for tounicode_anomaly. The modular
`bayyinah.scan_pdf` public API emits tier=2 starting at v1.3.0. The
asymmetric parity is admitted in `tests/test_integration.py` via the
documented `_v1_3_0_tounicode_tier_remap` remapper.

**Full rationale:** PARITY.md "Parity-break ledger" v1.3.0 entry.
