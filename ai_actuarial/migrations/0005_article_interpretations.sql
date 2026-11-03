-- Separate editorial drafts; the native schema dump includes these tables.
CREATE TABLE article_interpretation_state (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    last_source_key TEXT NOT NULL DEFAULT ''
);
INSERT INTO article_interpretation_state(singleton) VALUES (TRUE);
CREATE TABLE article_interpretation_rounds (
    round_key TEXT PRIMARY KEY,
    receipt_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE article_interpretations (
    interpretation_id TEXT PRIMARY KEY,
    file_url TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    markdown_sha256 TEXT NOT NULL,
    content_key TEXT NOT NULL,
    source_key TEXT NOT NULL,
    input_fingerprint TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL CHECK (status IN ('queued','running','ready','failed','skipped')),
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX article_interpretations_ready_content ON article_interpretations(content_key)
    WHERE status = 'ready';

CREATE INDEX article_interpretations_content_history ON article_interpretations(content_key,created_at);
