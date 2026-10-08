CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$ BEGIN
  CREATE TYPE memory_kind AS ENUM ('link', 'image', 'text', 'audio', 'video', 'file', 'place');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE memory_status AS ENUM ('queued', 'processing', 'ready', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE asset_status AS ENUM ('pending_upload', 'uploaded', 'attached', 'failed');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS app_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  auth_subject text NOT NULL UNIQUE,
  email text,
  display_name text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS spaces (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  name text NOT NULL,
  description text,
  color text,
  icon text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  UNIQUE (user_id, name)
);
CREATE INDEX IF NOT EXISTS spaces_user_created_idx ON spaces(user_id, created_at DESC) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS assets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  object_key text NOT NULL UNIQUE,
  original_filename text,
  mime_type text NOT NULL,
  byte_size bigint,
  checksum_sha256 text,
  status asset_status NOT NULL DEFAULT 'pending_upload',
  created_at timestamptz NOT NULL DEFAULT now(),
  uploaded_at timestamptz,
  UNIQUE (id, user_id)
);
CREATE INDEX IF NOT EXISTS assets_user_created_idx ON assets(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS memories (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  kind memory_kind NOT NULL,
  status memory_status NOT NULL DEFAULT 'queued',
  processing_error text,
  source_app text,
  source_url text,
  source_domain text,
  title text,
  description text,
  user_note text,
  content_text text,
  page_text text,
  ocr_text text,
  transcript text,
  ai_summary text,
  visual_description text,
  capture_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_hash text,
  embedding vector(1536),
  captured_at timestamptz NOT NULL DEFAULT now(),
  occurred_at timestamptz,
  last_opened_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz,
  idempotency_key text,
  search_document tsvector GENERATED ALWAYS AS (
    to_tsvector('simple',
      coalesce(title, '') || ' ' || coalesce(description, '') || ' ' ||
      coalesce(user_note, '') || ' ' || coalesce(content_text, '') || ' ' ||
      coalesce(page_text, '') || ' ' ||
      coalesce(ocr_text, '') || ' ' || coalesce(transcript, '') || ' ' ||
      coalesce(ai_summary, '') || ' ' || coalesce(visual_description, '') || ' ' ||
      coalesce(source_domain, '')
    )
  ) STORED,
  UNIQUE (user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS memories_user_captured_idx ON memories(user_id, captured_at DESC, id DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_user_kind_idx ON memories(user_id, kind, captured_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_search_document_idx ON memories USING gin(search_document) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS memories_embedding_hnsw_idx ON memories USING hnsw(embedding vector_cosine_ops) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS memory_assets (
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  asset_id uuid NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'original',
  position integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (memory_id, asset_id)
);
CREATE INDEX IF NOT EXISTS memory_assets_user_idx ON memory_assets(user_id, memory_id);

CREATE TABLE IF NOT EXISTS memory_spaces (
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  space_id uuid NOT NULL REFERENCES spaces(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  assigned_by text NOT NULL DEFAULT 'user',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (memory_id, space_id)
);
CREATE INDEX IF NOT EXISTS memory_spaces_space_idx ON memory_spaces(user_id, space_id, memory_id);

CREATE TABLE IF NOT EXISTS memory_topics (
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  topic text NOT NULL,
  confidence real NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (memory_id, topic)
);
CREATE INDEX IF NOT EXISTS memory_topics_user_topic_idx ON memory_topics(user_id, lower(topic));

CREATE TABLE IF NOT EXISTS memory_entities (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  entity_kind text NOT NULL,
  display_value text NOT NULL,
  normalized_value text,
  confidence real NOT NULL DEFAULT 0.5 CHECK (confidence >= 0 AND confidence <= 1),
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  user_confirmed boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memory_entities_user_kind_idx ON memory_entities(user_id, entity_kind, memory_id);

CREATE TABLE IF NOT EXISTS memory_relation_feedback (
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  related_memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  is_related boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (memory_id, related_memory_id),
  CHECK (memory_id <> related_memory_id)
);

CREATE TABLE IF NOT EXISTS memory_events (
  id bigserial PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
  memory_id uuid NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
  event_type text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS memory_events_user_memory_idx ON memory_events(user_id, memory_id, created_at DESC);

CREATE TABLE IF NOT EXISTS user_preferences (
  user_id uuid PRIMARY KEY REFERENCES app_users(id) ON DELETE CASCADE,
  resurfacing_enabled boolean NOT NULL DEFAULT false,
  resurfacing_cadence text NOT NULL DEFAULT 'weekly' CHECK (resurfacing_cadence IN ('weekly', 'monthly', 'off')),
  ai_processing_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS schema_migrations (
  id text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
