import { ApiError, request } from './client';
import { z } from 'zod';
import { requestBody, parseRequest, idSchema } from './schemas/common';
import { searchResponseSchema, relatedResponseSchema, feedbackRequestSchema, feedbackResponseSchema } from './schemas/search';
import { memoryFiltersSchema, filterParams, validRange } from './memory-filters';

const searchRequestSchema = memoryFiltersSchema.extend({ query: z.string().trim().min(1).max(1000), limit: z.number().int().min(1).max(50).optional() }).refine(validRange);
export type MemorySearchOptions = z.infer<typeof searchRequestSchema>;
export function searchMemories(options: MemorySearchOptions, signal?: AbortSignal) {
  const validated = parseRequest(searchRequestSchema, options);
  const params = filterParams(validated);
  params.set('q', validated.query); params.set('limit', String(validated.limit ?? 30));
  return request(`/v1/search?${params.toString()}`, searchResponseSchema, { signal });
}

export function getRelatedMemories(id: string, signal?: AbortSignal) {
  id = parseRequest(idSchema, id);
  const startedAt = Date.now();
  return request(`/v1/memories/${id}/related`, relatedResponseSchema, { signal }).then((result) => {
    if (__DEV__) console.info('[Trove API timing]', { operation: 'memory_related', outcome: 'success', elapsed_ms: Date.now() - startedAt });
    return result;
  }).catch((error: unknown) => {
    if (__DEV__) console.info('[Trove API timing]', {
      operation: 'memory_related', outcome: 'failure', elapsed_ms: Date.now() - startedAt,
      status: error instanceof ApiError ? error.status : undefined,
      code: error instanceof ApiError ? error.code : undefined,
    });
    throw error;
  });
}

export function sendRelatedFeedback(id: string, relatedId: string, isRelated: boolean) {
  id = parseRequest(idSchema, id); relatedId = parseRequest(idSchema, relatedId);
  return request(`/v1/memories/${id}/related/${relatedId}/feedback`, feedbackResponseSchema, {
    method: 'PUT', body: requestBody(feedbackRequestSchema, { isRelated }),
  });
}
