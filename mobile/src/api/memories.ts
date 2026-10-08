import { ApiError, request } from './client';
import { z } from 'zod';
import { emptyResponseSchema, requestBody, parseRequest, idSchema } from './schemas/common';
import { memoryListResponseSchema, memoryResponseSchema, memoryPatchSchema, moveMemoryRequestSchema, processingResponseSchema, type MemoryPatch } from './schemas/memories';
import type { Memory } from '../types';
import { memoryFiltersSchema, filterParams, validRange } from './memory-filters';

const listRequestSchema = memoryFiltersSchema.extend({
  limit: z.number().int().min(1).max(100).optional(), cursor: z.string().min(1).optional(),
}).refine(validRange);
export type MemoryListOptions = z.infer<typeof listRequestSchema>;
export function getMemories(options: MemoryListOptions = {}, signal?: AbortSignal) {
  const validated = parseRequest(listRequestSchema, options);
  const params = filterParams(validated);
  if (validated.cursor) params.set('cursor', validated.cursor);
  params.set('limit', String(validated.limit ?? 50));
  return request(`/v1/memories?${params.toString()}`, memoryListResponseSchema, { signal });
}

export async function getAllMemories() {
  const memories: Memory[] = [];
  let cursor: string | null = null;
  do {
    const page = await getMemories({ limit: 100, cursor: cursor ?? undefined });
    memories.push(...page.memories);
    cursor = page.nextCursor;
  } while (cursor);
  return memories;
}

export function getProcessingSummary(signal?: AbortSignal) {
  return request('/v1/processing', processingResponseSchema, { signal });
}

export async function getMemory(id: string, signal?: AbortSignal) {
  id = parseRequest(idSchema, id);
  const startedAt = Date.now();
  try {
    const result = await request(`/v1/memories/${id}`, memoryResponseSchema.refine(({ memory }) => memory.id === id), { signal });
    if (__DEV__) console.info('[Trove API timing]', { operation: 'memory_detail', outcome: 'success', elapsed_ms: Date.now() - startedAt });
    return result;
  } catch (error) {
    if (__DEV__) console.info('[Trove API timing]', {
      operation: 'memory_detail', outcome: 'failure', elapsed_ms: Date.now() - startedAt,
      status: error instanceof ApiError ? error.status : undefined,
      code: error instanceof ApiError ? error.code : undefined,
    });
    throw error;
  }
}

export function patchMemory(id: string, patch: MemoryPatch) {
  id = parseRequest(idSchema, id);
  return request(`/v1/memories/${id}`, memoryResponseSchema.refine(({ memory }) => memory.id === id), { method: 'PATCH', body: requestBody(memoryPatchSchema, patch) });
}

export function deleteMemory(id: string) {
  id = parseRequest(idSchema, id);
  return request(`/v1/memories/${id}`, emptyResponseSchema, { method: 'DELETE' });
}

export function moveMemory(id: string, fromSpaceId: string, toSpaceId: string) {
  id = parseRequest(idSchema, id);
  return request(`/v1/memories/${id}/move`, memoryResponseSchema.refine(({ memory }) => memory.id === id), {
    method: 'POST', body: requestBody(moveMemoryRequestSchema, { fromSpaceId, toSpaceId }),
  });
}
