import { z } from 'zod';
const apiBaseSchema = z.url({ protocol: /^https?$/ }).refine((value) => {
  const url = new URL(value);
  return !url.username && !url.password && !url.search && !url.hash;
});
export function getApiBaseUrl() {
  const parsed = apiBaseSchema.safeParse(process.env.EXPO_PUBLIC_API_URL);
  if (!parsed.success) throw new Error('Trove API is not configured. Set EXPO_PUBLIC_API_URL to the authenticated API address.');
  return parsed.data.replace(/\/$/, '');
}
export function getApiUrl(path: string) {
  if (!path.startsWith('/v1/') || path.startsWith('//') || path.includes('://')) throw new Error('Invalid Trove API path.');
  return `${getApiBaseUrl()}${path}`;
}
