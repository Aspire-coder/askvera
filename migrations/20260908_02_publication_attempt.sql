-- Make publication recoverable: record that an attempt began, so a retry can
-- tell "never tried" from "tried, outcome unknown".
--
-- The states are not_started, in_progress, succeeded, failed_recoverable.
-- in_progress is the one that matters: a worker killed between activating
-- sections and moving the generation pointer leaves the same row as one killed
-- after moving it, and only knowledge_active_generations distinguishes them.
-- Recovery reads that pointer. It never infers the outcome from an exception.
--
-- Existing rows default to not_started, which is correct for them: jobs that
-- published before this column existed are already status='ready', and
-- publication refuses anything that is not ready_for_review.

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS publication_state TEXT NOT NULL DEFAULT 'not_started';

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS publication_attempt_key TEXT NOT NULL DEFAULT '';

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS publication_detail TEXT NOT NULL DEFAULT '';

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS publication_attempted_at TIMESTAMPTZ;

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS publication_settled_at TIMESTAMPTZ;

COMMENT ON COLUMN ingestion_jobs.publication_state IS
    'not_started | in_progress | succeeded | failed_recoverable. in_progress means '
    'the outcome is unknown and must be established by reading the generation pointer.';
COMMENT ON COLUMN ingestion_jobs.publication_attempt_key IS
    'job_id:review_revision. Binds an attempt to the exact revision approved, so a '
    'metadata edit cannot be completed by an attempt authorised for other content.';
COMMENT ON COLUMN ingestion_jobs.publication_detail IS
    'Why an attempt settled as it did. Operator-facing, never parsed.';
