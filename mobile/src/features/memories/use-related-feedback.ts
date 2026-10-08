import { useMutation, useQueryClient } from '@tanstack/react-query';
import { getRelatedMemories, sendRelatedFeedback } from '../../api/search';

type Feedback = { memoryId: string; relatedId: string; isRelated: boolean };
type RelatedResponse = Awaited<ReturnType<typeof getRelatedMemories>>;

export function useRelatedFeedback(memoryId?: string) {
  const client = useQueryClient();
  const mutation = useMutation({
    mutationFn: ({ memoryId, relatedId, isRelated }: Feedback) => sendRelatedFeedback(memoryId, relatedId, isRelated),
    retry: false,
    onSuccess: async (_, feedback) => {
      const key = ['memory', feedback.memoryId, 'related'];
      await client.cancelQueries({ queryKey: key, exact: true });
      if (!feedback.isRelated) client.setQueryData<RelatedResponse>(key, (current) => current
        ? { ...current, memories: current.memories.filter((memory) => memory.id !== feedback.relatedId) }
        : current);
    },
  });
  const submit = (memoryId: string, relatedId: string, isRelated: boolean) => {
    if (!mutation.isPending) mutation.mutate({ memoryId, relatedId, isRelated });
  };
  return {
    submit,
    error: mutation.variables?.memoryId === memoryId ? mutation.error?.message ?? null : null,
    pendingId: mutation.isPending ? mutation.variables.relatedId : null,
  };
}
