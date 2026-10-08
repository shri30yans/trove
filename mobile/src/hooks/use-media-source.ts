import { useQuery } from '@tanstack/react-query';
import { mediaSource } from '../api/media';
export function useMediaSource(path: string) {
  return useQuery({ queryKey: ['media-source', path], queryFn: () => mediaSource(path) });
}
