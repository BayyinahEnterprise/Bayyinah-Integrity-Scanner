"""Signed scan attestations, the detector hash, and seal verification.

Three things a downstream reader of a scan report cannot otherwise know:

* that the report was produced for *this* file and has not been swapped
  or edited (the white paper's v1.0 "content-signed attestation");
* which detector produced it. The report's ``version`` field is frozen
  at "0.1.0" for byte parity, and a version string is in any case "a
  placeholder dressed as a commitment" (furqan-lint, Gate 11): two
  installs of one version with different code would report the same
  string. ``detector_set_hash`` is computed over the source bytes;
* whether a FATIMA seal found in a file is signed, and by which key.

Signatures are Ed25519 over sorted-key compact JSON. A valid signature
shows that the holder of a private key signed these bytes. It does not
show who holds the key: that is the verifier's trust decision, and every
result here keeps the two apart. Needs the ``cryptography`` package
(``pip install bayyinah[attest]``); without it, verification reports
``unverifiable`` and never ``valid``.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

ATTESTATION_SCHEMA: Final[str] = "bayyinah.scan-attestation/1"
DETECTOR_PACKAGES: Final[tuple[str, ...]] = (
    "analyzers", "application", "domain", "infrastructure",
)
_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_ZW: Final[frozenset[str]] = frozenset("​‌‍﻿")


class AttestationError(RuntimeError):
    pass


def _crypto():
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ImportError as exc:
        raise AttestationError(
            "signing and verification need the 'cryptography' package "
            "(pip install bayyinah[attest])") from exc
    return ed25519, serialization


def canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def detector_files(root: Path = _ROOT) -> list[Path]:
    """Every Python source file in the detector packages. Found by walking
    the packages, not from a list, so a new module cannot be left out."""
    files: list[Path] = []
    for pkg in DETECTOR_PACKAGES:
        files.extend(p for p in (root / pkg).rglob("*.py")
                     if "__pycache__" not in p.parts)
    return sorted(files)


def detector_set_hash(root: Path = _ROOT) -> str:
    """SHA-256 over (relative path, file SHA-256) of every detector file."""
    h = hashlib.sha256()
    for path in detector_files(root):
        rel = path.relative_to(root).as_posix()
        h.update(rel.encode("utf-8") + b"\0")
        h.update(hashlib.sha256(path.read_bytes()).digest())
    return h.hexdigest()


def generate_key(path: Path | str) -> str:
    """Write a new Ed25519 private key (PEM, mode 0600); return the public
    key as hex. Refuses to overwrite."""
    ed25519, ser = _crypto()
    key = ed25519.Ed25519PrivateKey.generate()
    pem = key.private_bytes(ser.Encoding.PEM, ser.PrivateFormat.PKCS8,
                            ser.NoEncryption())
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as fh:
        fh.write(pem)
    return key.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw).hex()


def _load_private(path: Path | str):
    ed25519, ser = _crypto()
    key = ser.load_pem_private_key(Path(path).read_bytes(), password=None)
    if not isinstance(key, ed25519.Ed25519PrivateKey):
        raise AttestationError("not an Ed25519 private key")
    return key, key.public_key().public_bytes(ser.Encoding.Raw, ser.PublicFormat.Raw).hex()


def attest(file_path: Path | str, key_path: Path | str) -> dict[str, Any]:
    """Scan ``file_path`` and return a signed attestation of the result."""
    from bayyinah import __version__, scan_file

    file_path = Path(file_path)
    data = file_path.read_bytes()
    report = scan_file(file_path)
    findings = [f.to_dict() for f in report.findings]
    key, public = _load_private(key_path)
    body: dict[str, Any] = {
        "schema": ATTESTATION_SCHEMA,
        "tool": "bayyinah",
        "tool_version": __version__,
        "detector_set_hash": detector_set_hash(),
        "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file_name": file_path.name,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "file_bytes": len(data),
        "integrity_score": round(report.integrity_score, 3),
        "score_axes": report.score_axes,
        "scan_incomplete": bool(report.scan_incomplete),
        "finding_count": len(findings),
        "mechanisms": sorted({f["mechanism"] for f in findings}),
        "findings_digest": hashlib.sha256(canonical(findings)).hexdigest(),
        "instruction_assessment": (report.instruction_assessment or {}).get("status"),
        "disclosures": [d["kind"] for d in report.disclosures],
        "public_key": public,
    }
    body["signature"] = key.sign(canonical(body)).hex()
    return body


def verify_attestation(
    attestation: dict[str, Any], file_path: Path | str | None = None,
    trusted_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Check an attestation. Four separate answers, never one boolean:

    ``signature``     "valid" | "invalid" | "unverifiable"
    ``key_trusted``   True / False when ``trusted_keys`` is given, else None
    ``file_matches``  True / False when ``file_path`` is given, else None
    ``same_detector`` whether this install's detector hash equals the
                      attestation's (a different hash is not an error; it
                      means a rescan here could differ)
    """
    out: dict[str, Any] = {"signature": "invalid", "key_trusted": None,
                           "file_matches": None, "same_detector": None}
    body = {k: v for k, v in attestation.items() if k != "signature"}
    public = attestation.get("public_key")
    if trusted_keys is not None:
        out["key_trusted"] = public in set(trusted_keys)
    if file_path is not None:
        out["file_matches"] = (
            hashlib.sha256(Path(file_path).read_bytes()).hexdigest()
            == attestation.get("file_sha256"))
    out["same_detector"] = attestation.get("detector_set_hash") == detector_set_hash()
    try:
        ed25519, _ = _crypto()
    except AttestationError:
        out["signature"] = "unverifiable"
        return out
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(
            bytes.fromhex(attestation["signature"]), canonical(body))
        out["signature"] = "valid"
    except Exception:
        out["signature"] = "invalid"
    return out


# ---------------------------------------------------------------------------
# FATIMA signed seals (encoder v11.2.0 and later)
# ---------------------------------------------------------------------------

_SEAL_FIELDS: Final[tuple[str, ...]] = ("protocol", "version", "timestamp", "source_file")


def trusted_seal_keys() -> list[str] | None:
    """Public keys the operator trusts, from ``BAYYINAH_TRUSTED_SEAL_KEYS``
    (comma-separated hex). ``None`` when the variable is unset."""
    raw = os.environ.get("BAYYINAH_TRUSTED_SEAL_KEYS")
    if raw is None:
        return None
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def verify_fatima_seal(text: str, declaration: dict[str, Any]) -> dict[str, Any]:
    """Check the signed seal in a decoded FATIMA declaration against the
    text it was found in.

    ``status``: "unsigned", "valid", "content_changed", "invalid" or
    "unverifiable" (the ``cryptography`` package is missing).

    A valid seal covers the *visible* text only. It says nothing about
    other zero-width payloads in the same file, which is why the scanner
    still decodes and assesses every one of them.
    """
    seal = declaration.get("seal")
    out: dict[str, Any] = {"status": "unsigned", "public_key": None, "key_trusted": None}
    if not isinstance(seal, dict):
        return out
    public = str(seal.get("public_key", "")).lower()
    out["public_key"] = public
    trusted = trusted_seal_keys()
    if trusted is not None:
        out["key_trusted"] = public in trusted
    try:
        ed25519, _ = _crypto()
    except AttestationError:
        out["status"] = "unverifiable"
        return out
    body = {k: declaration.get(k) for k in _SEAL_FIELDS}
    body["content_sha256"] = seal.get("content_sha256")
    try:
        ed25519.Ed25519PublicKey.from_public_bytes(bytes.fromhex(public)).verify(
            bytes.fromhex(seal["signature"]), canonical(body))
    except Exception:
        out["status"] = "invalid"
        return out
    visible = "".join(c for c in text if c not in _ZW)
    digest = hashlib.sha256(visible.encode("utf-8")).hexdigest()
    out["status"] = "valid" if digest == seal.get("content_sha256") else "content_changed"
    return out


__all__ = [
    "ATTESTATION_SCHEMA", "AttestationError", "attest", "canonical",
    "detector_files", "detector_set_hash", "generate_key",
    "trusted_seal_keys", "verify_attestation", "verify_fatima_seal",
]
