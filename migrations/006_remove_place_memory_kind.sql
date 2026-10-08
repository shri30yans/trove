-- Places are no longer a distinct memory kind. Preserve every saved Place as a
-- Note, then rebuild the enum without the removed value.
BEGIN;

UPDATE public.memories
SET kind = 'text'
WHERE kind::text = 'place';

ALTER TYPE public.memory_kind RENAME TO memory_kind_with_place;
CREATE TYPE public.memory_kind AS ENUM ('link', 'image', 'text', 'audio', 'video', 'file');

ALTER TABLE public.memories
  ALTER COLUMN kind TYPE public.memory_kind
  USING kind::text::public.memory_kind;

DROP TYPE public.memory_kind_with_place;

COMMIT;
