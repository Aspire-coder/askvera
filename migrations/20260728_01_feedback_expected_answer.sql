BEGIN;

ALTER TABLE feedback_events
ADD COLUMN IF NOT EXISTS expected_answer TEXT;

ALTER TABLE feedback_events
ADD COLUMN IF NOT EXISTS expected_answer_present BOOLEAN NOT NULL DEFAULT false;

COMMIT;
