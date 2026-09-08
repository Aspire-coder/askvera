-- Persist what was found about a document, and who decided what about it.
--
-- Findings live on the job because they describe one revision of one document
-- and are replaced wholesale when it is reassessed. Decisions live in their own
-- append-only table because they are history: overwriting the previous approval
-- would destroy the record of who approved what, which is the thing an audit
-- actually asks for.
--
-- A legacy job must read as UNEVALUATED, never as "no findings". Those are
-- different claims, and defaulting the second would publish every existing job
-- on the strength of an assessment that never ran. review_evaluated_at being
-- NULL is what distinguishes them, which is why review_findings is nullable
-- rather than defaulting to an empty array.

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS review_revision TEXT NOT NULL DEFAULT '';

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS review_findings JSONB;

ALTER TABLE ingestion_jobs
    ADD COLUMN IF NOT EXISTS review_evaluated_at TIMESTAMPTZ;

COMMENT ON COLUMN ingestion_jobs.review_revision IS
    'Fingerprint of content hash plus approval-relevant metadata. Empty means unevaluated.';
COMMENT ON COLUMN ingestion_jobs.review_findings IS
    'Versioned JSON: {"schema":1,"findings":[{field,severity,detail}],"uncertain_pages":[int]}. '
    'NULL means never assessed, which is not the same as assessed and clean.';
COMMENT ON COLUMN ingestion_jobs.review_evaluated_at IS
    'When the assessment completed. NULL alongside a populated status means a job '
    'that predates review persistence.';

-- Append-only. There is no UPDATE path in the application, so a later decision
-- adds a row rather than replacing one, and the sequence of who decided what,
-- when and why survives.
CREATE TABLE IF NOT EXISTS ingestion_review_decisions (
    -- TEXT ids elsewhere in this schema; the application supplies a uuid4 so
    -- an insert is idempotent on retry without a sequence round trip.
    decision_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    review_revision TEXT NOT NULL,
    decided_by TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('publish', 'reject')),
    reason TEXT NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Publication looks up the newest decision for one job and revision, which is
-- the only access pattern.
CREATE INDEX IF NOT EXISTS ingestion_review_decisions_job_revision_idx
    ON ingestion_review_decisions (job_id, review_revision, decided_at DESC);
