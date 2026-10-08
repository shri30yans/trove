import { z } from 'zod';
import { previewPathSchema } from './media';
import { idSchema, timestampSchema, countSchema, nullableText } from './common';
import { memoryCardSchema } from './memories';
import { cadenceSchema } from './preferences';
export const exploreSchema = z.object({ months: z.array(z.object({ month: z.iso.date(), memoryCount: countSchema })) });
export const resurfacingUpdateSchema = z.object({
  memory: memoryCardSchema.omit({ status: true }).extend({ previewUrl: previewPathSchema.nullable() }),
  relatedTo: z.object({ id: idSchema, title: nullableText, capturedAt: timestampSchema }), reason: z.string(), similarity: z.number(),
});
export const updatesResponseSchema = z.object({ enabled: z.boolean(), cadence: cadenceSchema, updates: z.array(resurfacingUpdateSchema) });
export type ExploreData = z.infer<typeof exploreSchema>;
export type ResurfacingUpdate = z.infer<typeof resurfacingUpdateSchema>;
