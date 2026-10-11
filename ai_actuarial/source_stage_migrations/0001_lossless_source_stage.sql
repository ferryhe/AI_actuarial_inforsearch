CREATE TABLE IF NOT EXISTS snapshot (
    source_name TEXT PRIMARY KEY,
    source_sha256 TEXT NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    schema_json TEXT NOT NULL,
    table_counts_json TEXT NOT NULL,
    table_digests_json TEXT NOT NULL,
    format_version INTEGER NOT NULL CHECK (format_version = 1)
);

CREATE TABLE IF NOT EXISTS table_rows (
    table_name TEXT NOT NULL,
    row_number BIGINT NOT NULL CHECK (row_number >= 0),
    row_json TEXT NOT NULL,
    PRIMARY KEY (table_name, row_number)
);

CREATE FUNCTION prevent_source_stage_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'lossless source stages are immutable';
END;
$$;

CREATE TRIGGER source_snapshots_are_immutable
BEFORE UPDATE OR DELETE ON snapshot
FOR EACH ROW EXECUTE FUNCTION prevent_source_stage_mutation();

CREATE TRIGGER source_table_rows_are_immutable
BEFORE UPDATE OR DELETE ON table_rows
FOR EACH ROW EXECUTE FUNCTION prevent_source_stage_mutation();
