-- Keep the existing per-account opt-in while making clear that vector embeddings are the
-- only provider-backed memory processing enabled by this preference.
ALTER TABLE public.user_preferences
  RENAME COLUMN ai_processing_enabled TO embeddings_enabled;
