# `legacy/` — Frozen Reference Implementations

This directory is an organisational pointer to the two historical
implementations of the Bayyinah PDF scanner that the project preserves
unchanged. The actual module files live at the repository root for
import-path compatibility:

| Module | Role | Location | MD5 (CI-enforced) |
|--------|------|----------|-------------------|
| `bayyinah_v0`    | Original monolithic scanner | `/bayyinah_v0.py`    | `87ba2ea48800ef616b303a25b01373d8` |
| `bayyinah_v0_1`  | Fat-split intermediate      | `/bayyinah_v0_1.py`  | `035aa578de7470c9465922bee2632cd5` |

## Why they live at the repository root, not here

Two reasons, both load-bearing:

1. **Additive-only invariant.** Any downstream caller that pinned to
   `import bayyinah_v0` (including the project's own CI parity sweep)
   must continue to resolve without changes. Physically moving the
   files under `legacy/` would rename `bayyinah_v0` → `legacy.bayyinah_v0`
   for that caller — a breaking change that violates the project's
   additive-only contract. The files therefore stay at the top level.

2. **Byte-identical fingerprinting.** CI asserts the md5 of each file
   on every push (see `.github/workflows/ci.yml`, "Verify v0 / v0.1
   reference modules unchanged"). The fingerprints above are the
   witness that the reference implementations have not drifted. Moving
   the files would change the asserted paths; keeping them in place
   keeps the invariant trivially checkable.

## What `legacy/__init__.py` provides

An additive import alias, so readers who prefer the conceptual grouping
can write:

```python
from bayyinah.legacy import bayyinah_v0
bayyinah_v0.scan_pdf("file.pdf")
```

…and get back exactly the same module object as the direct
`import bayyinah_v0`. Nothing is copied or shadowed; the `legacy`
package simply re-exports the top-level modules at a more conceptually
organised location.

## The parity guarantee

The refactored 1.0 scanner at `bayyinah.scan_pdf` is byte-identical to
`bayyinah_v0.scan_pdf` on every Phase 0 fixture — same findings, same
score, same error string, same `scan_incomplete` flag. This is the
central honesty of the project: three independent implementations
(monolith, fat-split, modular) producing identical results, measured
on every push by the CI parity sweep.

The reference modules in this conceptual `legacy/` directory are what
keep that guarantee auditable. If they ever drifted, the refactor's
claim to faithfulness would drift with them.

*"And thus We have made you a middle community, that you might be
witnesses over the people."* — Al-Baqarah 2:143
