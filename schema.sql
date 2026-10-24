-- Mood Log PostgreSQL Schema
-- Run: psql -U postgres -d postgres -f schema.sql

-- Mood entries: daily check-ins with optional self-score (DW) and/or LLM score
CREATE TABLE IF NOT EXISTS mood_log (
    id                 BIGSERIAL PRIMARY KEY,
    log_time           TIMESTAMPTZ NOT NULL UNIQUE,
    sentiment_score_dw NUMERIC,      -- user-provided 1-10 score
    sentiment_score_llm NUMERIC,     -- model-estimated 1-10 score
    comment            TEXT,
    tags               TEXT[],
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    updated_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Model predictions: ridge model output + workload features used for mood forecasting
CREATE TABLE IF NOT EXISTS mood_predict (
    date                      DATE PRIMARY KEY,
    predicted_mood            NUMERIC,
    actual_mood               NUMERIC,
    meeting_hours             NUMERIC,
    team_absence_count        INTEGER,
    personal_event_count      INTEGER,
    leadership_meeting_count  INTEGER,
    updated_at                TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mood_log_time ON mood_log (log_time DESC);