-- Cover composite foreign keys so parent deletes and key checks do not scan
-- the full child tables. The queue is small today, but has hot lease updates.
CREATE INDEX embeddings_memory_user_idx
  ON public.embeddings (memory_id, user_id)
  WHERE memory_id IS NOT NULL;
CREATE INDEX embeddings_asset_user_idx
  ON public.embeddings (asset_id, user_id)
  WHERE asset_id IS NOT NULL;
CREATE INDEX memory_processing_jobs_memory_user_idx
  ON public.memory_processing_jobs (memory_id, user_id);
CREATE INDEX memory_processing_jobs_user_idx
  ON public.memory_processing_jobs (user_id);
CREATE INDEX memory_relation_feedback_memory_user_idx
  ON public.memory_relation_feedback (memory_id, user_id);
