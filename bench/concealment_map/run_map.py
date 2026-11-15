"""Run the map: generate, render, scan, compare.

    python -m bench.concealment_map.run_map --max-changed 2 --out OUT.jsonl

For each generated page the expected verdict follows from two facts the
scanner is not consulted about: does a text extractor return the
payload, and can a reader see it.

    machine reads it, reader cannot see it  ->  must be reported
    reader can see it, legibly              ->  must not be reported
    machine does not read it                ->  nothing to report

Disagreements go to an append-only JSONL ledger with the configuration
that produced them. Pages the scanner could not scan are counted as
``incomplete``, never as agreeing.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from bench.concealment_map.grammar import MARK, Config, build, enumerate_configs
from bench.concealment_map.oracle import machine_reads, truth


def evaluate(cfg: Config, workdir: Path) -> dict:
    import bayyinah

    with_p, without_p = workdir / "with.pdf", workdir / "without.pdf"
    build(cfg, str(with_p), True)
    build(cfg, str(without_p), False)
    seen = truth(str(with_p), str(without_p))
    # A stroked 1 pt font renders as a smear four pixels tall, which the
    # pixel rule calls visible. Glyph size is a fact the generator knows,
    # so legibility is decided from it, at the scanner's own declared
    # line (SUBLEGIBLE_FONT_PT). That line is a stated convention, not a
    # measurement of what people can read.
    from analyzers.pdf_stream_concealment import SUBLEGIBLE_FONT_PT
    effective = float(cfg.size) * (0.001 if cfg.scale == "tiny" else 1)
    if seen == "visible" and effective < SUBLEGIBLE_FONT_PT:
        seen = "sub_legible"
    read = machine_reads(str(with_p), MARK)
    report = bayyinah.scan_file(with_p)
    baseline = {f.mechanism for f in bayyinah.scan_file(without_p).findings}
    mechs = sorted({f.mechanism for f in report.findings} - baseline)
    if report.scan_incomplete:
        outcome = "incomplete"
    elif not read:
        outcome = "not_extracted" if not mechs else "reported_unextracted"
    elif seen == "visible":
        outcome = "false_positive" if mechs else "agree_clean"
    else:
        outcome = "agree_reported" if mechs else "false_negative"
    return {"config": cfg.key(), "dims": asdict(cfg), "truth": seen,
            "machine_reads": read, "mechanisms": mechs, "outcome": outcome}


def run(max_changed: int | None, out: Path | None = None) -> tuple[Counter, list[dict]]:
    counts: Counter = Counter()
    disagreements: list[dict] = []
    with tempfile.TemporaryDirectory() as tmp:
        for cfg in enumerate_configs(max_changed):
            rec = evaluate(cfg, Path(tmp))
            counts[rec["outcome"]] += 1
            if rec["outcome"] in ("false_negative", "false_positive", "incomplete"):
                disagreements.append(rec)
    if out is not None:
        with out.open("a", encoding="utf-8") as fh:
            for rec in disagreements:
                fh.write(json.dumps(rec, sort_keys=True) + "\n")
    return counts, disagreements


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--max-changed", type=int, default=2,
                    help="dimensions allowed to differ from the baseline (default 2; 0 = all)")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    counts, bad = run(args.max_changed or None, args.out)
    total = sum(counts.values())
    print(f"pages: {total}")
    for k in sorted(counts):
        print(f"  {k:22s} {counts[k]}")
    by = Counter()
    for rec in bad:
        for k, v in rec["dims"].items():
            if rec["outcome"] == "false_negative":
                by[f"{k}={v}"] += 1
    if by:
        print("false negatives by choice:", dict(by.most_common(12)))


if __name__ == "__main__":
    main()
