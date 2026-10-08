import { z } from 'zod';
import { idSchema, timestampSchema, httpUrlSchema } from './common';
import { memoryKindSchema } from '../../domain/pending-capture';
export const uploadRequestSchema = z.strictObject({ filename: z.string().trim().min(1).max(240), mimeType: z.string().trim().min(3).max(160), byteSize: z.number().int().positive().max(52428800) });
export const uploadResponseSchema = z.object({ assetId: idSchema,
  uploadPath: z.string().regex(/^\/v1\/uploads\/[0-9a-f-]+\/content$/i), method: z.literal('PUT'), headers: z.record(z.string(), z.string()),
}).refine((upload) => upload.uploadPath === `/v1/uploads/${upload.assetId}/content`);
export const uploadContentResponseSchema = z.object({ assetId: idSchema, byteSize: z.number().int().positive() });
export const uploadCompleteSchema = z.object({ assetId: idSchema, status: z.enum(['uploaded', 'attached']), byteSize: z.number().int().positive() });
export const createMemorySchema = z.strictObject({
  kind: memoryKindSchema, capturedAt: timestampSchema, title: z.string().max(500).optional(), description: z.string().max(20000).optional(),
  userNote: z.string().max(20000).optional(), contentText: z.string().max(200000).optional(), sourceApp: z.string().optional(), sourceUrl: httpUrlSchema.optional(),
  captureMetadata: z.record(z.string(), z.unknown()), assetIds: z.array(idSchema), spaceIds: z.array(idSchema),
});
