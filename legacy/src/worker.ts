import { setTimeout as delay } from 'node:timers/promises';
import { claimMemoryProcessingJob, retryOrFailMemoryProcessingJob, renewMemoryProcessingLease, type ClaimedMemoryJob } from './queue.js';
import { pool } from './db/pool.js';
import { processMemory } from './process-memory.js';

const CONCURRENCY = 4;
const MAX_ATTEMPTS = 4;
const POLL_INTERVAL_MS = 800;
const LEASE_RENEW_INTERVAL_MS = 30_000;

let stopping = false;

function safeErrorCode(error: unknown) {
  return error instanceof Error ? error.name.slice(0, 80) : 'processing_error';
}

async function processClaimedJob(job: ClaimedMemoryJob) {
  const heartbeat = setInterval(() => {
    void renewMemoryProcessingLease(job).then((renewed) => {
      if (!renewed) console.warn(`Memory job lease was reassigned for ${job.memoryId}`);
    }).catch((error) => {
      console.error(`Could not renew memory job lease for ${job.memoryId}`, error);
    });
  }, LEASE_RENEW_INTERVAL_MS);

  try {
    if (job.attemptCount > MAX_ATTEMPTS) {
      await retryOrFailMemoryProcessingJob(job, 'processing_attempts_exhausted', MAX_ATTEMPTS);
      return;
    }
    await processMemory(job.memoryId, job.userId, job.leaseToken);
  } catch (error) {
    const result = await retryOrFailMemoryProcessingJob(job, safeErrorCode(error), MAX_ATTEMPTS);
    console.error(`Memory job ${job.memoryId} ${result}`, safeErrorCode(error));
  } finally {
    clearInterval(heartbeat);
  }
}

async function runWorker() {
  while (!stopping) {
    try {
      const job = await claimMemoryProcessingJob();
      if (!job) {
        await delay(POLL_INTERVAL_MS);
        continue;
      }
      await processClaimedJob(job);
    } catch (error) {
      console.error('Memory queue polling failed', safeErrorCode(error));
      await delay(POLL_INTERVAL_MS);
    }
  }
}

/** Runs the database-backed queue in the API process. */
export async function startMemoryQueue() {
  stopping = false;
  console.info(`Trove memory queue is ready with concurrency ${CONCURRENCY}`);
  const runners = Array.from({ length: CONCURRENCY }, () => runWorker());
  return async () => {
    stopping = true;
    await Promise.all(runners);
  };
}
