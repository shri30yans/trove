"""What the queue loop decides to do about a failure.

Retrying is the right default for a network or model hiccup and the wrong default for an error whose
cause is the stored bytes themselves: a second attempt downloads and decodes the same input.
"""

from __future__ import annotations

import asyncio
import contextlib
import types
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app import worker
from app.domain.enums import JobResolution
from app.domain.indexing import REINDEX_BATCH_LIMIT, REINDEX_RETRY_COOLDOWN_HOURS, REINDEX_STAGGER_SECONDS
from app.embedding import UnsupportedImage
from app.process_memory import AssetIntegrityError
from app.queue import ClaimedJob


class Recorder:
    def __init__(self, result: Any = JobResolution.FAILED) -> None:
        self.result = result
        self.calls: list[tuple[ClaimedJob, str, int]] = []

    async def __call__(self, job: ClaimedJob, error_code: str, max_attempts: int) -> Any:
        self.calls.append((job, error_code, max_attempts))
        return self.result


def make_job(attempt_count: int = 1) -> ClaimedJob:
    return ClaimedJob(
        memory_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        lease_token=str(uuid.uuid4()),
        attempt_count=attempt_count,
    )


@pytest.fixture
def retry(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    recorder = Recorder()
    monkeypatch.setattr(worker, "retry_or_fail_memory_processing_job", recorder)
    return recorder


async def test_a_corrupt_asset_fails_without_retried_attempts(monkeypatch: pytest.MonkeyPatch, retry: Recorder) -> None:
    async def fail(job: ClaimedJob) -> None:
        raise AssetIntegrityError("checksum mismatch")

    monkeypatch.setattr(worker, "process_memory", fail)
    await worker._process_claimed_job(make_job())
    assert retry.calls[0][2] == 1
    assert retry.calls[0][1] == "AssetIntegrityError"


async def test_an_undecodable_image_fails_without_retried_attempts(
    monkeypatch: pytest.MonkeyPatch, retry: Recorder
) -> None:
    async def fail(job: ClaimedJob) -> None:
        raise UnsupportedImage("not a supported image")

    monkeypatch.setattr(worker, "process_memory", fail)
    await worker._process_claimed_job(make_job())
    assert retry.calls[0][2] == 1


async def test_a_transient_failure_keeps_the_full_attempt_budget(
    monkeypatch: pytest.MonkeyPatch, retry: Recorder
) -> None:
    async def fail(job: ClaimedJob) -> None:
        raise TimeoutError("the page did not answer")

    monkeypatch.setattr(worker, "process_memory", fail)
    await worker._process_claimed_job(make_job())
    assert retry.calls[0][2] == worker.MAX_ATTEMPTS


async def test_a_successful_run_reschedules_nothing(monkeypatch: pytest.MonkeyPatch, retry: Recorder) -> None:
    ran: list[str] = []

    async def succeed(job: ClaimedJob) -> None:
        ran.append(job.memory_id)

    monkeypatch.setattr(worker, "process_memory", succeed)
    job = make_job()
    await worker._process_claimed_job(job)
    assert ran == [job.memory_id]
    assert retry.calls == []


async def test_a_job_past_its_attempts_fails_before_any_work_starts(
    monkeypatch: pytest.MonkeyPatch, retry: Recorder
) -> None:
    async def never(job: ClaimedJob) -> None:
        raise AssertionError("a job over its attempt budget must not be processed")

    monkeypatch.setattr(worker, "process_memory", never)
    await worker._process_claimed_job(make_job(worker.MAX_ATTEMPTS + 1))
    assert retry.calls[0][1] == "processing_attempts_exhausted"


@contextlib.asynccontextmanager
async def _fake_transaction() -> AsyncIterator[None]:
    yield None


class SweepRecorder:
    def __init__(self, stopping: asyncio.Event, *, raises: bool = False) -> None:
        self.stopping = stopping
        self.raises = raises
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, _connection: Any, space_id: str, **kwargs: Any) -> int:
        self.calls.append((space_id, kwargs))
        self.stopping.set()
        if self.raises:
            raise TimeoutError("the database hiccupped")
        return 7


async def test_a_reconcile_sweep_arms_missing_embeddings_with_the_batching_vocabulary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stopping = asyncio.Event()
    sweep = SweepRecorder(stopping)
    model_set = types.SimpleNamespace(space_id="embeddinggemma-2-space")
    monkeypatch.setattr(worker.embeddings, "models", lambda: model_set)
    monkeypatch.setattr(worker, "transaction", _fake_transaction)
    monkeypatch.setattr(worker, "enqueue_memories_needing_embedding", sweep)

    await asyncio.wait_for(worker._run_reconcile(stopping), timeout=5)

    space_id, kwargs = sweep.calls[0]
    assert space_id == "embeddinggemma-2-space"
    assert kwargs == {
        "limit": REINDEX_BATCH_LIMIT,
        "stagger_seconds": REINDEX_STAGGER_SECONDS,
        "failure_cooldown_hours": REINDEX_RETRY_COOLDOWN_HOURS,
    }


async def test_a_reconcile_sweep_failure_is_caught_so_the_next_sweep_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    stopping = asyncio.Event()
    sweep = SweepRecorder(stopping, raises=True)
    model_set = types.SimpleNamespace(space_id="embeddinggemma-2-space")
    monkeypatch.setattr(worker.embeddings, "models", lambda: model_set)
    monkeypatch.setattr(worker, "transaction", _fake_transaction)
    monkeypatch.setattr(worker, "enqueue_memories_needing_embedding", sweep)

    await asyncio.wait_for(worker._run_reconcile(stopping), timeout=5)

    assert len(sweep.calls) == 1


async def test_the_embedding_reconcile_runs_alongside_the_workers(monkeypatch: pytest.MonkeyPatch) -> None:
    async def idle(stopping: asyncio.Event) -> None:
        await stopping.wait()

    monkeypatch.setattr(worker, "_run_worker", idle)
    monkeypatch.setattr(worker, "_run_reconcile", idle)

    queue = worker.MemoryQueue()
    queue.start()
    names = [runner.get_name() for runner in queue._runners]
    await queue.stop()

    assert "trove-queue-reconcile" in names
    assert (
        sum(name.startswith("trove-queue-") and name != "trove-queue-reconcile" for name in names) == worker.CONCURRENCY
    )
