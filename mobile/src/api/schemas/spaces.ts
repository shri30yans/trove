import { z } from 'zod';
import { idSchema, timestampSchema, nullableText, countSchema } from './common';
export const spaceSchema = z.object({ id: idSchema, name: z.string().min(1), description: nullableText,
  color: nullableText, icon: nullableText, createdAt: timestampSchema, updatedAt: timestampSchema, memoryCount: countSchema.optional() });
export const spacesResponseSchema = z.object({ spaces: z.array(spaceSchema) });
export const spaceResponseSchema = z.object({ space: spaceSchema });
export const createSpaceSchema = z.strictObject({ name: z.string().trim().min(1).max(80), description: z.string().trim().max(500).nullable() });
export type Space = z.infer<typeof spaceSchema>;
