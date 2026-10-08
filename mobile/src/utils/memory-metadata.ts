import type { ComponentProps } from 'react';
import { Ionicons } from '@expo/vector-icons';
import type { Palette } from '../theme';
import type { Memory, MemoryKind } from '../types';

type IconName = ComponentProps<typeof Ionicons>['name'];
export type { IconName };

export const kindLabels: Record<MemoryKind, string> = {
  link: 'Link', image: 'Image', text: 'Note', audio: 'Audio', video: 'Video', file: 'File',
};

export const kindIcons: Record<MemoryKind, IconName> = {
  link: 'link-outline', image: 'image-outline', text: 'document-text-outline', audio: 'mic-outline',
  video: 'play-circle-outline', file: 'document-attach-outline',
};

export function kindColors(colors: Palette): Record<MemoryKind, string> {
  return {
    link: colors.icyBlue, image: colors.petal, text: colors.thistle, audio: colors.lavender,
    video: colors.skyBlue, file: colors.icyBlue,
  };
}

export function memoryTitle(memory: Memory) {
  if (memory.title?.trim()) return memory.title.trim();
  if (memory.sourceDomain) return memory.sourceDomain;
  if (memory.sourceUrl) {
    try { return new URL(memory.sourceUrl).hostname.replace(/^www\./, ''); } catch { /* use the type below */ }
  }
  return `${kindLabels[memory.kind]} memory`;
}

export function memoryDescription(memory: Memory) {
  return memory.reason || memory.description || memory.userNote || memory.matchExcerpt || memory.sourceUrl || 'Saved to your personal memory.';
}

export function shortDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date);
}
