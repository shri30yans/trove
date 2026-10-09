import { z } from 'zod';
import { idSchema, timestampSchema, nullableText, countSchema } from './common';
export const spaceSchema = z.object({ id: idSchema, name: z.string().min(1), description: nullableText,
  color: nullableText, icon: nullableText, createdAt: timestampSchema, updatedAt: timestampSchema });
/** GET /v1/spaces joins the count. A written Space answers without one: it has just been created,
 * so the workspace that stores it decides what its count means rather than every screen guessing. */
export const listedSpaceSchema = spaceSchema.extend({ memoryCount: countSchema });
export const spacesResponseSchema = z.object({ spaces: z.array(listedSpaceSchema) });
export const spaceResponseSchema = z.object({ space: spaceSchema });
export const createSpaceSchema = z.strictObject({ name: z.string().trim().min(1).max(80), description: z.string().trim().max(500).nullable() });
export type Space = z.infer<typeof listedSpaceSchema>;
export type WrittenSpace = z.infer<typeof spaceSchema>;
