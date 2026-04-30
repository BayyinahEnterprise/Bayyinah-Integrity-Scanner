"""
AnalyzerRegistry — the composer that turns per-analyzer reports into
one document-level IntegrityReport.

The registry is the operational consequence of the middle-community
contract (Al-Baqarah 2:143, see ``analyzers/base.py``): every registered
analyzer applies the same standard, and their outputs are composed
uniformly. No analyzer is given special weight, no analyzer's errors
are suppressed, no analyzer is allowed to overwrite another's findings.

Responsibilities:

    register       — accept an analyzer class, key it by its .name,
                     reject collisions
    unregister     — remove a class by name
    get / names    — inspection surface for tests and callers
    instantiate_all— realise one instance per registered class
    scan_all       — run every analyzer on ``file_path`` and compose
                     their IntegrityReports into a single merged
                     IntegrityReport

Composition rules (preserve v0.1 byte-identical behaviour where
applicable):

    findings       — concatenated in registration order (== v0's text
                     findings first, then object findings, when wired
                     through this way)
    error          — semicolon-joined ("A; B") across analyzer errors
                     and any exceptions raised mid-scan. Matches v0.1's
                     format for the common two-analyzer case
                     ("Text layer scan error: X; Object layer scan error: Y")
    integrity_score— recomputed via compute_muwazana_score over the
                     merged findings list (NOT averaged across analyzer
                     scores)
    scan_incomplete— True if (a) the file could not be opened, (b) any
                     analyzer raised, (c) any analyzer reported
                     scan_incomplete, or (d) the merged findings list
                     contains a scan_error finding. The integrity_score
                     is then clamped to SCAN_INCOMPLETE_CLAMP (0.5).

This is additive-only. It does not replace v0.1's ScanService; the two
compose differently (ScanService uses PDFContext and list[Finding],
the registry uses file_path and IntegrityReport). They coexist until a
later phase migrates the default pipeline onto the registry.
"""

from __future__ import annotations

import ast
import inspect
from functools import lru_cache
from pathlib import Path
from typing import Callable, Iterable

from analyzers.base import BaseAnalyzer
from domain import (
    BayyinahError,
    IntegrityReport,
    apply_scan_incomplete_clamp,
    compute_muwazana_score,
)
from domain.cost_classes import MECHANISM_COST_CLASS, CostClass
from infrastructure.file_router import FileKind


# ---------------------------------------------------------------------------
# v1.1.6 - Cost-class-aware production-mode ordering.
# ---------------------------------------------------------------------------
#
# Each registered analyzer has a "primary cost class" derived from the
# mechanisms its module (and one-hop sibling helpers it imports) emits.
# The primary class is the MAX over all emitted mechanisms because that
# is the worst-case cost we pay if we run the analyzer to completion.
# Production mode dispatches analyzers in (A, B, C, D) order, preserving
# registration order within each class. After each analyzer completes,
# if the merged report contains any Tier 1 finding at confidence >= 0.9,
# the loop exits without invoking later analyzers.
#
# Forensic mode (the default) is unchanged: every analyzer runs in
# registration order, regardless of earlier findings. Byte-parity with
# the pre-v1.1.6 test suite depends on this default.

_COST_CLASS_ORDER: dict[CostClass, int] = {
    CostClass.A: 0,
    CostClass.B: 1,
    CostClass.C: 2,
    CostClass.D: 3,
}


def _mechanisms_in_module(module_path: Path) -> set[str]:
    """Extract every mechanism string literal from a module via AST.

    Catches both ``Finding(mechanism="x")`` keyword arguments and
    ``{"mechanism": "x"}`` dict-style construction.
    """
    src = module_path.read_text()
    tree = ast.parse(src)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if (
                    kw.arg == "mechanism"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    found.add(kw.value.value)
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if (
                    isinstance(k, ast.Constant)
                    and k.value == "mechanism"
                    and isinstance(v, ast.Constant)
                    and isinstance(v.value, str)
                ):
                    found.add(v.value)
    return found


def _transitive_analyzer_imports(module_path: Path) -> set[Path]:
    """Return module_path plus every analyzers/*.py module it imports.

    One hop is sufficient: the dispatch pattern is that a top-level
    analyzer module imports detector helpers from sibling modules in
    analyzers/, and those helpers do not chain further (verified by
    spot-check at v1.1.6 design time).
    """
    result = {module_path}
    src = module_path.read_text()
    tree = ast.parse(src)
    analyzers_dir = module_path.parent
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("analyzers."):
                stem = node.module.split(".", 1)[1]
                cand = analyzers_dir / f"{stem}.py"
                if cand.exists():
                    result.add(cand)
    return result


@lru_cache(maxsize=None)
def _analyzer_primary_cost_class(
    analyzer_cls: type[BaseAnalyzer],
) -> CostClass:
    """Return the primary (worst-case) cost class for an analyzer class.

    Resolution order:

    1. If the class declares a ``primary_cost_class`` ClassVar, that
       value is used directly. Tests and analyzers whose source
       module cannot be reliably introspected (e.g. those defined
       inside a test module that registers many analyzers) use this
       opt-in path. Production analyzers inherit the AST-walked
       default and do not need the override.

    2. Otherwise the class is resolved by walking the AST of its
       source module plus any one-hop ``analyzers.*`` imports. The
       primary class is the MAX over the cost classes of every
       emitted mechanism, because that is the worst-case cost we
       pay if we run the analyzer to completion.

    3. Fallback: ``CostClass.D``. Pessimistic by design so an
       unrecognized analyzer runs LAST in production mode, never
       first; an unmapped analyzer cannot accidentally short-circuit
       ahead of a known cheap one.

    Cached because the result is purely a function of the class
    object, which is constant across a process lifetime.
    """
    declared = getattr(analyzer_cls, "primary_cost_class", None)
    if isinstance(declared, CostClass):
        return declared

    try:
        path = Path(inspect.getfile(analyzer_cls))
    except (TypeError, OSError):
        return CostClass.D

    modules = _transitive_analyzer_imports(path)
    mechs: set[str] = set()
    for m in modules:
        mechs |= _mechanisms_in_module(m)
    classes = [
        MECHANISM_COST_CLASS[m] for m in mechs if m in MECHANISM_COST_CLASS
    ]
    if not classes:
        return CostClass.D
    return max(classes, key=lambda c: _COST_CLASS_ORDER[c])


def _is_terminal_finding(finding) -> bool:  # type: ignore[no-untyped-def]
    """Return True if ``finding`` is a Tier 1 finding at confidence >= 0.9.

    A Tier 1 finding at high confidence is "verified concealment" per
    the tier legend. Once one is in the merged report, no later
    analyzer can change the verdict; production mode is permitted to
    skip them. Bookkeeping findings (scan_error, scan_limited) are
    Tier 3 and never satisfy this predicate.
    """
    return getattr(finding, "tier", None) == 1 and (
        float(getattr(finding, "confidence", 0.0)) >= 0.9
    )


# ---------------------------------------------------------------------------
# Registry-specific exceptions
# ---------------------------------------------------------------------------

class AnalyzerRegistrationError(BayyinahError):
    """Raised when a registration attempt violates a registry invariant.

    Examples: registering a class that is not a BaseAnalyzer subclass;
    registering a class whose .name is empty; registering a class whose
    .name collides with one already registered.
    """


# ---------------------------------------------------------------------------
# AnalyzerRegistry
# ---------------------------------------------------------------------------

class AnalyzerRegistry:
    """Composes one or more BaseAnalyzer subclasses into a unified scan.

    Instances are independent — there is no global registry. Tests and
    callers construct their own as needed, which also keeps parallel
    test runs from colliding.
    """

    def __init__(self) -> None:
        # Registration order matters: ``scan_all`` invokes analyzers in
        # the order they were registered, and the merged findings list
        # reflects that order. ``dict`` preserves insertion order as of
        # Python 3.7, which is sufficient.
        self._registry: dict[str, type[BaseAnalyzer]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        analyzer_cls: type[BaseAnalyzer],
    ) -> type[BaseAnalyzer]:
        """Register an analyzer class by its ``.name``.

        Returns the class so this method can also be used as a
        decorator:

            registry = AnalyzerRegistry()

            @registry.register
            class MyAnalyzer(BaseAnalyzer):
                name = "my_analyzer"
                source_layer = "zahir"
                error_prefix = "My analyzer error"
                def scan(self, file_path):
                    return self._empty_report(file_path)

        Raises ``AnalyzerRegistrationError`` if the argument is not a
        BaseAnalyzer subclass, has an empty name, or collides with a
        name already registered on this instance.
        """
        if not isinstance(analyzer_cls, type) or not issubclass(analyzer_cls, BaseAnalyzer):
            raise AnalyzerRegistrationError(
                f"register() expects a BaseAnalyzer subclass; "
                f"got {analyzer_cls!r}"
            )
        name = analyzer_cls.name
        if not isinstance(name, str) or not name:
            raise AnalyzerRegistrationError(
                f"Analyzer class {analyzer_cls.__name__} has empty .name; "
                "cannot register."
            )
        if name in self._registry:
            existing = self._registry[name].__name__
            raise AnalyzerRegistrationError(
                f"Analyzer name {name!r} is already registered to "
                f"{existing}; refusing to overwrite."
            )
        self._registry[name] = analyzer_cls
        return analyzer_cls

    def unregister(self, name: str) -> None:
        """Remove the class registered under ``name``. No-op if not present."""
        self._registry.pop(name, None)

    def clear(self) -> None:
        """Remove every registered analyzer. Primarily for tests."""
        self._registry.clear()

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get(self, name: str) -> type[BaseAnalyzer]:
        """Look up a registered analyzer class by name.

        Raises ``KeyError`` if the name is not registered.
        """
        if name not in self._registry:
            raise KeyError(
                f"No analyzer registered under {name!r}. "
                f"Registered: {list(self._registry)}"
            )
        return self._registry[name]

    def names(self) -> list[str]:
        """Names of every registered analyzer, in registration order."""
        return list(self._registry.keys())

    def classes(self) -> list[type[BaseAnalyzer]]:
        """Registered analyzer classes, in registration order."""
        return list(self._registry.values())

    def __len__(self) -> int:
        return len(self._registry)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._registry

    def __iter__(self) -> Iterable[str]:
        return iter(self._registry)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def instantiate_all(self) -> list[BaseAnalyzer]:
        """One instance per registered class, in registration order.

        Each class's ``__init__`` is called with no arguments, matching
        the ``BaseAnalyzer`` contract. Subclasses that require
        constructor parameters should expose them as keyword arguments
        with defaults, or be instantiated externally and composed via
        a separate scan_all-equivalent helper.
        """
        return [cls() for cls in self._registry.values()]

    def _sorted_for_production(self) -> list[type[BaseAnalyzer]]:
        """Return registered classes ordered by primary cost class.

        Order: Class A first, then B, then C, then D. Within each
        class the original registration order is preserved (Python's
        ``sorted`` is stable). The intent is that production mode
        runs cheap analyzers first so an early Tier 1 finding can
        skip the expensive ones.

        v1.1.6: this method is read-only and pure; calling it does
        not mutate the registry. Forensic mode never calls it.
        """
        # Stable sort over the registration-order list.
        return sorted(
            self._registry.values(),
            key=lambda cls: _COST_CLASS_ORDER[
                _analyzer_primary_cost_class(cls)
            ],
        )

    def scan_all(
        self,
        file_path: Path,
        kind: FileKind | None = None,
        mode: str = "forensic",
    ) -> IntegrityReport:
        """Compose every registered analyzer's report into one.

        This is the public entry point the registry exposes for
        document-level scanning. Semantics:

            1. If ``file_path`` does not exist, short-circuit with a
               scan_incomplete report and score 0.0 — matches v0/v0.1
               behaviour for missing files.
            2. If ``kind`` is given (Phase 9), filter analyzers to those
               whose ``supported_kinds`` includes it. When ``kind`` is
               ``None`` every analyzer runs — this is the legacy
               pre-Phase-9 behaviour and keeps v0.1-parity call sites
               byte-identical (the PDF registry contains only PDF-kind
               analyzers, so filter-or-not produces the same set).
            3. Instantiate and run every matching analyzer. Each
               analyzer returns its own IntegrityReport.
            4. Concatenate findings in registration order.
            5. Collect errors: per-analyzer ``report.error`` values and
               the text of any unexpected exception, joined with "; ".
            6. Recompute the merged integrity score via
               ``compute_muwazana_score``.
            7. Set ``scan_incomplete`` if ANY of (error present,
               per-analyzer scan_incomplete, scan_error finding in the
               merged list) is true. Apply the
               ``SCAN_INCOMPLETE_CLAMP`` (0.5) when so.

        v1.1.6 - mode parameter
        -----------------------
        ``mode="forensic"`` (the default) runs every applicable
        analyzer in registration order, regardless of earlier
        findings. Byte-parity with the existing test suite depends
        on this default.

        ``mode="production"`` runs analyzers in cost-class order
        (A first, then B, C, D) and exits the loop after the first
        analyzer whose findings include a Tier 1 finding at
        confidence >= 0.9. Determinism: the same input produces the
        same merged Tier 1 verdict regardless of class ordering,
        because each cost class entry in ``MECHANISM_COST_CLASS`` is
        an independent contract: no class-D mechanism is structurally
        required to confirm a class-A verdict. See
        ``docs/adr/ADR-003-v1_1_6-registry-shortcircuit.md``.
        """
        if mode not in ("production", "forensic"):
            raise ValueError(
                f"AnalyzerRegistry.scan_all() mode must be 'production' "
                f"or 'forensic'; got {mode!r}."
            )

        merged = IntegrityReport(file_path=str(file_path), integrity_score=1.0)

        if not file_path.exists():
            merged.error = f"File not found: {file_path}"
            merged.integrity_score = 0.0
            merged.scan_incomplete = True
            return merged

        errors: list[str] = []
        any_incomplete = False

        # v1.1.6 - dispatch order.
        # Forensic mode: registration order (legacy behaviour).
        # Production mode: cost-class-A-first, stable within each class.
        if mode == "production":
            classes_in_order = self._sorted_for_production()
            analyzers = [cls() for cls in classes_in_order]
        else:
            analyzers = self.instantiate_all()

        terminated_early = False
        for analyzer in analyzers:
            # Phase 9 — kind-based routing. An analyzer that does not
            # declare support for this file's kind is skipped entirely
            # (no findings, no error). Without a kind argument the
            # registry runs every analyzer, preserving legacy semantics.
            if kind is not None and kind not in analyzer.supported_kinds:
                continue
            try:
                sub = analyzer.scan(file_path)
            except Exception as exc:  # noqa: BLE001 — deliberately broad
                # Unexpected analyzer failure: preserve v0.1's format
                # "<prefix>: <exception text>" and continue with the
                # remaining analyzers. We do NOT propagate — the
                # middle-community contract requires that one witness
                # failing does not silence the others.
                errors.append(f"{analyzer.error_prefix}: {exc}")
                any_incomplete = True
                continue

            # Concatenate findings preserving order.
            merged.findings.extend(sub.findings)

            if sub.error is not None:
                errors.append(sub.error)
            if sub.scan_incomplete:
                any_incomplete = True

            # v1.1.6 - production-mode short-circuit.
            # After this analyzer's findings have been merged, check
            # whether any Tier 1 finding at confidence >= 0.9 is now
            # present. If so, no later analyzer can change the
            # verdict; exit the dispatch loop and let the merge,
            # error-join, and clamp logic below run normally.
            if mode == "production" and any(
                _is_terminal_finding(f) for f in merged.findings
            ):
                terminated_early = True
                break

        # ``terminated_early`` is intentionally local: the report shape
        # is unchanged across modes so forensic-mode callers see no
        # difference. The signal is observable to tests by counting
        # findings or by comparing analyzers-run, not by reading a
        # report attribute. The local variable is retained for
        # readability; it is not surfaced on the merged report.
        del terminated_early

        merged.error = "; ".join(errors) if errors else None
        merged.integrity_score = compute_muwazana_score(merged.findings)

        has_scan_error = any(
            f.mechanism == "scan_error" for f in merged.findings
        )
        if merged.error is not None or has_scan_error or any_incomplete:
            merged.scan_incomplete = True

        merged.integrity_score = apply_scan_incomplete_clamp(
            merged.integrity_score,
            scan_incomplete=merged.scan_incomplete,
        )
        return merged


# ---------------------------------------------------------------------------
# Decorator sugar
# ---------------------------------------------------------------------------

def registered(
    registry: AnalyzerRegistry,
) -> Callable[[type[BaseAnalyzer]], type[BaseAnalyzer]]:
    """Decorator factory binding an analyzer class to a specific registry.

    Equivalent to ``registry.register``; provided for readability in
    modules that register many analyzers against a named registry::

        from analyzers.registry import AnalyzerRegistry, registered

        pdf_registry = AnalyzerRegistry()

        @registered(pdf_registry)
        class MyAnalyzer(BaseAnalyzer):
            ...
    """
    def _decorator(cls: type[BaseAnalyzer]) -> type[BaseAnalyzer]:
        return registry.register(cls)
    return _decorator


__all__ = [
    "AnalyzerRegistry",
    "AnalyzerRegistrationError",
    "registered",
]
