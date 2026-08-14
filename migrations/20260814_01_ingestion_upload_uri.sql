-- Keep ingestion job reads compatible with the deployed ingestion model.
ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS upload_uri TEXT NOT NULL DEFAULT '';
