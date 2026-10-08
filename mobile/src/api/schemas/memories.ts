import { z } from 'zod';
import { idSchema, timestampSchema, nullableText, countSchema, httpUrlSchema } from './common';
import { assetContentPathSchema, previewPathSchema } from './media';
import { memoryKindSchema } from '../../domain/pending-capture';
export const memoryStatusSchema = z.enum(['queued', 'processing', 'ready', 'failed']);
export const memorySpaceSchema = z.object({ id: idSchema, name: z.string().min(1), color: nullableText, icon: nullableText });
export const assetSchema = z.object({
  id: idSchema, filename: nullableText, mimeType: z.string().min(1), byteSize: countSchema.nullable(),
  status: z.enum(['pending_upload', 'uploaded', 'attached', 'failed']), role: z.string().min(1),
  url: assetContentPathSchema, createdAt: timestampSchema,
});
export const memoryCardSchema = z.object({
  id: idSchema, kind: memoryKindSchema, status: memoryStatusSchema,
  sourceApp: nullableText, sourceUrl: httpUrlSchema.nullable(), sourceDomain: nullableText,
  title: nullableText, capturedAt: timestampSchema,
});
export const memoryListItemSchema = memoryCardSchema.extend({
  description: nullableText, userNote: nullableText, pageText: nullableText,
  createdAt: timestampSchema, previewUrl: previewPathSchema.nullable(),
});
export const memoryDetailSchema = memoryCardSchema.extend({
  processingError: nullableText, description: nullableText, userNote: nullableText, contentText: nullableText,
  pageText: nullableText,
  captureMetadata: z.record(z.string(), z.unknown()), occurredAt: timestampSchema.nullable(),
  createdAt: timestampSchema, updatedAt: timestampSchema,
  spaces: z.array(memorySpaceSchema),
  assets: z.array(assetSchema.refine((asset) => asset.url === `/v1/assets/${asset.id}/content`)),
});
export const memoryListResponseSchema = z.object({ memories: z.array(memoryListItemSchema), nextCursor: z.string().nullable() });
export const processingSummarySchema = z.object({
  queued: countSchema, processing: countSchema, ready: countSchema, failed: countSchema, total: countSchema,
});
export const processingResponseSchema = z.object({ processing: processingSummarySchema });
export type ProcessingSummary = z.infer<typeof processingSummarySchema>;
export const memoryResponseSchema = z.object({ memory: memoryDetailSchema });
export const memoryPatchSchema = z.strictObject({
  title: z.string().trim().max(500).nullable().optional(), userNote: z.string().max(20000).nullable().optional(),
  spaceIds: z.array(idSchema).optional(),
}).refine((patch) => Object.keys(patch).length > 0);
export type MemoryPatch = z.infer<typeof memoryPatchSchema>;
export type RemoteMemory = z.infer<typeof memoryDetailSchema>;

export const moveMemoryRequestSchema = z.strictObject({ fromSpaceId: idSchema, toSpaceId: idSchema }).refine((request) => request.fromSpaceId !== request.toSpaceId);
