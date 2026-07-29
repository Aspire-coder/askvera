ALTER TABLE admin_users
ADD COLUMN IF NOT EXISTS disabled_at TIMESTAMPTZ;

ALTER TABLE widget_configs
ADD COLUMN IF NOT EXISTS logo_url TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS support_routes (
    country TEXT PRIMARY KEY,
    department TEXT NOT NULL,
    email TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT true,
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_support_routes_enabled
ON support_routes (enabled, country);
