import type { Preferences } from '../api/schemas/preferences';
export type EmbeddingState = { state: 'loading' } | { state: 'error'; message: string } | { state: 'disabled' | 'unavailable' | 'available' };
export function embeddingState(preferences: Preferences | null, error: string | null): EmbeddingState {
  if (error) return { state: 'error', message: error };
  if (!preferences) return { state: 'loading' };
  if (!preferences.embeddingsEnabled) return { state: 'disabled' };
  return { state: preferences.embeddingsAvailable ? 'available' : 'unavailable' };
}
