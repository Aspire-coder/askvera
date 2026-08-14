-- Complete the ingestion job metadata required by the deployed admin API.
ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS content_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS accepted_by TEXT NOT NULL DEFAULT '';
ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS review_before_publish BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
