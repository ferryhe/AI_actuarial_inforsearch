CREATE TABLE source_portal_cards (
    portal_key TEXT PRIMARY KEY CHECK (portal_key ~ '^[a-z0-9][a-z0-9-]{0,63}$'),
    official_url TEXT NOT NULL,
    title_zh TEXT NOT NULL,
    title_en TEXT NOT NULL,
    institution_zh TEXT NOT NULL,
    institution_en TEXT NOT NULL,
    overview_zh TEXT NOT NULL,
    overview_en TEXT NOT NULL,
    sort_order INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_portal_updates (
    portal_key TEXT NOT NULL REFERENCES source_portal_cards(portal_key) ON DELETE RESTRICT,
    acquired_on DATE NOT NULL,
    capture_id BIGINT NOT NULL CHECK (capture_id > 0),
    captured_at TIMESTAMPTZ NOT NULL,
    description_zh TEXT NOT NULL,
    description_en TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (portal_key, acquired_on)
);
