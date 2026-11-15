"""Scan the PhantomText-generated documents once with the frozen scanner."""
import json, sys
from pathlib import Path
import bayyinah
from application.attestation import detector_set_hash
out = Path(sys.argv[1]); man = json.loads((out / "manifest.json").read_text())
print("detector_set_hash", detector_set_hash())
rows = []
for m in man:
    if not m["file"]: continue
    r = bayyinah.scan_file(out / m["file"]); d = r.to_dict()
    mechs = sorted({f.mechanism for f in r.findings})
    recovered = any("ZQXMARK" in (f.concealed or "") + (f.description or "") for f in r.findings)
    rows.append(dict(m, mechanisms=mechs, flagged=bool(mechs), payload_recovered=recovered,
                     assessment=(d.get("instruction_assessment") or {}).get("status"),
                     score=d["integrity_score"], incomplete=d["scan_incomplete"]))
(out / "results.json").write_text(json.dumps(rows, indent=1))
att = [x for x in rows if x["kind"] != "clean"]; clean = [x for x in rows if x["kind"] == "clean"]
print(f"attack documents: {len(att)}  reported: {sum(x['flagged'] for x in att)}  payload text recovered: {sum(x['payload_recovered'] for x in att if x['kind']=='injection')} of {sum(1 for x in att if x['kind']=='injection')} injections")
print(f"clean documents: {len(clean)}  reported: {sum(x['flagged'] for x in clean)}")
for x in rows:
    print(f"  {x['kind'][:3]} {x['technique']:18s} {x['modality']:22s} {x['format']:4s} flagged={str(x['flagged']):5s} recovered={str(x['payload_recovered']):5s} {x['mechanisms']}")
