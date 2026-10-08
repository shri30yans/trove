import { z } from 'zod';
const uuid = '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}';
export const assetContentPathSchema = z.string().regex(new RegExp(`^/v1/assets/${uuid}/content$`, 'i'));
export const previewPathSchema = z.string().regex(new RegExp(`^/v1/memories/${uuid}/preview$`, 'i'));
export const mediaPathSchema = z.union([assetContentPathSchema, previewPathSchema]);
export const localMediaUriSchema = z.string().regex(/^(file|content|blob):/);
