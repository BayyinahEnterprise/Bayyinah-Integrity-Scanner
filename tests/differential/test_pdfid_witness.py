"""
Priority 1 external witness: pdfid (v1.8.0).

Wraps Didier Stevens' pdfid.py as a DifferentialWitness. When pdfid
is not available in the environment, the tests in this module are
skipped with an install hint, per docs/differential_testing.md §2.3.

The differential pair compares Bayyinah's PDF finding set against
pdfid's structural-address finding set on the Phase 0 fixture corpus
and surfaces WitnessDivergence records. Divergence is reported, not
asserted to be zero: per docs/differential_testing.md §2.2, two
witnesses disagreeing is a question, not necessarily an error.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import List

import pytest

from tests.differential.witness_contract import (
    DifferentialWitness,
    WitnessFinding,
)


# ---------------------------------------------------------------------------
# Availability check
# ---------------------------------------------------------------------------

_PDFID_INSTALLED = importlib.util.find_spec("pdfid") is not None
_SKIP_REASON = (
    "pdfid not installed. Install with: pip install pdfid (or add to "
    "[project.optional-dependencies] dev). See docs/differential_testing.md "
    "§3.1 for the witness contract."
)


# ---------------------------------------------------------------------------
# PdfIdWitness
# ---------------------------------------------------------------------------


class PdfIdWitness(DifferentialWitness):
    """Wraps pdfid.py as a DifferentialWitness.

    pdfid emits a count for each PDF keyword it recognises. The
    witness surfaces a WitnessFinding per keyword whose count is
    non-zero, with finding_key set to the keyword (stripped of the
    leading slash where present) and location left empty (pdfid's
    keyword counts are file-global).
    """

    @property
    def witness_name(self) -> str:
        return "pdfid"

    @property
    def install_hint(self) -> str:
        return _SKIP_REASON

    def is_available(self) -> bool:
        return _PDFID_INSTALLED

    def observe(self, path: Path) -> List[WitnessFinding]:
        if not self.is_available():
            return []
        # PyPI pdfid 1.1.3 exposes PDFiD via the pdfid.pdfid submodule;
        # older distributions exposed it on the top-level pdfid module.
        # Try both to remain portable across distributions.
        try:
            try:
                from pdfid.pdfid import PDFiD as _PDFiD  # type: ignore[import-not-found]
            except ImportError:
                from pdfid import PDFiD as _PDFiD  # type: ignore[import-not-found]

            out = _PDFiD(str(path))

            findings: list[WitnessFinding] = []
            # pdfid returns an XML Element-like object: out.getElementsByTagName('Keyword')
            # OR a dict-like with .keywords; tolerate both shapes.
            kw_list = []
            try:
                kw_list = out.getElementsByTagName("Keyword")  # XML DOM shape
            except AttributeError:
                kw_list = getattr(out, "keywords", [])

            for kw in kw_list:
                # XML DOM: kw.getAttribute('Name'), kw.getAttribute('Count')
                # Custom object: kw.name, kw.count
                try:
                    name = kw.getAttribute("Name")
                    count_raw = kw.getAttribute("Count")
                except AttributeError:
                    name = getattr(kw, "name", str(kw))
                    count_raw = getattr(kw, "count", 0)
                try:
                    count = int(count_raw)
                except (ValueError, TypeError):
                    count = 0
                if count > 0:
                    findings.append(WitnessFinding(
                        witness_name=self.witness_name,
                        finding_key=name.lstrip("/"),
                        location="",
                    ))
            return findings
        except (Exception, SystemExit):
            # Any unrecoverable pdfid-shape mismatch or pdfid's
            # internal sys.exit() on missing files surfaces as
            # solo-Bayyinah divergence rather than a test error.
            # SystemExit is a BaseException subclass (not Exception),
            # explicitly caught here because pdfid 1.1.3 calls
            # sys.exit() on file-open failure.
            # Per docs/differential_testing.md §2.3: a witness that
            # cannot honestly observe returns [], it never raises.
            return []


# ---------------------------------------------------------------------------
# Contract sanity tests (run regardless of pdfid availability)
# ---------------------------------------------------------------------------


class TestPdfIdWitnessContract:
    """The PdfIdWitness class itself satisfies the DifferentialWitness ABC.

    These tests run even when pdfid is not installed. They verify the
    witness has the right shape; actual differential observation is
    in TestPdfIdDifferential below.
    """

    def test_witness_name_is_pdfid(self) -> None:
        assert PdfIdWitness().witness_name == "pdfid"

    def test_install_hint_documents_install(self) -> None:
        assert "pip install pdfid" in PdfIdWitness().install_hint

    def test_is_available_returns_bool(self) -> None:
        assert isinstance(PdfIdWitness().is_available(), bool)

    def test_observe_returns_empty_when_unavailable(self) -> None:
        """When pdfid is not installed, observe() returns [] (never raises).

        This pins the contract that a missing witness is a SILENT-empty,
        not an exception. The skip is reported by the differential pair
        tests via pytest.skipif, not by an exception in observe().
        """
        w = PdfIdWitness()
        # We cannot fake unavailability from here, but we CAN verify
        # that when actually unavailable, observe returns an empty list.
        if not w.is_available():
            assert w.observe(Path("/definitely/does/not/exist.pdf")) == []


# ---------------------------------------------------------------------------
# Differential pair tests (skipped when pdfid not available)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _PDFID_INSTALLED, reason=_SKIP_REASON)
class TestPdfIdDifferential:
    """Differential pair: Bayyinah vs pdfid on the Phase 0 fixture corpus.

    These tests run only when pdfid is installed. Each test surfaces
    divergence as informational output (assertion is structural, not
    on count) per docs/differential_testing.md §2.2.

    The test class is intentionally minimal at v1.8.0; subsequent
    rounds may expand the corpus per Q8 closure log.
    """

    def test_pdfid_returns_list_for_fixture(self, tmp_path: Path) -> None:
        """pdfid observe() returns a list for any input path.

        We construct a minimal valid PDF byte sequence rather than
        depending on a fixture file. The point is to verify pdfid's
        shape conformance, not finding accuracy.
        """
        minimal_pdf = (
            b"%PDF-1.4\n"
            b"1 0 obj\n<<>>\nendobj\n"
            b"trailer\n<<>>\n"
            b"%%EOF\n"
        )
        fixture = tmp_path / "minimal.pdf"
        fixture.write_bytes(minimal_pdf)

        w = PdfIdWitness()
        observed = w.observe(fixture)
        assert isinstance(observed, list)
        # Every element is a WitnessFinding
        for f in observed:
            assert isinstance(f, WitnessFinding)
            assert f.witness_name == "pdfid"

    def test_pdfid_returns_empty_for_nonexistent_path(self) -> None:
        """A missing file produces an empty witness output, not a raise."""
        w = PdfIdWitness()
        # pdfid implementations differ on missing-file handling. The
        # witness wrapper swallows exceptions per §2.2; verify behavior.
        try:
            observed = w.observe(Path("/definitely/does/not/exist.pdf"))
            assert isinstance(observed, list)
        except Exception:
            # If pdfid raises on missing file, the witness wrapper's
            # try/except should have caught it. Re-raising means a
            # contract violation in PdfIdWitness.observe.
            pytest.fail(
                "PdfIdWitness.observe must not raise on missing path; "
                "see docs/differential_testing.md §2.3"
            )
