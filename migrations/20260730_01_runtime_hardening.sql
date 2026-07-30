ALTER TABLE chat_sessions
    ADD COLUMN IF NOT EXISTS widget_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS origin TEXT NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS idx_chat_sessions_resume_binding
    ON chat_sessions (session_id, widget_id, origin, expires_at)
    WHERE ended_at IS NULL;

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS lease_owner TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS lease_expires_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_claim
    ON ingestion_jobs (status, lease_expires_at, created_at);

CREATE TABLE IF NOT EXISTS knowledge_active_generations (
    country TEXT NOT NULL,
    language TEXT NOT NULL,
    source_file TEXT NOT NULL,
    document_type TEXT NOT NULL,
    access_scope TEXT NOT NULL,
    active_ingestion_id TEXT NOT NULL,
    previous_ingestion_id TEXT NOT NULL DEFAULT '',
    activated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_by TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (country, language, source_file, document_type, access_scope)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_active_generations_locale
    ON knowledge_active_generations (country, language, access_scope);
