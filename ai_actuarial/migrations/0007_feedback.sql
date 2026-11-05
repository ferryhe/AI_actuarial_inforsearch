CREATE TABLE feedback_items (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    feedback_id UUID NOT NULL UNIQUE,
    client_request_id UUID NOT NULL UNIQUE,
    request_hash TEXT NOT NULL CHECK (request_hash ~ '^[0-9a-f]{64}$'),
    site_key TEXT NOT NULL CHECK (site_key ~ '^[a-z0-9][a-z0-9_-]{0,63}$'),
    content TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 4000),
    kind TEXT NOT NULL CHECK (kind IN ('suggestion', 'problem', 'other')),
    origin TEXT NOT NULL CHECK (origin IN ('widget', 'assistant')),
    user_id BIGINT CHECK (user_id > 0),
    page_path TEXT NOT NULL CHECK (char_length(page_path) BETWEEN 1 AND 2048),
    locale TEXT NOT NULL CHECK (char_length(locale) BETWEEN 2 AND 35),
    status TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'reviewed', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX feedback_items_status_id ON feedback_items (status, id);
CREATE INDEX feedback_items_site_id ON feedback_items (site_key, id);
CREATE INDEX feedback_items_site_status_id ON feedback_items (site_key, status, id);
