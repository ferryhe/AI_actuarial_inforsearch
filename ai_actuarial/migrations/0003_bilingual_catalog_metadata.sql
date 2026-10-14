-- Runtime bilingual catalog metadata is independent of the original source fields.
ALTER TABLE catalog_items
    ADD COLUMN IF NOT EXISTS bilingual_metadata_json TEXT;
