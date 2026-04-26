"""
ReportFormatter — making the report speak in the right dialect.

    وَمَا أَرْسَلْنَا مِن رَّسُولٍ إِلَّا بِلِسَانِ قَوْمِهِ لِيُبَيِّنَ لَهُمْ
    "We have not sent a messenger except with the language of his people,
    that he may make [the message] clear to them."  (Ibrahim 14:4)

The same IntegrityReport must be legible to an operator at a terminal,
to a CI pipeline consuming JSON, and (later) to a dashboard that wants
HTML. The report's content is invariant; only the *lisan* changes. The
formatter layer carries that responsibility and no other — it does not
scan, it does not merge, it does not score. It takes a finished
IntegrityReport and produces a string.

Three concrete formatters ship in Phase 3:

    TerminalReportFormatter — byte-identical to bayyinah_v0_1's
                              ``format_text_report``. Preserves the
                              parity invariant asserted by the fixture
                              tests.
    JsonReportFormatter     — byte-identical to bayyinah_v0_1's
                              ``print(json.dumps(report.to_dict(),
                              indent=2, default=str))`` path.
    PlainLanguageFormatter  — one-paragraph human summary, exposed for
                              reuse by the TerminalReportFormatter and
                              by callers that want the summary alone.

A tiny ``FormatterRegistry`` lets later phases register HTML, SARIF, or
SIEM formats without touching the abstract contract.

This is additive-only. bayyinah_v0_1.format_text_report and
bayyinah_v0_1.plain_language_summary are unchanged; the new formatters
produce the same strings, but neither shadows nor replaces the
originals.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Callable, Iterable

from domain import BayyinahError, IntegrityReport


# ---------------------------------------------------------------------------
# Formatter-specific exceptions
# ---------------------------------------------------------------------------

class FormatterRegistrationError(BayyinahError):
    """Raised on invalid formatter-registry operations.

    Mirrors ``AnalyzerRegistrationError`` in shape and intent: empty
    names, non-subclasses, and name collisions are rejected.
    """


# ---------------------------------------------------------------------------
# ReportFormatter — abstract contract
# ---------------------------------------------------------------------------

class ReportFormatter(ABC):
    """Abstract base class for every report renderer.

    Subclasses MUST declare a non-empty ``name`` class attribute and
    implement ``format(report: IntegrityReport) -> str``. Formatters are
    pure: they do not open files, they do not mutate the report, they
    do not emit side effects. The ``name`` is stable and suitable for
    CLI flag mapping (``--format terminal``, ``--format json``, ...).
    """

    name: str = ""
    """Short, stable identifier used by ``FormatterRegistry`` and CLI
    dispatch. Subclasses override."""

    content_type: str = "text/plain"
    """MIME-like hint for consumers that want to tag the output. Not
    load-bearing for correctness, but handy for HTTP adapters and for
    logging which format was emitted."""

    # ------------------------------------------------------------------
    # Subclass-time validation
    # ------------------------------------------------------------------

    def __init_subclass__(cls, **kwargs: object) -> None:
        """Enforce the formatter contract at class-definition time.

        Intermediate abstract subclasses (still carrying an abstract
        ``format`` method) are skipped — only concrete leaves are
        required to declare a non-empty ``name`` attribute. This lets
        the registry key by name without ever meeting a ``""`` key.
        """
        super().__init_subclass__(**kwargs)
        fmt_impl = getattr(cls, "format", None)
        if fmt_impl is None or getattr(fmt_impl, "__isabstractmethod__", False):
            return
        if not isinstance(cls.name, str) or not cls.name:
            raise TypeError(
                f"Concrete ReportFormatter subclass {cls.__name__!r} must "
                "declare a non-empty string class attribute 'name'."
            )

    # ------------------------------------------------------------------
    # Abstract contract
    # ------------------------------------------------------------------

    @abstractmethod
    def format(self, report: IntegrityReport) -> str:
        """Render ``report`` to a string in this formatter's dialect."""
        raise NotImplementedError

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


# ---------------------------------------------------------------------------
# Plain-language summary — a one-paragraph readable verdict
# ---------------------------------------------------------------------------

def plain_language_summary(report: IntegrityReport) -> str:
    """Return the one-paragraph human summary of ``report``.

    Byte-identical port of ``bayyinah_v0_1.plain_language_summary``.
    Exposed as a module-level function because both the
    TerminalReportFormatter and PlainLanguageFormatter need it, and
    other callers (e.g. CLI banners, emails) may want the paragraph
    without the surrounding terminal chrome.
    """
    incomplete_note = ""
    if report.scan_incomplete:
        incomplete_note = (
            "NOTE: scan_incomplete=true — one or more scanner paths reported an "
            "error or could not complete. The integrity score has been clamped "
            "to a maximum of 0.50 because portions of the document were not "
            "inspected; absence of findings in the uninspected regions cannot "
            "be taken as evidence of cleanness. "
        )
    if report.error:
        return incomplete_note + f"Scan did not complete cleanly: {report.error}"
    n = len(report.findings)
    s = report.integrity_score
    if n == 0:
        return incomplete_note + (
            f"Integrity score: {s:.2f}/1.00. No concealment mechanisms detected. "
            "What the file displays and what the file contains appear to match."
        )
    counts: dict[str, int] = {}
    for f in report.findings:
        counts[f.mechanism] = counts.get(f.mechanism, 0) + 1
    mech_list = ", ".join(
        f"{mech} ({n})" for mech, n in sorted(counts.items(), key=lambda x: -x[1])
    )
    by_tier = {1: 0, 2: 0, 3: 0}
    for f in report.findings:
        by_tier[f.tier] = by_tier.get(f.tier, 0) + 1
    return incomplete_note + (
        f"Integrity score: {s:.2f}/1.00. {n} finding(s) across "
        f"{len(counts)} mechanism(s): {mech_list}. "
        f"Validity tiers — Tier 1 (verified): {by_tier[1]}, "
        f"Tier 2 (structural): {by_tier[2]}, "
        f"Tier 3 (interpretive): {by_tier[3]}. "
        "What this means: the file displays one thing and contains additional "
        "content not visible in normal viewing. This report does NOT assert "
        "the file is malicious — it surfaces the gap between display and content. "
        "The reader performs the recognition."
    )


# ---------------------------------------------------------------------------
# Concrete formatters
# ---------------------------------------------------------------------------

class PlainLanguageFormatter(ReportFormatter):
    """Emit the one-paragraph summary alone.

    Useful when embedding the verdict in an email, a Slack message, or
    a CI status line — anywhere the full banner-and-findings block
    would be too much.
    """

    name = "plain"
    content_type = "text/plain"

    def format(self, report: IntegrityReport) -> str:
        """Return the one-paragraph plain-language summary of ``report``.

        Thin wrapper over the module-level ``plain_language_summary``;
        exposing it behind the formatter contract lets callers dispatch
        by name through the registry uniformly with the other formats.
        """
        return plain_language_summary(report)


class TerminalReportFormatter(ReportFormatter):
    """Emit the full operator-readable report.

    Byte-identical port of ``bayyinah_v0_1.format_text_report``. Every
    line matches the original, in the original order, with the
    original truncation widths. The parity invariant asserted in
    ``tests/test_fixtures.py`` covers this via ``report.to_dict()``,
    but this formatter is held to the same standard at the string
    level — it is exercised by ``tests/infrastructure/test_report_formatter.py``
    against sample reports.
    """

    name = "terminal"
    content_type = "text/plain"

    _BAR = "=" * 76
    _SUBBAR = "-" * 76

    def format(self, report: IntegrityReport) -> str:
        """Render the full banner-style terminal report.

        Layout: header bar, file + APS score, validity disclaimer,
        plain-language summary, per-finding block (mechanism / tier /
        confidence / severity / location / description / inversion
        recovery), and a trailing error line if present. The layout is
        a byte-identical port of ``bayyinah_v0_1.format_text_report``
        — every existing CI / log consumer continues to parse what it
        parsed before.
        """
        lines: list[str] = []
        lines.append(self._BAR)
        lines.append(" BAYYINAH v0.1 — PDF FILE INTEGRITY REPORT")
        lines.append(self._BAR)
        lines.append(f" File: {report.file_path}")
        lines.append(
            f" Integrity score: {report.integrity_score:.3f} / 1.000  (APS-continuous)"
        )
        lines.append("")
        lines.append(" Validity disclaimer (Godel constraint):")
        lines.append(
            "   This report presents observed mechanisms and their validity tiers."
        )
        lines.append(
            "   It does NOT self-validate a moral or malicious verdict. Bayyinah"
        )
        lines.append(
            "   makes the invisible visible; the reader performs the recognition."
        )
        lines.append("")
        lines.append(self._SUBBAR)
        lines.append(" PLAIN-LANGUAGE SUMMARY")
        lines.append(self._SUBBAR)
        lines.append(" " + plain_language_summary(report))
        lines.append("")

        if report.findings:
            lines.append(self._SUBBAR)
            lines.append(f" FINDINGS  ({len(report.findings)})")
            lines.append(self._SUBBAR)
            for i, f in enumerate(report.findings, 1):
                lines.append(
                    f" [{i}] {f.mechanism}   Tier {f.tier}   "
                    f"confidence {f.confidence:.2f}   severity {f.severity:.2f}"
                )
                lines.append(f"     Location:    {f.location}")
                lines.append(f"     Description: {f.description}")
                lines.append("     Inversion recovery:")
                lines.append(f"       Surface   : {f.surface[:240]}")
                lines.append(f"       Concealed : {f.concealed[:240]}")
                lines.append("")

        if report.error:
            lines.append(f" ERROR: {report.error}")

        lines.append(self._BAR)
        return "\n".join(lines)


class JsonReportFormatter(ReportFormatter):
    """Emit the report as pretty-printed JSON.

    Uses ``report.to_dict()`` so the serialised keys and ordering match
    the v0.1 shape exactly. Formatting arguments (``indent=2``,
    ``default=str``, no ``sort_keys``) mirror the v0.1 CLI path —
    CI consumers pinned on the v0.1 output will continue to parse what
    this formatter emits.

    No trailing newline is appended; callers that pipe the output to a
    file should add one if they want POSIX-line-terminator behaviour.
    """

    name = "json"
    content_type = "application/json"

    def format(self, report: IntegrityReport) -> str:
        """Serialise ``report.to_dict()`` as pretty-printed JSON.

        Keys and ordering match v0.1 exactly. ``default=str`` falls back
        to string coercion for any value not JSON-native (e.g. Path
        objects) so the serialisation never raises on well-formed
        reports.
        """
        return json.dumps(report.to_dict(), indent=2, default=str)


# ---------------------------------------------------------------------------
# FormatterRegistry — same shape as AnalyzerRegistry, for consistency
# ---------------------------------------------------------------------------

class FormatterRegistry:
    """Name-keyed lookup for ReportFormatter classes.

    Instances are independent — no global state. Construct one per
    subsystem that needs format dispatch (CLI, HTTP adapter, test
    harness) and register the formatters it actually supports. This
    mirrors the AnalyzerRegistry pattern: uniform contract, no magic
    globals, easy to exercise in tests.
    """

    def __init__(self) -> None:
        """Create an empty registry.

        No formatters are pre-registered; call ``register()`` (or the
        ``registered()`` decorator) to populate. Use
        ``default_formatter_registry()`` to obtain a registry already
        seeded with the shipped formatters.
        """
        self._registry: dict[str, type[ReportFormatter]] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        formatter_cls: type[ReportFormatter],
    ) -> type[ReportFormatter]:
        """Register a formatter class by its ``.name``.

        Returns the class so this method can be used as a decorator.
        Raises ``FormatterRegistrationError`` on non-subclass, empty
        name, or name collision.
        """
        if not isinstance(formatter_cls, type) or not issubclass(
            formatter_cls, ReportFormatter
        ):
            raise FormatterRegistrationError(
                f"register() expects a ReportFormatter subclass; "
                f"got {formatter_cls!r}"
            )
        name = formatter_cls.name
        if not isinstance(name, str) or not name:
            raise FormatterRegistrationError(
                f"Formatter class {formatter_cls.__name__} has empty .name; "
                "cannot register."
            )
        if name in self._registry:
            existing = self._registry[name].__name__
            raise FormatterRegistrationError(
                f"Formatter name {name!r} is already registered to "
                f"{existing}; refusing to overwrite."
            )
        self._registry[name] = formatter_cls
        return formatter_cls

    def unregister(self, name: str) -> None:
        """Remove the formatter registered under ``name``. No-op if absent."""
        self._registry.pop(name, None)

    def clear(self) -> None:
        """Remove every registered formatter. Primarily for tests."""
        self._registry.clear()

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def get(self, name: str) -> type[ReportFormatter]:
        """Look up a registered formatter class by name. KeyError on miss."""
        if name not in self._registry:
            raise KeyError(
                f"No formatter registered under {name!r}. "
                f"Registered: {list(self._registry)}"
            )
        return self._registry[name]

    def names(self) -> list[str]:
        """Names of every registered formatter, in registration order."""
        return list(self._registry.keys())

    def classes(self) -> list[type[ReportFormatter]]:
        """Registered formatter classes, in registration order."""
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

    def format(self, name: str, report: IntegrityReport) -> str:
        """Convenience — instantiate the named formatter and render.

        Equivalent to ``self.get(name)().format(report)``; provided so
        callers do not have to remember the instantiate-then-call dance.
        """
        return self.get(name)().format(report)


def registered(
    registry: FormatterRegistry,
) -> Callable[[type[ReportFormatter]], type[ReportFormatter]]:
    """Decorator factory binding a formatter class to a registry.

    Equivalent to ``registry.register``; symmetrical with the
    ``registered`` helper in ``analyzers/registry.py``.
    """

    def _decorator(cls: type[ReportFormatter]) -> type[ReportFormatter]:
        return registry.register(cls)

    return _decorator


# ---------------------------------------------------------------------------
# Default registry — populated with the three Phase 3 formatters.
# Callers may use it directly or construct their own registry.
# ---------------------------------------------------------------------------

def default_formatter_registry() -> FormatterRegistry:
    """Build a fresh FormatterRegistry populated with the Phase 3 set.

    Returns a new instance on every call so tests and independent
    callers cannot accidentally pollute each other's registries. The
    set includes ``terminal``, ``json``, and ``plain``.
    """
    registry = FormatterRegistry()
    registry.register(TerminalReportFormatter)
    registry.register(JsonReportFormatter)
    registry.register(PlainLanguageFormatter)
    return registry


__all__ = [
    "ReportFormatter",
    "TerminalReportFormatter",
    "JsonReportFormatter",
    "PlainLanguageFormatter",
    "FormatterRegistry",
    "FormatterRegistrationError",
    "registered",
    "default_formatter_registry",
    "plain_language_summary",
]
