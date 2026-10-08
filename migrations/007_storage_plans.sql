ALTER TABLE app_users
  ADD COLUMN storage_plan text NOT NULL DEFAULT 'free'
  CHECK (storage_plan IN ('free', 'paid'));
