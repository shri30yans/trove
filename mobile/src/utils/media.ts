export const WAVE_HEIGHTS = [12, 20, 15, 27, 18, 32, 21, 14, 25, 34, 17, 28, 15, 23, 32, 18, 25, 13, 21, 30, 16, 24];

export function formatDuration(seconds: number) {
  const safeSeconds = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
  return `${Math.floor(safeSeconds / 60)}:${String(safeSeconds % 60).padStart(2, '0')}`;
}
