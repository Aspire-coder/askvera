ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS logical_document_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS document_owner TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS approval_reference TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS effective_date DATE;

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS logical_document_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS document_owner TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS approval_reference TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS effective_date DATE;

ALTER TABLE knowledge_active_generations
    ADD COLUMN IF NOT EXISTS logical_document_id TEXT NOT NULL DEFAULT '';

UPDATE knowledge_active_generations
SET logical_document_id = concat_ws(
    ':',
    lower(access_scope),
    upper(country),
    lower(language),
    lower(document_type),
    left(
        COALESCE(
            NULLIF(
                trim(
                    both '-' from regexp_replace(
                        lower(regexp_replace(source_file, '\.[^.]+$', '')),
                        '[^a-z0-9]+',
                        '-',
                        'g'
                    )
                ),
                ''
            ),
            'document'
        ),
        96
    )
)
WHERE logical_document_id = '';

CREATE UNIQUE INDEX IF NOT EXISTS idx_knowledge_active_generations_logical_document
    ON knowledge_active_generations (logical_document_id);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_terminal_status
    ON ingestion_jobs (status, updated_at)
    WHERE status IN ('retryable', 'failed_terminal', 'dead_lettered');

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_logical_document
    ON knowledge_documents (logical_document_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS knowledge_document_generations (
    ingestion_id TEXT PRIMARY KEY,
    logical_document_id TEXT NOT NULL,
    country TEXT NOT NULL,
    language TEXT NOT NULL,
    source_file TEXT NOT NULL,
    document_type TEXT NOT NULL,
    access_scope TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('staging', 'active', 'retired', 'deleted')),
    activated_at TIMESTAMPTZ,
    retired_at TIMESTAMPTZ,
    activated_by TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_knowledge_document_generations_retention
    ON knowledge_document_generations (status, retired_at)
    WHERE status = 'retired';
