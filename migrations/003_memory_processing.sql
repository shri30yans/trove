-- Big-bang transition to the final multimodal embedding schema and Postgres
-- processing queue. Existing memory data is disposable during this cutover.
DELETE FROM public.memories;
DELETE FROM public.assets;

-- The original 1,536-dimensional embedding column is no longer part of the
-- application model. Drop it instead of keeping a rollback-only copy.
ALTER TABLE public.memories DROP COLUMN embedding;

CREATE TABLE public.embeddings (
  id bigserial PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES public.app_users(id) ON DELETE CASCADE,
  memory_id uuid,
  asset_id uuid,
  modality text NOT NULL CHECK (modality IN ('text', 'image')),
  embedding_space text NOT NULL,
  model_id text NOT NULL,
  model_revision text NOT NULL,
  source_checksum_sha256 text,
  embedding vector(768) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT embeddings_subject_modality_check CHECK (
    (memory_id IS NOT NULL AND asset_id IS NULL AND modality = 'text') OR
    (memory_id IS NULL AND asset_id IS NOT NULL AND modality = 'image')
  ),
  CONSTRAINT embeddings_memory_user_fk
    FOREIGN KEY (memory_id, user_id) REFERENCES public.memories(id, user_id) ON DELETE CASCADE,
  CONSTRAINT embeddings_asset_user_fk
    FOREIGN KEY (asset_id, user_id) REFERENCES public.assets(id, user_id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX embeddings_memory_space_uq
  ON public.embeddings(memory_id, embedding_space) WHERE memory_id IS NOT NULL;
CREATE UNIQUE INDEX embeddings_asset_space_uq
  ON public.embeddings(asset_id, embedding_space) WHERE asset_id IS NOT NULL;
CREATE INDEX embeddings_user_space_idx
  ON public.embeddings(user_id, embedding_space);
CREATE INDEX embeddings_user_space_hnsw_idx
  ON public.embeddings USING hnsw (embedding vector_cosine_ops);

COMMENT ON TABLE public.embeddings IS
  'Versioned text and image vectors stored in one compatible embedding space.';
COMMENT ON COLUMN public.embeddings.embedding_space IS
  'Identifies the paired text and image model revisions that produced this vector.';

ALTER TABLE public.embeddings ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.embeddings FROM PUBLIC;
REVOKE ALL PRIVILEGES ON SEQUENCE public.embeddings_id_seq FROM PUBLIC;

CREATE TABLE public.memory_processing_jobs (
  memory_id uuid PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES public.app_users(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_token uuid,
  lease_expires_at timestamptz,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT memory_processing_jobs_memory_user_fk
    FOREIGN KEY (memory_id, user_id) REFERENCES public.memories(id, user_id) ON DELETE CASCADE,
  CONSTRAINT memory_processing_jobs_lease_pair_check
    CHECK ((lease_token IS NULL) = (lease_expires_at IS NULL)),
  CONSTRAINT memory_processing_jobs_status_lease_check
    CHECK ((status = 'processing') = (lease_token IS NOT NULL))
);

CREATE INDEX memory_processing_jobs_queued_idx
  ON public.memory_processing_jobs (available_at, created_at)
  WHERE status = 'queued';
CREATE INDEX memory_processing_jobs_expired_lease_idx
  ON public.memory_processing_jobs (lease_expires_at)
  WHERE status = 'processing';

COMMENT ON TABLE public.memory_processing_jobs IS
  'Durable Postgres queue for asynchronous memory enrichment and embedding work.';
COMMENT ON COLUMN public.memory_processing_jobs.lease_token IS
  'Fences stale workers from committing results after a job lease has been reassigned.';

ALTER TABLE public.memory_processing_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.memory_processing_jobs FROM PUBLIC;

DO $$
DECLARE
  role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.embeddings FROM %I', role_name);
      EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.embeddings_id_seq FROM %I', role_name);
      EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.memory_processing_jobs FROM %I', role_name);
    END IF;
  END LOOP;
END $$;

-- Keep uploaded files in the private Supabase Storage bucket used by the API.
INSERT INTO storage.buckets (id, name, public, file_size_limit)
VALUES ('trove-private', 'trove-private', false, 52428800)
ON CONFLICT (id) DO UPDATE
SET name = EXCLUDED.name,
    public = false,
    file_size_limit = EXCLUDED.file_size_limit;
