-- Embeddings are derived data. Remove vectors from the incompatible local model,
-- then requeue eligible memories so the worker rebuilds them through Google's native embedContent API.
DELETE FROM public.embeddings;

DROP INDEX public.embeddings_user_space_hnsw_idx;
ALTER TABLE public.embeddings
  ALTER COLUMN embedding TYPE vector(768) USING embedding::vector(768);
CREATE INDEX embeddings_user_space_hnsw_idx
  ON public.embeddings USING hnsw (embedding vector_cosine_ops);
COMMENT ON COLUMN public.embeddings.embedding IS
  'L2-normalized 768-dimensional Google Gemini Embedding 2 vector.';

WITH candidates AS (
  SELECT m.id, m.user_id, m.created_at,
         m.status = 'ready' AND (
           NULLIF(concat_ws('', m.title, m.description, m.user_note, m.content_text, m.page_text), '') IS NOT NULL
           OR EXISTS (
             SELECT 1 FROM public.memory_assets ma
             JOIN public.assets a ON a.id = ma.asset_id AND a.user_id = ma.user_id
             WHERE ma.memory_id = m.id AND ma.user_id = m.user_id AND a.mime_type LIKE 'image/%'
           )
         ) AS reindex_only,
         row_number() OVER (ORDER BY m.created_at DESC, m.id) AS job_ordinal
  FROM public.memories m
  JOIN public.user_preferences p ON p.user_id = m.user_id AND p.embeddings_enabled
  WHERE m.deleted_at IS NULL
    AND (
      NULLIF(concat_ws('', m.title, m.description, m.user_note, m.content_text, m.page_text), '') IS NOT NULL
      OR m.source_url IS NOT NULL
      OR EXISTS (
        SELECT 1 FROM public.memory_assets ma
        JOIN public.assets a ON a.id = ma.asset_id AND a.user_id = ma.user_id
        WHERE ma.memory_id = m.id AND ma.user_id = m.user_id
          AND (a.mime_type LIKE 'image/%' OR a.mime_type LIKE 'audio/%')
      )
    )
), requeued AS (
  INSERT INTO public.memory_processing_jobs
    (memory_id, user_id, status, attempt_count, available_at, reindex_only)
  SELECT id, user_id, 'queued', 0,
         now() + ((job_ordinal - 1) * interval '3 seconds'), reindex_only
  FROM candidates
  ON CONFLICT (memory_id) DO UPDATE SET
    status = 'queued', attempt_count = 0, available_at = EXCLUDED.available_at,
    lease_token = NULL, lease_expires_at = NULL, last_error = NULL,
    reindex_only = EXCLUDED.reindex_only, updated_at = now()
  RETURNING memory_id, user_id
)
UPDATE public.memories m
SET status = 'queued', processing_error = NULL, updated_at = now()
FROM requeued q
WHERE m.id = q.memory_id AND m.user_id = q.user_id AND m.deleted_at IS NULL;
