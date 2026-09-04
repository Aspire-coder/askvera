-- Singleton runtime control for the admin-portal "current vs experimental"
-- chat behavior toggle (narrowing fallback, in-voice guardrail phrasing,
-- wider typo tolerance). All-FALSE default is indistinguishable from an
-- unreachable/missing row, so the fail-open path needs no special casing.
CREATE TABLE IF NOT EXISTS chat_candidate_control (
    control_id TEXT PRIMARY KEY CHECK (control_id = 'primary'),
    narrowing_fallback_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    in_voice_guardrail_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    wider_typo_tolerance_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    updated_by TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
