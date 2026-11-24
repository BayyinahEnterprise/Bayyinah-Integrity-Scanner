"""Scan the text cases published with "Reverse CAPTCHA"
(canonicalmg/reverse-captcha-eval, packs/reverse_captcha and
packs/hidden_message_extraction) with integrations.check_text. One JSON line
per case: whether anything was reported, whether the hidden text was decoded,
and whether it was read as an instruction.

    python scripts/benchmarks/reverse_captcha_run.py PATH/TO/reverse-captcha-eval results.jsonl
"""
import sys, json, pathlib
def main(root, out):
    import yaml
    from integrations import check_text
    root = pathlib.Path(root)
    with open(out, "w") as f:
        for pack in ("reverse_captcha", "hidden_message_extraction"):
            for c in yaml.safe_load(open(root / "packs" / pack / "cases.yaml")):
                hidden = (c.get("metadata") or {}).get("hidden_instruction") or c.get("expected_message") or ""
                try:
                    v = check_text(c["carrier_text"]); d = v.to_dict()
                    blob = json.dumps(d, ensure_ascii=False).lower()
                    row = dict(mechs=list(v.mechanisms), reported=bool(v.mechanisms), instruction=bool(v.instruction_like),
                               status=v.assessment_status, decoded=bool(hidden) and hidden.lower() in blob, error=None)
                except Exception as e:
                    row = dict(mechs=[], reported=False, instruction=False, status=None, decoded=False, error=repr(e)[:200])
                f.write(json.dumps(dict(pack=pack, id=c["id"], scheme=c["scheme"], has_hidden=bool(hidden), **row)) + "\n")
if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
