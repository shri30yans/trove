import type { MemoryCapture } from '../types';

export function detectCaptureUrl(text: string) {
  const match = text.match(/https?:\/\/[^\s<>"']+|\bwww\.[^\s<>"']+/i)?.[0]
    || (text.trim().match(/^(?:[\w-]+\.)+[a-z]{2,}(?::\d+)?(?:\/[^\s]*)?$/i)?.[0] ?? '');
  if (!match) return null;
  const candidate = match.replace(/[),.!?;:]+$/, '');
  try {
    const parsed = new URL(/^https?:\/\//i.test(candidate) ? candidate : `https://${candidate}`);
    return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : null;
  } catch {
    return null;
  }
}

export function isVideoUrl(url: string) {
  const host = new URL(url).hostname.replace(/^www\./i, '').toLowerCase();
  return ['youtube.com', 'youtu.be', 'vimeo.com', 'tiktok.com', 'dailymotion.com'].some((domain) => host === domain || host.endsWith(`.${domain}`));
}

export function kindFromMimeType(mimeType: string): MemoryCapture['kind'] {
  if (mimeType.startsWith('image/')) return 'image';
  if (mimeType.startsWith('video/')) return 'video';
  if (mimeType.startsWith('audio/')) return 'audio';
  return 'file';
}
