"""Persistent summarization queue for the public demo.

Backs the v1.2.2 cable-pull resilience claim. Demo summarization jobs
are enqueued to a SQLite database and drained by an asyncio worker
(``bayyinah.summary_worker``). Network loss does not lose jobs;
process restart does not lose jobs; the SQLite layer is the single
source of truth for queue state.

Design choices:
    * sqlite3 stdlib only. No new runtime dependency.
    * DB path comes from BAYYINAH_SUMMARY_QUEUE_DB. Default is
      /data/summary_queue.sqlite (Railway volume mount). If /data is
      not writable the queue falls back to /tmp/summary_queue.sqlite
      with a warning logged. Mirrors bayyinah/counter.py:_resolve_db_path
      exactly.
    * WAL journal mode, per the project standard for SQLite.
    * The recent_transitions ring buffer is in-memory only. It exists
      to drive the demo UI's drain log; it is NOT durable across
      process restart and does NOT synchronize across worker
      processes. See tests/fixtures/documented_limits/
      recent_transitions_single_worker.md for the documented
      limitation.
    * Privacy: extracted_text is held only as long as needed. It is
      cleared to '' the moment a job reaches a terminal state, and
      the row is deleted by the janitor within 60 seconds. The text
      is never logged and never returned by any endpoint.
"""
from __future__ import annotations

import collections
import datetime as _dt
import logging
import os
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "/data/summary_queue.sqlite"
_FALLBACK_DB_PATH = "/tmp/summary_queue.sqlite"

# Backoff schedule per the v1.2.2 contract: 1, 2, 4, 8, 16, 32, 60
# seconds, capped at 60 thereafter. Index = attempts already made;
# value = seconds until next_retry_at relative to now.
_BACKOFF_SCHEDULE = (1, 2, 4, 8, 16, 32, 60)
_BACKOFF_CAP_SECONDS = 60

# Permanent-failure cutoff: if the job has been queued for at least
# 24 hours from enqueued_at and still has not delivered, mark
# failed_permanent.
_PERMANENT_FAIL_AFTER_SECONDS = 24 * 60 * 60

# Janitor TTL: terminal-state rows older than this many seconds are
# deleted on every janitor pass.
_JANITOR_TTL_SECONDS = 60

# Status constants. Strings (not enum) so they round-trip cleanly
# through SQLite TEXT columns and JSON.
STATUS_QUEUED = "queued"
STATUS_IN_FLIGHT = "in_flight"
STATUS_DELIVERED = "delivered"
STATUS_FAILED_PERMANENT = "failed_permanent"

_TERMINAL_STATUSES = (STATUS_DELIVERED, STATUS_FAILED_PERMANENT)

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS summary_jobs ("
    "job_id TEXT PRIMARY KEY, "
    "enqueued_at TEXT NOT NULL, "
    "status TEXT NOT NULL, "
    "extracted_text TEXT NOT NULL, "
    "summary TEXT, "
    "error TEXT, "
    "attempts INTEGER NOT NULL DEFAULT 0, "
    "next_retry_at TEXT NOT NULL, "
    "delivered_at TEXT, "
    "last_attempted_at TEXT"
    ")"
)
_SCHEMA_INDEX = (
    "CREATE INDEX IF NOT EXISTS idx_summary_jobs_status_retry "
    "ON summary_jobs(status, next_retry_at)"
)


# ---------------------------------------------------------------------------
# Module-level recent-transitions ring buffer.
#
# In-memory only. Per-process. Documented as a v1.2.2 Remaining
# Limitation pinned by tests/test_documented_limits.py::
# test_recent_transitions_is_in_memory_only.
# ---------------------------------------------------------------------------

RECENT_TRANSITIONS_MAX = 20

recent_transitions: collections.deque = collections.deque(
    maxlen=RECENT_TRANSITIONS_MAX
)


def _utc_now() -> _dt.datetime:
    """UTC now as a timezone-aware datetime.

    Wrapped in a function so tests can monkeypatch this single symbol.
    Mirrors bayyinah.counter._utc_now.
    """
    return _dt.datetime.now(_dt.timezone.utc)


def _resolve_db_path() -> str:
    """Resolve which DB path to use, falling back if /data is read-only.

    Order of preference:
        1. BAYYINAH_SUMMARY_QUEUE_DB env var, if set.
        2. /data/summary_queue.sqlite, if /data exists and is writable.
        3. /tmp/summary_queue.sqlite (warning logged).

    Mirrors bayyinah.counter._resolve_db_path exactly, including the
    fallback warning shape.
    """
    env_path = os.environ.get("BAYYINAH_SUMMARY_QUEUE_DB")
    if env_path:
        return env_path

    parent = Path(_DEFAULT_DB_PATH).parent
    try:
        parent.mkdir(parents=True, exist_ok=True)
        probe = parent / ".summary_queue_write_probe"
        probe.touch()
        probe.unlink()
        return _DEFAULT_DB_PATH
    except (OSError, PermissionError) as exc:
        logger.warning(
            "summary_queue: %s not writable (%s); falling back to %s",
            parent, exc, _FALLBACK_DB_PATH,
        )
        return _FALLBACK_DB_PATH


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Open a SQLite connection in WAL mode."""
    path = db_path or _resolve_db_path()
    conn = sqlite3.connect(path, isolation_level=None)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Create the schema if it does not exist. Idempotent."""
    with _connect(db_path) as conn:
        conn.execute(_SCHEMA)
        conn.execute(_SCHEMA_INDEX)


def record_transition(job_id: str, from_status: str, to_status: str) -> None:
    """Append a transition to the in-memory ring buffer.

    Newest-first ordering: most recent transition is at index 0. The
    deque maxlen evicts the oldest transition once 21 are pushed.
    """
    transition = {
        "job_id": job_id,
        "from": from_status,
        "to": to_status,
        "at": _utc_now().isoformat(),
    }
    recent_transitions.appendleft(transition)


def enqueue(
    extracted_text: str,
    db_path: Optional[str] = None,
) -> str:
    """Enqueue a new summarization job. Return its job_id (uuid4)."""
    job_id = str(uuid.uuid4())
    now = _utc_now().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "INSERT INTO summary_jobs "
            "(job_id, enqueued_at, status, extracted_text, "
            " attempts, next_retry_at) "
            "VALUES (?, ?, ?, ?, 0, ?)",
            (job_id, now, STATUS_QUEUED, extracted_text, now),
        )
    record_transition(job_id, "(none)", STATUS_QUEUED)
    return job_id


def get_job(job_id: str, db_path: Optional[str] = None) -> Optional[dict]:
    """Return a single job's state as a dict, or None if not found.

    The extracted_text field is intentionally NOT returned.
    """
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT job_id, enqueued_at, status, summary, error, "
            "attempts, next_retry_at, delivered_at, last_attempted_at "
            "FROM summary_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def claim_next_job(db_path: Optional[str] = None) -> Optional[dict]:
    """Claim the soonest-due queued job; mark it in_flight; return it.

    Returns None if no queued job is currently due. The returned dict
    includes extracted_text because the worker needs it to call
    Anthropic. Caller must not log or persist the text outside this
    queue.
    """
    now = _utc_now().isoformat()
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT job_id, enqueued_at, status, extracted_text, "
            "summary, error, attempts, next_retry_at, delivered_at, "
            "last_attempted_at "
            "FROM summary_jobs "
            "WHERE status = ? AND next_retry_at <= ? "
            "ORDER BY next_retry_at ASC LIMIT 1",
            (STATUS_QUEUED, now),
        ).fetchone()
        if row is None:
            return None
        job_id = row["job_id"]
        conn.execute(
            "UPDATE summary_jobs SET status = ?, last_attempted_at = ? "
            "WHERE job_id = ?",
            (STATUS_IN_FLIGHT, now, job_id),
        )
        # Convert the sqlite3.Row to a mutable dict and reflect the
        # UPDATE we just performed, so the returned value matches the
        # row in the database. Without this refresh, callers see a
        # stale status='queued' and last_attempted_at=None even though
        # the row in the database is already in_flight. Reported by
        # Fraz, round 10 MEDIUM 2.
        result = dict(row)
        result["status"] = STATUS_IN_FLIGHT
        result["last_attempted_at"] = now
    record_transition(job_id, STATUS_QUEUED, STATUS_IN_FLIGHT)
    return result


def mark_delivered(
    job_id: str,
    summary: str,
    db_path: Optional[str] = None,
) -> None:
    """Mark a job delivered. Stores summary, clears extracted_text."""
    now = _utc_now().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE summary_jobs SET status = ?, summary = ?, "
            "extracted_text = '', delivered_at = ?, error = NULL "
            "WHERE job_id = ?",
            (STATUS_DELIVERED, summary, now, job_id),
        )
    record_transition(job_id, STATUS_IN_FLIGHT, STATUS_DELIVERED)


def mark_failed_retry(
    job_id: str,
    error: str,
    attempts_so_far: int,
    db_path: Optional[str] = None,
) -> None:
    """Record a retryable failure. Sets next_retry_at per backoff."""
    now = _utc_now()
    delay_idx = min(attempts_so_far, len(_BACKOFF_SCHEDULE) - 1)
    delay_seconds = (
        _BACKOFF_SCHEDULE[delay_idx]
        if attempts_so_far < len(_BACKOFF_SCHEDULE)
        else _BACKOFF_CAP_SECONDS
    )
    next_retry_at = (
        now + _dt.timedelta(seconds=delay_seconds)
    ).isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE summary_jobs SET status = ?, attempts = ?, "
            "error = ?, next_retry_at = ?, last_attempted_at = ? "
            "WHERE job_id = ?",
            (
                STATUS_QUEUED, attempts_so_far + 1, error,
                next_retry_at, now.isoformat(), job_id,
            ),
        )
    record_transition(job_id, STATUS_IN_FLIGHT, STATUS_QUEUED)


def mark_permanent_failure(
    job_id: str,
    error: str,
    db_path: Optional[str] = None,
) -> None:
    """Mark a job failed_permanent. Clears extracted_text."""
    now = _utc_now().isoformat()
    with _connect(db_path) as conn:
        conn.execute(
            "UPDATE summary_jobs SET status = ?, error = ?, "
            "extracted_text = '', delivered_at = ?, "
            "last_attempted_at = ? "
            "WHERE job_id = ?",
            (STATUS_FAILED_PERMANENT, error, now, now, job_id),
        )
    record_transition(job_id, STATUS_IN_FLIGHT, STATUS_FAILED_PERMANENT)


def is_past_permanent_cutoff(
    job_id: str,
    db_path: Optional[str] = None,
) -> bool:
    """True if the job has been enqueued for >= 24h. Caller-checked."""
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT enqueued_at FROM summary_jobs WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    if row is None:
        return False
    enqueued_at = _dt.datetime.fromisoformat(row["enqueued_at"])
    return (_utc_now() - enqueued_at).total_seconds() >= _PERMANENT_FAIL_AFTER_SECONDS


def recovery_sweep(db_path: Optional[str] = None) -> int:
    """Revert any in_flight rows to queued with next_retry_at = now.

    Idempotent. Called once on worker startup. Handles the case where
    the previous process died mid-call (segfault, OOM, container kill).
    Returns the number of rows reverted.
    """
    now = _utc_now().isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute(
            "UPDATE summary_jobs SET status = ?, next_retry_at = ? "
            "WHERE status = ?",
            (STATUS_QUEUED, now, STATUS_IN_FLIGHT),
        )
        n = cur.rowcount
    return n


def janitor_pass(db_path: Optional[str] = None) -> int:
    """Delete terminal-state rows older than _JANITOR_TTL_SECONDS.

    Returns the number of rows deleted. Called inside the worker
    loop. Privacy contract: extracted_text was already cleared on
    transition to terminal state; this pass removes the row entirely.
    """
    cutoff = (
        _utc_now() - _dt.timedelta(seconds=_JANITOR_TTL_SECONDS)
    ).isoformat()
    with _connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM summary_jobs "
            "WHERE status IN (?, ?) AND last_attempted_at <= ?",
            (STATUS_DELIVERED, STATUS_FAILED_PERMANENT, cutoff),
        )
    return cur.rowcount


def aggregate_state(db_path: Optional[str] = None) -> dict[str, Any]:
    """Return the queue's aggregate state for /demo/queue/state.

    Counts pending and in_flight strictly. Counts delivered and
    failed_permanent within the last hour (via delivered_at /
    last_attempted_at). Includes the in-memory recent_transitions
    ring as a list of dicts.
    """
    one_hour_ago = (
        _utc_now() - _dt.timedelta(hours=1)
    ).isoformat()
    with _connect(db_path) as conn:
        pending = conn.execute(
            "SELECT COUNT(*) AS n FROM summary_jobs WHERE status = ?",
            (STATUS_QUEUED,),
        ).fetchone()["n"]
        in_flight = conn.execute(
            "SELECT COUNT(*) AS n FROM summary_jobs WHERE status = ?",
            (STATUS_IN_FLIGHT,),
        ).fetchone()["n"]
        delivered_last_hour = conn.execute(
            "SELECT COUNT(*) AS n FROM summary_jobs "
            "WHERE status = ? AND delivered_at >= ?",
            (STATUS_DELIVERED, one_hour_ago),
        ).fetchone()["n"]
        failed_last_hour = conn.execute(
            "SELECT COUNT(*) AS n FROM summary_jobs "
            "WHERE status = ? AND last_attempted_at >= ?",
            (STATUS_FAILED_PERMANENT, one_hour_ago),
        ).fetchone()["n"]
    return {
        "pending": pending,
        "in_flight": in_flight,
        "delivered_last_hour": delivered_last_hour,
        "failed_permanent_last_hour": failed_last_hour,
        "recent_transitions": list(recent_transitions),
    }


def soonest_next_retry_at(db_path: Optional[str] = None) -> Optional[_dt.datetime]:
    """The soonest next_retry_at among queued jobs, or None if no queued.

    Used by the worker to compute its sleep timeout: sleep until the
    soonest-due job, or until an event wakes the worker, whichever
    comes first.
    """
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT next_retry_at FROM summary_jobs "
            "WHERE status = ? "
            "ORDER BY next_retry_at ASC LIMIT 1",
            (STATUS_QUEUED,),
        ).fetchone()
    if row is None:
        return None
    return _dt.datetime.fromisoformat(row["next_retry_at"])


__all__ = [
    "STATUS_QUEUED",
    "STATUS_IN_FLIGHT",
    "STATUS_DELIVERED",
    "STATUS_FAILED_PERMANENT",
    "RECENT_TRANSITIONS_MAX",
    "recent_transitions",
    "init_db",
    "enqueue",
    "get_job",
    "claim_next_job",
    "mark_delivered",
    "mark_failed_retry",
    "mark_permanent_failure",
    "is_past_permanent_cutoff",
    "recovery_sweep",
    "janitor_pass",
    "aggregate_state",
    "soonest_next_retry_at",
    "record_transition",
]
