import { z } from 'zod';
import { idSchema, timestampSchema } from './schemas/common';
import { memoryKindSchema } from '../domain/pending-capture';
export const memoryFiltersSchema = z.strictObject({
  kind: z.union([memoryKindSchema, z.literal('all')]).optional(), after: timestampSchema.optional(), before: timestampSchema.optional(),
  spaceId: idSchema.optional(), source: z.string().min(1).optional(),
});
export type MemoryFilters = z.infer<typeof memoryFiltersSchema>;
export function filterParams(filters: MemoryFilters) {
  const params = new URLSearchParams();
  for (const key of ['spaceId', 'after', 'before', 'source'] as const) {
    const value = filters[key]; if (value !== undefined) params.set(key, value);
  }
  if (filters.kind && filters.kind !== 'all') params.set('kind', filters.kind);
  return params;
}
export function validRange(filters: MemoryFilters) {
  return !filters.after || !filters.before || new Date(filters.after) < new Date(filters.before);
}
