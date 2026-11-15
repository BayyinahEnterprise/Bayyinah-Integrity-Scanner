"""
bayyinah CLI — the surface the world sees (Al-Baqarah 2:204).

    وَمِنَ النَّاسِ مَن يُعْجِبُكَ قَوْلُهُ فِي الْحَيَاةِ الدُّنْيَا
    "And of the people is he whose speech pleases you in worldly life..."

The architectural reading: a tool's CLI is the first thing a user sees
— its speech in the worldly life. Bayyinah's CLI must therefore be
unambiguous, predictable, and non-presumptuous: it reports what the
scan found, it does not assert a moral verdict, and it exits with
codes a CI pipeline can reliably branch on.

Public shape::

    bayyinah scan <file>                    # human-readable report
    bayyinah scan <file> --json             # machine-readable JSON
    bayyinah scan <file> --quiet            # suppress report, keep
                                            # the exit code
    bayyinah scan <file> --summary          # one-paragraph summary
    bayyinah --version                      # "bayyinah X.Y.Z"

Exit codes — stable contract, byte-identical to v0/v0.1::

    0   scan completed cleanly with zero findings
    1   scan completed with one or more findings
    2   scan could not complete (file not found, unparseable, ...)

Subcommand-based argparse layout is deliberate. The ``scan``
subcommand is the first of several this CLI will grow into later
(DOCX/HTML/code scanning, batch mode, registry inspection), and the
subcommand style keeps the surface extensible without rebinding
existing arguments.

Additive-only: this module does not import from ``bayyinah_v0`` or
``bayyinah_v0_1``. Both of those continue to ship their own
``main(argv)`` entry points at the ``bayyinah_v0`` /
``bayyinah_v0_1`` module level for callers that pinned to them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from bayyinah import (
    __version__,
    format_text_report,
    plain_language_summary,
    scan_pdf,
)


# ---------------------------------------------------------------------------
# Exit-code constants — named so callers / tests do not lean on magic numbers.
# ---------------------------------------------------------------------------

EXIT_CLEAN = 0
"""Scan completed with zero findings."""

EXIT_FINDINGS = 1
"""Scan completed; at least one concealment mechanism was detected."""

EXIT_ERROR = 2
"""Scan did not complete (missing file, unparseable PDF, …)."""


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    """Construct the top-level argparse parser.

    Factored out so tests can introspect the CLI surface without
    invoking ``main``.
    """
    parser = argparse.ArgumentParser(
        prog="bayyinah",
        description=(
            "Bayyinah — file integrity scanner that detects hidden, "
            "concealed, or adversarial content in digital documents. "
            "Reports the gap between what the file displays and what "
            "the file contains. Does not assert malicious intent — "
            "the reader performs the recognition."
        ),
        epilog=(
            "Reference: Munafiq Protocol — DOI 10.5281/zenodo.19677111. "
            "Licensed Apache-2.0."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"bayyinah {__version__}",
        help="show program version and exit",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        metavar="COMMAND",
        title="commands",
        description="Pick the operation to run.",
    )

    # ----- scan --------------------------------------------------------
    scan_p = subparsers.add_parser(
        "scan",
        help="scan a single document for integrity violations",
        description=(
            "Scan a single file. Emits findings, an integrity score, "
            "and a scan-incomplete flag if any analyzer could not "
            "fully cover its scope."
        ),
    )
    scan_p.add_argument(
        "file",
        metavar="FILE",
        type=Path,
        help=(
            "path to the document to scan — PDF, DOCX, HTML, XLSX, PPTX, "
            "EML, CSV, JSON, images (PNG / JPEG / GIF / BMP / TIFF / WebP), "
            "SVG, and Markdown / code / plain text are all supported; any "
            "other format surfaces an unknown_format finding via FallbackAnalyzer"
        ),
    )

    output_modes = scan_p.add_mutually_exclusive_group()
    output_modes.add_argument(
        "--json",
        action="store_true",
        help="emit the report as JSON on stdout (machine-readable)",
    )
    output_modes.add_argument(
        "--summary",
        action="store_true",
        help="emit only the one-paragraph plain-language summary",
    )
    output_modes.add_argument(
        "--quiet",
        action="store_true",
        help=(
            "suppress report output entirely; the exit code still "
            "reflects findings (0 clean, 1 findings, 2 error)"
        ),
    )

    # ----- clean -------------------------------------------------------
    clean_p = subparsers.add_parser(
        "clean",
        help="write a copy of a text file with hidden content removed",
        description=(
            "Remove hidden content from a text file (plain text, Markdown, "
            "code, CSV, JSON, HTML, logs) and write a receipt binding the "
            "original to the cleaned copy. The original is never modified. "
            "Binary containers (PDF, Office, images) are not cleaned."
        ),
    )
    clean_p.add_argument("file", metavar="FILE", type=Path,
                         help="path to the text file to clean")
    clean_p.add_argument("-o", "--output", metavar="OUT", type=Path,
                         default=None,
                         help="where to write the cleaned copy "
                              "(default: FILE with .clean before the suffix)")
    clean_p.add_argument("--force", action="store_true",
                         help="treat the file as UTF-8 text whatever its suffix")
    clean_p.add_argument("--json", action="store_true",
                         help="print the receipt as JSON")
    # ----- view --------------------------------------------------------
    view_p = subparsers.add_parser(
        "view",
        help="write the text a reader of a PDF or Office file could see",
        description=(
            "Render a PDF or Office file and write out only the text that "
            "left a visible mark, with a receipt. Hidden, clipped, covered, "
            "transparent and off-page text is left out. Office files are "
            "rendered by LibreOffice. The output is plain text, not the "
            "original document."
        ),
    )
    view_p.add_argument("file", metavar="FILE", type=Path,
                        help="path to a PDF or Office file")
    view_p.add_argument("-o", "--output", metavar="OUT", type=Path, default=None,
                        help="where to write the text "
                             "(default: FILE.reader-view.txt)")
    view_p.add_argument("--json", action="store_true",
                        help="print the receipt as JSON")
    return parser


# ---------------------------------------------------------------------------
# Exit-code resolution — one place, one rule.
# ---------------------------------------------------------------------------

def _exit_code_for(report) -> int:
    """Map an IntegrityReport to its CLI exit code.

    Preserved byte-identically from v0/v0.1:

        error present   → EXIT_ERROR    (2)
        findings > 0    → EXIT_FINDINGS (1)
        otherwise       → EXIT_CLEAN    (0)

    ``scan_incomplete`` without ``error`` (e.g. an analyzer that
    emitted a ``scan_error`` finding but cleared the top-level error)
    falls through to the findings-or-clean branch — that is v0's
    historical behaviour, and changing it would break CI pipelines.
    """
    if report.error:
        return EXIT_ERROR
    if report.findings:
        return EXIT_FINDINGS
    return EXIT_CLEAN


# ---------------------------------------------------------------------------
# Command dispatch
# ---------------------------------------------------------------------------

def _cmd_scan(args: argparse.Namespace) -> int:
    """Run the ``scan`` subcommand."""
    report = scan_pdf(args.file)

    if args.quiet:
        pass  # exit code only
    elif args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
    elif args.summary:
        print(plain_language_summary(report))
    else:
        print(format_text_report(report))

    return _exit_code_for(report)


# ---------------------------------------------------------------------------
# main — the script entry point
# ---------------------------------------------------------------------------

def _cmd_clean(args: argparse.Namespace) -> int:
    """Handle ``bayyinah clean``. Exit 0 on success, EXIT_ERROR otherwise."""
    import json as _json

    from application.sanitize import NotATextFile, clean_file

    try:
        receipt = clean_file(args.file, args.output, force=args.force)
    except (NotATextFile, OSError, ValueError) as exc:
        print(f"bayyinah clean: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(_json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    print(f"Cleaned copy: {receipt['cleaned_path']}")
    print(f"Receipt:      {receipt['receipt_path']}")
    if receipt["removed"]:
        for kind, n in receipt["removed"].items():
            print(f"  removed {n:>6}  {kind.replace('_', ' ')}")
    else:
        print("  nothing to remove")
    if receipt["kept_orthographic_zero_width"]:
        print(f"  kept    {receipt['kept_orthographic_zero_width']:>6}  "
              "zero-width characters the writing system requires")
    for p in receipt["hidden_payloads_removed"]:
        print(f"  hidden text removed ({p['channel']}): {p['preview'][:100]!r}")
    b, a = receipt["scan_before"], receipt["scan_after"]
    print(f"Findings before: {b['findings']}   after: {a['findings']}")
    if a["findings"]:
        print("  still reported: " + ", ".join(sorted(a["by_mechanism"])))
    return 0


def _cmd_view(args: argparse.Namespace) -> int:
    """Handle ``bayyinah view``. Exit 0 on success, EXIT_ERROR otherwise."""
    import json as _json

    from application.reader_view import ReaderViewError, reader_view

    try:
        receipt = reader_view(args.file, args.output)
    except (ReaderViewError, OSError) as exc:
        print(f"bayyinah view: {exc}", file=sys.stderr)
        return EXIT_ERROR
    if args.json:
        print(_json.dumps(receipt, indent=2, ensure_ascii=False))
        return 0
    print(f"Reader's view: {receipt['view_path']}")
    print(f"Receipt:       {receipt['receipt_path']}")
    print(f"  pages {receipt['pages_included']} of {receipt['pages_total']}, "
          f"rendered via {receipt['rendered_via']}")
    print(f"  kept {receipt['spans_kept']} text span(s), "
          f"left out {receipt['spans_left_out']} that a reader could not see")
    for line in receipt["left_out_preview"][:3]:
        print(f"    left out: {line!r}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Parameters
    ----------
    argv
        Argument vector (without the leading program name). If
        ``None``, ``sys.argv[1:]`` is used — the normal console-script
        behaviour.

    Returns
    -------
    int
        The exit code (0 / 1 / 2 as documented at the top of this
        module).

    The function is deliberately ``return`` instead of ``sys.exit`` so
    tests can call it in-process without intercepting ``SystemExit``.
    The ``if __name__ == '__main__'`` guard below calls ``sys.exit``
    with the return value for real console invocation.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help(sys.stderr)
        return EXIT_ERROR

    if args.command == "scan":
        return _cmd_scan(args)

    if args.command == "clean":
        return _cmd_clean(args)

    if args.command == "view":
        return _cmd_view(args)

    # argparse enforces the subparser choices, so the fall-through is
    # defensive: any new subcommand added without a handler will hit
    # this and surface a clear error instead of silently exiting 0.
    parser.error(f"unrecognised command: {args.command!r}")
    return EXIT_ERROR  # pragma: no cover — parser.error raises SystemExit


if __name__ == "__main__":  # pragma: no cover — exercised via console_scripts
    sys.exit(main())
