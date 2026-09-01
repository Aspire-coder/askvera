-- Operations portal governance and document lifecycle metadata.
CREATE TABLE IF NOT EXISTS market_readiness_governance (
    country TEXT PRIMARY KEY,
    owner_email TEXT NOT NULL DEFAULT '',
    deadline DATE,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS expiry_date DATE;
ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS malware_scan_status TEXT NOT NULL DEFAULT 'not_required';

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS expiry_date DATE;
ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS malware_scan_status TEXT NOT NULL DEFAULT 'not_required';

ALTER TABLE support_routes
    ADD COLUMN IF NOT EXISTS fallback_department TEXT NOT NULL DEFAULT '';
ALTER TABLE support_routes
    ADD COLUMN IF NOT EXISTS fallback_email TEXT NOT NULL DEFAULT '';

ALTER TABLE admin_users
    ADD COLUMN IF NOT EXISTS access_review_due_at DATE;
ALTER TABLE admin_users
    ADD COLUMN IF NOT EXISTS access_certified_at TIMESTAMPTZ;
ALTER TABLE admin_users
    ADD COLUMN IF NOT EXISTS access_certified_by TEXT NOT NULL DEFAULT '';
ALTER TABLE admin_users
    ADD COLUMN IF NOT EXISTS invite_expires_at TIMESTAMPTZ;

ALTER TABLE widget_configs
    ADD COLUMN IF NOT EXISTS previous_public_key TEXT NOT NULL DEFAULT '';
ALTER TABLE widget_configs
    ADD COLUMN IF NOT EXISTS previous_key_expires_at TIMESTAMPTZ;
ALTER TABLE widget_configs
    ADD COLUMN IF NOT EXISTS draft_config JSONB;

CREATE TABLE IF NOT EXISTS answer_review_cases (
    correlation_id TEXT PRIMARY KEY REFERENCES chat_analytics(correlation_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'open',
    assignee_email TEXT NOT NULL DEFAULT '',
    resolution_notes TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_answer_review_cases_queue
    ON answer_review_cases (status, assignee_email, updated_at DESC);

CREATE TABLE IF NOT EXISTS analytics_saved_views (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    owner_sub TEXT NOT NULL,
    filters JSONB NOT NULL DEFAULT '{}'::jsonb,
    schedule TEXT NOT NULL DEFAULT 'none',
    report_email TEXT NOT NULL DEFAULT '',
    alert_not_helpful_threshold DOUBLE PRECISION,
    enabled BOOLEAN NOT NULL DEFAULT true,
    last_sent_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_analytics_saved_views_due
    ON analytics_saved_views (enabled, next_run_at)
    WHERE schedule <> 'none';
