CREATE TABLE bilingual_metadata (
    content_version_id BIGINT NOT NULL REFERENCES content_versions(content_version_id),
    language_code TEXT NOT NULL CHECK (language_code IN ('zh', 'en')),
    markdown_text_variant_id BIGINT NOT NULL REFERENCES text_variants(text_variant_id),
    markdown_sha256 CHAR(64) NOT NULL CHECK (markdown_sha256 ~ '^[0-9a-f]{64}$'),
    title TEXT CHECK (title IS NULL OR btrim(title) <> ''),
    summary TEXT CHECK (summary IS NULL OR btrim(summary) <> ''),
    category TEXT CHECK (category IS NULL OR btrim(category) <> ''),
    keywords_json JSONB CHECK (
        keywords_json IS NULL OR
        (jsonb_typeof(keywords_json) = 'array' AND jsonb_array_length(keywords_json) > 0)
    ),
    provenance_json JSONB NOT NULL CHECK (
        jsonb_typeof(provenance_json) = 'array' AND jsonb_array_length(provenance_json) > 0
    ),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (content_version_id, language_code)
);

CREATE INDEX bilingual_metadata_language_version
ON bilingual_metadata(language_code, content_version_id);
