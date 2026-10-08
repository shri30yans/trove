import { moveMemory } from '../../api/memories';
import type { Memory } from '../../types';

export type MoveMemoryBatch = { memoryIds: string[]; fromSpaceId: string; toSpaceId: string };

/** Each server acknowledgement is reconciled immediately, independently of later failures. */
export async function moveMemoryBatch(input: MoveMemoryBatch, onConfirmed: (memory: Memory) => void) {
  const ids = [...new Set(input.memoryIds)];
  const results = await Promise.allSettled(ids.map(async (id) => {
    const result = await moveMemory(id, input.fromSpaceId, input.toSpaceId);
    try {
      onConfirmed(result.memory);
      return { id, refreshRequired: false };
    } catch {
      console.error('[Trove move]', { stage: 'reconciliation-failed', memoryId: id });
      return { id, refreshRequired: true };
    }
  }));
  return {
    confirmedIds: results.flatMap((result) => result.status === 'fulfilled' ? [result.value.id] : []),
    failedIds: ids.filter((_, index) => results[index].status === 'rejected'),
    refreshRequired: results.some((result) => result.status === 'fulfilled' && result.value.refreshRequired),
  };
}
