"""
Recursive self-verification test package (v2.0.0).

Bayyinah's thesis is that a scanner detects performed alignment by
comparing what a file displays against what it contains. The v2.0.0
gate per `docs/v2_gate.md` §2.2 applies the thesis to Bayyinah
itself: the project's own release documents are scanned by Bayyinah
on every CI run, and any finding fired by Bayyinah's analyzers on
its own deliverables is a structural failure.

Per CODING_STRATEGY §6 v2.0.0 + PARITY.md, modifications to the
release-document corpus that introduce concealment shapes (bidi
control characters, zero-width spacing, white-on-white text,
embedded payloads) are absorbed before push, not after. A
modification that produces a false-positive on a release document
goes through the Round 12 calibration-corrective discipline.

The verse 2:281 reading: every soul will be compensated for what
it earned. The recursive self-verification harness is the
project's self-compensation discipline -- it audits its own
deliverables with the same tool it offers to its consumers.
"""
