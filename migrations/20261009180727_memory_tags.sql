CREATE TABLE memory_tags (
  memory_id uuid NOT NULL,
  user_id uuid NOT NULL,
  tag text NOT NULL CHECK (length(tag) BETWEEN 1 AND 40 AND tag = lower(tag)),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (memory_id, tag),
  CONSTRAINT memory_tags_memory_user_fk
    FOREIGN KEY (memory_id, user_id) REFERENCES memories(id, user_id) ON DELETE CASCADE
);

CREATE INDEX memory_tags_memory_user_idx ON memory_tags(memory_id, user_id);
CREATE INDEX memory_tags_tag_user_memory_idx ON memory_tags(user_id, tag, memory_id);

ALTER TABLE public.memory_tags ENABLE ROW LEVEL SECURITY;
REVOKE ALL PRIVILEGES ON TABLE public.memory_tags FROM PUBLIC;

DO $$
DECLARE role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.memory_tags FROM %I', role_name);
    END IF;
  END LOOP;
END $$;
