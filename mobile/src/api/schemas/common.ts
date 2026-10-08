import { z } from 'zod';
export const idSchema = z.uuid();
export const timestampSchema = z.iso.datetime({ offset: true });
export const nullableText = z.string().nullable();
export const countSchema = z.number().int().nonnegative();
export const httpUrlSchema = z.url({ protocol: /^https?$/ });
export const emptyResponseSchema = z.undefined();
export const errorResponseSchema = z.object({ error: z.object({ code: z.string().min(1), message: z.string() }) });
export function parseContract<T>(schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (!result.success) throw new Error('Trove returned an invalid response. Update the app or contact the administrator.');
  return result.data;
}
export function parseRequest<T>(schema: z.ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (!result.success) throw new Error('The request details are invalid. Check them and try again.');
  return result.data;
}
export function requestBody<T>(schema: z.ZodType<T>, value: unknown): string {
  return JSON.stringify(parseRequest(schema, value));
}
