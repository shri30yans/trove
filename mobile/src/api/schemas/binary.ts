import { z } from 'zod';
import { parseContract } from './common';

const binaryResponseSchema = z.object({ status: z.literal(200), headers: z.record(z.string(), z.string()) });
export const downloadedFileSchema = z.object({ exists: z.literal(true), isDirectory: z.literal(false), size: z.number().int().positive() });
const binaryMetadataSchema = z.object({
  contentType: z.string().regex(/^[\w.+-]+\/[\w.+-]+$/),
  contentLength: z.string().regex(/^\d+$/).transform(Number).pipe(z.number().int().positive()),
});

export function validateBinaryResponse(response: unknown, byteSize: number, mimeType: string): void {
  const { headers } = parseContract(binaryResponseSchema, response);
  const normalized = Object.fromEntries(Object.entries(headers).map(([key, value]) => [key.toLowerCase(), value]));
  const metadata = parseContract(binaryMetadataSchema, {
    contentType: normalized['content-type']?.split(';')[0].trim().toLowerCase(),
    contentLength: normalized['content-length'],
  });
  if (metadata.contentType !== mimeType.toLowerCase() || metadata.contentLength !== byteSize) {
    throw new Error('Trove returned an incomplete or invalid file. Try again.');
  }
}

export function validateBinaryDownload(response: unknown, file: unknown, mimeType: string): void {
  const { size } = parseContract(downloadedFileSchema, file);
  validateBinaryResponse(response, size, mimeType);
}
