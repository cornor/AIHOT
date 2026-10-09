-- Company readers use separate identities/sessions; existing admin sessions keep their semantics.
ALTER TABLE admin_users ADD COLUMN sso_account text UNIQUE;
CREATE TABLE sso_users (
  account text PRIMARY KEY,
  display_name text NOT NULL,
  role text NOT NULL DEFAULT 'reader' CHECK (role IN ('reader','admin')),
  enabled boolean NOT NULL DEFAULT false,
  admin_user_id bigint REFERENCES admin_users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  last_login_at timestamptz
);
CREATE TABLE sso_sessions (
  id_hash text PRIMARY KEY,
  account text NOT NULL REFERENCES sso_users(account) ON DELETE CASCADE,
  csrf_token text NOT NULL,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX sso_sessions_account_idx ON sso_sessions(account);
CREATE TABLE sso_login_requests (
  state_hash text PRIMARY KEY,
  browser_hash text NOT NULL,
  return_to text NOT NULL,
  expires_at timestamptz NOT NULL
);
