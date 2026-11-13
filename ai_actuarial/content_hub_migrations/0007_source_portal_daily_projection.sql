ALTER TABLE source_portal_captures
    DROP CONSTRAINT source_portal_capture_evidence,
    ADD COLUMN generated_at TIMESTAMPTZ,
    ADD CONSTRAINT source_portal_capture_evidence CHECK (
        (capture_kind = 'directory' AND page_url IS NOT NULL AND page_sha256 IS NOT NULL
            AND evidence_json IS NULL AND evidence_sha256 IS NULL AND generated_at IS NULL)
        OR (capture_kind = 'daily_collection' AND page_url IS NULL AND page_sha256 IS NULL
            AND evidence_json IS NOT NULL AND evidence_sha256 IS NOT NULL AND generated_at IS NULL)
        OR (capture_kind = 'daily_projection' AND page_url IS NULL AND page_sha256 IS NULL
            AND evidence_json IS NOT NULL AND evidence_sha256 IS NOT NULL AND generated_at IS NOT NULL
            AND description_zh IS NOT NULL AND description_en IS NOT NULL)
    ),
    DROP CONSTRAINT source_portal_captures_capture_kind_check,
    ADD CONSTRAINT source_portal_captures_capture_kind_check
        CHECK (capture_kind IN ('directory', 'daily_collection', 'daily_projection'));
