-- Durable, privacy-safe generation model routing telemetry.
ALTER TABLE chat_analytics
    ADD COLUMN IF NOT EXISTS model_route_mode TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_analytics
    ADD COLUMN IF NOT EXISTS model_route_target TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_analytics
    ADD COLUMN IF NOT EXISTS model_route_reasons JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE chat_analytics
    ADD COLUMN IF NOT EXISTS actual_model TEXT NOT NULL DEFAULT '';
ALTER TABLE chat_analytics
    ADD COLUMN IF NOT EXISTS generation_latency_ms INTEGER NOT NULL DEFAULT 0;
ALTER TABLE chat_analytics
    ADD COLUMN IF NOT EXISTS cache_hit BOOLEAN NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_chat_analytics_model_routing
    ON chat_analytics (created_at DESC, country, model_route_target)
    WHERE model_route_target <> '';
