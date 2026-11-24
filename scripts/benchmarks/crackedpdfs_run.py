"""Scan the CrackedPDFs test split with the scanner's defaults (no flags,
no second script). A file counts as an attack when the report contains a
concealed_instruction finding. One JSON line per file."""
import sys, json, pathlib, time
from multiprocessing import Pool
ROOT = pathlib.Path(sys.argv[1])
def one(rel):
    import bayyinah
    t = time.time(); p = ROOT / rel
    try:
        r = bayyinah.scan_file(p); mechs = [f.mechanism for f in r.findings]
        err, inc, score = r.error, bool(r.scan_incomplete), r.integrity_score
    except Exception as e:
        mechs, err, inc, score = [], repr(e)[:200], True, None
    return {"file_path": rel, "findings": [{"mechanism": m} for m in mechs],
            "instruction_like": "concealed_instruction" in mechs, "error": err,
            "scan_incomplete": inc, "integrity_score": score, "seconds": round(time.time() - t, 4)}
if __name__ == "__main__":
    import pandas as pd
    rels = pd.read_csv(sys.argv[2]).file_path.tolist()
    with Pool(4) as pool, open(sys.argv[3], "w") as out:
        for rec in pool.imap(one, rels, chunksize=16): out.write(json.dumps(rec) + "\n")
