"""The Postgres-backed memory processing queue: enqueue, claim, renew, retry, complete."""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import asyncpg

from app.db import fetchrow, get_pool, transaction
from app.domain.enums import JobResolution, JobStatus

LEASE_SECONDS = 120

# The single spelling of "a finished job can be re-armed with a fresh availability". Both enqueue
# paths interpolate this; a second hand-typed copy previously drifted exactly like the retire
# statement that tests_no_module guards against.
_REARM_FINISHED_JOBS = """ON CONFLICT (memory_id) DO UPDATE SET
             status='queued', attempt_count=0, available_at=excluded.available_at, lease_token=NULL,
             lease_expires_at=NULL, last_error=NULL, reindex_only=false, updated_at=now()
           WHERE memory_processing_jobs.status IN ('completed', 'failed')"""


@dataclass(frozen=True)
class ClaimedJob:
    memory_id: str
    user_id: str
    lease_token: str
    attempt_count: int
    reindex_only: bool = False

    @property
    def memory_uuid(self) -> uuid.UUID:
        return uuid.UUID(self.memory_id)

    @property
    def user_uuid(self) -> uuid.UUID:
        return uuid.UUID(self.user_id)

    @property
    def lease_uuid(self) -> uuid.UUID:
        return uuid.UUID(self.lease_token)


def _uuids(values: Sequence[str]) -> list[uuid.UUID]:
    return [uuid.UUID(value) for value in values]


async def enqueue_memory_processing(
    connection: asyncpg.Connection,
    user_id: uuid.UUID,
    memory_ids: Sequence[str],
    *,
    stagger_seconds: float = 0.0,
) -> None:
    """Queue a memory, re-arming it when a previous run already finished.

    stagger_seconds pushes a large batch into the future. The queue claims by available_at, so
    a reindex that is all available now would put a fresh capture behind thousands of jobs.
    """
    if not memory_ids:
        return
    await connection.execute(
        f"""INSERT INTO memory_processing_jobs (memory_id, user_id, available_at)
           SELECT input.memory_id, $1,
                  now() + make_interval(secs => (input.job_ordinal - 1) * $3::double precision)
           FROM unnest($2::uuid[]) WITH ORDINALITY AS input(memory_id, job_ordinal)
           {_REARM_FINISHED_JOBS}""",
        user_id,
        _uuids(memory_ids),
        stagger_seconds,
    )


async def enqueue_memories_needing_embedding(
    connection: asyncpg.Connection,
    space_id: str,
    *,
    limit: int,
    stagger_seconds: float,
    failure_cooldown_hours: float,
) -> int:
    """Queue one batch of opted-in memories that have no embeddings yet.

    This is the sweep that makes "embedding search on implies eventually indexed" an invariant of
    the queue itself rather than a side effect of whichever route happened to flip the flag.
    Failures inside the cooldown are left alone so a broken memory cannot re-burn provider calls
    every sweep. Returns the number of jobs actually armed.
    """
    enqueued = await connection.fetch(
        f"""WITH candidates AS (
             SELECT m.id, m.user_id, row_number() OVER (ORDER BY m.created_at, m.id) AS job_ordinal
             FROM memories m
             JOIN user_preferences p ON p.user_id=m.user_id AND p.embeddings_enabled
             WHERE m.deleted_at IS NULL AND m.status IN ('ready','failed')
               AND (
                 (
                   (COALESCE(m.title,'') || COALESCE(m.description,'') || COALESCE(m.user_note,'') ||
                     COALESCE(m.content_text,'') || COALESCE(m.page_text,'')) <> ''
                   AND NOT EXISTS (
                     SELECT 1 FROM embeddings e WHERE e.memory_id=m.id AND e.embedding_space=$1
                   )
                 )
                 OR EXISTS (
                   SELECT 1 FROM memory_assets ma
                   JOIN assets a ON a.id=ma.asset_id AND a.user_id=ma.user_id
                   WHERE ma.memory_id=m.id AND ma.user_id=m.user_id AND a.mime_type LIKE 'image/%'
                     AND NOT EXISTS (
                       SELECT 1 FROM embeddings e WHERE e.asset_id=a.id AND e.embedding_space=$1
                     )
                 )
               )
               AND NOT EXISTS (
                 SELECT 1 FROM memory_processing_jobs recent_failure
                 WHERE recent_failure.memory_id=m.id AND recent_failure.status='failed'
                   AND recent_failure.updated_at > now() - $3::interval
               )
             ORDER BY m.created_at, m.id LIMIT $2
           )
           INSERT INTO memory_processing_jobs (memory_id, user_id, available_at)
           SELECT id, user_id,
                  now() + make_interval(secs => (job_ordinal - 1) * $4::double precision)
           FROM candidates
           {_REARM_FINISHED_JOBS}
           RETURNING memory_id, user_id""",
        space_id,
        limit,
        dt.timedelta(hours=failure_cooldown_hours),
        stagger_seconds,
    )
    if enqueued:
        await connection.execute(
            """UPDATE memories m
               SET status='queued', processing_error=NULL, updated_at=now()
               FROM unnest($1::uuid[],$2::uuid[]) AS hit(memory_id,user_id)
               WHERE m.id=hit.memory_id AND m.user_id=hit.user_id
                 AND m.deleted_at IS NULL AND m.status IN ('ready','failed')""",
            [row["memory_id"] for row in enqueued],
            [row["user_id"] for row in enqueued],
        )
    return len(enqueued)


async def claim_memory_processing_job() -> ClaimedJob | None:
    lease_token = uuid.uuid4()
    row = await fetchrow(
        """WITH candidate AS MATERIALIZED (
                 SELECT job.memory_id
                       , job.user_id
                 FROM memory_processing_jobs job
                 JOIN app_users account ON account.id=job.user_id
                 WHERE ((job.status='queued' AND job.available_at <= now())
                    OR (job.status='processing' AND job.lease_expires_at <= now()))
                   AND EXISTS (
                     SELECT 1 FROM memories memory
                     WHERE memory.id=job.memory_id AND memory.user_id=job.user_id AND memory.deleted_at IS NULL
                   )
                 ORDER BY (account.storage_plan='paid') DESC, job.available_at, job.created_at
                 LIMIT 1
                 FOR UPDATE OF job SKIP LOCKED
               ), activated_memory AS (
                 UPDATE memories memory
                 SET status='processing', processing_error=NULL, updated_at=now()
                 FROM candidate
                 WHERE memory.id=candidate.memory_id AND memory.user_id=candidate.user_id
                   AND memory.deleted_at IS NULL
                 RETURNING memory.id AS memory_id, memory.user_id
               ), claimed AS (
                 UPDATE memory_processing_jobs job
                 SET status=CASE WHEN active.memory_id IS NULL THEN 'completed' ELSE 'processing' END,
                     attempt_count=job.attempt_count + CASE WHEN active.memory_id IS NULL THEN 0 ELSE 1 END,
                     lease_token=CASE WHEN active.memory_id IS NULL THEN NULL ELSE $1::uuid END,
                     lease_expires_at=CASE WHEN active.memory_id IS NULL THEN NULL
                       ELSE now()+make_interval(secs => $2) END,
                     last_error=CASE WHEN active.memory_id IS NULL THEN NULL ELSE job.last_error END,
                     updated_at=now()
                 FROM candidate
                 LEFT JOIN activated_memory active
                   ON active.memory_id=candidate.memory_id AND active.user_id=candidate.user_id
                 WHERE job.memory_id=candidate.memory_id AND job.user_id=candidate.user_id
                 RETURNING job.memory_id, job.user_id, job.lease_token, job.attempt_count,
                   job.reindex_only, active.memory_id IS NOT NULL AS memory_claimed
               )
               SELECT memory_id, user_id, lease_token, attempt_count, reindex_only
               FROM claimed WHERE memory_claimed""",
        lease_token,
        LEASE_SECONDS,
    )
    if row is None:
        return None
    return ClaimedJob(
        memory_id=str(row["memory_id"]),
        user_id=str(row["user_id"]),
        lease_token=str(row["lease_token"]),
        attempt_count=int(row["attempt_count"]),
        reindex_only=bool(row["reindex_only"]),
    )


async def complete_job(connection: asyncpg.Connection, job: ClaimedJob) -> None:
    """One job reached a terminal state: retire it and drop the lease so a stale worker is fenced."""
    await connection.execute(
        """UPDATE memory_processing_jobs
           SET status=$4, lease_token=NULL, lease_expires_at=NULL, last_error=NULL, updated_at=now()
           WHERE memory_id=$1 AND user_id=$2 AND lease_token=$3::uuid""",
        job.memory_uuid,
        job.user_uuid,
        job.lease_uuid,
        JobStatus.COMPLETED.value,
    )


async def renew_memory_processing_lease(job: ClaimedJob) -> bool:
    renewed = await get_pool().fetchval(
        """UPDATE memory_processing_jobs
           SET lease_expires_at=now()+make_interval(secs => $4), updated_at=now()
           WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
           RETURNING memory_id""",
        job.memory_uuid,
        job.user_uuid,
        job.lease_uuid,
        LEASE_SECONDS,
    )
    return renewed is not None


async def complete_missing_memory_job(job: ClaimedJob) -> JobResolution:
    """Resolve a job whose memory disappeared: re-arm it, or finish it if the row is gone."""
    async with transaction() as connection:
        held = await connection.fetchrow(
            """SELECT memory_id FROM memory_processing_jobs
               WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
               FOR UPDATE""",
            job.memory_uuid,
            job.user_uuid,
            job.lease_uuid,
        )
        if held is None:
            return JobResolution.LEASE_LOST

        memory = await connection.fetchrow(
            "SELECT deleted_at FROM memories WHERE id=$1 AND user_id=$2 FOR UPDATE",
            job.memory_uuid,
            job.user_uuid,
        )
        if memory is not None and memory["deleted_at"] is None:
            await connection.execute(
                """UPDATE memories SET status='queued', processing_error=NULL, updated_at=now()
                   WHERE id=$1 AND user_id=$2""",
                job.memory_uuid,
                job.user_uuid,
            )
            await connection.execute(
                """UPDATE memory_processing_jobs
                   SET status='queued', attempt_count=GREATEST(attempt_count-1,0), available_at=now(),
                       lease_token=NULL, lease_expires_at=NULL, last_error=NULL, updated_at=now()
                   WHERE memory_id=$1 AND user_id=$2 AND lease_token=$3::uuid""",
                job.memory_uuid,
                job.user_uuid,
                job.lease_uuid,
            )
            return JobResolution.REQUEUED

        await complete_job(connection, job)
        return JobResolution.COMPLETED


async def retry_or_fail_memory_processing_job(job: ClaimedJob, error_code: str, max_attempts: int) -> JobResolution:
    retry = job.attempt_count < max_attempts
    delay = dt.timedelta(milliseconds=2_000 * 2 ** max(0, job.attempt_count - 1))
    status = JobStatus.QUEUED if retry else JobStatus.FAILED
    async with transaction() as connection:
        updated = await connection.fetchrow(
            """UPDATE memory_processing_jobs
               SET status=$4, available_at=CASE WHEN $4='queued' THEN now()+($5 * interval '1 millisecond') ELSE available_at END,
                   lease_token=NULL, lease_expires_at=NULL, last_error=$6, updated_at=now()
               WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
               RETURNING memory_id""",
            job.memory_uuid,
            job.user_uuid,
            job.lease_uuid,
            status.value,
            float(delay.total_seconds() * 1000),
            error_code[:80],
        )
        if updated is None:
            return JobResolution.LEASE_LOST

        await connection.execute(
            """UPDATE memories SET status=$3, processing_error=$4, updated_at=now()
               WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL""",
            job.memory_uuid,
            job.user_uuid,
            status.value,
            error_code[:80],
        )
        return JobResolution.REQUEUED if retry else JobResolution.FAILED
