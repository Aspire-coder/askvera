BEGIN;

CREATE TABLE IF NOT EXISTS widget_configs (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    customer TEXT NOT NULL DEFAULT '',
    allowed_origins JSONB NOT NULL DEFAULT '[]'::jsonb,
    markets JSONB NOT NULL DEFAULT '[]'::jsonb,
    languages JSONB NOT NULL DEFAULT '[]'::jsonb,
    default_market TEXT NOT NULL DEFAULT '',
    default_language TEXT NOT NULL DEFAULT '',
    display_name TEXT NOT NULL DEFAULT 'AskVera',
    greeting TEXT NOT NULL DEFAULT '',
    accent_color TEXT NOT NULL DEFAULT '#2F7D4E',
    position TEXT NOT NULL DEFAULT 'bottom-right',
    legal_version TEXT NOT NULL DEFAULT '',
    rate_limit_tier TEXT NOT NULL DEFAULT 'standard',
    usage_cap INTEGER,
    public_key TEXT NOT NULL UNIQUE,
    key_version INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'active',
    created_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

COMMIT;
