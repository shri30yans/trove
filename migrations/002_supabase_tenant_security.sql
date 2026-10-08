-- Trove accesses its data through the authenticated Fastify API and a server-side
-- PostgreSQL connection. Keep direct Supabase Data API access closed until the
-- application is deliberately moved to per-user Supabase Auth/RLS policies.

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memories'::regclass AND conname = 'memories_id_user_key'
  ) THEN
    ALTER TABLE public.memories
      ADD CONSTRAINT memories_id_user_key UNIQUE (id, user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.spaces'::regclass AND conname = 'spaces_id_user_key'
  ) THEN
    ALTER TABLE public.spaces
      ADD CONSTRAINT spaces_id_user_key UNIQUE (id, user_id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_assets'::regclass AND conname = 'memory_assets_memory_user_fk'
  ) THEN
    ALTER TABLE public.memory_assets
      ADD CONSTRAINT memory_assets_memory_user_fk
      FOREIGN KEY (memory_id, user_id) REFERENCES public.memories (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_assets'::regclass AND conname = 'memory_assets_asset_user_fk'
  ) THEN
    ALTER TABLE public.memory_assets
      ADD CONSTRAINT memory_assets_asset_user_fk
      FOREIGN KEY (asset_id, user_id) REFERENCES public.assets (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_spaces'::regclass AND conname = 'memory_spaces_memory_user_fk'
  ) THEN
    ALTER TABLE public.memory_spaces
      ADD CONSTRAINT memory_spaces_memory_user_fk
      FOREIGN KEY (memory_id, user_id) REFERENCES public.memories (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_spaces'::regclass AND conname = 'memory_spaces_space_user_fk'
  ) THEN
    ALTER TABLE public.memory_spaces
      ADD CONSTRAINT memory_spaces_space_user_fk
      FOREIGN KEY (space_id, user_id) REFERENCES public.spaces (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_topics'::regclass AND conname = 'memory_topics_memory_user_fk'
  ) THEN
    ALTER TABLE public.memory_topics
      ADD CONSTRAINT memory_topics_memory_user_fk
      FOREIGN KEY (memory_id, user_id) REFERENCES public.memories (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_entities'::regclass AND conname = 'memory_entities_memory_user_fk'
  ) THEN
    ALTER TABLE public.memory_entities
      ADD CONSTRAINT memory_entities_memory_user_fk
      FOREIGN KEY (memory_id, user_id) REFERENCES public.memories (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_relation_feedback'::regclass AND conname = 'memory_relation_feedback_memory_user_fk'
  ) THEN
    ALTER TABLE public.memory_relation_feedback
      ADD CONSTRAINT memory_relation_feedback_memory_user_fk
      FOREIGN KEY (memory_id, user_id) REFERENCES public.memories (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_relation_feedback'::regclass AND conname = 'memory_relation_feedback_related_user_fk'
  ) THEN
    ALTER TABLE public.memory_relation_feedback
      ADD CONSTRAINT memory_relation_feedback_related_user_fk
      FOREIGN KEY (related_memory_id, user_id) REFERENCES public.memories (id, user_id) ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conrelid = 'public.memory_events'::regclass AND conname = 'memory_events_memory_user_fk'
  ) THEN
    ALTER TABLE public.memory_events
      ADD CONSTRAINT memory_events_memory_user_fk
      FOREIGN KEY (memory_id, user_id) REFERENCES public.memories (id, user_id) ON DELETE CASCADE;
  END IF;
END $$;

-- Index composite foreign keys so joins and parent deletes remain efficient.
CREATE INDEX IF NOT EXISTS memory_assets_memory_user_idx ON public.memory_assets (memory_id, user_id);
CREATE INDEX IF NOT EXISTS memory_assets_asset_user_idx ON public.memory_assets (asset_id, user_id);
CREATE INDEX IF NOT EXISTS memory_spaces_memory_user_idx ON public.memory_spaces (memory_id, user_id);
CREATE INDEX IF NOT EXISTS memory_spaces_space_user_idx ON public.memory_spaces (space_id, user_id);
CREATE INDEX IF NOT EXISTS memory_topics_memory_user_idx ON public.memory_topics (memory_id, user_id);
CREATE INDEX IF NOT EXISTS memory_entities_memory_user_idx ON public.memory_entities (memory_id, user_id);
CREATE INDEX IF NOT EXISTS memory_relation_feedback_user_memory_idx ON public.memory_relation_feedback (user_id, memory_id);
CREATE INDEX IF NOT EXISTS memory_relation_feedback_related_user_idx ON public.memory_relation_feedback (related_memory_id, user_id);
CREATE INDEX IF NOT EXISTS memory_events_memory_user_idx ON public.memory_events (memory_id, user_id);

-- RLS is enabled on every application table. There are intentionally no direct
-- client policies yet: the app does not connect from the mobile client.
ALTER TABLE public.app_users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.spaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_assets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_spaces ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_entities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_relation_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.schema_migrations ENABLE ROW LEVEL SECURITY;

REVOKE ALL PRIVILEGES ON TABLE
  public.app_users, public.spaces, public.assets, public.memories,
  public.memory_assets, public.memory_spaces, public.memory_topics,
  public.memory_entities, public.memory_relation_feedback, public.memory_events,
  public.user_preferences, public.schema_migrations
FROM PUBLIC;

DO $$
DECLARE
  role_name text;
  table_list text := 'public.app_users, public.spaces, public.assets, public.memories, public.memory_assets, public.memory_spaces, public.memory_topics, public.memory_entities, public.memory_relation_feedback, public.memory_events, public.user_preferences, public.schema_migrations';
  sequence_exists boolean := to_regclass('public.memory_events_id_seq') IS NOT NULL;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %s FROM %I', table_list, role_name);
      IF sequence_exists THEN
        EXECUTE format('REVOKE ALL PRIVILEGES ON SEQUENCE public.memory_events_id_seq FROM %I', role_name);
      END IF;
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL PRIVILEGES ON TABLES FROM %I',
        current_user, role_name
      );
      EXECUTE format(
        'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL PRIVILEGES ON SEQUENCES FROM %I',
        current_user, role_name
      );
    END IF;
  END LOOP;

  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL PRIVILEGES ON TABLES FROM PUBLIC',
    current_user
  );
  EXECUTE format(
    'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public REVOKE ALL PRIVILEGES ON SEQUENCES FROM PUBLIC',
    current_user
  );
END $$;

REVOKE ALL PRIVILEGES ON SEQUENCE public.memory_events_id_seq FROM PUBLIC;
