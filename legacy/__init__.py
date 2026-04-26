"""
bayyinah.legacy — pointers to the frozen reference implementations.

Bayyinah preserves two complete prior implementations of the PDF scanner
for reproducibility and byte-identical parity testing:

* ``bayyinah_v0``    — the original monolithic scanner (v0).
* ``bayyinah_v0_1``  — the fat-split intermediate (v0.1).

These modules ship unchanged at the top level of the distribution
(``bayyinah_v0.py`` and ``bayyinah_v0_1.py``). Their bytes are
md5-fingerprinted and the fingerprints are asserted in CI after every
push — the ``additive-only`` invariant of the project. The refactored
scanner at ``bayyinah.scan_pdf`` is byte-identical to
``bayyinah_v0.scan_pdf`` on every Phase 0 fixture; this guarantee is
what keeps the 1.0 release honest.

This package exists as an organisational pointer. The reference modules
*must* remain importable at their original top-level names for parity
CI and for any downstream caller that pinned to those paths — so they
are not physically moved. ``legacy.bayyinah_v0`` and
``legacy.bayyinah_v0_1`` are provided as additive aliases for readers
who prefer the conceptual grouping.

Usage::

    # Canonical — unchanged since v0:
    import bayyinah_v0
    bayyinah_v0.scan_pdf("file.pdf")

    # Conceptual alias (added in 1.0 for organisational clarity):
    from bayyinah.legacy import bayyinah_v0
    bayyinah_v0.scan_pdf("file.pdf")

Both resolve to the same module object.

Reference: Al-Baqarah 2:143 — the middle community as uniform witness.
The v0 / v0.1 modules are the preserved witnesses against which every
later refactor has been measured.
"""

from __future__ import annotations

# Re-export both reference modules at their conceptual location.
# These ``import`` statements bind ``legacy.bayyinah_v0`` and
# ``legacy.bayyinah_v0_1`` as attributes of this package without
# copying or shadowing the original top-level modules.
import bayyinah_v0  # noqa: F401 — public re-export
import bayyinah_v0_1  # noqa: F401 — public re-export


__all__ = [
    "bayyinah_v0",
    "bayyinah_v0_1",
]
