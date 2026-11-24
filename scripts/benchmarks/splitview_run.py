"""Scan the PDFs published with "What Users See Is Not What Models Read"
(SD957/Split-View-PDF: corpus_a canaries and corpus_b documents) with the
scanner's defaults. One JSON line per file.

    python scripts/benchmarks/splitview_run.py PATH/TO/Split-View-PDF results.jsonl

The payloads in this benchmark are ordinary claims, not instructions, so the
question asked is whether the scan reports the divergence at all. Findings
that describe a file's history or metadata rather than its text
(GENERIC below) are not counted as reporting it.
"""
import sys, json, pathlib, time
GENERIC = {"metadata_anomaly", "incremental_update", "pdf_metadata_analyzer"}
def main(root, out):
    import bayyinah
    root = pathlib.Path(root)
    with open(out, "w") as f:
        for sub in ("corpus_a/pdfs", "corpus_b/primary_25/pdfs", "corpus_b/qa_adapted_11/pdfs"):
            for p in sorted((root / sub).glob("*.pdf")):
                t = time.time()
                try:
                    r = bayyinah.scan_file(p); mechs = [x.mechanism for x in r.findings]
                    err, inc = r.error, bool(r.scan_incomplete)
                    status = (r.instruction_assessment or {}).get("status")
                except Exception as e:
                    mechs, err, inc, status = [], repr(e)[:200], True, None
                f.write(json.dumps(dict(set=sub.split("/")[-2] if sub.startswith("corpus_b") else "corpus_a", file=p.name,
                    mechs=mechs, reported=any(m not in GENERIC for m in mechs), error=err, incomplete=inc,
                    instruction=status, secs=round(time.time() - t, 3))) + "\n")
if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
