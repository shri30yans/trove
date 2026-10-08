import { randomUUID } from 'node:crypto';
import type { PoolClient } from 'pg';
import { pool } from './db/pool.js';

const LEASE_SECONDS = 120;

export type ClaimedMemoryJob = {
  memoryId: string;
  userId: string;
  leaseToken: string;
  attemptCount: number;
};

export async function enqueueMemoryProcessing(client: PoolClient, userId: string, memoryId: string) {
  await enqueueMemoryProcessingBatch(client, userId, [memoryId]);
}

export async function enqueueMemoryProcessingBatch(client: PoolClient, userId: string, memoryIds: string[]) {
  if (!memoryIds.length) return;
  await client.query(
    `INSERT INTO memory_processing_jobs (memory_id, user_id)
     SELECT input.memory_id, $1 FROM unnest($2::uuid[]) AS input(memory_id)
     ON CONFLICT (memory_id) DO UPDATE SET
       status='queued', attempt_count=0, available_at=now(), lease_token=NULL,
       lease_expires_at=NULL, last_error=NULL, updated_at=now()
     WHERE memory_processing_jobs.status IN ('completed', 'failed')`,
    [userId, memoryIds],
  );
}

export async function claimMemoryProcessingJob(): Promise<ClaimedMemoryJob | null> {
  const client = await pool.connect();
  const leaseToken = randomUUID();
  try {
    await client.query('BEGIN');
    const result = await client.query<{
      memory_id: string;
      user_id: string;
      lease_token: string;
      attempt_count: number;
    }>(
      `WITH candidate AS (
         SELECT job.memory_id
         FROM memory_processing_jobs job
         WHERE ((job.status='queued' AND job.available_at <= now())
            OR (job.status='processing' AND job.lease_expires_at <= now()))
           AND EXISTS (
             SELECT 1 FROM memories memory
             WHERE memory.id=job.memory_id AND memory.user_id=job.user_id AND memory.deleted_at IS NULL
           )
         ORDER BY job.available_at, job.created_at
         LIMIT 1
         FOR UPDATE SKIP LOCKED
       )
       UPDATE memory_processing_jobs job
       SET status='processing', attempt_count=job.attempt_count+1,
           lease_token=$1::uuid, lease_expires_at=now()+make_interval(secs => $2), updated_at=now()
       FROM candidate
       WHERE job.memory_id=candidate.memory_id
       RETURNING job.memory_id, job.user_id, job.lease_token, job.attempt_count`,
      [leaseToken, LEASE_SECONDS],
    );

    const row = result.rows[0];
    if (!row) {
      await client.query('COMMIT');
      return null;
    }

    const activeMemory = await client.query(
      `UPDATE memories SET status='processing', processing_error=NULL, updated_at=now()
       WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL RETURNING id`,
      [row.memory_id, row.user_id],
    );
    if (!activeMemory.rowCount) {
      await client.query(
        `UPDATE memory_processing_jobs
         SET status='completed', lease_token=NULL, lease_expires_at=NULL, updated_at=now()
         WHERE memory_id=$1 AND lease_token=$2::uuid`,
        [row.memory_id, row.lease_token],
      );
      await client.query('COMMIT');
      return null;
    }

    await client.query('COMMIT');
    return {
      memoryId: row.memory_id,
      userId: row.user_id,
      leaseToken: row.lease_token,
      attemptCount: Number(row.attempt_count),
    };
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}

export async function renewMemoryProcessingLease(job: ClaimedMemoryJob) {
  const result = await pool.query(
    `UPDATE memory_processing_jobs
     SET lease_expires_at=now()+make_interval(secs => $4), updated_at=now()
     WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
     RETURNING memory_id`,
    [job.memoryId, job.userId, job.leaseToken, LEASE_SECONDS],
  );
  return result.rowCount === 1;
}

export async function completeMissingMemoryJob(memoryId: string, userId: string, leaseToken: string) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const job = await client.query(
      `SELECT memory_id FROM memory_processing_jobs
       WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
       FOR UPDATE`,
      [memoryId, userId, leaseToken],
    );
    if (!job.rowCount) {
      await client.query('ROLLBACK');
      return false;
    }

    const memory = await client.query<{ deleted_at: Date | null }>(
      `SELECT deleted_at FROM memories WHERE id=$1 AND user_id=$2 FOR UPDATE`,
      [memoryId, userId],
    );
    if (memory.rows[0] && !memory.rows[0].deleted_at) {
      await client.query(
        `UPDATE memories SET status='queued', processing_error=NULL, updated_at=now()
         WHERE id=$1 AND user_id=$2`,
        [memoryId, userId],
      );
      await client.query(
        `UPDATE memory_processing_jobs
         SET status='queued', attempt_count=GREATEST(attempt_count-1,0), available_at=now(),
             lease_token=NULL, lease_expires_at=NULL, last_error=NULL, updated_at=now()
         WHERE memory_id=$1 AND user_id=$2 AND lease_token=$3::uuid`,
        [memoryId, userId, leaseToken],
      );
      await client.query('COMMIT');
      return false;
    }

    await client.query(
      `UPDATE memory_processing_jobs
       SET status='completed', lease_token=NULL, lease_expires_at=NULL,
           last_error=NULL, updated_at=now()
       WHERE memory_id=$1 AND user_id=$2 AND lease_token=$3::uuid`,
      [memoryId, userId, leaseToken],
    );
    await client.query('COMMIT');
    return true;
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}

export async function retryOrFailMemoryProcessingJob(
  job: ClaimedMemoryJob,
  errorCode: string,
  maxAttempts: number,
) {
  const retry = job.attemptCount < maxAttempts;
  const delayMs = 2_000 * 2 ** Math.max(0, job.attemptCount - 1);
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const updated = await client.query(
      `UPDATE memory_processing_jobs
       SET status=$4, available_at=CASE WHEN $4='queued' THEN now()+($5 * interval '1 millisecond') ELSE available_at END,
           lease_token=NULL, lease_expires_at=NULL, last_error=$6, updated_at=now()
       WHERE memory_id=$1 AND user_id=$2 AND status='processing' AND lease_token=$3::uuid
       RETURNING memory_id`,
      [job.memoryId, job.userId, job.leaseToken, retry ? 'queued' : 'failed', delayMs, errorCode],
    );
    if (!updated.rowCount) {
      await client.query('ROLLBACK');
      return 'lease_lost' as const;
    }

    await client.query(
      `UPDATE memories SET status=$3, processing_error=$4, updated_at=now()
       WHERE id=$1 AND user_id=$2 AND deleted_at IS NULL`,
      [job.memoryId, job.userId, retry ? 'queued' : 'failed', errorCode],
    );
    await client.query('COMMIT');
    return retry ? 'queued' as const : 'failed' as const;
  } catch (error) {
    await client.query('ROLLBACK').catch(() => undefined);
    throw error;
  } finally {
    client.release();
  }
}
