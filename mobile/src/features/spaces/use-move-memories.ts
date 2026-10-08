import { useMutation } from '@tanstack/react-query';
import type { Memory } from '../../types';
import { moveMemoryBatch, type MoveMemoryBatch } from './move-memory-batch';

export function useMoveMemories(onConfirmed: (memory: Memory) => void) {
  return useMutation({ mutationFn: (input: MoveMemoryBatch) => moveMemoryBatch(input, onConfirmed), retry: false });
}
