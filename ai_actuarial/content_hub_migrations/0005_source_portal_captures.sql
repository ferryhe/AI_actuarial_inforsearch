CREATE TABLE source_portal_captures (
    capture_id BIGSERIAL PRIMARY KEY,
    portal_key TEXT NOT NULL CHECK (portal_key ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
    page_url TEXT NOT NULL,
    scope_key TEXT NOT NULL CHECK (btrim(scope_key) <> ''),
    captured_at TIMESTAMPTZ NOT NULL,
    acquired_on DATE NOT NULL,
    page_sha256 CHAR(64) NOT NULL CHECK (page_sha256 ~ '^[0-9a-f]{64}$'),
    complete BOOLEAN NOT NULL,
    description_zh TEXT,
    description_en TEXT,
    UNIQUE (portal_key, scope_key, acquired_on, captured_at)
);
CREATE INDEX source_portal_captures_latest
    ON source_portal_captures (portal_key, scope_key, complete, acquired_on DESC, captured_at DESC, capture_id DESC);

CREATE TABLE source_portal_entries (
    capture_id BIGINT NOT NULL REFERENCES source_portal_captures(capture_id) ON DELETE RESTRICT,
    entry_url TEXT NOT NULL,
    title TEXT NOT NULL CHECK (btrim(title) <> ''),
    PRIMARY KEY (capture_id, entry_url)
);
