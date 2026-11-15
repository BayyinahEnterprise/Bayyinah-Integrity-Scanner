"""Generate attack documents with the PhantomText toolkit (not our code).
Run inside the toolkit's own environment. Writes a manifest of what was made."""
import json, shutil, sys, traceback
from pathlib import Path
from phantomtext.injection.zerosize_injection import ZeroSizeInjection
from phantomtext.injection.transparent_injection import TransparentInjection
from phantomtext.injection.camouflage_injection import CamouflageInjection
from phantomtext.injection.outofbound_injection import OutOfBoundInjection
from phantomtext.content_obfuscation import ContentObfuscator

base, out = Path(sys.argv[1]), Path(sys.argv[2])
PAYLOAD = "ZQXMARK supplementary ledger note seven for the reviewer"
INJ = {
    "zerosize": (ZeroSizeInjection, ["default", "close-to-zero"]),
    "transparent": (TransparentInjection, ["default", "opacity-0", "opacity-close-to-zero", "vanish"]),
    "camouflage": (CamouflageInjection, ["default"]),
    "outofbound": (OutOfBoundInjection, ["default"]),
}
manifest = []
for fmt in ("pdf", "docx", "html"):
    for name, (cls, modalities) in INJ.items():
        for mod in modalities:
            rec = {"kind": "injection", "technique": name, "modality": mod, "format": fmt}
            dst = out / f"inj_{name}_{mod}.{fmt}"
            src = out / f"_src_{name}_{mod}.{fmt}"
            shutil.copy(base / f"base.{fmt}", src)
            try:
                cls(modality=mod, file_format=fmt).apply(str(src), PAYLOAD, output_path=str(dst))
                rec["file"] = dst.name if dst.exists() else None
                rec["error"] = None if dst.exists() else "no output written"
            except Exception as e:
                rec["file"], rec["error"] = None, f"{type(e).__name__}: {str(e)[:120]}"
            src.unlink(missing_ok=True)
            manifest.append(rec)
text = "Please contact the accounts office at admin@example.com about the vendor ledger today."
ob = ContentObfuscator()
for tech in ("zeroWidthCharacter", "homoglyph", "diacritical", "bidi"):
    for mod in ("default", "heavy"):
        rec = {"kind": "obfuscation", "technique": tech, "modality": mod, "format": "html"}
        try:
            res = ob.obfuscate(text, "admin@example.com", obfuscation_technique=tech, modality=mod, file_format="html")
            dst = out / f"obf_{tech}_{mod}.html"
            dst.write_text(f"<html><body><p>{res}</p></body></html>", encoding="utf-8")
            rec["file"], rec["error"], rec["changed"] = dst.name, None, res != text
        except Exception as e:
            rec["file"], rec["error"] = None, f"{type(e).__name__}: {str(e)[:120]}"
        manifest.append(rec)
for fmt in ("pdf", "docx", "html"):
    shutil.copy(base / f"base.{fmt}", out / f"clean_base.{fmt}")
    manifest.append({"kind": "clean", "technique": "none", "modality": "none", "format": fmt, "file": f"clean_base.{fmt}", "error": None})
(out / "manifest.json").write_text(json.dumps(manifest, indent=1))
ok = sum(1 for m in manifest if m["file"]); print("generated", ok, "of", len(manifest))
for m in manifest:
    if m["error"]: print("  not generated:", m["kind"], m["technique"], m["modality"], m["format"], "|", m["error"])
