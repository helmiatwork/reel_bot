-- Create api_usage table for tracking all API/LLM calls
CREATE TABLE IF NOT EXISTS api_usage (
    id               BIGSERIAL PRIMARY KEY,
    agent            TEXT,                          -- which flow: analyze | clipper | gender | ...
    model            TEXT,
    prompt_tokens    BIGINT DEFAULT 0,
    completion_tokens BIGINT DEFAULT 0,
    total_tokens     BIGINT DEFAULT 0,
    cost_usd         NUMERIC(12,6) DEFAULT 0,
    created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS api_usage_created_at_idx ON api_usage (created_at DESC);
CREATE INDEX IF NOT EXISTS api_usage_agent_idx ON api_usage (agent);
