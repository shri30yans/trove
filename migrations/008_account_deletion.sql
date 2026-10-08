-- The pending record supports the disclosed seven-day recovery window and durable cleanup retries.
CREATE TABLE IF NOT EXISTS account_deletion_requests (
  auth_subject text PRIMARY KEY,
  user_id uuid NOT NULL,
  requested_at timestamptz NOT NULL DEFAULT now(),
  delete_after timestamptz NOT NULL
);

-- Keep only the provider subject needed to reject access tokens after account deletion.
-- This deliberately has no foreign key to app_users and stores no email or user content.
CREATE TABLE IF NOT EXISTS deleted_auth_subjects (
  auth_subject text PRIMARY KEY,
  deleted_at timestamptz NOT NULL DEFAULT now()
);
