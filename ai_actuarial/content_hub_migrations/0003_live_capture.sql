ALTER TABLE source_snapshots
    DROP CONSTRAINT source_snapshots_sqlite_user_version_check,
    ALTER COLUMN sqlite_user_version DROP NOT NULL,
    ADD COLUMN source_kind TEXT NOT NULL DEFAULT 'sqlite_v16',
    ADD CONSTRAINT source_snapshots_kind_version_check CHECK (
        (source_kind = 'sqlite_v16' AND sqlite_user_version = 16)
        OR (source_kind = 'live_capture' AND sqlite_user_version IS NULL)
    );

CREATE TABLE IF NOT EXISTS excluded_urls (
    url_identity_sha256 CHAR(64) PRIMARY KEY,
    url_value_json TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('recruitment', 'tender')),
    excluded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS article_enrichment_annotations (
    content_version_id BIGINT PRIMARY KEY REFERENCES content_versions(content_version_id),
    source_text_variant_id BIGINT NOT NULL,
    source_markdown_sha256 CHAR(64) NOT NULL CHECK (source_markdown_sha256 ~ '^[0-9a-f]{64}$'),
    source_primary_category TEXT,
    source_signature CHAR(64) NOT NULL CHECK (source_signature ~ '^[0-9a-f]{64}$'),
    categories_json JSONB NOT NULL CHECK (
        jsonb_typeof(categories_json) = 'array'
        AND jsonb_array_length(categories_json) BETWEEN 1 AND 4
    ),
    date_facts_json JSONB NOT NULL CHECK (jsonb_typeof(date_facts_json) = 'object'),
    date_review_status TEXT NOT NULL CHECK (
        date_review_status IN ('complete', 'candidate_limit_gap', 'unsupported_format_gap')
    ),
    date_review_reason TEXT,
    date_review_unresolved_json JSONB NOT NULL CHECK (
        jsonb_typeof(date_review_unresolved_json) = 'array'
    ),
    result_sha256 CHAR(64) NOT NULL CHECK (result_sha256 ~ '^[0-9a-f]{64}$'),
    recipe TEXT NOT NULL,
    run_id TEXT NOT NULL,
    annotated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
