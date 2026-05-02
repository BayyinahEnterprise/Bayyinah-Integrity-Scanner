"""Persistent scan counter for the public demo.

Records every successful /demo/summarize call (blocked or clean) into a
SQLite database, plus a daily-salt-rotated SHA-256 hash of the client IP
for unique-visitor counting. The salt rotates every UTC day so the same
IP on the same day produces the same hash, but cross-day correlation is
impossible without the per-process secret.

Design choices:
    * sqlite3 stdlib only. No new runtime dependency.
    * DB path comes from BAYYINAH_COUNTER_DB. Default is /data/counter.db
      (Railway volume mount). If /data is not writable the counter falls
      back to /tmp/counter.db with a warning logged. Local dev therefore
      works without configuration; production sets the env var explicitly.
    * BAYYINAH_COUNTER_SECRET feeds the daily-salt HMAC. If unset, a
      per-process secret is generated and a warning is logged. The
      counter is therefore reset (in unique-visitor sense) every process
      restart in dev. Production must set the env var.
    * All counts are SELECT COUNT(*). No caching. SQLite at the scale
      this counter runs at (single-digit thousands per day) is fine.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import hmac
import logging
import os
import secrets
import sqlite3
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "/data/counter.db"
_FALLBACK_DB_PATH = "/tmp/counter.db"

_SCHEMA_SCANS = (
    "CREATE TABLE IF NOT EXISTS scans ("
    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "ts TEXT NOT NULL"
    ")"
)
_SCHEMA_UNIQUE = (
    "CREATE TABLE IF NOT EXISTS unique_visitors ("
    "date TEXT NOT NULL, "
    "ip_hash TEXT NOT NULL, "
    "PRIMARY KEY(date, ip_hash)"
    ")"
)


def _utc_now() -> _dt.datetime:
    """UTC now as a timezone-aware datetime.

    Wrapped in a function so tests can monkeypatch this single symbol.
    """
    return _dt.datetime.now(_dt.timezone.utc)


def _utc_today_iso() -> str:
    """ISO-format UTC date string (YYYY-MM-DD)."""
    return _utc_now().date().isoformat()


def _resolve_db_path() -> str:
    """Resolve which DB path to use, falling back if /data is read-only.

    Order of preference:
        1. BAYYINAH_COUNTER_DB env var, if set.
        2. /data/counter.db, if /data exists and is writable.
        3. /tmp/counter.db (warning logged).
    """
    env_path = os.environ.get("BAYYINAH_COUNTER_DB")
    if env_path:
        return env_path

    parent = Path(_DEFAULT_DB_PATH).parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        # Touch a probe file to verify the dir is writable.
        probe = parent / ".counter_write_probe"
        probe.touch()
        probe.unlink()
        return _DEFAULT_DB_PATH
    except (OSError, PermissionError) as exc:
        logger.warning(
            "counter: %s not writable (%s); falling back to %s",
            parent, exc, _FALLBACK_DB_PATH,
        )
        return _FALLBACK_DB_PATH


_secret_lock = threading.Lock()
_process_secret: Optional[bytes] = None


def _resolve_secret() -> bytes:
    """Return the HMAC secret for daily-salt derivation.

    Pulled from BAYYINAH_COUNTER_SECRET. If missing, a per-process random
    secret is generated and reused for the lifetime of the process; a
    warning is logged on first generation. Acceptable in dev (the unique
    counter resets on restart). Production must set the env var.
    """
    global _process_secret
    raw = os.environ.get("BAYYINAH_COUNTER_SECRET")
    if raw:
        return raw.encode("utf-8")
    with _secret_lock:
        if _process_secret is None:
            _process_secret = secrets.token_bytes(32)
            logger.warning(
                "counter: BAYYINAH_COUNTER_SECRET not set; "
                "generated a per-process secret. Unique-visitor counts "
                "will reset on process restart. Set the env var in "
                "production."
            )
    return _process_secret


def _daily_salt(date_iso: str) -> bytes:
    """Derive the per-day salt as HMAC-SHA256(secret, date_iso)."""
    return hmac.new(
        _resolve_secret(),
        date_iso.encode("utf-8"),
        hashlib.sha256,
    ).digest()


def hash_ip(ip: str, date_iso: Optional[str] = None) -> str:
    """SHA-256 hex digest of (daily_salt || ip).

    Same IP + same UTC day = same hash. Same IP + different UTC day =
    different hash. Cross-day correlation requires the per-process or
    env-var secret.
    """
    if date_iso is None:
        date_iso = _utc_today_iso()
    salt = _daily_salt(date_iso)
    h = hashlib.sha256()
    h.update(salt)
    h.update(ip.encode("utf-8"))
    return h.hexdigest()


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a short-lived SQLite connection and ensure the schema exists.

    A new connection per call is fine at this scale. SQLite handles the
    concurrency, and we avoid the threading subtleties of a shared
    connection across the FastAPI worker pool.
    """
    path = db_path or _resolve_db_path()
    parent = Path(path).parent
    if str(parent) and parent != Path("."):
        parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=5.0, isolation_level=None)
    conn.execute(_SCHEMA_SCANS)
    conn.execute(_SCHEMA_UNIQUE)
    return conn


def record_scan(ip: str, db_path: Optional[str] = None) -> None:
    """Record one successful scan. Insert a row in ``scans`` and an
    upsert-style row in ``unique_visitors`` keyed by (utc-day, ip_hash).

    Errors are caught and logged. Counter failure must never break the
    user's scan response.
    """
    try:
        now = _utc_now()
        date_iso = now.date().isoformat()
        ts_iso = now.isoformat()
        ip_h = hash_ip(ip, date_iso)
        conn = _connect(db_path)
        try:
            conn.execute("INSERT INTO scans (ts) VALUES (?)", (ts_iso,))
            conn.execute(
                "INSERT OR IGNORE INTO unique_visitors (date, ip_hash) "
                "VALUES (?, ?)",
                (date_iso, ip_h),
            )
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - counter must never raise
        logger.warning("counter: record_scan failed: %s", exc)


def get_stats(db_path: Optional[str] = None) -> dict:
    """Return the public stats payload.

    Schema:
        {
          "scans": int,                  # total successful scans recorded
          "unique_visitors_total": int,  # distinct (day, ip_hash) pairs
          "unique_visitors_today": int,  # distinct ip_hash for today UTC
          "since": str | None,           # ISO ts of earliest scan, or None
          "as_of": str,                  # ISO ts of this snapshot
        }
    """
    today = _utc_today_iso()
    as_of = _utc_now().isoformat()
    try:
        conn = _connect(db_path)
        try:
            cur = conn.execute("SELECT COUNT(*) FROM scans")
            scans = int(cur.fetchone()[0])

            cur = conn.execute("SELECT COUNT(*) FROM unique_visitors")
            uniq_total = int(cur.fetchone()[0])

            cur = conn.execute(
                "SELECT COUNT(*) FROM unique_visitors WHERE date = ?",
                (today,),
            )
            uniq_today = int(cur.fetchone()[0])

            cur = conn.execute("SELECT MIN(ts) FROM scans")
            since_row = cur.fetchone()
            since = since_row[0] if since_row and since_row[0] else None
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001 - stats must never raise
        logger.warning("counter: get_stats failed: %s", exc)
        return {
            "scans": 0,
            "unique_visitors_total": 0,
            "unique_visitors_today": 0,
            "since": None,
            "as_of": as_of,
        }
    return {
        "scans": scans,
        "unique_visitors_total": uniq_total,
        "unique_visitors_today": uniq_today,
        "since": since,
        "as_of": as_of,
    }


def client_ip(request) -> str:
    """Extract a client IP from a Starlette/FastAPI Request.

    Prefer the first hop of X-Forwarded-For (Railway sets this). Fall
    back to request.client.host. Returns "unknown" if neither is
    available.
    """
    xff = request.headers.get("x-forwarded-for") if request else None
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    if request is not None and request.client and request.client.host:
        return request.client.host
    return "unknown"


__all__ = [
    "client_ip",
    "get_stats",
    "hash_ip",
    "record_scan",
]
