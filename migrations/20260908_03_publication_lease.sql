-- Ownership of a publication attempt, so recovery cannot race a live worker.
--
-- The previous shape had one key doing two jobs. It identified the logical
-- publication AND was meant to identify the attempt, so two requests recovering
-- the same job produced the same key and neither could tell itself from the
-- other. A request that saw in_progress and no visible generation concluded the
-- worker had died and proceeded - but "not visible yet" is not "dead", and two
-- workers could activate at once.
--
-- Split into three:
--
--   publication_idempotency_key   job_id:revision. Is this the same logical
--                                 publication? A duplicate request is a no-op.
--   publication_attempt_key       a fresh uuid per attempt. The fencing token:
--                                 every later write is conditioned on it, so a
--                                 worker whose lease was taken over updates
--                                 nothing.
--   publication_lease_expires_at  when this attempt may be taken over. An
--                                 attempt that is merely slow is not stolen
--                                 from.
--
-- Existing rows get an empty idempotency key and a NULL lease. NULL reads as
-- expired, which is right: an attempt recorded before leases existed has no
-- owner that can still be running.

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS publication_idempotency_key TEXT NOT NULL DEFAULT '';

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS publication_lease_expires_at TIMESTAMPTZ;

COMMENT ON COLUMN ingestion_jobs.publication_idempotency_key IS
    'job_id:review_revision. Identifies the logical publication, not the attempt.';
COMMENT ON COLUMN ingestion_jobs.publication_lease_expires_at IS
    'When this attempt may be taken over. NULL means expired: no owner can still be running.';
