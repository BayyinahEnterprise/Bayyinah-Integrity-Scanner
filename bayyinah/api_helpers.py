"""HTTP-API helper functions shared between /scan and /demo/summarize.

The single helper here, ``scan_file_bytes``, encapsulates the temp-file
write, ``scan_file`` call, dict shaping, and cleanup that both the
production /scan endpoint and the v1.1.9 demo firewall endpoint need.
Extracted from the original /scan handler in api.py so the demo route
can reuse the exact same scan path without duplicating the temp-file
dance.

Failure semantics are caller-shaped: this helper does not catch
exceptions from ``scan_file``. Callers that want to render a 500
response (production /scan) catch ``Exception`` themselves; callers
that want a different failure shape (the demo handler returns scan
errors as part of its JSON envelope) catch what they need.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from bayyinah import scan_file
from domain.value_objects import tamyiz_verdict


def scan_file_bytes(
    contents: bytes,
    filename: str,
    mode: str = "forensic",
) -> dict:
    """Scan ``contents`` and return the IntegrityReport as a dict.

    Steps:
      1. Write ``contents`` to a temp file with ``filename``'s suffix.
         The suffix is load-bearing: Bayyinah's FileRouter uses both
         magic bytes and the extension to pick the analyzer set.
      2. Call ``scan_file(tmp_path, mode=mode)``.
      3. Convert the report to a dict, substitute ``filename`` back
         in (so the caller does not see the temp path), add the
         ``verdict`` field.
      4. Clean up the temp file.

    Raises whatever ``scan_file`` raises. Callers shape the failure
    response.
    """
    suffix = Path(filename).suffix
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        tmp.write(contents)
        tmp.close()
        report = scan_file(tmp.name, mode=mode)
        payload = report.to_dict()
        payload["file_path"] = filename
        payload["verdict"] = tamyiz_verdict(report)
        return payload
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


__all__ = ["scan_file_bytes"]
