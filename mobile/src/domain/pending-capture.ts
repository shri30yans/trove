import { z } from 'zod';

export const memoryKindSchema = z.enum(['link', 'image', 'text', 'audio', 'video', 'file']);
const metadata = z.record(z.string(), z.unknown());
export const captureSchema = z.strictObject({
  kind: memoryKindSchema,
  capturedAt: z.iso.datetime({ offset: true }).optional(),
  title: z.string().optional(), description: z.string().optional(),
  userNote: z.string().optional(), contentText: z.string().optional(),
  sourceApp: z.string().optional(), sourceUrl: z.string().optional(),
  spaceIds: z.array(z.string().min(1)).optional(), captureMetadata: metadata.optional(),
  attachments: z.array(z.strictObject({
    kind: memoryKindSchema, title: z.string().optional(), sourceApp: z.string().optional(), captureMetadata: metadata.optional(),
    asset: z.strictObject({ uri: z.string().min(1), filename: z.string().min(1), mimeType: z.string().min(1), byteSize: z.number().nonnegative().optional() }),
  })).optional(),
});
export type MemoryKind = z.infer<typeof memoryKindSchema>;
export type MemoryCapture = z.input<typeof captureSchema>;
export type CaptureAttachment = NonNullable<MemoryCapture['attachments']>[number];
export type CaptureAsset = CaptureAttachment['asset'];

const pendingSchema = z.strictObject({
  key: z.string().min(1), localId: z.string().regex(/^[A-Za-z0-9-]+$/), capture: captureSchema,
  attempts: z.number().int().nonnegative().default(0), retryAt: z.number().nonnegative().default(0),
  blocked: z.boolean().default(false), lastError: z.string().optional(),
  assetIds: z.array(z.string().min(1)).default([]),
});
export type PendingCapture = Omit<z.infer<typeof pendingSchema>, 'capture'> & { capture: z.infer<typeof captureSchema> & { capturedAt: string } };

export function parsePendingCapture(value: unknown): PendingCapture {
  const parsed = pendingSchema.safeParse(value);
  if (!parsed.success) throw new Error('Could not read saved items on this device. Your local data has been kept.');
  const entry = parsed.data;
  if (!entry.capture.capturedAt) {
    const timestamp = Number(entry.localId.split('-')[0]);
    if (!Number.isFinite(timestamp) || timestamp <= 0 || !Number.isFinite(new Date(timestamp).getTime())) {
      throw new Error('A saved item has no valid capture date. Your local data has been kept.');
    }
    entry.capture.capturedAt = new Date(timestamp).toISOString();
  }
  return { ...entry, capture: { ...entry.capture, capturedAt: entry.capture.capturedAt } };
}

export function parseLegacyQueue(raw: string | null): PendingCapture[] {
  if (raw === null) return [];
  const values: unknown = JSON.parse(raw);
  if (!Array.isArray(values)) throw new Error('Could not read saved items on this device. Your local data has been kept.');
  return values.map(parsePendingCapture);
}
