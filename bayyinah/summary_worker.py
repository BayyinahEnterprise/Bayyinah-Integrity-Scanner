"""Background asyncio worker that drains the summarization queue.

Started by the FastAPI lifespan (api.py) when BAYYINAH_DEMO_ENABLED=1.
Cancelled cleanly on shutdown. Strictly single-in-flight: only one
Anthropic call at a time, gated by an asyncio.Lock.

Sleep injection: the module exports ``_sleep`` as an alias for
``asyncio.sleep``. Tests monkeypatch ``bayyinah.summary_worker._sleep``
to a controllable async mock without affecting unrelated awaits
(httpx calls, sqlite calls). This mirrors the dependency-injection
pattern bayyinah.counter._utc_now uses for time.

The worker is robust against unhandled exceptions in the Anthropic
call: they are caught at the per-job boundary and treated as
retryable failures with error="anthropic_error: <text>". The loop
itself does not die.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Awaitable, Callable, Optional

import httpx

from bayyinah import summary_queue

logger = logging.getLogger(__name__)

# Module-level alias for asyncio.sleep so tests can monkeypatch it
# at this single import point without affecting other awaits in the
# loop. See framework §5 acceptance-criteria sharpening pattern and
# the bayyinah.counter._utc_now precedent.
_sleep = asyncio.sleep

# Default loop sleep when the queue is empty. Bounded so the worker
# wakes periodically even without a wakeup event (defensive).
_IDLE_SLEEP_SECONDS = 60.0

# Anthropic API constants (mirror bayyinah.demo).
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_ANTHROPIC_TIMEOUT_S = 30.0
_ANTHROPIC_MAX_TOKENS = 300
_DEMO_MODEL = "claude-sonnet-4-6"

# HTTP status semantics. 408 (Request Timeout), 425 (Too Early), and
# 429 (Too Many Requests) are retryable; other 4xx are permanent.
_RETRYABLE_4XX = frozenset({408, 425, 429})


async def _call_anthropic(api_key: str, text: str) -> tuple[int, dict]:
    """POST to Anthropic; return (status_code, response_json).

    Raises httpx.TimeoutException, httpx.ConnectError, etc. on
    transport failure. Caller catches and converts to a retryable
    error string.
    """
    async with httpx.AsyncClient(timeout=_ANTHROPIC_TIMEOUT_S) as client:
        r = await client.post(
            _ANTHROPIC_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": _DEMO_MODEL,
                "max_tokens": _ANTHROPIC_MAX_TOKENS,
                "messages": [{
                    "role": "user",
                    "content": (
                        "Summarize this document in 2-3 sentences. "
                        "Do not speculate beyond the text:\n\n" + text
                    ),
                }],
            },
        )
    if r.status_code >= 400:
        return r.status_code, {}
    return r.status_code, r.json()


async def _process_one_job(
    db_path: Optional[str],
    anthropic_call: Callable[[str, str], Awaitable[tuple[int, dict]]],
) -> bool:
    """Claim and process one queued job. Return True if a job was
    handled (regardless of outcome), False if the queue had nothing
    due. Single-in-flight contract: caller holds the worker lock.
    """
    job = summary_queue.claim_next_job(db_path=db_path)
    if job is None:
        return False
    job_id = job["job_id"]
    text = job["extracted_text"]
    attempts_so_far = job["attempts"]

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # Should not normally happen because the demo handler short-
        # circuits on missing key without enqueueing. If a job was
        # enqueued under a key that has since been removed, treat
        # the missing key as a retryable error (the operator may
        # restore the key). Do not mark permanent.
        summary_queue.mark_failed_retry(
            job_id, "anthropic_key_missing", attempts_so_far,
            db_path=db_path,
        )
        return True

    try:
        status, data = await anthropic_call(api_key, text)
    except httpx.TimeoutException:
        summary_queue.mark_failed_retry(
            job_id, "anthropic_timeout", attempts_so_far,
            db_path=db_path,
        )
        if summary_queue.is_past_permanent_cutoff(job_id, db_path=db_path):
            summary_queue.mark_permanent_failure(
                job_id, "anthropic_timeout (permanent after 24h)",
                db_path=db_path,
            )
        return True
    except (httpx.ConnectError, httpx.NetworkError, httpx.HTTPError) as exc:
        summary_queue.mark_failed_retry(
            job_id, f"anthropic_network: {type(exc).__name__}",
            attempts_so_far, db_path=db_path,
        )
        if summary_queue.is_past_permanent_cutoff(job_id, db_path=db_path):
            summary_queue.mark_permanent_failure(
                job_id, "anthropic_network (permanent after 24h)",
                db_path=db_path,
            )
        return True
    except Exception as exc:  # noqa: BLE001 - worker robustness
        # Any other exception: treat as a retryable error so the loop
        # does not die. The privacy contract still holds: extracted_text
        # is in the queue, not in this log line.
        logger.warning(
            "summary_worker: unexpected exception processing job %s: %s",
            job_id, type(exc).__name__,
        )
        summary_queue.mark_failed_retry(
            job_id, f"anthropic_error: {type(exc).__name__}",
            attempts_so_far, db_path=db_path,
        )
        if summary_queue.is_past_permanent_cutoff(job_id, db_path=db_path):
            summary_queue.mark_permanent_failure(
                job_id, "anthropic_error (permanent after 24h)",
                db_path=db_path,
            )
        return True

    # HTTP-level outcomes
    if status >= 400:
        if status in _RETRYABLE_4XX or status >= 500:
            summary_queue.mark_failed_retry(
                job_id, f"anthropic_status_{status}",
                attempts_so_far, db_path=db_path,
            )
            if summary_queue.is_past_permanent_cutoff(
                job_id, db_path=db_path
            ):
                summary_queue.mark_permanent_failure(
                    job_id,
                    f"anthropic_status_{status} (permanent after 24h)",
                    db_path=db_path,
                )
            return True
        # Hard 4xx (other than 408/425/429): permanent immediately.
        summary_queue.mark_permanent_failure(
            job_id, f"anthropic_status_{status}", db_path=db_path,
        )
        return True

    # 2xx: extract the summary text.
    try:
        summary_text = data["content"][0]["text"]
    except (KeyError, IndexError, TypeError) as exc:
        # Malformed 2xx body: treat as retryable. Should be rare.
        summary_queue.mark_failed_retry(
            job_id, f"anthropic_malformed_response: {type(exc).__name__}",
            attempts_so_far, db_path=db_path,
        )
        return True
    summary_queue.mark_delivered(job_id, summary_text, db_path=db_path)
    return True


async def worker_loop(
    wakeup_event: asyncio.Event,
    db_path: Optional[str] = None,
    anthropic_call: Optional[
        Callable[[str, str], Awaitable[tuple[int, dict]]]
    ] = None,
) -> None:
    """Run the worker loop until cancelled.

    Process at most one job per iteration. After each iteration:
      1. Run the janitor pass (delete terminal rows past the TTL).
      2. Compute the soonest next_retry_at; sleep until then or until
         the wakeup event fires, whichever comes first.

    The wakeup_event is set by the demo handler whenever a new job
    is enqueued, so the worker drains opportunistically without
    waiting for the timer.

    The anthropic_call argument exists for tests; production passes
    None and the loop uses _call_anthropic.
    """
    if anthropic_call is None:
        anthropic_call = _call_anthropic

    # Recovery sweep on entry.
    n_recovered = summary_queue.recovery_sweep(db_path=db_path)
    if n_recovered:
        logger.info(
            "summary_worker: recovery sweep reverted %d in_flight rows "
            "to queued", n_recovered,
        )

    lock = asyncio.Lock()

    while True:
        try:
            async with lock:
                handled = await _process_one_job(db_path, anthropic_call)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - loop robustness
            logger.warning(
                "summary_worker: unexpected loop error: %s",
                type(exc).__name__,
            )

        try:
            summary_queue.janitor_pass(db_path=db_path)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - loop robustness
            logger.warning(
                "summary_worker: janitor error: %s", type(exc).__name__,
            )

        # Compute sleep timeout.
        wakeup_event.clear()
        soonest = summary_queue.soonest_next_retry_at(db_path=db_path)
        if soonest is None:
            timeout = _IDLE_SLEEP_SECONDS
        else:
            now = summary_queue._utc_now()
            delta = (soonest - now).total_seconds()
            timeout = max(0.0, min(delta, _IDLE_SLEEP_SECONDS))

        # Race the wakeup event against the timer. The timer goes
        # through _sleep so tests that monkeypatch _sleep collapse the
        # wait to instantaneous; production uses real asyncio.sleep.
        sleep_task = asyncio.create_task(_sleep(timeout))
        wait_task = asyncio.create_task(wakeup_event.wait())
        try:
            done, pending = await asyncio.wait(
                {sleep_task, wait_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            sleep_task.cancel()
            wait_task.cancel()
            raise
        for t in pending:
            t.cancel()
        # Drain any cancellations.
        for t in pending:
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

        # Defensive minimum yield so a runaway error path cannot hot-
        # loop. Uses _sleep (the test-injectable alias).
        await _sleep(0)


__all__ = [
    "_sleep",
    "_call_anthropic",
    "_process_one_job",
    "worker_loop",
]
