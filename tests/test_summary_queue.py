"""Persistence + privacy tests for bayyinah.summary_queue.

No network. Pure SQLite. Each test gets its own tmp DB path so tests
do not pollute each other.
"""
from __future__ import annotations

import collections
import datetime as _dt
import os
import sqlite3
from pathlib import Path

import pytest

from bayyinah import summary_queue as sq


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    """Per-test SQLite path. init_db is called once."""
    p = str(tmp_path / "summary_queue.sqlite")
    sq.init_db(p)
    return p


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def test_enqueue_and_get_round_trips_fields(db_path):
    """Enqueue followed by get returns the documented fields."""
    job_id = sq.enqueue("hello world", db_path=db_path)
    job = sq.get_job(job_id, db_path=db_path)
    assert job is not None
    assert job["job_id"] == job_id
    assert job["status"] == sq.STATUS_QUEUED
    assert job["attempts"] == 0
    assert job["summary"] is None
    assert job["error"] is None
    assert job["delivered_at"] is None
    assert job["last_attempted_at"] is None
    # extracted_text is intentionally NOT in the get_job projection.
    assert "extracted_text" not in job


def test_init_db_is_idempotent(db_path):
    """Running init twice is a no-op, not an error."""
    sq.init_db(db_path)
    sq.init_db(db_path)
    sq.init_db(db_path)


def test_wal_mode_is_set(db_path):
    """After init, journal_mode reads back as wal."""
    conn = sqlite3.connect(db_path)
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode.lower() == "wal"


def test_janitor_removes_old_terminal_rows(db_path, monkeypatch):
    """Terminal rows older than 60s are deleted; newer terminals stay."""
    # Old delivered job (last_attempted_at: 5 minutes ago).
    fake_old = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(minutes=5)
    monkeypatch.setattr(sq, "_utc_now", lambda: fake_old)
    job_old = sq.enqueue("old text", db_path=db_path)
    sq.claim_next_job(db_path=db_path)
    sq.mark_delivered(job_old, "old summary", db_path=db_path)

    # Fresh delivered job (now).
    monkeypatch.setattr(
        sq, "_utc_now",
        lambda: _dt.datetime.now(_dt.timezone.utc),
    )
    job_fresh = sq.enqueue("fresh text", db_path=db_path)
    sq.claim_next_job(db_path=db_path)
    sq.mark_delivered(job_fresh, "fresh summary", db_path=db_path)

    # Pending job (not terminal).
    job_pending = sq.enqueue("pending text", db_path=db_path)

    deleted = sq.janitor_pass(db_path=db_path)
    assert deleted == 1
    assert sq.get_job(job_old, db_path=db_path) is None
    assert sq.get_job(job_fresh, db_path=db_path) is not None
    assert sq.get_job(job_pending, db_path=db_path) is not None


def test_recovery_sweep_reverts_in_flight_to_queued(db_path):
    """Worker startup sweep reverts in_flight rows to queued."""
    job_id = sq.enqueue("text", db_path=db_path)
    sq.claim_next_job(db_path=db_path)
    job = sq.get_job(job_id, db_path=db_path)
    assert job["status"] == sq.STATUS_IN_FLIGHT

    n = sq.recovery_sweep(db_path=db_path)
    assert n == 1
    job_after = sq.get_job(job_id, db_path=db_path)
    assert job_after["status"] == sq.STATUS_QUEUED
    # Sweep is idempotent.
    n2 = sq.recovery_sweep(db_path=db_path)
    assert n2 == 0


def test_resolve_db_path_honors_env_var(monkeypatch, tmp_path):
    """BAYYINAH_SUMMARY_QUEUE_DB takes precedence over defaults."""
    custom = str(tmp_path / "custom.sqlite")
    monkeypatch.setenv("BAYYINAH_SUMMARY_QUEUE_DB", custom)
    assert sq._resolve_db_path() == custom


def test_resolve_db_path_falls_back_when_data_unwritable(monkeypatch):
    """If /data is not writable, fall back to /tmp/summary_queue.sqlite."""
    monkeypatch.delenv("BAYYINAH_SUMMARY_QUEUE_DB", raising=False)
    # Force the /data probe to fail by monkeypatching Path.mkdir for the
    # /data parent path. Cleanest is to pretend /data is non-writable.
    import pathlib
    real_mkdir = pathlib.Path.mkdir

    def fake_mkdir(self, *args, **kwargs):
        if str(self) == "/data":
            raise PermissionError("simulated")
        return real_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "mkdir", fake_mkdir)
    assert sq._resolve_db_path() == "/tmp/summary_queue.sqlite"


# ---------------------------------------------------------------------------
# State transitions
# ---------------------------------------------------------------------------

def test_claim_picks_due_queued_job(db_path):
    job_id = sq.enqueue("text", db_path=db_path)
    claimed = sq.claim_next_job(db_path=db_path)
    assert claimed is not None
    assert claimed["job_id"] == job_id
    after = sq.get_job(job_id, db_path=db_path)
    assert after["status"] == sq.STATUS_IN_FLIGHT


def test_claim_skips_future_next_retry(db_path, monkeypatch):
    """A job whose next_retry_at is in the future is not picked."""
    fake_past = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(seconds=10)
    monkeypatch.setattr(sq, "_utc_now", lambda: fake_past)
    job_id = sq.enqueue("text", db_path=db_path)
    # Mark as failed so next_retry_at is set 1s into the (real) future.
    sq.claim_next_job(db_path=db_path)
    sq.mark_failed_retry(job_id, "test", 0, db_path=db_path)

    # Now query at fake_past + 0.5s (still before next_retry_at).
    monkeypatch.setattr(
        sq, "_utc_now",
        lambda: fake_past + _dt.timedelta(milliseconds=500),
    )
    assert sq.claim_next_job(db_path=db_path) is None


def test_mark_delivered_clears_extracted_text(db_path):
    """Privacy contract: extracted_text -> '' on delivery."""
    job_id = sq.enqueue("sensitive text", db_path=db_path)
    sq.claim_next_job(db_path=db_path)
    sq.mark_delivered(job_id, "the summary", db_path=db_path)
    # Read the extracted_text column directly (not via get_job which
    # intentionally excludes it).
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT extracted_text, summary, status FROM summary_jobs "
            "WHERE job_id = ?", (job_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == ""  # extracted_text cleared
    assert row[1] == "the summary"
    assert row[2] == sq.STATUS_DELIVERED


def test_mark_permanent_failure_clears_extracted_text(db_path):
    """Same privacy contract for failed_permanent."""
    job_id = sq.enqueue("sensitive text", db_path=db_path)
    sq.claim_next_job(db_path=db_path)
    sq.mark_permanent_failure(job_id, "anthropic_status_401", db_path=db_path)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT extracted_text, status FROM summary_jobs "
            "WHERE job_id = ?", (job_id,),
        ).fetchone()
    finally:
        conn.close()
    assert row[0] == ""
    assert row[1] == sq.STATUS_FAILED_PERMANENT


def test_backoff_progression(db_path, monkeypatch):
    """Failures 1..7 produce delays 1, 2, 4, 8, 16, 32, 60 seconds."""
    expected = [1, 2, 4, 8, 16, 32, 60]
    for attempts_so_far, delay in enumerate(expected):
        # Pin _utc_now to a fixed instant so we can compute the
        # expected next_retry_at deterministically.
        now = _dt.datetime(2026, 5, 2, 12, 0, 0, tzinfo=_dt.timezone.utc)
        monkeypatch.setattr(sq, "_utc_now", lambda n=now: n)
        job_id = sq.enqueue("text", db_path=db_path)
        sq.claim_next_job(db_path=db_path)
        sq.mark_failed_retry(job_id, "test", attempts_so_far, db_path=db_path)
        job = sq.get_job(job_id, db_path=db_path)
        next_retry = _dt.datetime.fromisoformat(job["next_retry_at"])
        assert (next_retry - now).total_seconds() == delay, (
            f"attempts_so_far={attempts_so_far}: expected {delay}s, "
            f"got {(next_retry - now).total_seconds()}"
        )


def test_backoff_caps_at_60_seconds(db_path, monkeypatch):
    """Attempts >= 7 stay at 60 seconds."""
    now = _dt.datetime(2026, 5, 2, 12, 0, 0, tzinfo=_dt.timezone.utc)
    monkeypatch.setattr(sq, "_utc_now", lambda: now)
    job_id = sq.enqueue("text", db_path=db_path)
    sq.claim_next_job(db_path=db_path)
    sq.mark_failed_retry(job_id, "test", 100, db_path=db_path)
    job = sq.get_job(job_id, db_path=db_path)
    next_retry = _dt.datetime.fromisoformat(job["next_retry_at"])
    assert (next_retry - now).total_seconds() == 60


def test_is_past_permanent_cutoff_24h(db_path, monkeypatch):
    """A job enqueued 24 hours ago is past the cutoff; one minute ago is not."""
    fake_old = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=25)
    monkeypatch.setattr(sq, "_utc_now", lambda: fake_old)
    old_job = sq.enqueue("text", db_path=db_path)
    monkeypatch.setattr(
        sq, "_utc_now",
        lambda: _dt.datetime.now(_dt.timezone.utc),
    )
    fresh_job = sq.enqueue("text", db_path=db_path)

    assert sq.is_past_permanent_cutoff(old_job, db_path=db_path) is True
    assert sq.is_past_permanent_cutoff(fresh_job, db_path=db_path) is False


# ---------------------------------------------------------------------------
# Aggregate state + ring buffer
# ---------------------------------------------------------------------------

def test_aggregate_state_reflects_counts(db_path):
    j1 = sq.enqueue("a", db_path=db_path)
    j2 = sq.enqueue("b", db_path=db_path)
    sq.enqueue("c", db_path=db_path)
    sq.claim_next_job(db_path=db_path)  # j1 -> in_flight
    sq.mark_delivered(j1, "summary a", db_path=db_path)
    state = sq.aggregate_state(db_path=db_path)
    assert state["pending"] == 2
    assert state["in_flight"] == 0
    assert state["delivered_last_hour"] == 1
    assert state["failed_permanent_last_hour"] == 0
    assert isinstance(state["recent_transitions"], list)


def test_recent_transitions_is_bounded_and_newest_first(db_path):
    """The ring is maxlen=20 and newest-first."""
    sq.recent_transitions.clear()
    for i in range(25):
        sq.record_transition(f"job-{i}", "queued", "in_flight")
    assert len(sq.recent_transitions) == 20
    assert sq.recent_transitions[0]["job_id"] == "job-24"
    assert sq.recent_transitions[19]["job_id"] == "job-5"


def test_soonest_next_retry_at(db_path, monkeypatch):
    """The soonest next_retry_at among queued jobs drives worker timing."""
    j = sq.enqueue("text", db_path=db_path)
    sq.claim_next_job(db_path=db_path)
    sq.mark_failed_retry(j, "test", 2, db_path=db_path)  # 4s delay
    sn = sq.soonest_next_retry_at(db_path=db_path)
    assert sn is not None
    delta = (sn - _dt.datetime.now(_dt.timezone.utc)).total_seconds()
    assert 2 < delta < 5  # roughly 4 seconds out


def test_soonest_returns_none_when_empty(db_path):
    """No queued jobs -> None."""
    assert sq.soonest_next_retry_at(db_path=db_path) is None


def test_claim_next_job_returned_dict_reflects_in_flight_state(db_path):
    """The dict returned by claim_next_job must show post-UPDATE state.

    Before the v1.2.3 fix, claim_next_job returned a dict captured
    from the pre-UPDATE SELECT, so callers saw status='queued' and
    last_attempted_at=None even though the DB row had been
    transitioned to in_flight. Closes Fraz round 10 MEDIUM 2.

    The load-bearing assertion is the final one: it reads the row
    directly from SQLite and checks the returned dict equals the DB
    truth, rather than asserting hard-coded constants. That keeps the
    regression test honest if status/last_attempted_at semantics
    change in a future release.
    """
    import sqlite3 as _sqlite3

    sq.enqueue("text", db_path=db_path)
    claimed = sq.claim_next_job(db_path=db_path)
    assert claimed is not None

    # Caller-visible state matches the post-UPDATE contract.
    assert claimed["status"] == sq.STATUS_IN_FLIGHT
    assert claimed["last_attempted_at"] is not None
    assert isinstance(claimed["last_attempted_at"], str)
    assert claimed["last_attempted_at"] != ""

    # DB truth equals caller-visible truth.
    conn = _sqlite3.connect(db_path)
    conn.row_factory = _sqlite3.Row
    try:
        db_row = dict(conn.execute(
            "SELECT status, last_attempted_at FROM summary_jobs "
            "WHERE job_id = ?",
            (claimed["job_id"],),
        ).fetchone())
    finally:
        conn.close()
    assert claimed["status"] == db_row["status"]
    assert claimed["last_attempted_at"] == db_row["last_attempted_at"]
