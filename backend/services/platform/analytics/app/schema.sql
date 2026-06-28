-- VietCropDoctor Analytics — ClickHouse DDL
-- Run once at service startup via app/queries.py:init_schema() (called from app/main.py)

CREATE TABLE IF NOT EXISTS predictions
(
    event_id        UUID,
    timestamp       DateTime,
    disease         String,
    confidence      Float32,
    severity        String,
    crop            String,
    session_id      String,
    latency_ms      Float32,
    ensemble_used   UInt8,
    agreement_score Float32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, crop, disease);

-- Migration: add user_id if not present (idempotent in ClickHouse)
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS user_id String DEFAULT '';

CREATE TABLE IF NOT EXISTS chat_events
(
    event_id         UUID,
    timestamp        DateTime,
    session_id       String,
    disease          String,
    question         String,
    answer_len       UInt32,
    retrieved_chunks UInt8,
    latency_ms       Float32
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, session_id);

CREATE TABLE IF NOT EXISTS alerts
(
    alert_id   UUID,
    timestamp  DateTime,
    disease    String,
    severity   String,
    confidence Float32,
    crop       String
)
ENGINE = MergeTree()
ORDER BY timestamp;

-- Human feedback events (from the feedback.submitted topic). Powers feedback
-- analytics (correction rate per disease) and the threshold-based retrain trigger.
CREATE TABLE IF NOT EXISTS feedback_events
(
    event_id          UUID,
    timestamp         DateTime,
    feedback_id       String,
    user_id           String,
    predicted_disease String,
    is_correct        UInt8,
    corrected_disease String,
    confirmed_label   String,
    crop              String
)
ENGINE = MergeTree()
PARTITION BY toYYYYMM(timestamp)
ORDER BY (timestamp, predicted_disease)
