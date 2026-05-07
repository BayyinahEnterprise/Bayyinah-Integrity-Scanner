#!/usr/bin/env python3
"""Build a LibreOffice Writer-produced PDF (not synthetic).

Used to verify the producer-family coverage check (§6 corpus
widening). The fixture verdicts sahih on v1.2.4 because no
/OpenAction is emitted by this minimal export.

Output: fixture_libreoffice_writer_native.pdf
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

HERE = Path(__file__).parent
HTML_SOURCE = b"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Round 12 LibreOffice Native</title></head>
<body><h1>LibreOffice Writer Native</h1>
<p>Minimal LibreOffice export for producer-family coverage.</p>
</body></html>
"""


def build(output_path: Path) -> None:
    workdir = output_path.parent / "_build_libreoffice_native"
    workdir.mkdir(parents=True, exist_ok=True)
    seed_html = workdir / "seed.html"
    seed_html.write_bytes(HTML_SOURCE)
    env = os.environ.copy()
    env["SOURCE_DATE_EPOCH"] = "0"
    subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "seed.html",
         "--outdir", str(workdir)],
        cwd=workdir, env=env, check=True, capture_output=True,
    )
    (workdir / "seed.pdf").rename(output_path)
    for f in workdir.glob("*"):
        f.unlink(missing_ok=True)
    workdir.rmdir()


if __name__ == "__main__":
    out = HERE / "fixture_libreoffice_writer_native.pdf"
    build(out)
    print(f"wrote {out} ({out.stat().st_size} bytes)")
