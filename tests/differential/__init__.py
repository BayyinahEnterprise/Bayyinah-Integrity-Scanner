"""
Differential testing package (v1.8.0).

External-witness layer per docs/differential_testing.md.

Per CODING_STRATEGY §6 v1.8.0 + PARITY.md, modifications to
DifferentialWitness, WitnessFinding, or WitnessDivergence that break
contract pins in tests/contracts/ are regressions requiring the
parity-break ceremony.

The two-witnesses principle (al-Baqarah 2:282) applied to Bayyinah
itself: the existing fixture-pinning tests witness Bayyinah's own
behavior; differential pairs add an independent witness for the same
input fixture.
"""
