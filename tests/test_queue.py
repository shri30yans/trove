"""The queue's Python-side decisions: what each transition resolves to, and which SQL it binds.

These tests drive the real functions through a recording connection, so they prove the branch taken,
the statements issued and the values bound to them. They do not prove Postgres accepts the SQL; that
needs a database, which local.env does not currently point at.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import pathlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app import queue
from app.domain.enums import JobResolution, JobStatus

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

USER_ID = str(uuid.UUID("11111111-1111-4111-8111-111111111111"))
MEMORY_ID = str(uuid.UUID("22222222-2222-4222-8222-222222222222"))
LEASE_ID = str(uuid.UUID("33333333-3333-4333-8333-333333333333"))

# The one statement that retires a job, now that every caller goes through queue.complete_job.
COMPLETE_JOB_STATEMENT = (
    "UPDATE memory_processing_jobs SET status=$4, lease_token=NULL, lease_expires_at=NULL, "
    "last_error=NULL, updated_at=now() WHERE memory_id=$1 AND user_id=$2 AND lease_token=$3::uuid"
)


class RecordingConnection:
    """Stands in for an asyncpg connection: records statements, replays canned rows in order."""

    def __init__(self, *, fetch_rows: list[list[Any]] | None = None, fetchrow_rows: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetch_rows = fetch_rows or []
        self.fetchrow_rows = fetchrow_rows or []

    @property
    def statements(self) -> list[str]:
        return [" ".join(sql.split()) for _, sql, _ in self.calls]

    @property
    def bindings(self) -> list[tuple[Any, ...]]:
        return [args for _, _, args in self.calls]

    async def execute(self, sql: str, *args: Any) -> None:
        self.calls.append(("execute", sql, args))

    async def fetchrow(self, sql: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", sql, args))
        return self.fetchrow_rows.pop(0) if self.fetchrow_rows else None

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", sql, args))
        return self.fetch_rows.pop(0) if self.fetch_rows else []


@contextlib.asynccontextmanager
async def _transaction(connection: RecordingConnection) -> AsyncIterator[RecordingConnection]:
    yield connection


@pytest.fixture
def connection(monkeypatch: pytest.MonkeyPatch) -> RecordingConnection:
    """A recording connection that app.queue's transaction() hands out."""
    fake = RecordingConnection()
    monkeypatch.setattr(queue, "transaction", lambda: _transaction(fake))
    return fake


def make_job(attempt_count: int = 1) -> queue.ClaimedJob:
    return queue.ClaimedJob(memory_id=MEMORY_ID, user_id=USER_ID, lease_token=LEASE_ID, attempt_count=attempt_count)


async def test_an_empty_batch_never_reaches_the_database(connection: RecordingConnection) -> None:
    await queue.enqueue_memory_processing(connection, uuid.UUID(USER_ID), [])
    assert connection.calls == []


async def test_a_staggered_batch_is_spread_from_now_in_ordinality_order(connection: RecordingConnection) -> None:
    await queue.enqueue_memory_processing(connection, uuid.UUID(USER_ID), [MEMORY_ID], stagger_seconds=3.0)
    statement = connection.statements[0]
    assert "WITH ORDINALITY" in statement
    assert "make_interval(secs => (input.job_ordinal - 1) * $3::double precision)" in statement
    assert connection.bindings[0] == (uuid.UUID(USER_ID), [uuid.UUID(MEMORY_ID)], 3.0)


async def test_an_unstaggered_batch_is_available_immediately(connection: RecordingConnection) -> None:
    await queue.enqueue_memory_processing(connection, uuid.UUID(USER_ID), [MEMORY_ID])
    assert connection.bindings[0][2] == 0.0


async def test_requeueing_only_arms_a_job_that_already_finished(connection: RecordingConnection) -> None:
    await queue.enqueue_memory_processing(connection, uuid.UUID(USER_ID), [MEMORY_ID])
    statement = connection.statements[0]
    assert "ON CONFLICT (memory_id) DO UPDATE" in statement
    # A queued or processing job keeps its own availability and attempt count.
    assert "WHERE memory_processing_jobs.status IN ('completed', 'failed')" in statement
    assert "attempt_count=0" in statement


SPACE = "embeddinggemma-2-space"


async def test_the_reconcile_sweep_only_arms_embedding_enabled_memories_without_vectors(
    connection: RecordingConnection,
) -> None:
    connection.fetch_rows = [[{"memory_id": uuid.UUID(MEMORY_ID), "user_id": uuid.UUID(USER_ID)}]]
    count = await queue.enqueue_memories_needing_embedding(
        connection, SPACE, limit=500, stagger_seconds=3.0, failure_cooldown_hours=24.0
    )
    assert count == 1
    sweep = connection.statements[0]
    assert "JOIN user_preferences p ON p.user_id=m.user_id AND p.embeddings_enabled" in sweep
    assert "e.memory_id=m.id AND e.embedding_space=$1" in sweep
    assert "e.asset_id=a.id AND e.embedding_space=$1" in sweep
    assert "memory_processing_jobs.status IN ('completed', 'failed')" in sweep
    assert connection.bindings[0] == (SPACE, 500, dt.timedelta(hours=24), 3.0)


async def test_the_reconcile_sweep_leaves_recent_failures_alone(connection: RecordingConnection) -> None:
    connection.fetch_rows = [[]]
    count = await queue.enqueue_memories_needing_embedding(
        connection, SPACE, limit=500, stagger_seconds=3.0, failure_cooldown_hours=24.0
    )
    assert count == 0
    sweep = connection.statements[0]
    assert "recent_failure.updated_at > now() - $3::interval" in sweep
    # Nothing was armed, so no memory may flip to queued.
    assert [kind for kind, _, _ in connection.calls] == ["fetch"]


async def test_the_reconcile_sweep_spreads_and_requeues_its_batch(connection: RecordingConnection) -> None:
    connection.fetch_rows = [[{"memory_id": uuid.UUID(MEMORY_ID), "user_id": uuid.UUID(USER_ID)}]]
    await queue.enqueue_memories_needing_embedding(
        connection, SPACE, limit=500, stagger_seconds=3.0, failure_cooldown_hours=24.0
    )
    sweep = connection.statements[0]
    assert "row_number() OVER (ORDER BY m.created_at, m.id) AS job_ordinal" in sweep
    assert "make_interval(secs => (job_ordinal - 1) * $4::double precision)" in sweep
    requeue = connection.statements[1]
    assert "UPDATE memories m SET status='queued', processing_error=NULL" in requeue
    assert "m.status IN ('ready','failed')" in requeue
    assert connection.bindings[1] == ([uuid.UUID(MEMORY_ID)], [uuid.UUID(USER_ID)])


async def test_only_the_lease_holder_can_complete_a_job(connection: RecordingConnection) -> None:
    await queue.complete_job(connection, make_job())
    statement = connection.statements[0]
    assert "status=$4" in statement
    assert "lease_token=$3::uuid" in statement
    assert "user_id=$2" in statement
    assert connection.bindings[0] == (uuid.UUID(MEMORY_ID), uuid.UUID(USER_ID), uuid.UUID(LEASE_ID), "completed")


async def test_a_job_whose_lease_is_gone_is_left_alone(connection: RecordingConnection) -> None:
    resolution = await queue.complete_missing_memory_job(make_job())
    assert resolution is JobResolution.LEASE_LOST
    # The first SELECT is the lease check; nothing is written once it fails.
    assert [kind for kind, _, _ in connection.calls] == ["fetchrow"]


async def test_a_memory_that_is_still_present_is_put_back_on_the_queue(connection: RecordingConnection) -> None:
    connection.fetchrow_rows = [{"memory_id": MEMORY_ID}, {"deleted_at": None}]
    resolution = await queue.complete_missing_memory_job(make_job())
    assert resolution is JobResolution.REQUEUED
    assert len(connection.calls) == 4
    assert "UPDATE memories SET status='queued', processing_error=NULL" in connection.statements[2]
    requeue = connection.statements[3]
    assert "attempt_count=GREATEST(attempt_count-1,0)" in requeue
    assert "available_at=now()" in requeue
    assert "lease_token=$3::uuid" in requeue


async def test_a_deleted_memory_retires_the_job(connection: RecordingConnection) -> None:
    connection.fetchrow_rows = [{"memory_id": MEMORY_ID}, None]
    resolution = await queue.complete_missing_memory_job(make_job())
    assert resolution is JobResolution.COMPLETED
    assert connection.statements[-1] == COMPLETE_JOB_STATEMENT
    assert connection.bindings[-1] == (
        uuid.UUID(MEMORY_ID),
        uuid.UUID(USER_ID),
        uuid.UUID(LEASE_ID),
        JobStatus.COMPLETED.value,
    )


async def test_a_claim_on_a_deleted_memory_completes_the_job_without_returning_it(
    connection: RecordingConnection,
) -> None:
    connection.fetch_rows = [
        [
            {
                "memory_id": MEMORY_ID,
                "user_id": USER_ID,
                "lease_token": LEASE_ID,
                "attempt_count": 1,
                "reindex_only": False,
            }
        ]
    ]
    assert await queue.claim_memory_processing_job() is None
    assert connection.bindings[-1] == (
        uuid.UUID(MEMORY_ID),
        uuid.UUID(USER_ID),
        uuid.UUID(LEASE_ID),
        JobStatus.COMPLETED.value,
    )


async def test_an_empty_claim_writes_nothing(connection: RecordingConnection) -> None:
    assert await queue.claim_memory_processing_job() is None
    assert [kind for kind, _, _ in connection.calls] == ["fetch"]


async def test_a_claim_hands_back_the_job_and_marks_the_memory_processing(connection: RecordingConnection) -> None:
    connection.fetch_rows = [
        [
            {
                "memory_id": MEMORY_ID,
                "user_id": USER_ID,
                "lease_token": LEASE_ID,
                "attempt_count": 2,
                "reindex_only": False,
            }
        ]
    ]
    connection.fetchrow_rows = [{"id": MEMORY_ID}]
    job = await queue.claim_memory_processing_job()
    assert job is not None
    assert (job.memory_id, job.user_id, job.lease_token, job.attempt_count) == (MEMORY_ID, USER_ID, LEASE_ID, 2)
    assert "UPDATE memories SET status='processing', processing_error=NULL" in connection.statements[1]
    assert connection.bindings[1] == (uuid.UUID(MEMORY_ID), uuid.UUID(USER_ID))


class FakePool:
    def __init__(self, value: Any) -> None:
        self.value = value
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.calls.append((" ".join(sql.split()), args))
        return self.value


async def test_renewing_a_lease_only_extends_the_current_holder(monkeypatch: pytest.MonkeyPatch) -> None:
    pool = FakePool(MEMORY_ID)
    monkeypatch.setattr(queue, "get_pool", lambda: pool)
    assert await queue.renew_memory_processing_lease(make_job()) is True
    statement, args = pool.calls[0]
    assert "status='processing'" in statement
    assert "lease_token=$3::uuid" in statement
    assert args == (uuid.UUID(MEMORY_ID), uuid.UUID(USER_ID), uuid.UUID(LEASE_ID), queue.LEASE_SECONDS)


async def test_a_renewal_that_matches_no_row_means_the_lease_moved(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(queue, "get_pool", lambda: FakePool(None))
    assert await queue.renew_memory_processing_lease(make_job()) is False


async def test_a_first_failure_is_retried_with_backoff(connection: RecordingConnection) -> None:
    connection.fetchrow_rows = [{"memory_id": MEMORY_ID}]
    resolution = await queue.retry_or_fail_memory_processing_job(make_job(1), "TimeoutError", 4)
    assert resolution is JobResolution.REQUEUED
    assert connection.bindings[0][3] == JobStatus.QUEUED.value
    assert connection.bindings[0][4] == 2_000.0


async def test_the_backoff_doubles_with_the_attempt_count(connection: RecordingConnection) -> None:
    connection.fetchrow_rows = [{"memory_id": MEMORY_ID}]
    await queue.retry_or_fail_memory_processing_job(make_job(3), "EmbeddingError", 4)
    assert connection.bindings[0][4] == 8_000.0


async def test_exhausting_the_attempts_fails_the_job(connection: RecordingConnection) -> None:
    connection.fetchrow_rows = [{"memory_id": MEMORY_ID}]
    resolution = await queue.retry_or_fail_memory_processing_job(make_job(4), "AssetIntegrityError", 4)
    assert resolution is JobResolution.FAILED
    assert connection.bindings[0][3] == JobStatus.FAILED.value
    # The delay is still bound, but the statement's CASE only moves available_at when status is queued.
    assert "CASE WHEN $4='queued'" in connection.statements[0]
    assert "UPDATE memories SET status=$3" in connection.statements[1]


async def test_losing_the_lease_wins_over_the_retry_decision(connection: RecordingConnection) -> None:
    resolution = await queue.retry_or_fail_memory_processing_job(make_job(1), "TimeoutError", 4)
    assert resolution is JobResolution.LEASE_LOST
    assert [kind for kind, _, _ in connection.calls] == ["fetchrow"]


async def test_a_long_error_code_is_cut_to_the_column_width(connection: RecordingConnection) -> None:
    connection.fetchrow_rows = [{"memory_id": MEMORY_ID}]
    await queue.retry_or_fail_memory_processing_job(make_job(1), "E" * 200, 4)
    assert connection.bindings[0][5] == "E" * 80
    assert connection.bindings[1][3] == "E" * 80


def test_the_resolutions_are_the_four_outcomes_a_claim_loop_distinguishes() -> None:
    assert {resolution.value for resolution in JobResolution} == {
        "requeued",
        "completed",
        "failed",
        "lease_lost",
    }


def test_no_module_retypies_the_retire_statement() -> None:
    """The copies that existed before queue.complete_job had already drifted, one of them dropping
    last_error=NULL. A fourth spelling of the same UPDATE is a bug waiting to happen again."""
    sources = {path.name: path.read_text(encoding="utf-8") for path in (REPO_ROOT / "app").rglob("*.py")}
    retyped = [name for name, source in sources.items() if "status='completed', lease_token=NULL" in source]
    assert retyped == []


def test_no_module_retypies_the_rearm_guard() -> None:
    sources = {path.name: path.read_text(encoding="utf-8") for path in (REPO_ROOT / "app").rglob("*.py")}
    marker = "attempt_count=0, available_at=excluded.available_at"
    copies = [name for name, source in sources.items() if marker in source]
    assert copies == ["queue.py"]
