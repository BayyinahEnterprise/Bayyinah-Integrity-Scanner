# Week-1 Assessment Response

This note records which issues from the Week-1 assessment were applied to produce this unified folder, which were declined, and why.

## Applied fixes

### I1 — Repository contained 7 duplicate codebase copies *(resolved)*

The assessment listed: top-level, `Bayyinah_Final/`, `Bayyinah V1.0 Complete/`, `Bayyinah V1.0 Completed/`, `Bayyinah V1.0 Refinement/`, `bayyinah-1.0.0/`, `Bayyinah_Final/bayyinah-1.0.0/`, plus 8 nested `.zip` files — totalling 242,874 lines of Python for only ~16,575 unique source lines.

**Resolution:** This folder (`Bayyinah V1.0/`) is now the single canonical source. It was rsynced from the refined `Bayyinah_Final/` state with the following excludes applied during copy: `__pycache__`, `*.pyc`, `*.egg-info`, `.pytest_cache`, `.mypy_cache`, `.ruff_cache`, `.DS_Store`, `__MACOSX`, `build/`, `bayyinah-1.0.0/`, `UNKNOWN.egg-info`. The older sibling folders (`Bayyinah V1.0 Complete/`, `Completed/`, `Refinement/`, `Bayyinah_Final/`) remain in the parent directory for the user to delete via Finder — the sandbox's FUSE mount blocks recursive deletion of files it did not create. They contain no unique source not already present here.

### I3 — Missing `scan_file()` public API *(added)*

**Before:** `bayyinah/__init__.py` exposed only `scan_pdf()` as the public convenience entry point, even though the scanner has handled 12 formats via `FileRouter` + `ScanService` since Phase 9.

**After:** `bayyinah/__init__.py` now defines and exports `scan_file(file_path: Path | str) -> IntegrityReport`. It is a format-agnostic entry point: hand it any supported file and it dispatches through the default `ScanService`, which routes via `FileRouter` to the correct analyzer set for the detected `FileKind`. Unknown formats fall through to `FallbackAnalyzer` rather than passing silent-clean. `scan_pdf()` is preserved as a backward-compatible alias; both functions delegate to the same `ScanService.scan()` internally.

**Exported as part of the additive-only public surface.** The CI workflow's required-symbol gate now includes `scan_file` — removal would fail CI.

**Tests:** `tests/test_scan_file_public_api.py` pins the new surface with six tests covering export, `__all__` membership, PDF-input parity with `scan_pdf`, non-PDF dispatch, string-path acceptance, and `unknown_format` fall-through.

### I4 — CLI help text said "PDF supported today" *(updated)*

**Before:** `cli/main.py:122` — `help="path to the document to scan (PDF supported today)"`.

**After:** Lists all 12 supported formats and notes that anything else surfaces an `unknown_format` finding via `FallbackAnalyzer`. The help text is now an accurate description of the scanner's surface.

### I5 — `UNKNOWN.egg-info` in top-level *(excluded)*

The stray `UNKNOWN.egg-info/` from a pre-`pyproject.toml` build is not present in this folder. Explicitly excluded in the rsync.

### I6 — `.DS_Store` files and `__MACOSX` directories *(cleaned)*

All `.DS_Store` and `__MACOSX` entries excluded during assembly. The `.gitignore` already contains `.DS_Store` (and `.AppleDouble` / `.LSOverride`) — no change needed there. Before a GitHub push, the user can run `find . -name '.DS_Store' -delete` at the repo root for belt-and-braces, but this folder ships clean.

## Not auto-applied (flagged for maintainer)

### I2 — "Top-level (1,283 tests) vs Bayyinah_Final (1,295 tests)" divergence *(resolved by selection, not merge)*

The top-level at the `Bayyinah/` workspace root was an orphaned intermediate with the older `pdf_path` signature. It is not copied into this unified folder. The canonical source is the post-Phase-22+23 state (with `file_path` rename, kwarg compat shim, polish docstrings). No merging was needed — the correct version was selected outright.

### I7 — April 21 tests didn't collect under modular `testpaths` *(informational, not a bug)*

The April 21 snapshot represents the pre-modular era (the monolithic `bayyinah_v0.py` and fat-split `bayyinah_v0_1.py` stage). Those two files are preserved here as byte-frozen reference modules at the repo root. They are not tested in isolation by the pytest harness — they are tested indirectly through the CI parity sweep, which asserts that `bayyinah.scan_pdf(f) == bayyinah_v0.scan_pdf(f)` for every Phase 0 fixture. That is the correct regression surface for frozen legacy code. The assessment's observation is accurate; no remediation needed.

### TOOL_VERSION drift *(flagged previously, still open)*

Noted in the earlier enforcement-mode review: `domain/config.py` declares `TOOL_VERSION = "0.1.0"` while `pyproject.toml` / `bayyinah.__version__` declare `1.0.0`. The test `tests/domain/test_config.py:70` pins the `"0.1.0"` value. This is either an intentional pin of the report-format generation to the byte-identical-v0.1 semantic surface, or an oversight. Per the enforcement-review principle M2 ("when in doubt, refuse to interpret"), this is not auto-resolved. Maintainer decision required.

## Verification after I3 + I4

- **Test suite:** 1,301 passed in 9.25s (1,295 baseline + 6 new `scan_file` tests).
- **PDF parity:** OK across 17 Phase 0 fixtures — `bayyinah.scan_pdf` byte-identical to `bayyinah_v0.scan_pdf`.
- **Additive-only public surface:** 54 required symbols present, 54 exported via `bayyinah.__all__`. `scan_file` added without removing anything.
- **Reference MD5s:** `bayyinah_v0.py` = `87ba2ea4…` ✓, `bayyinah_v0_1.py` = `035aa578…` ✓ — byte-identical to 1.0 baseline.
- **Wheel:** `dist/bayyinah-1.0.0-py3-none-any.whl` rebuilt from polished source — 268,515 bytes, contains `scan_file` in `bayyinah/__init__.py` and `__all__`.

*Bismillah ar-Rahman ar-Raheem. Al-hamdu lillah.*
