BEGIN;

CREATE TABLE IF NOT EXISTS admin_users (
    id TEXT PRIMARY KEY,
    cognito_sub TEXT UNIQUE,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL DEFAULT 'section_scoped',
    status TEXT NOT NULL DEFAULT 'invited',
    last_login TIMESTAMPTZ,
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS admin_user_scopes (
    user_id TEXT NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
    market TEXT NOT NULL,
    section TEXT NOT NULL,
    permission TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, market, section, permission)
);

CREATE TABLE IF NOT EXISTS admin_audit_log (
    event_id TEXT PRIMARY KEY,
    actor_sub TEXT NOT NULL,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_admin_users_status
ON admin_users (status, role, updated_at DESC);

COMMIT;
