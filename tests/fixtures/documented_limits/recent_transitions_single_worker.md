# Documented limitation: recent_transitions ring is process-local

**Pinned in:** `tests/test_documented_limits.py::test_recent_transitions_is_in_memory_only`
**Introduced:** v1.2.2

## Behavior

`bayyinah.summary_queue.recent_transitions` is an in-memory
`collections.deque(maxlen=20)` that records the most recent 20 queue-
state transitions (newest first). It exists to drive the demo UI's
drain-log panel.

The ring is per-process. SQLite-backed counts (pending, in_flight,
delivered_last_hour, failed_permanent_last_hour) are consistent across
worker processes because they are computed from a single shared
database. The transitions ring is not.

## Why this is a deliberate limitation, not a bug

A multi-worker uvicorn deployment (`uvicorn --workers N`) would have
N separate rings, one per process. The `/demo/queue/state` endpoint
would return whichever ring the load balancer routed the request to.
Counts would still be correct; the recent-transitions log would be
arbitrary.

Production runs single-worker uvicorn today. The limitation does not
manifest under the current deployment shape.

## Why it has not been promoted to a fix in v1.2.2

The fix shape (move recent_transitions into SQLite as a bounded table
with a row-count trigger) is not free: it changes the cost shape of
every transition from a single deque append to a SQLite write. For a
demo UI, the in-memory ring is sufficient; for production-grade
multi-worker deployments, the SQLite-backed shape is correct. v1.2.2
ships the demo-grade shape and pins the limitation; v1.3 evaluates
whether the production-grade shape is needed.

## Test that pins this behavior

```python
def test_recent_transitions_is_in_memory_only():
    from bayyinah.summary_queue import recent_transitions, RECENT_TRANSITIONS_MAX
    import collections
    assert isinstance(recent_transitions, collections.deque)
    assert recent_transitions.maxlen == RECENT_TRANSITIONS_MAX
    assert RECENT_TRANSITIONS_MAX == 20
```

If this test fails, either the ring's storage shape changed
(intentional promotion to a different store, requiring this fixture
to retire per `PARITY.md` and the framework's retirement procedure),
or the maxlen was changed without updating the README user-facing
limitations bullet. Both are findings.

## Audit trail

This limitation was introduced as part of v1.2.2's queue-and-worker
implementation per the v2 prompt. The four-place documentation pattern
artifacts in v1.2.2:

- CHANGELOG `## [1.2.2]` "Remaining limitations" subsection.
- README "Remaining limitations" bullet.
- This fixture file (you are reading it).
- The pinning test cited above.
