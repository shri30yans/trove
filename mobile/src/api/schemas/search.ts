import { z } from 'zod';
import { previewPathSchema } from './media';
import { nullableText } from './common';
import { memoryCardSchema } from './memories';
export const searchResponseSchema = z.object({ query: z.string(), semanticSearch: z.boolean(), memories: z.array(memoryCardSchema.extend({
  description: nullableText, userNote: nullableText, pageText: nullableText, score: z.number(), matchType: z.enum(['text', 'meaning', 'text_and_meaning']),
  matchExcerpt: nullableText, previewUrl: previewPathSchema.nullable(),
})) });
export const relatedResponseSchema = z.object({ memories: z.array(memoryCardSchema.extend({
  similarity: z.number(), reason: z.string(), relation: z.enum(['similar_idea', 'same_topic']), previewUrl: previewPathSchema.nullable(),
})) });
export const feedbackRequestSchema = z.strictObject({ isRelated: z.boolean() });
export const feedbackResponseSchema = z.object({ saved: z.literal(true) });
