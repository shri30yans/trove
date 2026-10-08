import { z } from 'zod';

export const memoryKinds = ['link', 'image', 'text', 'audio', 'video', 'file'] as const;
export const createMemorySchema = z.object({
  kind: z.enum(memoryKinds),
  sourceApp: z.string().trim().max(120).optional(),
  sourceUrl: z.string().url().max(4096).refine((url) => ['http:', 'https:'].includes(new URL(url).protocol), 'Only HTTP and HTTPS links are supported').optional(),
  title: z.string().trim().max(500).optional(),
  description: z.string().max(20_000).optional(),
  userNote: z.string().max(20_000).optional(),
  contentText: z.string().max(200_000).optional(),
  captureMetadata: z.record(z.string(), z.unknown()).default({}),
  capturedAt: z.string().datetime().optional(),
  assetIds: z.array(z.string().uuid()).max(20).default([]),
  spaceIds: z.array(z.string().uuid()).max(50).default([]),
});

export const updateMemorySchema = z.object({
  title: z.string().trim().max(500).nullable().optional(),
  userNote: z.string().max(20_000).nullable().optional(),
  spaceIds: z.array(z.string().uuid()).max(50).optional(),
});

export const createSpaceSchema = z.object({
  name: z.string().trim().min(1).max(80),
  description: z.string().trim().max(500).optional(),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/).optional(),
  icon: z.string().trim().max(40).optional(),
});

export const updateSpaceSchema = createSpaceSchema.partial().refine((value) => Object.keys(value).length > 0);

export const createUploadSchema = z.object({
  filename: z.string().trim().min(1).max(240),
  mimeType: z.string().trim().min(3).max(160),
  byteSize: z.number().int().positive().max(52_428_800),
  checksumSha256: z.string().regex(/^[a-fA-F0-9]{64}$/).optional(),
});

export const relatedFeedbackSchema = z.object({ isRelated: z.boolean() });
export const askSchema = z.object({ question: z.string().trim().min(3).max(4000), spaceId: z.string().uuid().optional() });

export function sourceDomain(url?: string) {
  if (!url) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, '').toLowerCase();
  } catch {
    return null;
  }
}
