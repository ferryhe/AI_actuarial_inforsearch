ALTER TABLE source_portal_captures
    ADD COLUMN capture_kind TEXT NOT NULL DEFAULT 'directory'
        CHECK (capture_kind IN ('directory', 'daily_collection')),
    ADD COLUMN evidence_json JSONB,
    ADD COLUMN evidence_sha256 CHAR(64)
        CHECK (evidence_sha256 ~ '^[0-9a-f]{64}$'),
    ALTER COLUMN page_url DROP NOT NULL,
    ALTER COLUMN page_sha256 DROP NOT NULL,
    ADD CONSTRAINT source_portal_capture_evidence CHECK (
        (capture_kind = 'directory' AND page_url IS NOT NULL AND page_sha256 IS NOT NULL
            AND evidence_json IS NULL AND evidence_sha256 IS NULL)
        OR (capture_kind = 'daily_collection' AND page_url IS NULL AND page_sha256 IS NULL
            AND evidence_json IS NOT NULL AND evidence_sha256 IS NOT NULL)
    );
CREATE UNIQUE INDEX source_portal_daily_run
    ON source_portal_captures (portal_key, (evidence_json->>'run_id'))
    WHERE capture_kind = 'daily_collection';
