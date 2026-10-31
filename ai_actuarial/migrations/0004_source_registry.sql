CREATE TABLE canonical_sources (
    source_key TEXT PRIMARY KEY CHECK (source_key ~ '^[a-z0-9][a-z0-9_-]{0,63}$'),
    name_zh TEXT NOT NULL CHECK (btrim(name_zh) <> ''),
    name_en TEXT NOT NULL CHECK (btrim(name_en) <> ''),
    status TEXT NOT NULL CHECK (status IN ('active', 'retired')),
    official_url TEXT,
    evidence_json JSONB NOT NULL
);
CREATE TABLE source_aliases (
    alias_norm TEXT NOT NULL CHECK (btrim(alias_norm) <> ''),
    alias_kind TEXT NOT NULL CHECK (alias_kind IN ('name', 'hostname')),
    source_key TEXT REFERENCES canonical_sources(source_key),
    resolution_status TEXT NOT NULL CHECK (resolution_status IN ('verified', 'ambiguous')),
    evidence_json JSONB NOT NULL,
    CHECK (resolution_status <> 'verified' OR source_key IS NOT NULL)
);
CREATE UNIQUE INDEX source_aliases_verified ON source_aliases(alias_kind, alias_norm)
    WHERE resolution_status = 'verified';
CREATE TABLE source_registry_state (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    registry_version BIGINT NOT NULL CHECK (registry_version > 0),
    registry_sha256 CHAR(64) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE source_registry_receipts (
    receipt_id TEXT PRIMARY KEY,
    receipt_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE source_correction_receipts (
    receipt_id TEXT PRIMARY KEY,
    receipt_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE source_projection (
    url TEXT NOT NULL,
    raw_sha256 CHAR(64) NOT NULL,
    source_key TEXT REFERENCES canonical_sources(source_key),
    correction_receipt_id TEXT REFERENCES source_correction_receipts(receipt_id)
        DEFERRABLE INITIALLY DEFERRED,
    PRIMARY KEY (url, raw_sha256)
);
ALTER TABLE files ADD COLUMN source_key TEXT REFERENCES canonical_sources(source_key);
CREATE INDEX files_source_key ON files(source_key);
