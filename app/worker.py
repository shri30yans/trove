"""The background queue loop that claims and processes memories inside the API process."""

from __future__ import annotations

import asyncio
import contextlib
import logging

from app.db import transaction
from app.domain.indexing import REINDEX_BATCH_LIMIT, REINDEX_RETRY_COOLDOWN_HOURS, REINDEX_STAGGER_SECONDS
from app.embedding import PermanentEmbeddingError, embeddings
from app.process_memory import AssetIntegrityError, process_memory
from app.queue import (
    ClaimedJob,
    claim_memory_processing_job,
    enqueue_memories_needing_embedding,
    renew_memory_processing_lease,
    retry_or_fail_memory_processing_job,
)

# Keep one fixed, deliberately small processing ceiling. Paid-plan jobs are selected first by the
# shared Postgres queue; increasing worker count would raise model/storage pressure, not DB capacity.
CONCURRENCY = 2
MAX_ATTEMPTS = 4
POLL_INTERVAL_SECONDS = 0.8
LEASE_RENEW_INTERVAL_SECONDS = 30.0
RECONCILE_INTERVAL_SECONDS = 60.0

# A second attempt reads the same bytes and decodes the same image, so these end the job now instead
# of after four downloads, four model runs, and four backoffs.
PERMANENT_ERRORS = (AssetIntegrityError, PermanentEmbeddingError)

logger = logging.getLogger("trove.queue")


def _error_code(error: BaseException) -> str:
    return type(error).__name__[:80]


async def _renew_lease_while_working(job: ClaimedJob) -> None:
    while True:
        await asyncio.sleep(LEASE_RENEW_INTERVAL_SECONDS)
        try:
            if not await renew_memory_processing_lease(job):
                logger.warning("Memory job lease was reassigned for %s", job.memory_id)
        except Exception as error:  # noqa: BLE001 - the next attempt renews again
            logger.error("Could not renew memory job lease for %s: %s", job.memory_id, _error_code(error))


async def _process_claimed_job(job: ClaimedJob) -> None:
    heartbeat = asyncio.create_task(_renew_lease_while_working(job))
    try:
        if job.attempt_count > MAX_ATTEMPTS:
            await retry_or_fail_memory_processing_job(job, "processing_attempts_exhausted", MAX_ATTEMPTS)
            return
        await process_memory(job)
    except Exception as error:  # noqa: BLE001 - every failure is retried or failed in the queue
        code = _error_code(error)
        attempts = 1 if isinstance(error, PERMANENT_ERRORS) else MAX_ATTEMPTS
        result = await retry_or_fail_memory_processing_job(job, code, attempts)
        logger.error("Memory job %s %s (%s)", job.memory_id, result.value, code)
    finally:
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


async def _run_worker(stopping: asyncio.Event) -> None:
    while not stopping.is_set():
        # Keep queued memories pending when provider credentials are missing; don't burn retries.
        if not embeddings.ready:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=POLL_INTERVAL_SECONDS)
            continue

        try:
            job = await claim_memory_processing_job()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001 - keep polling through transient database errors
            logger.error("Memory queue polling failed: %s", _error_code(error))
            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            continue
        if job is None:
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(stopping.wait(), timeout=POLL_INTERVAL_SECONDS)
            continue
        await _process_claimed_job(job)


async def _run_reconcile(stopping: asyncio.Event) -> None:
    """Keep enabled memory libraries eventually embedded without route-specific repair logic.

    One sweep per interval lets the queue recover missing vectors after transient failures.
    """
    while not stopping.is_set():
        model_set = embeddings.models()
        if model_set is not None:
            try:
                async with transaction() as connection:
                    enqueued = await enqueue_memories_needing_embedding(
                        connection,
                        model_set.space_id,
                        limit=REINDEX_BATCH_LIMIT,
                        stagger_seconds=REINDEX_STAGGER_SECONDS,
                        failure_cooldown_hours=REINDEX_RETRY_COOLDOWN_HOURS,
                    )
                if enqueued:
                    logger.info("embedding_reconcile stage=sweep space=%s enqueued=%s", model_set.space_id, enqueued)
            except Exception as error:  # noqa: BLE001 - the next sweep retries the same work
                logger.error("embedding_reconcile stage=sweep outcome=failure error=%s", _error_code(error))
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stopping.wait(), timeout=RECONCILE_INTERVAL_SECONDS)


class MemoryQueue:
    def __init__(self) -> None:
        self._stopping: asyncio.Event | None = None
        self._runners: list[asyncio.Task[None]] = []

    def start(self) -> None:
        if self._runners:
            return
        self._stopping = asyncio.Event()
        self._runners = [
            asyncio.create_task(_run_worker(self._stopping), name=f"trove-queue-{index}")
            for index in range(CONCURRENCY)
        ]
        self._runners.append(asyncio.create_task(_run_reconcile(self._stopping), name="trove-queue-reconcile"))
        logger.info("Trove memory queue is ready with concurrency %s", CONCURRENCY)

    async def stop(self) -> None:
        if not self._runners:
            return
        assert self._stopping is not None
        self._stopping.set()
        runners, self._runners = self._runners, []
        await asyncio.gather(*runners, return_exceptions=True)


memory_queue = MemoryQueue()
