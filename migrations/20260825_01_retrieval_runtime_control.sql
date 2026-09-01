-- Singleton runtime control for safe retrieval shadow comparisons.
CREATE TABLE IF NOT EXISTS retrieval_runtime_control (
    control_id TEXT PRIMARY KEY CHECK (control_id = 'primary'),
    mode TEXT NOT NULL CHECK (mode IN ('current', 'shadow')),
    sample_rate DOUBLE PRECISION NOT NULL CHECK (sample_rate >= 0 AND sample_rate <= 1),
    updated_by TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

