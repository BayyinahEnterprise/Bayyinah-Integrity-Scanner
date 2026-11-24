"""Scan the test documents shipped in tobycmurray/phantom-lint (tests/bad and
tests/good) with the scanner's defaults. A file counts as caught when the
report contains a concealed_instruction finding. One JSON line per file.

    python scripts/benchmarks/phantomlint_run.py PATH/TO/phantom-lint/tests results.jsonl
"""
import sys, json, pathlib, time
from multiprocessing import Pool
def one(arg):
    label, p = arg
    import bayyinah
    t = time.time()
    try:
        r = bayyinah.scan_file(pathlib.Path(p)); mechs = [f.mechanism for f in r.findings]
        err, inc, score = r.error, bool(r.scan_incomplete), r.integrity_score
        det = [getattr(f, "description", "")[:300] for f in r.findings if f.mechanism == "concealed_instruction"]
    except Exception as e:
        mechs, err, inc, score, det = [], repr(e)[:200], True, None, []
    return dict(label=label, file=pathlib.Path(p).name, mechs=mechs, hit="concealed_instruction" in mechs, error=err,
                incomplete=inc, score=score, detail=det, secs=round(time.time() - t, 3))
if __name__ == "__main__":
    root = pathlib.Path(sys.argv[1]); items = []
    for label in ("bad", "good"):
        for p in sorted((root / label).iterdir()):
            if p.is_file() and p.suffix.lower() in (".pdf", ".html"): items.append((label, str(p)))
    with Pool(2) as pool, open(sys.argv[2], "w") as out:
        for rec in pool.imap(one, items, chunksize=2): out.write(json.dumps(rec) + "\n"); out.flush()
